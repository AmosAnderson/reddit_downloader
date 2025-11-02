"""URL parsing utilities for Reddit URLs."""

import re
from typing import TypedDict
from urllib.parse import urlparse

from reddit_downloader.types import URLType


class ParsedURL(TypedDict):
    """Result of parsing a Reddit URL."""

    url_type: URLType
    username: str | None
    post_id: str | None


def validate_reddit_url(url: str) -> bool:
    """Validate if a URL is a Reddit URL.

    Args:
        url: URL to validate

    Returns:
        True if URL is a valid Reddit URL, False otherwise
    """
    parsed = urlparse(url)
    return parsed.netloc in (
        "reddit.com",
        "www.reddit.com",
        "old.reddit.com",
        "new.reddit.com",
    )


def extract_username(url: str) -> str:
    """Extract username from a Reddit user URL.

    Args:
        url: Reddit user profile URL

    Returns:
        Username extracted from URL

    Raises:
        ValueError: If URL is not a valid user URL
    """
    # Match patterns like:
    # https://www.reddit.com/user/username
    # https://www.reddit.com/u/username
    pattern = r"reddit\.com/(?:user|u)/([^/]+)"
    match = re.search(pattern, url)
    if not match:
        raise ValueError(f"Could not extract username from URL: {url}")
    return match.group(1)


def extract_post_id(url: str) -> str:
    """Extract post ID from a Reddit post URL.

    Args:
        url: Reddit post URL

    Returns:
        Post ID extracted from URL

    Raises:
        ValueError: If URL is not a valid post URL
    """
    # Match patterns like:
    # https://www.reddit.com/r/subreddit/comments/post_id/...
    # The post ID is a unique alphanumeric string
    pattern = r"reddit\.com/r/[^/]+/comments/([a-z0-9]+)"
    match = re.search(pattern, url)
    if not match:
        raise ValueError(f"Could not extract post ID from URL: {url}")
    return match.group(1)


def parse_url(url: str) -> ParsedURL:
    """Parse a Reddit URL to determine its type and extract relevant information.

    Args:
        url: Reddit URL to parse

    Returns:
        ParsedURL dictionary containing url_type and extracted information
    """
    if not validate_reddit_url(url):
        return ParsedURL(url_type=URLType.INVALID, username=None, post_id=None)

    # Check if it's a user URL
    if re.search(r"reddit\.com/(?:user|u)/", url):
        try:
            username = extract_username(url)
            return ParsedURL(url_type=URLType.USER, username=username, post_id=None)
        except ValueError:
            return ParsedURL(url_type=URLType.INVALID, username=None, post_id=None)

    # Check if it's a post URL
    if re.search(r"reddit\.com/r/[^/]+/comments/", url):
        try:
            post_id = extract_post_id(url)
            return ParsedURL(url_type=URLType.POST, username=None, post_id=post_id)
        except ValueError:
            return ParsedURL(url_type=URLType.INVALID, username=None, post_id=None)

    # If we get here, it's a Reddit URL but not a recognized type
    return ParsedURL(url_type=URLType.INVALID, username=None, post_id=None)
