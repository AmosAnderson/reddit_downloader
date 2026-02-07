"""Reddit API client wrapper using PRAW."""

import logging
import os
from collections.abc import Iterator
from typing import Any, Self

import praw
from dotenv import load_dotenv
from praw.models import Redditor, Submission
from prawcore import exceptions as prawcore_exceptions

logger = logging.getLogger(__name__)


class RedditClient:
    """Wrapper for PRAW Reddit client with authentication and convenience methods."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        user_agent: str | None = None,
        *,
        load_env: bool = True,
    ) -> None:
        """Initialize Reddit client.

        Args:
            client_id: Reddit API client ID (defaults to REDDIT_CLIENT_ID env var)
            client_secret: Reddit API client secret (defaults to REDDIT_CLIENT_SECRET env var)
            user_agent: User agent string (defaults to REDDIT_USER_AGENT env var
                        or a default value)
            load_env: Whether to load environment variables from .env file

        Raises:
            ValueError: If credentials are not provided or found in environment
        """
        if load_env:
            load_dotenv()

        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
        self.user_agent = user_agent or os.getenv("REDDIT_USER_AGENT", "reddit_downloader/0.1.0")

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Reddit API credentials required. "
                "Provide client_id and client_secret or set "
                "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables."
            )

        self._reddit: praw.Reddit = praw.Reddit(
            client_id=self.client_id,
            client_secret=self.client_secret,
            user_agent=self.user_agent,
            check_for_async=False,
        )

    def __enter__(self) -> Self:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        # PRAW doesn't require explicit cleanup
        pass

    def is_authenticated(self) -> bool:
        """Check if client is authenticated and can access Reddit API.

        Returns:
            True if authenticated, False otherwise
        """
        try:
            # Try to access read-only endpoint
            _ = self._reddit.read_only
            return True
        except (
            praw.exceptions.PRAWException,
            prawcore_exceptions.PrawcoreException,
            AttributeError,
        ) as e:
            logger.debug(f"Authentication check failed: {e}")
            return False

    def get_post(self, post_id: str) -> Submission:
        """Fetch a single Reddit post by ID.

        Args:
            post_id: Reddit post ID

        Returns:
            PRAW Submission object

        Raises:
            Exception: If post cannot be fetched
        """
        return self._reddit.submission(id=post_id)

    def get_user_posts(self, username: str, limit: int | None = None) -> Iterator[Submission]:
        """Fetch posts from a user's profile.

        Args:
            username: Reddit username
            limit: Maximum number of posts to fetch (None for all available)

        Returns:
            Iterator of PRAW Submission objects

        Raises:
            Exception: If user cannot be found or posts cannot be fetched
        """
        user: Redditor = self._reddit.redditor(username)

        # Get submissions from the user
        # Using 'new' to get posts in chronological order
        submissions = user.submissions.new(limit=limit)

        return iter(submissions)

    @property
    def reddit(self) -> praw.Reddit:
        """Access to underlying PRAW Reddit instance.

        Returns:
            PRAW Reddit instance
        """
        return self._reddit
