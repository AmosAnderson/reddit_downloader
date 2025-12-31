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
    """Validate if a URL belongs to Reddit or supported short domains."""

    parsed = urlparse(url)
    netloc = parsed.netloc.lower()

    if not netloc:
        return False

    if netloc.endswith(".reddit.com") or netloc == "reddit.com":
        return True

    return netloc in {"redd.it", "www.redd.it", "v.redd.it"}


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
    pattern = r"reddit\.com/(?:user|u)/([^/?#]+)"
    match = re.search(pattern, url)
    if not match:
        raise ValueError(f"Could not extract username from URL: {url}")
    return match.group(1)


def extract_post_id(url: str) -> str:
    """Extract post ID from a Reddit post URL or shortlink."""

    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    # Handle redd.it and v.redd.it shortlinks
    if netloc in {"redd.it", "www.redd.it", "v.redd.it"}:
        if path_parts:
            return path_parts[0].lower()
        raise ValueError(f"Could not extract post ID from URL: {url}")

    if not (netloc.endswith(".reddit.com") or netloc == "reddit.com"):
        raise ValueError(f"Could not extract post ID from URL: {url}")

    if len(path_parts) >= 4 and path_parts[0] == "r" and path_parts[2] == "comments":
        return path_parts[3].lower()

    if len(path_parts) >= 2 and path_parts[0] == "comments":
        return path_parts[1].lower()

    # Fallback to regex search for robustness
    match = re.search(r"comments/([a-z0-9]+)", parsed.path, re.IGNORECASE)
    if match:
        return match.group(1).lower()

    raise ValueError(f"Could not extract post ID from URL: {url}")


def parse_url(url: str) -> ParsedURL:
    """Parse a Reddit URL to determine its type and extract relevant information."""

    if not validate_reddit_url(url):
        return ParsedURL(url_type=URLType.INVALID, username=None, post_id=None)

    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    # User URLs: https://www.reddit.com/user/<name> or /u/<name>
    if netloc.endswith(".reddit.com") or netloc == "reddit.com":
        if path_parts and path_parts[0] in {"user", "u"}:
            try:
                username = extract_username(url)
                return ParsedURL(url_type=URLType.USER, username=username, post_id=None)
            except ValueError:
                return ParsedURL(url_type=URLType.INVALID, username=None, post_id=None)

    # Post URLs (including shortlinks)
    try:
        post_id = extract_post_id(url)
    except ValueError:
        return ParsedURL(url_type=URLType.INVALID, username=None, post_id=None)

    return ParsedURL(url_type=URLType.POST, username=None, post_id=post_id)
