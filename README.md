# Reddit Post Downloader

A robust, production-ready Reddit post extractor designed to bypass the 1000-post API limit using intelligent time-windowing. Perfect for researchers, data analysts, and anyone needing comprehensive historical Reddit data.

## Features

- **Time-Windowing**: Automatically partitions searches into time windows to bypass Reddit's 1000-post limit
- **Crash-Resistant**: Incremental saves ensure no data loss if interrupted
- **Resume Capability**: Automatically resumes from the last checkpoint after interruption
- **Rate Limit Handling**: Intelligent exponential backoff for API rate limits
- **Comprehensive Logging**: Detailed logs for monitoring and debugging
- **Flexible Date Ranges**: Extract from subreddit creation to present day
- **Excel Export**: Clean, structured data in .xlsx format

## Installation

### Using pip (recommended)

```bash
# Clone the repository
git clone https://github.com/trissim/reddit_post_downloader.git
cd reddit_post_downloader

# Install dependencies
pip install -r requirements.txt
```

### Using pyproject.toml

```bash
# Install in development mode
pip install -e .

# Or install with dev dependencies
pip install -e ".[dev]"
```

## Reddit API Setup

Before using the downloader, you need Reddit API credentials:

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Fill in the form:
   - **name**: Your app name (e.g., "Data Research Tool")
   - **App type**: Select "script"
   - **description**: Optional
   - **about url**: Optional
   - **redirect uri**: http://localhost:8080 (required but not used)
4. Click "Create app"
5. Note your credentials:
   - **client_id**: The string under "personal use script"
   - **client_secret**: The "secret" value

## Quick Start

### Basic Usage

```python
from downloader import OvernightExtractor

# Configure your Reddit API credentials
CLIENT_ID = "your_client_id_here"
CLIENT_SECRET = "your_client_secret_here"
USER_AGENT = "python:my_research_tool:v1.0 (by /u/your_reddit_username)"

# Initialize the extractor
extractor = OvernightExtractor(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    user_agent=USER_AGENT,
    output_path="reddit_data.xlsx"
)

# Extract complete history from the beginning of a subreddit
extractor.extract_complete_history(
    subreddit="Python",
    query="tutorial",
    from_beginning=True,  # Starts from subreddit creation date
    window_size="monthly"  # or "yearly" for faster extraction
)
```

### Example Configuration File

Create a `config.py` file:

```python
# Reddit API Credentials
CLIENT_ID = "your_client_id"
CLIENT_SECRET = "your_client_secret"
USER_AGENT = "python:research_tool:v1.0 (by /u/your_username)"

# Extraction Settings
SUBREDDIT = "Python"
QUERY = "tutorial"
OUTPUT_PATH = "python_tutorials.xlsx"
WINDOW_SIZE = "monthly"  # or "yearly"
```

Then use it:

```python
from downloader import OvernightExtractor
import config

extractor = OvernightExtractor(
    client_id=config.CLIENT_ID,
    client_secret=config.CLIENT_SECRET,
    user_agent=config.USER_AGENT,
    output_path=config.OUTPUT_PATH
)

extractor.extract_complete_history(
    subreddit=config.SUBREDDIT,
    query=config.QUERY,
    from_beginning=True,
    window_size=config.WINDOW_SIZE
)
```

## Advanced Usage

### Custom Date Range

```python
from datetime import datetime

extractor.extract_complete_history(
    subreddit="Python",
    query="async",
    start_date=datetime(2020, 1, 1),
    end_date=datetime(2023, 12, 31),
    window_size="monthly"
)
```

### Resuming Interrupted Extractions

The downloader automatically saves progress. If interrupted, simply run the same command again:

```python
# If this was interrupted...
extractor.extract_complete_history(
    subreddit="Python",
    query="tutorial",
    from_beginning=True
)

# Just run it again - it will resume from the last checkpoint
extractor.extract_complete_history(
    subreddit="Python",
    query="tutorial",
    from_beginning=True
)
```

## Output Format

