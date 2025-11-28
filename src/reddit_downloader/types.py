"""Type definitions for reddit_downloader."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class URLType(Enum):
    """Type of Reddit URL."""

    POST = "post"
    USER = "user"
    INVALID = "invalid"


class MediaType(Enum):
    """Type of media content."""

    IMAGE = "image"
    VIDEO = "video"
    GALLERY = "gallery"
    EXTERNAL = "external"  # External links (Imgur, Gfycat, etc.)
    NONE = "none"  # Text-only posts


class JobStatus(Enum):
    """Status of a download job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MediaInfo:
    """Information about media to be downloaded."""

    url: str
    media_type: MediaType
    filename: str
    post_id: str
    post_title: str


@dataclass
class DownloadResult:
    """Result of a media download operation."""

    success: bool
    file_path: Path | None
    error: str | None = None
    media_info: MediaInfo | None = None


@dataclass
class DownloadJob:
    """Represents a download job in the web interface."""

    job_id: str
    url: str
    status: JobStatus
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    current_item: str | None = None
    error: str | None = None
    results: list[DownloadResult] | None = None
    created_at: datetime = field(default_factory=datetime.now)
