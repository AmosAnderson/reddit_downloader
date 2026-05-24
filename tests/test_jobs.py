"""Tests for core job manager."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from reddit_downloader.types import JobStatus, URLType
from reddit_downloader.jobs import JobManager


class TestJobManager:
    """Test JobManager class."""

    def test_create_job(self) -> None:
        """Test job creation."""
        manager = JobManager()

        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")

        assert job_id is not None
        job = manager.get_job(job_id)
        assert job is not None
        assert job.job_id == job_id
        assert job.url == "https://reddit.com/r/test/comments/abc123/test/"
        assert job.status == JobStatus.QUEUED

    def test_create_job_with_limit(self) -> None:
        """Test job creation with limit."""
        manager = JobManager()

        job_id = manager.create_job("https://reddit.com/user/testuser/", limit=10)

        assert job_id is not None
        job = manager.get_job(job_id)
        assert job is not None

    def test_get_job_not_found(self) -> None:
        """Test getting non-existent job."""
        manager = JobManager()

        job = manager.get_job("nonexistent-id")

        assert job is None

    def test_update_job(self) -> None:
        """Test job update."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")

        manager.update_job(job_id, status=JobStatus.RUNNING, total_items=5)

        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.RUNNING
        assert job.total_items == 5

    def test_update_nonexistent_job(self) -> None:
        """Test updating non-existent job."""
        manager = JobManager()

        # Should not raise error
        manager.update_job("nonexistent", status=JobStatus.RUNNING)

    def test_update_rejects_unknown_fields(self) -> None:
        """Test updating unknown job fields fails fast."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")

        try:
            manager.update_job(job_id, missing_field="value")
        except ValueError as e:
            assert "missing_field" in str(e)
        else:
            raise AssertionError("Expected ValueError")

    def test_get_job_returns_snapshot(self) -> None:
        """Test returned jobs cannot mutate manager state."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")

        job = manager.get_job(job_id)
        assert job is not None
        job.status = JobStatus.COMPLETED

        fresh_job = manager.get_job(job_id)
        assert fresh_job is not None
        assert fresh_job.status == JobStatus.QUEUED

    def test_cleanup_jobs_removes_old_jobs_and_directory(self, tmp_path: Path) -> None:
        """Test old terminal jobs and their directories are removed."""
        manager = JobManager(max_job_age_seconds=60)
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")
        job_dir = tmp_path / job_id
        job_dir.mkdir()
        (job_dir / "file.jpg").write_text("data")
        manager.update_job(job_id, status=JobStatus.COMPLETED)
        with manager._lock:
            manager.jobs[job_id].updated_at = datetime.now() - timedelta(seconds=120)

        manager.cleanup_jobs(tmp_path)

        assert manager.get_job(job_id) is None
        assert not job_dir.exists()

    def test_cleanup_jobs_keeps_running_jobs(self, tmp_path: Path) -> None:
        """Test running jobs are not removed by cleanup."""
        manager = JobManager(max_job_age_seconds=60)
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")
        manager.update_job(job_id, status=JobStatus.RUNNING)
        with manager._lock:
            manager.jobs[job_id].updated_at = datetime.now() - timedelta(seconds=120)

        manager.cleanup_jobs(tmp_path)

        assert manager.get_job(job_id) is not None

    def test_list_jobs(self) -> None:
        """Test listing jobs."""
        manager = JobManager()
        job_id1 = manager.create_job("https://reddit.com/r/test/comments/abc1/test/")
        job_id2 = manager.create_job("https://reddit.com/r/test/comments/abc2/test/")

        jobs = manager.list_jobs()

        assert len(jobs) == 2
        # Jobs should be in reverse chronological order (newest first)
        assert jobs[0].job_id == job_id2
        assert jobs[1].job_id == job_id1

    def test_list_jobs_empty(self) -> None:
        """Test listing jobs when empty."""
        manager = JobManager()

        jobs = manager.list_jobs()

        assert jobs == []

    @patch("reddit_downloader.jobs.parse_url")
    @patch("reddit_downloader.jobs.MediaDownloader")
    def test_run_job_invalid_url(self, mock_downloader: MagicMock, mock_parse: MagicMock) -> None:
        """Test running job with invalid URL."""
        manager = JobManager()
        job_id = manager.create_job("https://invalid.com")
        mock_parse.return_value = {"url_type": URLType.INVALID}

        manager.run_job(job_id, MagicMock(), Path("/tmp"), None)

        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert job.error == "Invalid Reddit URL"

    @patch("reddit_downloader.jobs.parse_url")
    @patch("reddit_downloader.jobs.MediaDownloader")
    def test_run_job_single_post(
        self, mock_downloader_class: MagicMock, mock_parse: MagicMock
    ) -> None:
        """Test running job for single post."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")

        mock_parse.return_value = {"url_type": URLType.POST, "post_id": "abc123"}
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_client.get_post.return_value = mock_post

        mock_downloader = MagicMock()
        mock_result = MagicMock(success=True)
        mock_downloader.download_post_media.return_value = [mock_result]
        mock_downloader_class.return_value = mock_downloader

        manager.run_job(job_id, mock_client, Path("/tmp"), None)

        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert job.completed_items == 1
        mock_client.get_post.assert_called_once_with("abc123")
        mock_downloader_class.assert_called_once()
        assert mock_downloader_class.call_args.args == (Path("/tmp") / job_id,)
        assert "cancel_event" in mock_downloader_class.call_args.kwargs
        mock_downloader.download_post_media.assert_called_once_with(mock_post)

    @patch("reddit_downloader.jobs.parse_url")
    @patch("reddit_downloader.jobs.MediaDownloader")
    def test_run_job_user_posts(
        self, mock_downloader_class: MagicMock, mock_parse: MagicMock
    ) -> None:
        """Test running job for user posts."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/user/testuser/", limit=2)

        mock_parse.return_value = {"url_type": URLType.USER, "username": "testuser"}
        mock_client = MagicMock()

        mock_post1 = MagicMock()
        mock_post1.title = "Test Post 1"
        mock_post2 = MagicMock()
        mock_post2.title = "Test Post 2"
        mock_client.get_user_posts.return_value = [mock_post1, mock_post2]

        mock_downloader = MagicMock()
        mock_result = MagicMock(success=True)
        mock_downloader.download_post_media.return_value = [mock_result]
        mock_downloader_class.return_value = mock_downloader

        manager.run_job(job_id, mock_client, Path("/tmp"), limit=2)

        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED
        assert job.completed_items == 2
        assert job.total_items == 2
        mock_client.get_user_posts.assert_called_once_with("testuser", limit=2)

    @patch("reddit_downloader.jobs.parse_url")
    @patch("reddit_downloader.jobs.MediaDownloader")
    def test_run_job_cancelled_during_single_post(
        self, mock_downloader_class: MagicMock, mock_parse: MagicMock
    ) -> None:
        """Test cancellation reported while a single post is downloading."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")
        mock_parse.return_value = {"url_type": URLType.POST, "post_id": "abc123"}
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_client.get_post.return_value = mock_post
        mock_downloader = MagicMock()

        def download_post_media(post: MagicMock) -> list[MagicMock]:
            manager.cancel_job(job_id)
            return [MagicMock(success=False)]

        mock_downloader.download_post_media.side_effect = download_post_media
        mock_downloader_class.return_value = mock_downloader

        manager.run_job(job_id, mock_client, Path("/tmp"), None)

        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.CANCELLED
        assert job.results is not None

    @patch("reddit_downloader.jobs.parse_url")
    def test_run_job_exception(self, mock_parse: MagicMock) -> None:
        """Test running job with exception."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")

        mock_parse.side_effect = Exception("Test error")

        manager.run_job(job_id, MagicMock(), Path("/tmp"), None)

        job = manager.get_job(job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert "Test error" in str(job.error)

    @patch("reddit_downloader.jobs.parse_url")
    @patch("reddit_downloader.jobs.MediaDownloader")
    def test_run_job_uses_client_factory(
        self, mock_downloader_class: MagicMock, mock_parse: MagicMock
    ) -> None:
        """Test jobs can create a per-job Reddit client from a factory."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")
        mock_parse.return_value = {"url_type": URLType.POST, "post_id": "abc123"}
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_client.get_post.return_value = mock_post
        factory = MagicMock(return_value=mock_client)
        mock_downloader = MagicMock()
        mock_downloader.download_post_media.return_value = [MagicMock(success=True)]
        mock_downloader_class.return_value = mock_downloader

        manager.run_job(job_id, None, Path("/tmp"), None, client_factory=factory)

        factory.assert_called_once_with()
        mock_client.get_post.assert_called_once_with("abc123")

    @patch("reddit_downloader.jobs.threading.Thread")
    def test_start_job(self, mock_thread: MagicMock) -> None:
        """Test starting job in background thread."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")
        mock_client = MagicMock()
        output_dir = Path("/tmp")

        manager.start_job(job_id, mock_client, output_dir, None)

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()

    def test_cancel_job_queued(self) -> None:
        """Test cancelling a queued job."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")

        result = manager.cancel_job(job_id)

        assert result is True
        # Job status will be updated when run_job checks the stop event
        # The stop event should be set
        assert job_id in manager._stop_events
        assert manager._stop_events[job_id].is_set()

    def test_cancel_job_running(self) -> None:
        """Test cancelling a running job."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")
        manager.update_job(job_id, status=JobStatus.RUNNING)

        result = manager.cancel_job(job_id)

        assert result is True
        # The stop event should be set
        assert job_id in manager._stop_events
        assert manager._stop_events[job_id].is_set()

    def test_cancel_job_completed(self) -> None:
        """Test cancelling a completed job."""
        manager = JobManager()
        job_id = manager.create_job("https://reddit.com/r/test/comments/abc123/test/")
        manager.update_job(job_id, status=JobStatus.COMPLETED)

        result = manager.cancel_job(job_id)

        assert result is False

    def test_cancel_nonexistent_job(self) -> None:
        """Test cancelling non-existent job."""
        manager = JobManager()

        result = manager.cancel_job("nonexistent")

        assert result is False