The downloader creates an Excel file with the following columns:

| Column | Description |
|--------|-------------|
| url | Direct link to the Reddit post |
| title | Post title |
| date | Post creation date/time |
| user | Username of the post author |
| n_votes | Number of upvotes (score) |
| n_comments | Total number of comments |
| text_op | Original post text content |
| text_comments | All comments concatenated |

## How It Works

### Time-Windowing Strategy

Reddit's API limits searches to 1000 results. This tool bypasses that by:

1. Dividing the time range into smaller windows (monthly or yearly)
2. Searching each window individually
3. Combining results from all windows

For example, searching 10 years with monthly windows gives you up to 120,000 posts (1000 × 120 months) instead of just 1000.

### Architecture

```
OvernightExtractor (Main Orchestrator)
├── RedditClient (API Communication)
│   └── RateLimitHandler (Exponential Backoff)
├── PostParser (Data Extraction)
├── IncrementalExporter (Data Persistence)
├── ProgressTracker (Resume Capability)
└── TimeWindowGenerator (Window Creation)
```

## Configuration Options

### Window Size

- `"monthly"`: More thorough, slower (recommended for most use cases)
- `"yearly"`: Faster but may miss posts if yearly limit exceeds 1000

### Rate Limiting

Default settings work well, but you can customize:

```python
from downloader import RateLimitHandler

# Custom rate limiter
rate_limiter = RateLimitHandler(
    base_delay=2.0,    # Wait 2 seconds between requests
    max_delay=300.0    # Max 5 minutes for rate limit backoff
)
```

## Files Created

- `reddit_data.xlsx`: Main output file with extracted posts
- `extraction_progress.json`: Checkpoint file for resume capability
- `extraction.log`: Detailed log of the extraction process
- `.tmp.xlsx`: Temporary file during saves (automatically cleaned up)

## Troubleshooting

### "Invalid credentials" Error

- Verify your `CLIENT_ID` and `CLIENT_SECRET` are correct
- Make sure you created a "script" type app (not "web app")
- Check that your `USER_AGENT` follows the format: `platform:app_name:version (by /u/username)`

### Rate Limiting Issues

The tool handles rate limits automatically with exponential backoff. If you see many rate limit warnings:

- Increase `base_delay` in RateLimitHandler
- Use `window_size="yearly"` for faster extraction
- Run during off-peak hours

### No Results Found

- Verify the subreddit name is correct (case-insensitive)
- Check that your search query matches actual posts
- Try a broader query or different date range

### Module Import Error

```bash
# Make sure you're in the project directory
cd /path/to/reddit_post_downloader

# Reinstall dependencies
pip install -r requirements.txt
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# With coverage
pytest --cov=downloader
```

### Code Formatting

```bash
# Format code
black downloader.py

# Check style
flake8 downloader.py
```

## Best Practices

1. **Start Small**: Test with a small date range first
2. **Monitor Logs**: Watch `extraction.log` for issues
3. **Respect Rate Limits**: Don't modify the rate limiter unless necessary
4. **Save Credentials Securely**: Use environment variables or a config file (don't commit to git)
5. **Regular Backups**: The tool is crash-resistant, but backup your `.xlsx` files

## License

MIT License - Feel free to use for research and commercial purposes.

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Support

- **Issues**: Report bugs at https://github.com/trissim/reddit_post_downloader/issues
- **Documentation**: This README and inline code documentation

## Acknowledgments

- Built with [PRAW](https://praw.readthedocs.io/) (Python Reddit API Wrapper)
- Data processing with [pandas](https://pandas.pydata.org/)
- Excel export with [openpyxl](https://openpyxl.readthedocs.io/)

## Research Use Cases

This tool is particularly useful for:

- Academic research on social media behavior
- Market research and sentiment analysis
- Content analysis and trend identification
- Archival and documentation projects
- Training data collection for ML/AI models

## Version History

- **v1.0.0** (2025): Initial release with time-windowing and crash resistance

---

Made with data science in mind. Happy researching!
