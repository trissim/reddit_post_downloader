"""
Example configuration file for Reddit Post Downloader.

Copy this file to config.py and fill in your actual credentials.
DO NOT commit config.py to version control!

To get Reddit API credentials:
1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Select "script" type
4. Copy your client_id and client_secret
"""

# ============================================================================
# REDDIT API CREDENTIALS (Required)
# ============================================================================

# Your Reddit app client ID (found under "personal use script")
CLIENT_ID = "your_client_id_here"

# Your Reddit app client secret
CLIENT_SECRET = "your_client_secret_here"

# User agent format: "platform:app_name:version (by /u/your_reddit_username)"
USER_AGENT = "python:reddit_research:v1.0 (by /u/your_username)"


# ============================================================================
# EXTRACTION SETTINGS
# ============================================================================

# Target subreddit (without the r/ prefix)
SUBREDDIT = "Python"

# Search query (leave as "*" to get all posts)
QUERY = "tutorial"

# Output file path
OUTPUT_PATH = "reddit_data.xlsx"


# ============================================================================
# ADVANCED SETTINGS (Optional)
# ============================================================================

# Window size for time partitioning
# Options: "monthly" (more thorough) or "yearly" (faster)
WINDOW_SIZE = "monthly"

# Start from the beginning of the subreddit's history
FROM_BEGINNING = True

# Custom date range (optional - only used if FROM_BEGINNING is False)
# from datetime import datetime
# START_DATE = datetime(2020, 1, 1)
# END_DATE = datetime(2023, 12, 31)

# Rate limiting settings
BASE_DELAY = 2.0  # Seconds between requests
MAX_DELAY = 300.0  # Maximum backoff delay in seconds


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

"""
After filling in your credentials, run:

    python3 -c "
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
        from_beginning=config.FROM_BEGINNING,
        window_size=config.WINDOW_SIZE
    )
    "

Or create your own Python script:

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
        from_beginning=config.FROM_BEGINNING,
        window_size=config.WINDOW_SIZE
    )
"""
