"""Tests for the command-line interface."""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

from reddit_downloader.__main__ import main


class TestCliMain:
    """Tests for CLI argument handling."""

    @patch("reddit_downloader.__main__.RedditClient")
    def test_user_limit_must_be_positive(
        self, mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test user --limit rejects non-positive values before client init."""
        with patch.object(sys, "argv", ["reddit_downloader", "user", "testuser", "--limit", "0"]):
            result = main()

        assert result == 1
        mock_client.assert_not_called()
        captured = capsys.readouterr()
        assert "--limit must be between" in captured.err

    @patch("reddit_downloader.__main__.RedditClient")
    def test_user_limit_has_upper_bound(
        self, mock_client: MagicMock, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test user --limit rejects values above the configured cap."""
        with patch.object(
            sys, "argv", ["reddit_downloader", "user", "testuser", "--limit", "1001"]
        ):
            result = main()

        assert result == 1
        mock_client.assert_not_called()
        captured = capsys.readouterr()
        assert "--limit must be between" in captured.err

    @patch("reddit_downloader.__main__.logging.basicConfig")
    @patch("reddit_downloader.__main__.download_post")
    @patch("reddit_downloader.__main__.RedditClient")
    def test_verbose_configures_debug_logging(
        self,
        mock_client_class: MagicMock,
        mock_download_post: MagicMock,
        mock_basic_config: MagicMock,
    ) -> None:
        """Test verbose mode configures debug logging."""
        mock_download_post.return_value = 0
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        argv = [
            "reddit_downloader",
            "post",
            "https://redd.it/abc123",
            "--client-id",
            "id",
            "--client-secret",
            "secret",
            "--verbose",
        ]

        with patch.object(sys, "argv", argv):
            result = main()

        assert result == 0
        assert mock_basic_config.call_args.kwargs["level"] == logging.DEBUG

    @patch("reddit_downloader.web.app.run_web_server")
    def test_web_no_open_browser_flag(self, mock_run_web_server: MagicMock) -> None:
        """Test --no-open-browser is passed to the web server."""
        mock_run_web_server.return_value = 0

        with patch.object(sys, "argv", ["reddit_downloader", "web", "--no-open-browser"]):
            result = main()

        assert result == 0
        assert mock_run_web_server.call_args.kwargs["open_browser_on_start"] is False
