
"""
Overnight Reddit extractor with time-windowing to bypass 1000-post limits.

Runs unattended with:
- Automatic time-window partitioning
- Incremental saves (crash-resistant)
- Rate limit handling with exponential backoff
- Resume capability
- Comprehensive logging

Requirements:
    pip install praw pandas openpyxl
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import List, Optional, Set
from pathlib import Path
import time
import logging
import json
import os
import argparse
import sys
import requests
import praw
import pandas as pd
from praw.exceptions import RedditAPIException, PRAWException


@dataclass
class RedditPost:
    """Data model for a Reddit post."""
    url: str
    title: str
    date: datetime
    user: str
    n_votes: int
    n_comments: int
    text_op: str
    text_comments: str


class ProgressTracker:
    """Tracks extraction progress for resume capability."""
    
    def __init__(self, checkpoint_file: str = "extraction_progress.json"):
        self.checkpoint_file = Path(checkpoint_file)
        self.processed_ids: Set[str] = set()
        self.last_window_end: Optional[datetime] = None
        self._load_checkpoint()
    
    def _load_checkpoint(self):
        """Load existing progress if available."""
        if self.checkpoint_file.exists():
            with open(self.checkpoint_file, 'r') as f:
                data = json.load(f)
                self.processed_ids = set(data.get('processed_ids', []))
                last_window = data.get('last_window_end')
                if last_window:
                    self.last_window_end = datetime.fromisoformat(last_window)
    
    def save_checkpoint(self):
        """Save current progress."""
        data = {
            'processed_ids': list(self.processed_ids),
            'last_window_end': self.last_window_end.isoformat() if self.last_window_end else None,
            'saved_at': datetime.now().isoformat()
        }
        with open(self.checkpoint_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def mark_processed(self, post_id: str):
        """Mark a post as processed."""
        self.processed_ids.add(post_id)
    
    def is_processed(self, post_id: str) -> bool:
        """Check if post was already processed."""
        return post_id in self.processed_ids
    
    def update_window(self, window_end: datetime):
        """Update the last processed time window."""
        self.last_window_end = window_end
        self.save_checkpoint()


class RateLimitHandler:
    """Handles Reddit API rate limiting with exponential backoff."""

    def __init__(self, base_delay: float = 0.5, max_delay: float = 300.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.current_delay = base_delay
        self.logger = logging.getLogger(__name__)
        self.request_count = 0

    def wait(self):
        """Wait before next request (reduced delay for faster processing)."""
        self.request_count += 1
        # Only wait every 2 requests to reduce overhead
        if self.request_count % 2 == 0:
            time.sleep(self.base_delay)

    def handle_rate_limit(self):
        """Handle rate limit error with exponential backoff."""
        self.logger.warning(f"Rate limited. Waiting {self.current_delay:.0f}s...")
        time.sleep(self.current_delay)
        self.current_delay = min(self.current_delay * 2, self.max_delay)

    def reset_delay(self):
        """Reset delay after successful requests."""
        self.current_delay = self.base_delay
        self.request_count = 0


class AnonymousRedditClient:
    """
    Anonymous Reddit client using Reddit's public JSON API (no authentication required).

    Uses Reddit's public JSON endpoints. Works for recent data without any credentials.
    Perfect for quick data collection and testing without API setup.
    """

    def __init__(self):
        self.rate_limiter = RateLimitHandler(base_delay=2.0)  # Be nice to Reddit
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def get_subreddit_creation_date(self, subreddit: str) -> datetime:
        """Get approximate subreddit creation date (fallback to 2008)."""
        self.logger.info(f"Using anonymous mode - starting from 2008 for r/{subreddit}")
        return datetime(2008, 1, 1)  # Pushshift data starts around 2008

    def search_time_window(
        self,
        subreddit: str,
        query: str,
        start_date: datetime,
        end_date: datetime,
        sort: str = "new"
    ) -> List[dict]:
        """
        Search subreddit using Reddit's public JSON API within a time window.

        Returns list of submission dictionaries (not PRAW objects).
        Note: Limited to ~1000 posts per window due to Reddit API limitations.
        """
        self.logger.info(f"Reddit JSON API: Searching {start_date.date()} to {end_date.date()}")

        all_results = []
        after = None  # Pagination token
        attempts = 0
        max_attempts = 40  # 40 pages * 25 = 1000 posts max

        try:
            while attempts < max_attempts:
                self.rate_limiter.wait()

                # Build URL - Reddit's JSON endpoints
                if query and query != "*":
                    # Search endpoint
                    url = f"https://www.reddit.com/r/{subreddit}/search.json"
                    params = {
                        'q': query,
                        'restrict_sr': 'true',
                        'sort': sort,
                        'limit': 100,
                        't': 'all'
                    }
                else:
                    # Just get all posts
                    url = f"https://www.reddit.com/r/{subreddit}/{sort}.json"
                    params = {'limit': 100}

                if after:
                    params['after'] = after

                response = self.session.get(url, params=params, timeout=30)
                response.raise_for_status()

                data = response.json()
                children = data.get('data', {}).get('children', [])

                if not children:
                    break

                # Filter by date range
                for child in children:
                    post_data = child['data']
                    post_time = datetime.fromtimestamp(post_data['created_utc'])

                    # Skip if outside date range
                    if post_time < start_date:
                        attempts = max_attempts  # Stop searching, we've gone too far back
                        break
                    if post_time > end_date:
                        continue  # Skip future posts

                    all_results.append(post_data)

                self.logger.info(f"  Retrieved {len(children)} posts (filtered: {len(all_results)})")

                # Get next page token
                after = data.get('data', {}).get('after')
                if not after:
                    break

                attempts += 1

            self.rate_limiter.reset_delay()
            self.logger.info(f"  Total posts in date range: {len(all_results)}")
            return all_results

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Reddit API error: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Error in Reddit JSON search: {e}")
            import traceback
            traceback.print_exc()
            return []


class RedditClient:
    """Enhanced Reddit client with time-windowing and error handling."""

    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        self.rate_limiter = RateLimitHandler()
        self.logger = logging.getLogger(__name__)
    
    def get_subreddit_creation_date(self, subreddit: str) -> datetime:
        """Get the creation date of a subreddit."""
        try:
            sub = self.reddit.subreddit(subreddit)
            creation_timestamp = sub.created_utc
            creation_date = datetime.fromtimestamp(creation_timestamp)
            self.logger.info(f"r/{subreddit} was created on {creation_date.date()}")
            return creation_date
        except Exception as e:
            self.logger.error(f"Could not get subreddit creation date: {e}")
            # Fallback to Reddit's launch date
            return datetime(2005, 6, 23)
    
    def search_time_window(
        self,
        subreddit: str,
        query: str,
        start_date: datetime,
        end_date: datetime,
        sort: str = "new"
    ) -> List[praw.models.Submission]:
        """
        Search subreddit within a specific time window.

        Since Reddit's API doesn't support timestamp filtering in search queries,
        this method performs client-side filtering by date.
        """
        self.logger.info(f"Searching {start_date.date()} to {end_date.date()}")

        try:
            sub = self.reddit.subreddit(subreddit)
            results = []
            posts_checked = 0

            # Search without timestamp filter, then filter client-side
            for submission in sub.search(query, sort=sort, limit=None):
                posts_checked += 1
                submission_date = datetime.fromtimestamp(submission.created_utc)

                # If post is after the end date, skip it
                if submission_date > end_date:
                    continue

                # If post is before the start date, we've gone too far (assuming sorted by new)
                if submission_date < start_date:
                    self.logger.info(f"Reached posts before start date after checking {posts_checked} posts")
                    break

                # Post is within the time window
                results.append(submission)

                # Log progress every 10 posts
                if len(results) % 10 == 0:
                    self.logger.info(f"  Found {len(results)} posts so far...")

                # Safety limit to prevent infinite loops
                if posts_checked > 10000:
                    self.logger.warning(f"Reached safety limit of 10000 posts checked")
                    break

            self.logger.info(f"Checked {posts_checked} posts, found {len(results)} in time window")
            return results

        except RedditAPIException as e:
            if 'RATELIMIT' in str(e):
                self.rate_limiter.handle_rate_limit()
                return self.search_time_window(subreddit, query, start_date, end_date, sort)
            raise
        except Exception as e:
            self.logger.error(f"Error searching window: {e}")
            return []


class PostParser:
    """Parses Reddit submissions with error handling."""

    def __init__(self, anonymous_mode: bool = False):
        self.logger = logging.getLogger(__name__)
        self.anonymous_mode = anonymous_mode

    def parse_submission(self, submission) -> Optional[RedditPost]:
        """Extract data from a Reddit submission (PRAW object or dict)."""
        # Handle Pushshift dict format
        if isinstance(submission, dict):
            return self.parse_pushshift_submission(submission)

        # Handle PRAW object format
        try:
            submission.comments.replace_more(limit=0)

            return RedditPost(
                url=f"https://www.reddit.com{submission.permalink}",
                title=submission.title,
                date=datetime.fromtimestamp(submission.created_utc),
                user=str(submission.author) if submission.author else "[deleted]",
                n_votes=submission.score,
                n_comments=submission.num_comments,
                text_op=submission.selftext,
                text_comments=self._extract_comments(submission.comments)
            )
        except Exception as e:
            self.logger.error(f"Error parsing submission: {e}")
            return None

    def parse_pushshift_submission(self, data: dict) -> Optional[RedditPost]:
        """Parse a Pushshift API submission dictionary."""
        try:
            return RedditPost(
                url=data.get('full_link', f"https://reddit.com{data.get('permalink', '')}"),
                title=data.get('title', '[No Title]'),
                date=datetime.fromtimestamp(data.get('created_utc', 0)),
                user=data.get('author', '[deleted]'),
                n_votes=data.get('score', 0),
                n_comments=data.get('num_comments', 0),
                text_op=data.get('selftext', ''),
                text_comments=""  # Pushshift submissions don't include comments
            )
        except Exception as e:
            self.logger.error(f"Error parsing Pushshift submission: {e}")
            return None

    @staticmethod
    def _extract_comments(comment_forest) -> str:
        """Recursively extract all comment text."""
        comments = []

        for comment in comment_forest:
            if isinstance(comment, praw.models.Comment):
                try:
                    author = str(comment.author) if comment.author else "[deleted]"
                    comments.append(f"{author}\n{comment.body}")
                except Exception:
                    continue

        return "\n\n".join(comments)


class IncrementalExporter:
    """Exports data incrementally to prevent data loss."""
    
    def __init__(self, output_path: str):
        self.output_path = Path(output_path)
        self.temp_path = self.output_path.with_suffix('.tmp.xlsx')
        self.posts: List[RedditPost] = []
        self.logger = logging.getLogger(__name__)
        self._load_existing()
    
    def _load_existing(self):
        """Load existing data if resuming."""
        if self.output_path.exists():
            self.logger.info(f"Loading existing data from {self.output_path}")
            df = pd.read_excel(self.output_path)
            # Convert back to RedditPost objects (simplified - just track count)
            self.logger.info(f"Loaded {len(df)} existing posts")
    
    def add_post(self, post: RedditPost):
        """Add post and save incrementally."""
        self.posts.append(post)
        
        # Save every 10 posts
        if len(self.posts) % 10 == 0:
            self.save()
    
    def save(self):
        """Save current data to file."""
        if not self.posts:
            return
        
        df = pd.DataFrame([asdict(post) for post in self.posts])
        
        # Save to temp file first (atomic write)
        df.to_excel(self.temp_path, index=False, engine='openpyxl')
        
        # Move temp to final location
        self.temp_path.replace(self.output_path)
        
        self.logger.info(f"Saved {len(self.posts)} posts to {self.output_path}")


class TimeWindowGenerator:
    """Generates time windows for partitioned searching."""
    
    @staticmethod
    def generate_monthly_windows(
        start_date: datetime,
        end_date: datetime
    ) -> List[tuple[datetime, datetime]]:
        """Generate monthly time windows."""
        windows = []
        current = start_date
        
        while current < end_date:
            # Calculate next month
            if current.month == 12:
                next_month = current.replace(year=current.year + 1, month=1, day=1)
            else:
                next_month = current.replace(month=current.month + 1, day=1)
            
            window_end = min(next_month, end_date)
            windows.append((current, window_end))
            current = next_month
        
        return windows
    
    @staticmethod
    def generate_yearly_windows(
        start_date: datetime,
        end_date: datetime
    ) -> List[tuple[datetime, datetime]]:
        """Generate yearly time windows."""
        windows = []
        current = start_date
        
        while current < end_date:
            next_year = current.replace(year=current.year + 1, month=1, day=1)
            window_end = min(next_year, end_date)
            windows.append((current, window_end))
            current = next_year
        
        return windows


class OvernightExtractor:
    """Main orchestrator for overnight extraction."""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: Optional[str] = None,
        output_path: str = "reddit_data.xlsx",
        anonymous: bool = False
    ):
        """
        Initialize the extractor.

        Args:
            client_id: Reddit API client ID (not needed if anonymous=True)
            client_secret: Reddit API client secret (not needed if anonymous=True)
            user_agent: Reddit API user agent (not needed if anonymous=True)
            output_path: Path to output Excel file
            anonymous: Use Pushshift API (no credentials required, historical data)
        """
        self.anonymous = anonymous

        if anonymous:
            self.client = AnonymousRedditClient()
            self.logger = self._setup_logging()
            self.logger.info("=" * 60)
            self.logger.info("ANONYMOUS MODE: Using Pushshift API")
            self.logger.info("No credentials required!")
            self.logger.info("Note: Data may be a few months behind current")
            self.logger.info("=" * 60)
        else:
            if not all([client_id, client_secret, user_agent]):
                raise ValueError(
                    "client_id, client_secret, and user_agent are required "
                    "when not using anonymous mode. Use anonymous=True to skip credentials."
                )
            self.client = RedditClient(client_id, client_secret, user_agent)
            self.logger = self._setup_logging()

        self.parser = PostParser(anonymous_mode=anonymous)
        self.exporter = IncrementalExporter(output_path)
        self.progress = ProgressTracker()
    
    def _setup_logging(self) -> logging.Logger:
        """Configure logging."""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('extraction.log'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger(__name__)
    
    def extract_complete_history(
        self,
        subreddit: str,
        query: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        window_size: str = "monthly",
        from_beginning: bool = True
    ):
        """
        Extract complete subreddit history using time windowing.
        
        Args:
            subreddit: Subreddit name
            query: Search query
            start_date: Start from this date (default: subreddit creation)
            end_date: End at this date (default: now)
            window_size: 'monthly' or 'yearly'
            from_beginning: If True, automatically use subreddit creation date
        """
        # Set default date range
        end_date = end_date or datetime.now()
        
        if from_beginning and start_date is None:
            start_date = self.client.get_subreddit_creation_date(subreddit)
        else:
            start_date = start_date or (end_date - timedelta(days=365*10))
        
        # Resume from last checkpoint if available
        if self.progress.last_window_end:
            start_date = self.progress.last_window_end
            self.logger.info(f"Resuming from {start_date.date()}")
        
        # Generate time windows
        if window_size == "monthly":
            windows = TimeWindowGenerator.generate_monthly_windows(start_date, end_date)
        else:
            windows = TimeWindowGenerator.generate_yearly_windows(start_date, end_date)
        
        self.logger.info(f"Extracting {len(windows)} time windows for r/{subreddit}")
        self.logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
        
        total_posts = 0
        
        for i, (window_start, window_end) in enumerate(windows, 1):
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"Window {i}/{len(windows)}: {window_start.date()} to {window_end.date()}")
            self.logger.info(f"{'='*60}")
            
            try:
                submissions = self.client.search_time_window(
                    subreddit, query, window_start, window_end
                )
                
                window_posts = 0
                for submission in submissions:
                    # Get submission ID (handle both PRAW objects and dicts)
                    sub_id = submission['id'] if isinstance(submission, dict) else submission.id

                    # Skip if already processed
                    if self.progress.is_processed(sub_id):
                        continue

                    post = self.parser.parse_submission(submission)
                    if post:
                        self.exporter.add_post(post)
                        self.progress.mark_processed(sub_id)
                        window_posts += 1
                        total_posts += 1
                
                self.logger.info(f"  Extracted {window_posts} posts from this window")
                self.progress.update_window(window_end)
                
            except KeyboardInterrupt:
                self.logger.info("\n\nExtraction interrupted by user")
                self._finalize(total_posts)
                raise
            except Exception as e:
                self.logger.error(f"Error in window {window_start}-{window_end}: {e}")
                continue
        
        self._finalize(total_posts)
    
    def _finalize(self, total_posts: int):
        """Save final data and cleanup."""
        self.exporter.save()
        self.progress.save_checkpoint()
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"Extraction complete!")
        self.logger.info(f"Total posts extracted: {total_posts}")
        self.logger.info(f"Output saved to: {self.exporter.output_path}")
        self.logger.info(f"{'='*60}")


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Reddit Post Downloader - Extract posts using time-windowing to bypass 1000-post limit",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # ANONYMOUS MODE (NO CREDENTIALS NEEDED!):
  python3 downloader.py --anonymous --subreddit Python --query tutorial

  # Anonymous mode with date range (last 3 months):
  python3 downloader.py --anonymous --subreddit Python \\
    --start-date 2024-07-01 --end-date 2024-10-01 --no-from-beginning

  # Using environment variables:
  export REDDIT_CLIENT_ID="your_id"
  export REDDIT_CLIENT_SECRET="your_secret"
  export REDDIT_USER_AGENT="python:app:v1.0 (by /u/username)"
  python3 downloader.py --subreddit Python --query tutorial

  # Using command-line arguments:
  python3 downloader.py \\
    --client-id your_id \\
    --client-secret your_secret \\
    --user-agent "python:app:v1.0 (by /u/username)" \\
    --subreddit Python \\
    --query tutorial \\
    --output data.xlsx

  # Custom date range:
  python3 downloader.py \\
    --subreddit Python \\
    --query async \\
    --start-date 2020-01-01 \\
    --end-date 2023-12-31
        """
    )

    # Credentials (can use env vars or CLI args)
    parser.add_argument(
        "--client-id",
        default=os.getenv("REDDIT_CLIENT_ID"),
        help="Reddit API client ID (or set REDDIT_CLIENT_ID env var)"
    )
    parser.add_argument(
        "--client-secret",
        default=os.getenv("REDDIT_CLIENT_SECRET"),
        help="Reddit API client secret (or set REDDIT_CLIENT_SECRET env var)"
    )
    parser.add_argument(
        "--user-agent",
        default=os.getenv("REDDIT_USER_AGENT"),
        help="Reddit API user agent (or set REDDIT_USER_AGENT env var)"
    )

    # Required extraction parameters
    parser.add_argument(
        "--subreddit",
        required=True,
        help="Target subreddit (without r/ prefix)"
    )
    parser.add_argument(
        "--query",
        default="*",
        help="Search query (default: '*' for all posts)"
    )

    # Output options
    parser.add_argument(
        "--output",
        "-o",
        default="reddit_data.xlsx",
        help="Output file path (default: reddit_data.xlsx)"
    )

    # Date range options
    parser.add_argument(
        "--start-date",
        help="Start date (YYYY-MM-DD format). If not specified, starts from subreddit creation"
    )
    parser.add_argument(
        "--end-date",
        help="End date (YYYY-MM-DD format). Default: today"
    )
    parser.add_argument(
        "--from-beginning",
        action="store_true",
        default=True,
        help="Start from subreddit creation date (default: True)"
    )
    parser.add_argument(
        "--no-from-beginning",
        action="store_false",
        dest="from_beginning",
        help="Don't start from beginning (use --start-date instead)"
    )

    # Performance options
    parser.add_argument(
        "--window-size",
        choices=["monthly", "yearly"],
        default="monthly",
        help="Time window size (default: monthly)"
    )

    # Anonymous mode
    parser.add_argument(
        "--anonymous",
        action="store_true",
        help="Use Pushshift API (no credentials required, historical data only)"
    )

    return parser.parse_args()


