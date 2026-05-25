"""Tests for the Textual TUI app."""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

from reddit_downloader.tui.app import JobWidget, RedditDownloaderTUI
from reddit_downloader.types import DownloadJob, JobStatus


def test_tui_app_mount(tmp_path: Path) -> None:
    """Test that the TUI app mounts properly with correct initial state."""
    app = RedditDownloaderTUI(output_dir=tmp_path)

    async def run() -> None:
        async with app.run_test():
            # Verify basic attributes
            assert app.output_dir == tmp_path
            assert app.TITLE == "Reddit Downloader TUI"
            assert not app.web_server_running

            # Verify sidebar inputs exist
            url_input = app.query_one("#input_url")
            assert url_input is not None

            limit_input = app.query_one("#input_limit")
            assert limit_input is not None

    asyncio.run(run())


def test_job_widget_updates(tmp_path: Path) -> None:
    """Test that the JobWidget correctly displays job status and info updates."""
    job = DownloadJob(
        job_id="test-job-123",
        url="https://reddit.com/r/pics/comments/12345",
        status=JobStatus.RUNNING,
        total_items=10,
        completed_items=4,
        failed_items=1,
        current_item="Some Post Title",
    )

    app = RedditDownloaderTUI(output_dir=tmp_path)

    async def run() -> None:
        async with app.run_test():
            widget = JobWidget(job, tmp_path)
            await app.query_one("#jobs_scroll").mount(widget)

            # Check initial values displayed in the widget
            assert widget.status == JobStatus.RUNNING
            assert widget.total_items == 10
            assert widget.completed_items == 4

            # Update job state
            updated_job = DownloadJob(
                job_id="test-job-123",
                url="https://reddit.com/r/pics/comments/12345",
                status=JobStatus.COMPLETED,
                total_items=10,
                completed_items=9,
                failed_items=1,
                current_item=None,
            )
            widget.update_job(updated_job)

            # Check updated values
            assert widget.status == JobStatus.COMPLETED
            assert widget.completed_items == 9

    asyncio.run(run())


@patch("reddit_downloader.tui.app.RedditClient")
def test_tui_api_status_check(mock_client_class: MagicMock, tmp_path: Path) -> None:
    """Test the Reddit client API validation routine in the TUI."""
    # Configure mock client
    mock_client = MagicMock()
    mock_client.can_access_api.return_value = True
    mock_client_class.return_value = mock_client

    app = RedditDownloaderTUI(
        output_dir=tmp_path,
        client_id="fake_id",
        client_secret="fake_secret",
        user_agent="fake_ua",
    )

    async def run() -> None:
        async with app.run_test():
            # Let the background status check thread complete
            await asyncio.sleep(0.2)

            # Since can_access_api was True, reddit_client should be initialized
            assert app.reddit_client is not None
            assert app.reddit_client.can_access_api() is True

    asyncio.run(run())
