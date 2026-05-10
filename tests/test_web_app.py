"""Tests for web application."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient

from reddit_downloader.types import DownloadJob, DownloadResult, JobStatus
from reddit_downloader.web import app
from reddit_downloader.web.app import RedditDownloaderApp


@pytest.fixture
def mock_job_manager() -> MagicMock:
    """Create mock job manager."""
    return MagicMock()


@pytest.fixture
def mock_reddit_client() -> MagicMock:
    """Create mock Reddit client."""
    return MagicMock()


@pytest.fixture
def flask_app(
    mock_job_manager: MagicMock, mock_reddit_client: MagicMock, tmp_path: Path
) -> RedditDownloaderApp:
    """Configure Flask app with mocks."""
    test_app = app.create_app(
        reddit_client=mock_reddit_client, output_dir=tmp_path
    )
    test_app.job_manager = mock_job_manager
    return test_app


@pytest.fixture
def client(flask_app: RedditDownloaderApp) -> Generator[FlaskClient, None, None]:
    """Create Flask test client."""
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as test_client:
        yield test_client


class TestWebAppRoutes:
    """Test web application routes."""

    def test_index(self, client: FlaskClient) -> None:
        """Test index route."""
        response = client.get("/")
        assert response.status_code == 200

    def test_api_download_success(
        self, client: FlaskClient, mock_job_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Test successful download API call."""
        mock_job_manager.create_job.return_value = "test-job-id"

        response = client.post(
            "/api/download",
            json={"url": "https://reddit.com/r/test/comments/abc123/test/", "limit": None},
        )

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["job_id"] == "test-job-id"
        mock_job_manager.create_job.assert_called_once()
        mock_job_manager.cleanup_jobs.assert_called_once_with(tmp_path)
        mock_job_manager.start_job.assert_called_once()

    def test_api_download_missing_url(self, client: FlaskClient) -> None:
        """Test download API with missing URL."""
        response = client.post("/api/download", json={"limit": None})

        assert response.status_code == 400
        data = response.get_json()
        assert data is not None
        assert data["success"] is False
        assert "URL required" in data["error"]

    def test_api_download_invalid_url(self, client: FlaskClient) -> None:
        """Test download API with invalid URL."""
        response = client.post("/api/download", json={"url": "https://example.com"})

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False
        assert "Invalid Reddit URL" in data["error"]

    def test_api_download_no_json(self, client: FlaskClient) -> None:
        """Test download API without JSON payload."""
        response = client.post("/api/download", data="not json")

        assert response.status_code == 400
        data = response.get_json()
        assert data is not None
        assert data["success"] is False
        assert "valid JSON" in data["error"]

    def test_api_download_malformed_json(self, client: FlaskClient) -> None:
        """Test download API with malformed JSON payload."""
        response = client.post(
            "/api/download",
            data='{"url": "https://reddit.com/r/test/comments/abc123/test/",',
            content_type="application/json",
        )

        assert response.status_code == 400
        data = response.get_json()
        assert data is not None
        assert data["success"] is False
        assert "valid JSON" in data["error"]

    def test_api_status_success(
        self, client: FlaskClient, mock_job_manager: MagicMock
    ) -> None:
        """Test successful status check."""
        mock_job = DownloadJob(
            job_id="test-job-id",
            url="https://reddit.com/r/test/comments/abc123/test/",
            status=JobStatus.RUNNING,
            total_items=10,
            completed_items=5,
            failed_items=0,
            current_item="test item",
            error=None,
            results=None,
        )
        mock_job_manager.get_job.return_value = mock_job

        response = client.get("/api/status/test-job-id")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["job_id"] == "test-job-id"
        assert data["status"] == "running"
        assert data["total_items"] == 10
        assert data["completed_items"] == 5

    def test_api_status_not_found(
        self, client: FlaskClient, mock_job_manager: MagicMock
    ) -> None:
        """Test status check for non-existent job."""
        mock_job_manager.get_job.return_value = None

        response = client.get("/api/status/nonexistent")

        assert response.status_code == 404
        data = response.get_json()
        assert data["success"] is False

    def test_api_downloads(
        self, client: FlaskClient, mock_job_manager: MagicMock
    ) -> None:
        """Test downloads list API."""
        mock_jobs = [
            DownloadJob(
                job_id="job1",
                url="https://reddit.com/r/test/comments/abc123/test/",
                status=JobStatus.COMPLETED,
                total_items=5,
                completed_items=5,
                failed_items=0,
                current_item=None,
                error=None,
                results=None,
            ),
            DownloadJob(
                job_id="job2",
                url="https://reddit.com/user/testuser/",
                status=JobStatus.RUNNING,
                total_items=10,
                completed_items=3,
                failed_items=0,
                current_item="current",
                error=None,
                results=None,
            ),
        ]
        mock_job_manager.list_jobs.return_value = mock_jobs

        response = client.get("/api/downloads")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["jobs"]) == 2
        assert data["jobs"][0]["job_id"] == "job1"
        assert data["jobs"][1]["job_id"] == "job2"

    def test_api_cancel_success(
        self, client: FlaskClient, mock_job_manager: MagicMock
    ) -> None:
        """Test successful job cancellation."""
        mock_job_manager.cancel_job.return_value = True

        response = client.post("/api/cancel/test-job-id")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True

    def test_api_cancel_failure(
        self, client: FlaskClient, mock_job_manager: MagicMock
    ) -> None:
        """Test failed job cancellation."""
        mock_job_manager.cancel_job.return_value = False

        response = client.post("/api/cancel/test-job-id")

        assert response.status_code == 400
        data = response.get_json()
        assert data["success"] is False

    def test_create_app_uses_reddit_client_factory(
        self, mock_job_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Test API downloads can be started with a client factory instead of shared client."""
        client_factory = MagicMock()
        test_app = app.create_app(output_dir=tmp_path, reddit_client_factory=client_factory)
        test_app.job_manager = mock_job_manager
        test_app.config["TESTING"] = True
        mock_job_manager.create_job.return_value = "job-id"

        with test_app.test_client() as test_client:
            response = test_client.post(
                "/api/download",
                json={"url": "https://reddit.com/r/test/comments/abc123/test/", "limit": None},
            )

        assert response.status_code == 200
        mock_job_manager.start_job.assert_called_once()
        assert mock_job_manager.start_job.call_args.kwargs["client_factory"] is client_factory

    def test_api_config(self, client: FlaskClient) -> None:
        """Test config API."""
        response = client.get("/api/config")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert "output_dir" in data

    def test_api_files_success(
        self, client: FlaskClient, mock_job_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Test files API with successful job."""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test content")

        mock_result = DownloadResult(
            success=True,
            file_path=test_file,
            error=None,
            media_info=None,
        )
        mock_job = DownloadJob(
            job_id="test-job-id",
            url="https://reddit.com/r/test/comments/abc123/test/",
            status=JobStatus.COMPLETED,
            total_items=1,
            completed_items=1,
            failed_items=0,
            current_item=None,
            error=None,
            results=[mock_result],
        )
        mock_job_manager.get_job.return_value = mock_job

        response = client.get("/api/files/test-job-id")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert len(data["files"]) == 1
        assert data["files"][0]["filename"] == "test.jpg"

    def test_download_file_retains_source_file(
        self, client: FlaskClient, mock_job_manager: MagicMock, tmp_path: Path
    ) -> None:
        """Test single-file downloads do not immediately delete source files."""
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test content")
        mock_job_manager.get_job.return_value = DownloadJob(
            job_id="test-job-id",
            url="https://reddit.com/r/test/comments/abc123/test/",
            status=JobStatus.COMPLETED,
            results=[DownloadResult(success=True, file_path=test_file)],
        )

        response = client.get("/api/download-file/test-job-id/0")
        response.close()

        assert response.status_code == 200
        assert test_file.exists()

    def test_api_files_empty_results(
        self, client: FlaskClient, mock_job_manager: MagicMock
    ) -> None:
        """Test files API with no results."""
        mock_job = DownloadJob(
            job_id="test-job-id",
            url="https://reddit.com/r/test/comments/abc123/test/",
            status=JobStatus.COMPLETED,
            total_items=0,
            completed_items=0,
            failed_items=0,
            current_item=None,
            error=None,
            results=None,
        )
        mock_job_manager.get_job.return_value = mock_job

        response = client.get("/api/files/test-job-id")

        assert response.status_code == 200
        data = response.get_json()
        assert data["success"] is True
        assert data["files"] == []


class TestWebAppAuth:
    """Test optional API authentication."""

    def test_api_requires_token_when_configured(
        self, mock_reddit_client: MagicMock, tmp_path: Path
    ) -> None:
        """Test API routes reject requests without the configured bearer token."""
        test_app = app.create_app(
            reddit_client=mock_reddit_client,
            output_dir=tmp_path,
            auth_token="secret-token",
        )
        test_app.config["TESTING"] = True

        with test_app.test_client() as test_client:
            response = test_client.get("/api/config")

        assert response.status_code == 401
        data = response.get_json()
        assert data is not None
        assert data["success"] is False

    def test_api_accepts_valid_token(
        self, mock_reddit_client: MagicMock, tmp_path: Path
    ) -> None:
        """Test API routes accept requests with the configured bearer token."""
        test_app = app.create_app(
            reddit_client=mock_reddit_client,
            output_dir=tmp_path,
            auth_token="secret-token",
        )
        test_app.config["TESTING"] = True

        with test_app.test_client() as test_client:
            response = test_client.get(
                "/api/config",
                headers={"Authorization": "Bearer secret-token"},
            )

        assert response.status_code == 200
        data = response.get_json()
        assert data is not None
        assert data["success"] is True

    def test_index_is_public_when_token_configured(
        self, mock_reddit_client: MagicMock, tmp_path: Path
    ) -> None:
        """Test non-API routes remain public with API auth enabled."""
        test_app = app.create_app(
            reddit_client=mock_reddit_client,
            output_dir=tmp_path,
            auth_token="secret-token",
        )
        test_app.config["TESTING"] = True

        with test_app.test_client() as test_client:
            response = test_client.get("/")

        assert response.status_code == 200


class TestOpenBrowser:
    """Test browser opening utility."""

    @patch("reddit_downloader.web.app.webbrowser.open")
    @patch("reddit_downloader.web.app.Timer")
    def test_open_browser(self, mock_timer: MagicMock, mock_open: MagicMock) -> None:
        """Test browser opening with delay."""
        app.open_browser("http://localhost:5000", delay=1.0)

        mock_timer.assert_called_once()
        assert mock_timer.call_args[0][0] == 1.0
        mock_timer.return_value.start.assert_called_once()
