"""Flask web application for reddit_downloader."""

import logging
import shutil
import tarfile
import tempfile
import webbrowser
import zipfile
from pathlib import Path
from threading import Timer
from typing import Any, cast

import zstandard as zstd
from flask import Flask, Response, current_app, g, render_template, request, send_file
from werkzeug.exceptions import BadRequest

from reddit_downloader.client import RedditClient
from reddit_downloader.parser import validate_reddit_url
from reddit_downloader.web.jobs import JobManager

logger = logging.getLogger(__name__)


class RedditDownloaderApp(Flask):
    """Flask app with typed dependencies."""

    job_manager: JobManager
    reddit_client: RedditClient | None
    output_directory: Path | None


def _get_app() -> RedditDownloaderApp:
    """Return the current app with typed attributes."""
    return cast(RedditDownloaderApp, current_app)


def create_app(
    reddit_client: RedditClient | None = None,
    output_dir: Path | None = None,
) -> RedditDownloaderApp:
    """Create and configure Flask application.

    Args:
        reddit_client: Reddit API client instance
        output_dir: Output directory for downloads

    Returns:
        Configured Flask app
    """
    app = RedditDownloaderApp(__name__)
    app.config["JSON_SORT_KEYS"] = False

    # Store dependencies in app config
    app.job_manager = JobManager()
    app.reddit_client = reddit_client
    app.output_directory = output_dir

    @app.before_request
    def before_request() -> None:
        """Set up request context."""
        import uuid
        g.request_id = str(uuid.uuid4())
        logger.debug(f"Request {g.request_id}: {request.method} {request.path}")

    @app.route("/")
    def index() -> str:
        """Render main page."""
        return render_template("index.html")

    @app.route("/health")
    def health() -> tuple[dict[str, str], int]:
        """Health check endpoint."""
        import time
        return {"status": "ok", "timestamp": str(time.time())}, 200

    @app.route("/api/download", methods=["POST"])
    def api_download() -> tuple[dict[str, str | bool], int]:
        """Start a new download job.

        Request JSON:
            {
                "url": "reddit_url",
                "limit": null | int
            }

        Returns:
            JSON response with job_id
        """
        if not request.json:
            raise BadRequest("Request must be JSON")

        url = request.json.get("url")
        limit = request.json.get("limit")

        if not url:
            return {"success": False, "error": "URL required"}, 400

        if not validate_reddit_url(url):
            return {"success": False, "error": "Invalid Reddit URL"}, 400

        # Validate limit parameter
        if limit is not None:
            if not isinstance(limit, int) or limit < 1 or limit > 1000:
                return {
                    "success": False,
                    "error": "Limit must be an integer between 1 and 1000",
                }, 400

        app_context = _get_app()
        job_manager = app_context.job_manager
        reddit_client = app_context.reddit_client
        output_directory = app_context.output_directory

        if job_manager is None or reddit_client is None or output_directory is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        # Create and start job
        job_id = job_manager.create_job(url, limit)
        job_manager.start_job(job_id, reddit_client, output_directory, limit)

        logger.info(f"Started job {job_id} for URL: {url}")

        return {
            "success": True,
            "job_id": job_id,
            "message": "Download started",
        }, 200

    @app.route("/api/status/<job_id>", methods=["GET"])
    def api_status(job_id: str) -> tuple[dict[str, str | int | bool | None], int]:
        """Get status of a download job.

        Args:
            job_id: Job ID

        Returns:
            JSON response with job status
        """
        job_manager = _get_app().job_manager
        if job_manager is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        job = job_manager.get_job(job_id)

        if not job:
            return {"success": False, "error": "Job not found"}, 404

        return {
            "success": True,
            "job_id": job.job_id,
            "status": job.status.value,
            "url": job.url,
            "total_items": job.total_items,
            "completed_items": job.completed_items,
            "failed_items": job.failed_items,
            "current_item": job.current_item,
            "error": job.error,
        }, 200

    @app.route("/api/downloads", methods=["GET"])
    def api_downloads() -> tuple[dict[str, bool | str | list[dict[str, str | int | None]]], int]:
        """Get list of all download jobs.

        Returns:
            JSON response with list of jobs
        """
        job_manager = _get_app().job_manager
        if job_manager is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        jobs = job_manager.list_jobs()

        jobs_data = [
            {
                "job_id": job.job_id,
                "url": job.url,
                "status": job.status.value,
                "total_items": job.total_items,
                "completed_items": job.completed_items,
                "failed_items": job.failed_items,
                "error": job.error,
            }
            for job in jobs
        ]

        return {"success": True, "jobs": jobs_data}, 200

    @app.route("/api/cancel/<job_id>", methods=["POST"])
    def api_cancel(job_id: str) -> tuple[dict[str, bool | str], int]:
        """Cancel a running job.

        Args:
            job_id: Job ID

        Returns:
            JSON response indicating success
        """
        job_manager = _get_app().job_manager
        if job_manager is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        success = job_manager.cancel_job(job_id)

        if success:
            logger.info(f"Cancelled job {job_id}")
            return {"success": True, "message": "Job cancelled"}, 200
        else:
            return {"success": False, "error": "Job not found or cannot be cancelled"}, 400

    @app.route("/api/config", methods=["GET"])
    def api_config() -> tuple[dict[str, bool | str], int]:
        """Get server configuration.

        Returns:
            JSON response with server config
        """
        output_directory = _get_app().output_directory
        if output_directory is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        return {
            "success": True,
            "output_dir": str(output_directory),
        }, 200

    @app.route("/api/files/<job_id>", methods=["GET"])
    def api_files(job_id: str) -> tuple[dict[str, object], int]:
        """Get list of files for a completed job.

        Args:
            job_id: Job ID

        Returns:
            JSON response with list of files
        """
        job_manager = _get_app().job_manager
        if job_manager is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        job = job_manager.get_job(job_id)

        if not job:
            return {"success": False, "error": "Job not found"}, 404

        if not job.results:
            return {"success": True, "files": []}, 200

        files = []
        for index, result in enumerate(job.results):
            if result.success and result.file_path and result.file_path.exists():
                files.append(
                    {
                        "index": index,
                        "filename": result.file_path.name,
                        "size": result.file_path.stat().st_size,
                    }
                )

        return {"success": True, "files": files}, 200

    @app.route("/api/download-file/<job_id>/<int:file_index>", methods=["GET"])
    def api_download_file(job_id: str, file_index: int) -> Response | tuple[dict[str, Any], int]:
        """Download a single file and delete it after sending.

        Args:
            job_id: Job ID
            file_index: Index of the file in the job's results

        Returns:
            File download response
        """
        app_context = _get_app()
        job_manager = app_context.job_manager
        output_directory = app_context.output_directory

        if job_manager is None or output_directory is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        job = job_manager.get_job(job_id)

        if not job:
            return {"success": False, "error": "Job not found"}, 404

        if not job.results or file_index >= len(job.results) or file_index < 0:
            return {"success": False, "error": "File not found"}, 404

        result = job.results[file_index]

        if not result.success or not result.file_path or not result.file_path.exists():
            return {"success": False, "error": "File not available"}, 404

        file_path = result.file_path

        # Validate path is within output directory (security check)
        try:
            if not file_path.resolve().is_relative_to(output_directory.resolve()):
                logger.warning(f"Attempted access to file outside output dir: {file_path}")
                return {"success": False, "error": "Invalid file path"}, 403
        except ValueError:
            logger.warning(f"Path validation failed for: {file_path}")
            return {"success": False, "error": "Invalid file path"}, 403

        # Send file and delete after
        response = send_file(
            str(file_path),
            as_attachment=True,
            download_name=file_path.name,
        )

        # Delete file after sending (only if response successful)
        @response.call_on_close
        def cleanup() -> None:
            try:
                if file_path.exists():
                    file_path.unlink()
                    logger.info(f"Deleted downloaded file: {file_path}")
            except OSError as e:
                logger.warning(f"Failed to delete file {file_path}: {e}")

        return response

    @app.route("/api/download-archive/<job_id>", methods=["GET"])
    def api_download_archive(job_id: str) -> Response | tuple[dict[str, Any], int]:
        """Download all files as an archive and delete them after sending.

        Args:
            job_id: Job ID

        Query params:
            format: 'zip' or 'tar.zst' (default: zip)

        Returns:
            Archive download response
        """
        app_context = _get_app()
        job_manager = app_context.job_manager
        output_directory = app_context.output_directory

        if job_manager is None or output_directory is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        job = job_manager.get_job(job_id)

        if not job:
            return {"success": False, "error": "Job not found"}, 404

        if not job.results:
            return {"success": False, "error": "No files to download"}, 404

        # Get all successful downloads
        files = [
            result.file_path
            for result in job.results
            if result.success and result.file_path and result.file_path.exists()
        ]

        if not files:
            return {"success": False, "error": "No files available"}, 404

        # Validate all paths are within output directory (security check)
        output_root = output_directory.resolve()
        validated_files: list[Path] = []
        for file_path in files:
            try:
                if file_path.resolve().is_relative_to(output_root):
                    validated_files.append(file_path)
                else:
                    logger.warning(f"Skipping file outside output dir: {file_path}")
            except ValueError:
                logger.warning(f"Path validation failed for: {file_path}")
        files = validated_files

        if not files:
            return {"success": False, "error": "No valid files available"}, 404

        # Get archive format from query params
        archive_format = request.args.get("format", "zip").lower()

        if archive_format not in ["zip", "tar.zst"]:
            return {"success": False, "error": "Invalid format. Use 'zip' or 'tar.zst'"}, 400

        # Create archive in temporary file instead of memory (avoids OOM)
        try:
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=f".{archive_format.replace('.', '_')}"
            ) as temp_archive:
                temp_path = Path(temp_archive.name)

            if archive_format == "zip":
                with zipfile.ZipFile(temp_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    for file_path in files:
                        zf.write(str(file_path), arcname=file_path.name)
                mimetype = "application/zip"
                extension = "zip"
            else:  # tar.zst
                # Create tar first
                tar_path = temp_path.with_suffix(".tar")
                with tarfile.open(tar_path, mode="w") as tar:
                    for file_path in files:
                        tar.add(str(file_path), arcname=file_path.name)

                # Compress with zstandard
                cctx = zstd.ZstdCompressor(level=3)
                with open(tar_path, "rb") as tar_file, open(temp_path, "wb") as zst_file:
                    with cctx.stream_writer(zst_file) as compressor:
                        shutil.copyfileobj(tar_file, compressor)

                # Clean up tar file
                tar_path.unlink()
                mimetype = "application/zstd"
                extension = "tar.zst"

            # Clean job ID for filename
            safe_job_id = "".join(c if c.isalnum() else "_" for c in job_id)
            download_name = f"reddit_download_{safe_job_id}.{extension}"

            # Send archive
            response = send_file(
                str(temp_path),
                mimetype=mimetype,
                as_attachment=True,
                download_name=download_name,
            )

            # Delete all files after sending
            @response.call_on_close
            def cleanup() -> None:
                deleted_count = 0

                # Delete temporary archive
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except OSError as e:
                    logger.warning(f"Failed to delete temp archive {temp_path}: {e}")

                # Delete downloaded files only on success
                if response.status_code != 200:
                    logger.warning(
                        "Archive download returned status %s; skipping source cleanup",
                        response.status_code,
                    )
                    return

                # Delete downloaded files
                for file_path in files:
                    try:
                        if file_path.exists():
                            file_path.unlink()
                            deleted_count += 1
                    except OSError as e:
                        logger.warning(f"Failed to delete file {file_path}: {e}")

                logger.info(f"Deleted {deleted_count}/{len(files)} files from archive download")

            return response

        except (OSError, IOError) as e:
            logger.error(f"Failed to create archive: {e}")
            return {"success": False, "error": f"Failed to create archive: {str(e)}"}, 500

    return app


def open_browser(url: str, delay: float = 1.0) -> None:
    """Open browser after a delay.

    Args:
        url: URL to open
        delay: Delay in seconds before opening
    """

    def _open() -> None:
        webbrowser.open(url)

    Timer(delay, _open).start()


def run_web_server(
    host: str = "127.0.0.1",
    port: int = 5000,
    output_dir: Path | str = Path("downloads"),
    client_id: str | None = None,
    client_secret: str | None = None,
    user_agent: str | None = None,
    debug: bool = False,
    open_browser_on_start: bool = True,
) -> int:
    """Run the web server.

    Args:
        host: Host address
        port: Port number
        output_dir: Output directory for downloads
        client_id: Reddit API client ID
        client_secret: Reddit API client secret
        user_agent: Reddit API user agent
        debug: Enable debug mode
        open_browser_on_start: Automatically open browser

    Returns:
        Exit code
    """
    output_directory = Path(output_dir)

    try:
        reddit_client = RedditClient(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except ValueError as e:
        logger.error(f"Failed to initialize Reddit client: {e}")
        print(f"Error: {e}")
        return 1

    # Create app with dependencies
    app = create_app(reddit_client=reddit_client, output_dir=output_directory)

    url = f"http://{host}:{port}"
    print(f"Starting Reddit Downloader web interface at {url}")
    print(f"Output directory: {output_directory.absolute()}")
    print("\nPress Ctrl+C to stop the server")

    if open_browser_on_start:
        open_browser(url)

    try:
        app.run(host=host, port=port, debug=debug)
        return 0
    except Exception as e:
        logger.error(f"Error running server: {e}")
        print(f"Error running server: {e}")
        return 1
