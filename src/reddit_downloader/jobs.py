"""Background job management for TUI and web interface."""

import logging
import shutil
import threading
import uuid
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from reddit_downloader.client import RedditClient
from reddit_downloader.downloader import MediaDownloader
from reddit_downloader.parser import parse_url
from reddit_downloader.types import DownloadJob, JobStatus, URLType

logger = logging.getLogger(__name__)


class JobManager:
    """Manage background download jobs."""

    def __init__(self, *, max_job_age_seconds: int = 24 * 60 * 60, max_jobs: int = 100) -> None:
        """Initialize job manager."""
        self.jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()
        self._stop_events: dict[str, threading.Event] = {}
        self.max_job_age_seconds = max_job_age_seconds
        self.max_jobs = max_jobs
        self._allowed_update_fields = set(DownloadJob.__dataclass_fields__)

    def create_job(self, url: str, limit: int | None = None) -> str:
        """Create a new download job.

        Args:
            url: Reddit URL to download from
            limit: Maximum number of posts (for user URLs)

        Returns:
            Job ID
        """
        job_id = str(uuid.uuid4())

        with self._lock:
            self.jobs[job_id] = DownloadJob(
                job_id=job_id,
                url=url,
                status=JobStatus.QUEUED,
                total_items=0,
                completed_items=0,
                failed_items=0,
                current_item=None,
                error=None,
                results=None,
            )
            # Create stop event for this job
            self._stop_events[job_id] = threading.Event()

        return job_id

    def get_job(self, job_id: str) -> DownloadJob | None:
        """Get job by ID.

        Args:
            job_id: Job ID

        Returns:
            DownloadJob if found, None otherwise
        """
        with self._lock:
            job = self.jobs.get(job_id)
            return deepcopy(job) if job is not None else None

    def update_job(self, job_id: str, **kwargs: Any) -> None:
        """Update job fields.

        Args:
            job_id: Job ID
            **kwargs: Fields to update
        """
        with self._lock:
            if job_id in self.jobs:
                unknown_fields = set(kwargs) - self._allowed_update_fields
                if unknown_fields:
                    raise ValueError(f"Unknown job field(s): {', '.join(sorted(unknown_fields))}")

                job = self.jobs[job_id]
                for key, value in kwargs.items():
                    setattr(job, key, value)
                job.updated_at = datetime.now()

    def list_jobs(self) -> list[DownloadJob]:
        """Get list of all jobs sorted by creation time (newest first).

        Returns:
            List of all jobs in reverse chronological order
        """
        self.cleanup_jobs()
        with self._lock:
            return deepcopy(
                sorted(
                    self.jobs.values(),
                    key=lambda job: job.created_at,
                    reverse=True,
                )
            )

    def cleanup_jobs(self, output_dir: Path | None = None) -> None:
        """Remove expired or excess completed jobs and their output directories."""
        cutoff = datetime.now() - timedelta(seconds=self.max_job_age_seconds)
        removable_statuses = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}

        with self._lock:
            removable_ids = [
                job_id
                for job_id, job in self.jobs.items()
                if job.status in removable_statuses and job.updated_at < cutoff
            ]

            if len(self.jobs) - len(removable_ids) > self.max_jobs:
                retained_removable = [
                    job
                    for job in sorted(self.jobs.values(), key=lambda item: item.created_at)
                    if job.status in removable_statuses and job.job_id not in removable_ids
                ]
                overflow = len(self.jobs) - len(removable_ids) - self.max_jobs
                removable_ids.extend(job.job_id for job in retained_removable[:overflow])

            for job_id in removable_ids:
                self.jobs.pop(job_id, None)
                self._stop_events.pop(job_id, None)

        if output_dir is not None:
            for job_id in removable_ids:
                job_dir = output_dir / job_id
                try:
                    if job_dir.exists() and job_dir.is_dir():
                        shutil.rmtree(job_dir)
                except OSError as e:
                    logger.warning("Failed to remove job directory %s: %s", job_dir, e)

    def run_job(
        self,
        job_id: str,
        client: RedditClient | None,
        output_dir: Path,
        limit: int | None = None,
        client_factory: Callable[[], RedditClient] | None = None,
    ) -> None:
        """Run a download job in the background.

        Args:
            job_id: Job ID
            client: Reddit API client
            output_dir: Output directory for downloads
            limit: Maximum number of posts to process
        """
        job = self.get_job(job_id)
        if not job:
            return

        stop_event = self._stop_events.get(job_id)
        if not stop_event:
            logger.error(f"No stop event found for job {job_id}")
            return

        try:
            self.update_job(job_id, status=JobStatus.RUNNING)
            if client is None:
                if client_factory is None:
                    raise ValueError("Reddit client or client factory required")
                client = client_factory()

            parsed = parse_url(job.url)
            job_output_dir = output_dir / job_id
            downloader = MediaDownloader(job_output_dir, cancel_event=stop_event)

            if parsed["url_type"] == URLType.INVALID:
                self.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    error="Invalid Reddit URL",
                )
                return

            results = []

            if parsed["url_type"] == URLType.POST:
                # Check if cancelled
                if stop_event.is_set():
                    self.update_job(job_id, status=JobStatus.CANCELLED)
                    logger.info(f"Job {job_id} cancelled before starting")
                    return

                # Download single post
                post_id = parsed["post_id"]
                if not post_id:
                    self.update_job(
                        job_id,
                        status=JobStatus.FAILED,
                        error="Could not extract post ID",
                    )
                    return

                self.update_job(job_id, total_items=1, current_item=f"Post {post_id}")
                post = client.get_post(post_id)
                post_results = downloader.download_post_media(post)
                results.extend(post_results)
                if stop_event.is_set():
                    self.update_job(job_id, status=JobStatus.CANCELLED, results=results)
                    logger.info(f"Job {job_id} cancelled while processing post {post_id}")
                    return
                self.update_job(job_id, completed_items=1)

            elif parsed["url_type"] == URLType.USER:
                # Download from user without pre-loading every submission
                username = parsed["username"]
                if not username:
                    self.update_job(
                        job_id,
                        status=JobStatus.FAILED,
                        error="Could not extract username",
                    )
                    return

                estimated_total = limit or 0
                processed = 0

                if estimated_total:
                    self.update_job(job_id, total_items=estimated_total)

                for post in client.get_user_posts(username, limit=limit):
                    # Check if job was cancelled
                    if stop_event.is_set():
                        self.update_job(job_id, status=JobStatus.CANCELLED, results=results)
                        logger.info(f"Job {job_id} cancelled after processing {processed} posts")
                        return

                    processed += 1
                    total_items = estimated_total or processed

                    # Truncate long titles for display
                    display_title = post.title[:50] + "..." if len(post.title) > 50 else post.title

                    self.update_job(
                        job_id,
                        current_item=display_title,
                        total_items=total_items,
                    )

                    post_results = downloader.download_post_media(post)
                    results.extend(post_results)

                    if stop_event.is_set():
                        self.update_job(job_id, status=JobStatus.CANCELLED, results=results)
                        logger.info(f"Job {job_id} cancelled while processing {display_title}")
                        return

                    self.update_job(
                        job_id,
                        completed_items=processed,
                    )

                final_total = processed or estimated_total
                self.update_job(job_id, completed_items=processed, total_items=final_total)

            # Calculate success/failure counts
            success_count = sum(1 for r in results if r.success)
            failed_count = len(results) - success_count

            self.update_job(
                job_id,
                status=JobStatus.COMPLETED,
                failed_items=failed_count,
                results=results,
                current_item=None,
            )

        except Exception as e:
            logger.error(f"Job {job_id} failed with error: {e}", exc_info=True)
            self.update_job(
                job_id,
                status=JobStatus.FAILED,
                error=str(e),
            )
        finally:
            # Clean up stop event
            with self._lock:
                if job_id in self._stop_events:
                    del self._stop_events[job_id]

    def start_job(
        self,
        job_id: str,
        client: RedditClient | None,
        output_dir: Path,
        limit: int | None = None,
        client_factory: Callable[[], RedditClient] | None = None,
    ) -> None:
        """Start a job in a background thread.

        Args:
            job_id: Job ID
            client: Reddit API client
            output_dir: Output directory for downloads
            limit: Maximum number of posts to process
        """
        thread = threading.Thread(
            target=self.run_job,
            args=(job_id, client, output_dir, limit, client_factory),
            daemon=True,
        )
        thread.start()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job.

        Args:
            job_id: Job ID

        Returns:
            True if job was cancelled, False otherwise
        """
        job = self.get_job(job_id)
        if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            # Signal the job to stop
            if job_id in self._stop_events:
                self._stop_events[job_id].set()
                logger.info(f"Cancellation requested for job {job_id}")
                return True
        return False
