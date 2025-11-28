"""Tests for URL parser."""

import pytest

from reddit_downloader.parser import (
    extract_post_id,
    extract_username,
    parse_url,
    validate_reddit_url,
)
from reddit_downloader.types import URLType


class TestValidateRedditUrl:
    """Tests for validate_reddit_url function."""

    def test_valid_reddit_urls(self) -> None:
        """Test validation of valid Reddit URLs."""
        valid_urls = [
            "https://reddit.com/r/test/comments/abc123/title",
            "https://www.reddit.com/user/testuser",
            "https://old.reddit.com/r/test",
            "https://new.reddit.com/u/testuser",
            "https://redd.it/abc123",
            "https://v.redd.it/abc123",
        ]

        for url in valid_urls:
            assert validate_reddit_url(url) is True

    def test_invalid_urls(self) -> None:
        """Test validation of invalid URLs."""
        invalid_urls = [
            "https://google.com",
            "https://twitter.com/user",
            "not a url",
            "",
        ]

        for url in invalid_urls:
            assert validate_reddit_url(url) is False


class TestExtractUsername:
    """Tests for extract_username function."""

    def test_extract_from_user_url(self) -> None:
        """Test extracting username from /user/ URL."""
        url = "https://www.reddit.com/user/testuser123"
        assert extract_username(url) == "testuser123"

    def test_extract_from_u_url(self) -> None:
        """Test extracting username from /u/ URL."""
        url = "https://www.reddit.com/u/testuser456"
        assert extract_username(url) == "testuser456"

    def test_invalid_url_raises_error(self) -> None:
        """Test that invalid URL raises ValueError."""
        with pytest.raises(ValueError):
            extract_username("https://www.reddit.com/r/test")


class TestExtractPostId:
    """Tests for extract_post_id function."""

    def test_extract_from_post_url(self) -> None:
        """Test extracting post ID from post URL."""
        url = "https://www.reddit.com/r/pics/comments/abc123/my_title/xyz"
        assert extract_post_id(url) == "abc123"

    def test_extract_from_simple_post_url(self) -> None:
        """Test extracting post ID from simple post URL."""
        url = "https://reddit.com/r/test/comments/def456/title"
        assert extract_post_id(url) == "def456"

    def test_extract_from_comments_root_url(self) -> None:
        """Test extracting post ID from /comments/<id> URL."""
        url = "https://www.reddit.com/comments/ghi789/something"
        assert extract_post_id(url) == "ghi789"

    def test_extract_from_shortlink(self) -> None:
        """Test extracting post ID from redd.it shortlink."""
        url = "https://redd.it/jkl012"
        assert extract_post_id(url) == "jkl012"

    def test_invalid_url_raises_error(self) -> None:
        """Test that invalid URL raises ValueError."""
        with pytest.raises(ValueError):
            extract_post_id("https://www.reddit.com/user/test")


class TestParseUrl:
    """Tests for parse_url function."""

    def test_parse_post_url(self) -> None:
        """Test parsing a post URL."""
        url = "https://www.reddit.com/r/test/comments/abc123/title"
        result = parse_url(url)

        assert result["url_type"] == URLType.POST
        assert result["post_id"] == "abc123"
        assert result["username"] is None

    def test_parse_user_url(self) -> None:
        """Test parsing a user URL."""
        url = "https://www.reddit.com/user/testuser"
        result = parse_url(url)

        assert result["url_type"] == URLType.USER
        assert result["username"] == "testuser"
        assert result["post_id"] is None

    def test_parse_u_url(self) -> None:
        """Test parsing a /u/ user URL."""
        url = "https://www.reddit.com/u/testuser123"
        result = parse_url(url)

        assert result["url_type"] == URLType.USER
        assert result["username"] == "testuser123"
        assert result["post_id"] is None

    def test_parse_invalid_url(self) -> None:
        """Test parsing an invalid URL."""
        url = "https://google.com"
        result = parse_url(url)

        assert result["url_type"] == URLType.INVALID
        assert result["username"] is None
        assert result["post_id"] is None

    def test_parse_reddit_but_unsupported_url(self) -> None:
        """Test parsing a Reddit URL that's not a post or user."""
        url = "https://www.reddit.com/r/test"
        result = parse_url(url)

        assert result["url_type"] == URLType.INVALID

    def test_parse_shortlink_url(self) -> None:
        """Test parsing redd.it shortlink as post URL."""
        url = "https://redd.it/mno345"
        result = parse_url(url)

        assert result["url_type"] == URLType.POST
        assert result["post_id"] == "mno345"
        assert result["username"] is None
