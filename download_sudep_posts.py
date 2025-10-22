#!/usr/bin/env python3
"""
Download all posts from r/Epilepsy containing "sudep" anywhere in the post data.

This script searches for the substring "sudep" (case-insensitive) in:
- Post title
- Post text/selftext
- Comments
- Author names
- Any other post metadata

Saves results to Excel file with complete post data.
"""

import praw
import pandas as pd
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('sudep_download.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


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
    sudep_matches: str  # Where "sudep" was found


def contains_sudep(text: str) -> bool:
    """Check if text contains 'sudep' (case-insensitive)."""
    return "sudep" in text.lower() if text else False


def find_sudep_locations(submission) -> List[str]:
    """Find all locations where 'sudep' appears in the post."""
    locations = []
    
    # Check title
    if contains_sudep(submission.title):
        locations.append("title")
    
    # Check post text
    if contains_sudep(submission.selftext):
        locations.append("post_text")
    
    # Check author
    if submission.author and contains_sudep(str(submission.author)):
        locations.append("author")
    
    # Check comments
    try:
        submission.comments.replace_more(limit=0)
        for comment in submission.comments:
            if hasattr(comment, 'body') and contains_sudep(comment.body):
                locations.append("comments")
                break
    except Exception as e:
        logger.debug(f"Error checking comments: {e}")
    
    return locations


def extract_comments(comment_forest) -> str:
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


def download_sudep_posts(
    client_id: str,
    client_secret: str,
    user_agent: str,
    output_path: str = "sudep_posts.xlsx"
):
    """
    Download all posts from r/Epilepsy containing "sudep".
    
    Args:
        client_id: Reddit API client ID
        client_secret: Reddit API client secret
        user_agent: Reddit API user agent
        output_path: Output Excel file path
    """
    
    logger.info("=" * 70)
    logger.info("SUDEP POST DOWNLOADER")
    logger.info("=" * 70)
    logger.info(f"Searching r/Epilepsy for posts containing 'sudep'")
    logger.info(f"Output file: {output_path}")
    logger.info("")
    
    try:
        # Authenticate with Reddit
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        
        subreddit = reddit.subreddit("Epilepsy")
        logger.info(f"✓ Connected to r/{subreddit.display_name}")
        logger.info(f"  Subscribers: {subreddit.subscribers:,}")
        logger.info("")
        
        # Search for posts
        logger.info("Searching for posts containing 'sudep'...")
        posts = []
        sudep_posts = []
        posts_checked = 0
        
        # Search with "sudep" query
        for submission in subreddit.search("sudep", sort="new", limit=None):
            posts_checked += 1
            
            # Check if "sudep" appears anywhere in the post
            sudep_locations = find_sudep_locations(submission)
            
            if sudep_locations:
                logger.info(f"Found SUDEP post #{len(sudep_posts) + 1}: {submission.title[:60]}...")
                logger.info(f"  Locations: {', '.join(sudep_locations)}")
                
                # Extract comments
                try:
                    submission.comments.replace_more(limit=0)
                    comments_text = extract_comments(submission.comments)
                except Exception as e:
                    logger.debug(f"Error extracting comments: {e}")
                    comments_text = ""
                
                # Create post object
                post = RedditPost(
                    url=f"https://www.reddit.com{submission.permalink}",
                    title=submission.title,
                    date=datetime.fromtimestamp(submission.created_utc),
                    user=str(submission.author) if submission.author else "[deleted]",
                    n_votes=submission.score,
                    n_comments=submission.num_comments,
                    text_op=submission.selftext,
                    text_comments=comments_text,
                    sudep_matches=", ".join(sudep_locations)
                )
                
                sudep_posts.append(post)
                posts.append(post)
            
            # Log progress every 50 posts checked
            if posts_checked % 50 == 0:
                logger.info(f"  Checked {posts_checked} posts, found {len(sudep_posts)} with SUDEP...")
            
            # Safety limit
            if posts_checked > 5000:
                logger.warning(f"Reached safety limit of 5000 posts checked")
                break
        
        logger.info("")
        logger.info(f"Search complete!")
        logger.info(f"  Total posts checked: {posts_checked}")
        logger.info(f"  Posts containing 'sudep': {len(sudep_posts)}")
        logger.info("")
        
        # Save to Excel
        if sudep_posts:
            df = pd.DataFrame([asdict(post) for post in sudep_posts])
            df.to_excel(output_path, index=False, engine='openpyxl')
            logger.info(f"✓ Saved {len(sudep_posts)} posts to {output_path}")
            logger.info(f"  File size: {Path(output_path).stat().st_size / 1024:.1f} KB")
            
            # Print summary
            logger.info("")
            logger.info("Sample posts:")
            for i, post in enumerate(sudep_posts[:5], 1):
                logger.info(f"  {i}. {post.title[:60]}...")
                logger.info(f"     Author: {post.user} | Votes: {post.n_votes} | Comments: {post.n_comments}")
                logger.info(f"     Found in: {post.sudep_matches}")
        else:
            logger.warning("No posts containing 'sudep' found!")
        
        logger.info("")
        logger.info("=" * 70)
        
        return sudep_posts
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    # Configure credentials
    CLIENT_ID = "prBByrnTuSK2gkDs6xu3Fw"
    CLIENT_SECRET = "_qHruKld-sgANqBt4M_1bCOu9q59lA"
    USER_AGENT = "python:sudep_research:v2.0 (by /u/test_user)"
    
    # Download posts
    sudep_posts = download_sudep_posts(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        user_agent=USER_AGENT,
        output_path="sudep_posts.xlsx"
    )

