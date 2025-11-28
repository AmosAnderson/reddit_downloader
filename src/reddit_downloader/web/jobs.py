"""Background job management for web interface."""

import threading
import uuid
from pathlib import Path
from typing import Any

from reddit_downloader.client import RedditClient
from reddit_downloader.downloader import MediaDownloader
from reddit_downloader.parser import parse_url
from reddit_downloader.types import DownloadJob, JobStatus, URLType


class JobManager:
    """Manage background download jobs."""

    def __init__(self) -> None:
        """Initialize job manager."""
        self.jobs: dict[str, DownloadJob] = {}
        self._lock = threading.Lock()

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

        return job_id

    def get_job(self, job_id: str) -> DownloadJob | None:
        """Get job by ID.

        Args:
            job_id: Job ID

        Returns:
            DownloadJob if found, None otherwise
        """
        with self._lock:
            return self.jobs.get(job_id)

    def update_job(self, job_id: str, **kwargs: Any) -> None:
        """Update job fields.

        Args:
            job_id: Job ID
            **kwargs: Fields to update
        """
        with self._lock:
            if job_id in self.jobs:
                job = self.jobs[job_id]
                for key, value in kwargs.items():
                    if hasattr(job, key):
                        setattr(job, key, value)

    def list_jobs(self) -> list[DownloadJob]:
        """Get list of all jobs sorted by creation time (newest first).

        Returns:
            List of all jobs in reverse chronological order
        """
        with self._lock:
            return sorted(
                self.jobs.values(),
                key=lambda job: job.created_at,
                reverse=True,
            )

    def run_job(
        self,
        job_id: str,
        client: RedditClient,
        output_dir: Path,
        limit: int | None = None,
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

        try:
            self.update_job(job_id, status=JobStatus.RUNNING)

            parsed = parse_url(job.url)
            downloader = MediaDownloader(output_dir)

            if parsed["url_type"] == URLType.INVALID:
                self.update_job(
                    job_id,
                    status=JobStatus.FAILED,
                    error="Invalid Reddit URL",
                )
                return

            results = []

            if parsed["url_type"] == URLType.POST:
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
                    processed += 1
                    total_items = estimated_total or processed

                    self.update_job(
                        job_id,
                        current_item=f"{post.title[:50]}...",
                        completed_items=processed - 1,
                        total_items=total_items,
                    )

                    post_results = downloader.download_post_media(post)
                    results.extend(post_results)

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
            self.update_job(
                job_id,
                status=JobStatus.FAILED,
                error=str(e),
            )

    def start_job(
        self,
        job_id: str,
        client: RedditClient,
        output_dir: Path,
        limit: int | None = None,
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
            args=(job_id, client, output_dir, limit),
            daemon=True,
        )
        thread.start()

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job.

        Note: This currently only marks the job as cancelled.
        Full implementation would need to interrupt the download thread.

        Args:
            job_id: Job ID

        Returns:
            True if job was cancelled, False otherwise
        """
        job = self.get_job(job_id)
        if job and job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
            self.update_job(job_id, status=JobStatus.CANCELLED)
            return True
        return False