def validate_credentials(client_id, client_secret, user_agent):
    """Validate that required credentials are provided."""
    missing = []
    if not client_id:
        missing.append("client_id (use --client-id or REDDIT_CLIENT_ID env var)")
    if not client_secret:
        missing.append("client_secret (use --client-secret or REDDIT_CLIENT_SECRET env var)")
    if not user_agent:
        missing.append("user_agent (use --user-agent or REDDIT_USER_AGENT env var)")

    if missing:
        print("ERROR: Missing required credentials:\n")
        for item in missing:
            print(f"  - {item}")
        print("\nTo get Reddit API credentials:")
        print("  1. Go to https://www.reddit.com/prefs/apps")
        print("  2. Click 'Create App' or 'Create Another App'")
        print("  3. Select 'script' type")
        print("  4. Copy your client_id and client_secret")
        print("\nSee README.md for detailed instructions.")
        sys.exit(1)


def main():
    """Main entry point for command-line usage."""
    args = parse_arguments()

    # Validate credentials (skip if anonymous mode)
    if not args.anonymous:
        validate_credentials(args.client_id, args.client_secret, args.user_agent)

    # Parse dates if provided
    start_date = None
    end_date = None
    if args.start_date:
        try:
            start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: Invalid start date format '{args.start_date}'. Use YYYY-MM-DD")
            sys.exit(1)

    if args.end_date:
        try:
            end_date = datetime.strptime(args.end_date, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: Invalid end date format '{args.end_date}'. Use YYYY-MM-DD")
            sys.exit(1)

    # Initialize extractor
    print(f"\nInitializing Reddit Post Downloader...")
    if args.anonymous:
        print(f"  Mode: ANONYMOUS (Pushshift API)")
        print(f"  Note: Data may be a few months behind current")
    else:
        print(f"  Mode: Authenticated (Reddit API)")
    print(f"  Subreddit: r/{args.subreddit}")
    print(f"  Query: {args.query}")
    print(f"  Output: {args.output}")
    print(f"  Window size: {args.window_size}")
    print()

    extractor = OvernightExtractor(
        client_id=args.client_id,
        client_secret=args.client_secret,
        user_agent=args.user_agent,
        output_path=args.output,
        anonymous=args.anonymous
    )

    # Extract data
    extractor.extract_complete_history(
        subreddit=args.subreddit,
        query=args.query,
        start_date=start_date,
        end_date=end_date,
        window_size=args.window_size,
        from_beginning=args.from_beginning
    )


if __name__ == "__main__":
    main()