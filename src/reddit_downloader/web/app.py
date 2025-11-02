"""Flask web application for reddit_downloader."""

import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, render_template, request
from werkzeug.exceptions import BadRequest

from reddit_downloader.client import RedditClient
from reddit_downloader.parser import validate_reddit_url
from reddit_downloader.web.jobs import JobManager

# Global job manager (will be initialized when server starts)
job_manager: JobManager | None = None
reddit_client: RedditClient | None = None
output_directory: Path | None = None


def create_app() -> Flask:
    """Create and configure Flask application.

    Returns:
        Configured Flask app
    """
    app = Flask(__name__)
    app.config["JSON_SORT_KEYS"] = False

    @app.route("/")
    def index() -> str:
        """Render main page."""
        return render_template("index.html")

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

        if job_manager is None or reddit_client is None or output_directory is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        # Create and start job
        job_id = job_manager.create_job(url, limit)
        job_manager.start_job(job_id, reddit_client, output_directory, limit)

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
        if job_manager is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        success = job_manager.cancel_job(job_id)

        if success:
            return {"success": True, "message": "Job cancelled"}, 200
        else:
            return {"success": False, "error": "Job not found or cannot be cancelled"}, 400

    @app.route("/api/config", methods=["GET"])
    def api_config() -> tuple[dict[str, bool | str], int]:
        """Get server configuration.

        Returns:
            JSON response with server config
        """
        if output_directory is None:
            return {"success": False, "error": "Server not properly initialized"}, 500

        return {
            "success": True,
            "output_dir": str(output_directory),
        }, 200

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
    global job_manager, reddit_client, output_directory

    # Initialize globals
    job_manager = JobManager()
    output_directory = Path(output_dir)

    try:
        reddit_client = RedditClient(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent,
        )
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    app = create_app()

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
        print(f"Error running server: {e}")
        return 1
