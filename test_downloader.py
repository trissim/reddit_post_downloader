#!/usr/bin/env python3
"""
Test script to validate the downloader functionality.
Tests core components without requiring real Reddit API credentials.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path
import json

# Test imports
print("Testing imports...")
try:
    from downloader import (
        RedditPost,
        ProgressTracker,
        RateLimitHandler,
        TimeWindowGenerator,
        IncrementalExporter,
        PostParser,
        OvernightExtractor
    )
    print("✓ All imports successful")
except ImportError as e:
    print(f"✗ Import error: {e}")
    sys.exit(1)

# Test 1: RedditPost dataclass
print("\n1. Testing RedditPost dataclass...")
try:
    post = RedditPost(
        url="https://reddit.com/r/test/comments/123",
        title="Test Post",
        date=datetime.now(),
        user="testuser",
        n_votes=100,
        n_comments=50,
        text_op="This is a test post",
        text_comments="Comment 1\n\nComment 2"
    )
    print(f"✓ RedditPost created: {post.title}")
except Exception as e:
    print(f"✗ RedditPost failed: {e}")
    sys.exit(1)

# Test 2: ProgressTracker
print("\n2. Testing ProgressTracker...")
try:
    # Clean up any existing checkpoint
    checkpoint_file = Path("test_checkpoint.json")
    if checkpoint_file.exists():
        checkpoint_file.unlink()

    tracker = ProgressTracker(checkpoint_file="test_checkpoint.json")
    tracker.mark_processed("post123")
    tracker.mark_processed("post456")
    tracker.update_window(datetime.now())

    assert tracker.is_processed("post123"), "Post not marked as processed"
    assert not tracker.is_processed("post789"), "Non-existent post marked as processed"

    # Test persistence
    tracker2 = ProgressTracker(checkpoint_file="test_checkpoint.json")
    assert tracker2.is_processed("post123"), "Progress not persisted"

    print("✓ ProgressTracker working (save/load/check)")

    # Cleanup
    checkpoint_file.unlink()
except Exception as e:
    print(f"✗ ProgressTracker failed: {e}")
    sys.exit(1)

# Test 3: RateLimitHandler
print("\n3. Testing RateLimitHandler...")
try:
    handler = RateLimitHandler(base_delay=0.1, max_delay=1.0)

    # Test delay increase
    initial_delay = handler.current_delay
    handler.handle_rate_limit()
    assert handler.current_delay > initial_delay, "Delay didn't increase"

    # Test reset
    handler.reset_delay()
    assert handler.current_delay == handler.base_delay, "Delay didn't reset"

    print("✓ RateLimitHandler working (backoff/reset)")
except Exception as e:
    print(f"✗ RateLimitHandler failed: {e}")
    sys.exit(1)

# Test 4: TimeWindowGenerator
print("\n4. Testing TimeWindowGenerator...")
try:
    start = datetime(2023, 1, 1)
    end = datetime(2023, 6, 1)

    monthly_windows = TimeWindowGenerator.generate_monthly_windows(start, end)
    assert len(monthly_windows) == 5, f"Expected 5 monthly windows, got {len(monthly_windows)}"

    yearly_windows = TimeWindowGenerator.generate_yearly_windows(start, end)
    assert len(yearly_windows) == 1, f"Expected 1 yearly window, got {len(yearly_windows)}"

    # Check window boundaries
    first_start, first_end = monthly_windows[0]
    assert first_start == start, "First window doesn't start at start date"

    print(f"✓ TimeWindowGenerator working (monthly: {len(monthly_windows)}, yearly: {len(yearly_windows)})")
except Exception as e:
    print(f"✗ TimeWindowGenerator failed: {e}")
    sys.exit(1)

# Test 5: IncrementalExporter
print("\n5. Testing IncrementalExporter...")
try:
    # Clean up any existing test files
    test_file = Path("test_export.xlsx")
    test_tmp = Path("test_export.tmp.xlsx")
    for f in [test_file, test_tmp]:
        if f.exists():
            f.unlink()

    exporter = IncrementalExporter("test_export.xlsx")

    # Add test posts
    for i in range(5):
        post = RedditPost(
            url=f"https://reddit.com/r/test/comments/{i}",
            title=f"Test Post {i}",
            date=datetime.now(),
            user=f"user{i}",
            n_votes=i * 10,
            n_comments=i * 5,
            text_op=f"Post content {i}",
            text_comments=f"Comments for post {i}"
        )
        exporter.add_post(post)

    # Force save
    exporter.save()

    assert test_file.exists(), "Export file not created"

    # Check file size
    file_size = test_file.stat().st_size
    assert file_size > 0, "Export file is empty"

    print(f"✓ IncrementalExporter working (created {test_file}, {file_size} bytes)")

    # Cleanup
    test_file.unlink()
except Exception as e:
    print(f"✗ IncrementalExporter failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: PostParser
print("\n6. Testing PostParser...")
try:
    parser = PostParser()

    # We can't test with real Reddit objects without credentials,
    # but we can verify the class initializes
    assert parser.logger is not None, "Logger not initialized"

    print("✓ PostParser initialized")
except Exception as e:
    print(f"✗ PostParser failed: {e}")
    sys.exit(1)

# Test 7: OvernightExtractor initialization
print("\n7. Testing OvernightExtractor initialization...")
try:
    # This will fail to connect to Reddit, but should initialize
    extractor = OvernightExtractor(
        client_id="test_id",
        client_secret="test_secret",
        user_agent="test_agent",
        output_path="test_output.xlsx"
    )

    assert extractor.client is not None, "Client not initialized"
    assert extractor.parser is not None, "Parser not initialized"
    assert extractor.exporter is not None, "Exporter not initialized"
    assert extractor.progress is not None, "Progress tracker not initialized"

    print("✓ OvernightExtractor initialized with all components")

    # Cleanup
    for f in [Path("test_output.xlsx"), Path("extraction_progress.json"),
              Path("extraction.log")]:
        if f.exists():
            f.unlink()

except Exception as e:
    print(f"✗ OvernightExtractor failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "="*60)
print("ALL TESTS PASSED!")
print("="*60)
print("\nThe downloader is ready to use.")
print("To run with real data, you'll need:")
print("1. Reddit API credentials (CLIENT_ID, CLIENT_SECRET)")
print("2. A valid USER_AGENT string")
print("\nSee README.md for setup instructions.")
