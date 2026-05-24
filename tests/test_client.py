"""Tests for Reddit client."""

import os
from unittest.mock import MagicMock, patch

import praw
import pytest

from reddit_downloader.client import RedditClient


class TestRedditClientInit:
    """Test RedditClient initialization."""

    @patch("reddit_downloader.client.praw.Reddit")
    def test_init_with_credentials(self, mock_reddit: MagicMock) -> None:
        """Test initialization with explicit credentials."""
        client = RedditClient(
            client_id="test_id", client_secret="test_secret", user_agent="test_agent"
        )

        assert client.client_id == "test_id"
        assert client.client_secret == "test_secret"
        assert client.user_agent == "test_agent"
        mock_reddit.assert_called_once_with(
            client_id="test_id",
            client_secret="test_secret",
            user_agent="test_agent",
            check_for_async=False,
        )

    @patch.dict(
        os.environ,
        {
            "REDDIT_CLIENT_ID": "env_id",
            "REDDIT_CLIENT_SECRET": "env_secret",
            "REDDIT_USER_AGENT": "env_agent",
        },
    )
    @patch("reddit_downloader.client.praw.Reddit")
    def test_init_from_environment(self, mock_reddit: MagicMock) -> None:
        """Test initialization from environment variables."""
        client = RedditClient()

        assert client.client_id == "env_id"
        assert client.client_secret == "env_secret"
        assert client.user_agent == "env_agent"

    @patch.dict(os.environ, {"REDDIT_CLIENT_ID": "env_id", "REDDIT_CLIENT_SECRET": "env_secret"})
    @patch("reddit_downloader.client.praw.Reddit")
    def test_init_default_user_agent(self, mock_reddit: MagicMock) -> None:
        """Test default user agent when not provided."""
        client = RedditClient()

        assert client.user_agent is not None
        assert "reddit_downloader" in client.user_agent

    @patch.dict(os.environ, {}, clear=True)
    def test_init_missing_credentials(self) -> None:
        """Test initialization fails without credentials."""
        with pytest.raises(ValueError, match="Reddit API credentials required"):
            RedditClient(load_env=False)

    @patch.dict(os.environ, {"REDDIT_CLIENT_ID": "test_id"}, clear=True)
    def test_init_missing_secret(self) -> None:
        """Test initialization fails without client secret."""
        with pytest.raises(ValueError, match="Reddit API credentials required"):
            RedditClient(load_env=False)


class TestRedditClientMethods:
    """Test RedditClient methods."""

    @patch("reddit_downloader.client.praw.Reddit")
    def test_context_manager(self, mock_reddit: MagicMock) -> None:
        """Test RedditClient as context manager."""
        with RedditClient(
            client_id="test_id", client_secret="test_secret", user_agent="test_agent"
        ) as client:
            assert isinstance(client, RedditClient)

    @patch("reddit_downloader.client.praw.Reddit")
    def test_can_access_api_success(self, mock_reddit: MagicMock) -> None:
        """Test successful Reddit API access check."""
        mock_reddit_instance = MagicMock()
        mock_subreddit = MagicMock()
        mock_subreddit.hot.return_value = iter([MagicMock()])
        mock_reddit_instance.subreddit.return_value = mock_subreddit
        mock_reddit.return_value = mock_reddit_instance

        client = RedditClient(
            client_id="test_id", client_secret="test_secret", user_agent="test_agent"
        )

        assert client.can_access_api() is True
        assert client.is_authenticated() is True
        mock_reddit_instance.subreddit.assert_called_with("all")
        mock_subreddit.hot.assert_called_with(limit=1)

    @patch("reddit_downloader.client.praw.Reddit")
    def test_can_access_api_failure(self, mock_reddit: MagicMock) -> None:
        """Test failed Reddit API access check."""
        mock_reddit_instance = MagicMock()
        mock_reddit_instance.subreddit.side_effect = praw.exceptions.PRAWException("Auth failed")
        mock_reddit.return_value = mock_reddit_instance

        client = RedditClient(
            client_id="test_id", client_secret="test_secret", user_agent="test_agent"
        )

        assert client.can_access_api() is False
        assert client.is_authenticated() is False

    @patch("reddit_downloader.client.praw.Reddit")
    def test_get_post(self, mock_reddit: MagicMock) -> None:
        """Test fetching a post by ID."""
        mock_reddit_instance = MagicMock()
        mock_submission = MagicMock()
        mock_reddit_instance.submission.return_value = mock_submission
        mock_reddit.return_value = mock_reddit_instance

        client = RedditClient(
            client_id="test_id", client_secret="test_secret", user_agent="test_agent"
        )

        result = client.get_post("test_post_id")

        assert result == mock_submission
        mock_reddit_instance.submission.assert_called_once_with(id="test_post_id")

    @patch("reddit_downloader.client.praw.Reddit")
    def test_get_user_posts(self, mock_reddit: MagicMock) -> None:
        """Test fetching user posts."""
        mock_reddit_instance = MagicMock()
        mock_redditor = MagicMock()
        mock_submissions = [MagicMock(), MagicMock()]
        mock_redditor.submissions.new.return_value = mock_submissions
        mock_reddit_instance.redditor.return_value = mock_redditor
        mock_reddit.return_value = mock_reddit_instance

        client = RedditClient(
            client_id="test_id", client_secret="test_secret", user_agent="test_agent"
        )

        result = client.get_user_posts("test_user", limit=10)

        mock_reddit_instance.redditor.assert_called_once_with("test_user")
        mock_redditor.submissions.new.assert_called_once_with(limit=10)
        assert list(result) == mock_submissions

    @patch("reddit_downloader.client.praw.Reddit")
    def test_get_user_posts_no_limit(self, mock_reddit: MagicMock) -> None:
        """Test fetching user posts without limit."""
        mock_reddit_instance = MagicMock()
        mock_redditor = MagicMock()
        mock_redditor.submissions.new.return_value = []
        mock_reddit_instance.redditor.return_value = mock_redditor
        mock_reddit.return_value = mock_reddit_instance

        client = RedditClient(
            client_id="test_id", client_secret="test_secret", user_agent="test_agent"
        )

        client.get_user_posts("test_user")

        mock_redditor.submissions.new.assert_called_once_with(limit=None)

    @patch("reddit_downloader.client.praw.Reddit")
    def test_reddit_property(self, mock_reddit: MagicMock) -> None:
        """Test access to underlying PRAW Reddit instance."""
        mock_reddit_instance = MagicMock()
        mock_reddit.return_value = mock_reddit_instance

        client = RedditClient(
            client_id="test_id", client_secret="test_secret", user_agent="test_agent"
        )

        assert client.reddit == mock_reddit_instance
