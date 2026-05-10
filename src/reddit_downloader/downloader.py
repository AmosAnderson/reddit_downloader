"""Media downloader for Reddit posts."""

import logging
import re
import subprocess
import tempfile
import threading
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from praw.models import Submission
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from reddit_downloader.security import validate_public_download_url
from reddit_downloader.types import DownloadResult, MediaInfo, MediaType

logger = logging.getLogger(__name__)


class MediaDownloader:
    """Download media files from Reddit posts."""

    # Maximum file size (100MB)
    MAX_FILE_SIZE = 100 * 1024 * 1024
    IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp")

    def __init__(
        self,
        output_dir: Path | str,
        *,
        verbose: bool = False,
        timeout: int = 300,
        cancel_event: threading.Event | None = None,
    ) -> None:
        """Initialize media downloader.

        Args:
            output_dir: Directory where media files will be saved
            verbose: Emit debug logging when True
            timeout: Request timeout in seconds (default: 300)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._verbose = verbose
        self.timeout = timeout
        self.cancel_event = cancel_event
        self._last_download_error: str | None = None

        # Configure session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def _log_debug(self, message: str) -> None:
        """Emit debug logs only when verbose output is requested."""

        if self._verbose:
            logger.debug(message)

    def _is_cancelled(self) -> bool:
        """Return whether this downloader has been asked to cancel work."""

        return self.cancel_event is not None and self.cancel_event.is_set()

    def _set_download_error(self, message: str) -> None:
        """Remember the most recent download error for higher-level results."""

        self._last_download_error = message

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem compatibility.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename safe for use on all platforms
        """
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', "_", filename)
        # Limit length
        if len(filename) > 200:
            filename = filename[:200]
        return filename

    def _extract_url_extension(self, url: str, default: str = "jpg") -> str:
        """Extract a file extension (without a dot) from a URL path."""

        path = urlparse(url).path
        suffix = Path(path).suffix.lower().lstrip(".")
        return suffix or default

    def _construct_audio_url(self, base_url: str, audio_variant: str) -> str:
        """Construct audio URL by replacing video DASH variant with audio variant.

        Args:
            base_url: Base video URL with DASH variant
            audio_variant: Audio variant to use (e.g., "DASH_audio.mp4")

        Returns:
            Constructed audio URL
        """
        return re.sub(r"DASH_[^.]+\.mp4", audio_variant, base_url)

    def _create_media_info(
        self, post: Submission, media_type: MediaType, filename: str
    ) -> MediaInfo:
        """Create MediaInfo object from post data.

        Args:
            post: PRAW Submission object
            media_type: Type of media
            filename: Filename for the media

        Returns:
            MediaInfo object
        """
        return MediaInfo(
            url=post.url,
            media_type=media_type,
            filename=filename,
            post_id=post.id,
            post_title=post.title,
        )

    def _create_download_result(
        self,
        filepath: Path | None,
        media_info: MediaInfo | None,
        error_msg: str = "Download failed",
    ) -> DownloadResult:
        """Create DownloadResult object.

        Args:
            filepath: Path to downloaded file, or None if failed
            media_info: MediaInfo object, or None
            error_msg: Error message to use if download failed

        Returns:
            DownloadResult object
        """
        return DownloadResult(
            success=filepath is not None,
            file_path=filepath,
            error=None if filepath else error_msg,
            media_info=media_info,
        )

    def _get_media_type(self, post: Submission) -> MediaType:
        """Determine the type of media in a Reddit post.

        Args:
            post: PRAW Submission object

        Returns:
            MediaType enum value
        """
        # Check if it's a text-only post
        if post.is_self:
            return MediaType.NONE

        # Check for Reddit-hosted gallery
        if hasattr(post, "is_gallery") and post.is_gallery:
            return MediaType.GALLERY

        # Check for Reddit-hosted video
        if hasattr(post, "is_video") and post.is_video:
            return MediaType.VIDEO

        # Check URL path for image extensions, ignoring query parameters/fragments.
        url = post.url.lower()
        url_path = urlparse(post.url).path.lower()
        if any(url_path.endswith(ext) for ext in self.IMAGE_EXTENSIONS):
            return MediaType.IMAGE

        # Check for common image/video hosting domains
        if any(
            domain in url
            for domain in ("i.redd.it", "i.imgur.com", "imgur.com", "gfycat.com", "redgifs.com")
        ):
            return MediaType.EXTERNAL

        # Default to external for other URLs
        if post.url:
            return MediaType.EXTERNAL

        return MediaType.NONE

    def _download_file(self, url: str, filepath: Path) -> bool:
        """Download a file from URL to filepath.

        Args:
            url: URL to download from
            filepath: Local path to save file

        Returns:
            True if successful, False otherwise
        """
        temp_path: Path | None = None
        self._last_download_error = None

        if self._is_cancelled():
            self._set_download_error("Download cancelled")
            return False

        try:
            validate_public_download_url(url)
        except ValueError as e:
            self._set_download_error(str(e))
            logger.warning("Blocked unsafe download URL %s: %s", url, e)
            return False

        try:
            with self.session.get(url, timeout=self.timeout, stream=True) as response:
                try:
                    response.raise_for_status()
                except requests.HTTPError as e:
                    status = response.status_code
                    reason = response.reason or "HTTP error"
                    self._set_download_error(f"HTTP {status}: {reason}")
                    raise e

                # Check content length
                content_length = response.headers.get("content-length")
                if content_length and int(content_length) > self.MAX_FILE_SIZE:
                    error = f"File too large: {content_length} bytes (max: {self.MAX_FILE_SIZE})"
                    logger.warning(error)
                    self._set_download_error(error)
                    return False

                filepath.parent.mkdir(parents=True, exist_ok=True)

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    dir=str(filepath.parent),
                ) as tmp_file:
                    temp_path = Path(tmp_file.name)

                    # Track downloaded size
                    downloaded = 0
                    size_exceeded = False
                    for chunk in response.iter_content(chunk_size=8192):
                        if self._is_cancelled():
                            self._set_download_error("Download cancelled")
                            size_exceeded = True
                            break
                        if chunk:
                            downloaded += len(chunk)
                            if downloaded > self.MAX_FILE_SIZE:
                                error = f"File exceeded size limit: {downloaded} bytes"
                                logger.warning(error)
                                self._set_download_error(error)
                                size_exceeded = True
                                break
                            tmp_file.write(chunk)

                if size_exceeded:
                    if temp_path is not None and temp_path.exists():
                        try:
                            temp_path.unlink()
                        except OSError as e:
                            logger.warning(
                                "Failed to delete oversized temp file %s: %s", temp_path, e
                            )
                    return False

            if self._is_cancelled():
                self._set_download_error("Download cancelled")
                if temp_path is not None and temp_path.exists():
                    temp_path.unlink()
                return False

            if temp_path is not None:
                temp_path.replace(filepath)

            return True
        except requests.Timeout as e:
            self._set_download_error(f"Download timed out after {self.timeout} seconds")
            logger.error(f"Download timed out for {url}: {e}")
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError as cleanup_err:
                    logger.warning("Failed to delete temp file %s: %s", temp_path, cleanup_err)
            return False
        except requests.RequestException as e:
            if self._last_download_error is None:
                self._set_download_error(f"Network error: {e}")
            logger.error(f"Download failed for {url}: {e}")
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError as cleanup_err:
                    logger.warning("Failed to delete temp file %s: %s", temp_path, cleanup_err)
            return False
        except OSError as e:
            self._set_download_error(f"File system error: {e}")
            logger.error(f"File system error: {e}")
            if temp_path is not None and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError as cleanup_err:
                    logger.warning("Failed to delete temp file %s: %s", temp_path, cleanup_err)
            return False

    def download_image(self, url: str, filename: str) -> Path | None:
        """Download a single image.

        Args:
            url: Image URL
            filename: Desired filename (will be sanitized)

        Returns:
            Path to downloaded file, or None if download failed
        """
        safe_filename = self._sanitize_filename(filename)
        filepath = self.output_dir / safe_filename

        if self._download_file(url, filepath):
            return filepath
        return None

    def _candidate_audio_urls(self, reddit_video: dict[str, Any]) -> list[str]:
        """Build a list of possible audio stream URLs for a Reddit video."""

        fallback_url = reddit_video.get("fallback_url")
        if not fallback_url:
            return []

        possible_urls: list[str] = []

        if audio_url := reddit_video.get("audio_url"):
            possible_urls.append(audio_url)

        if hls_url := reddit_video.get("hls_url"):
            base_url = hls_url.rsplit("/", 1)[0]
            possible_urls.extend([f"{base_url}/DASH_audio.mp4", f"{base_url}/DASH_audio_128.mp4"])

        audio_variants = [
            "DASH_audio_128.mp4",
            "DASH_AUDIO_128.mp4",
            "DASH_audio.mp4",
            "DASH_AUDIO.mp4",
        ]
        possible_urls.extend(
            self._construct_audio_url(fallback_url, variant) for variant in audio_variants
        )

        base_fallback = fallback_url.split("?")[0]
        if base_fallback != fallback_url:
            possible_urls.extend(
                self._construct_audio_url(base_fallback, variant)
                for variant in ("DASH_audio_128.mp4", "DASH_audio.mp4")
            )

        unique_urls: list[str] = []
        seen: set[str] = set()
        for url in possible_urls:
            if url == fallback_url or url in seen:
                continue
            seen.add(url)
            unique_urls.append(url)

        return unique_urls

    def download_video(self, post: Submission, filename: str) -> Path | None:
        """Download a Reddit-hosted video with audio.

        Reddit videos have separate video and audio streams that need to be merged.

        Args:
            post: PRAW Submission object
            filename: Desired filename (will be sanitized)

        Returns:
            Path to downloaded file, or None if download failed
        """
        if not hasattr(post, "media") or not post.media:
            logger.debug("Post %s has no media attribute; skipping video download", post.id)
            return None

        # Get video URL from media dict
        media_dict: dict[str, Any] = post.media
        reddit_video = media_dict.get("reddit_video")
        if not isinstance(reddit_video, dict):
            logger.debug("Post %s media payload has no reddit_video dict; skipping", post.id)
            return None

        video_url = reddit_video.get("fallback_url")
        if not isinstance(video_url, str) or not video_url:
            logger.warning("reddit_video payload missing fallback_url for post %s", post.id)
            return None

        # Add .mp4 extension if not present
        if not filename.lower().endswith(".mp4"):
            filename = f"{filename}.mp4"

        safe_filename = self._sanitize_filename(filename)
        filepath = self.output_dir / safe_filename

        # Build list of possible audio URLs to try
        unique_audio_urls = self._candidate_audio_urls(reddit_video)
        self._log_debug(f"Video URL: {video_url}")
        self._log_debug(f"Trying {len(unique_audio_urls)} candidate audio URL(s)")

        # Download video stream to unique temporary files to avoid concurrent job collisions.
        video_tmp_file = tempfile.NamedTemporaryFile(
            delete=False,
            dir=str(self.output_dir),
            prefix="video_",
            suffix=f"_{safe_filename}",
        )
        audio_tmp_file = tempfile.NamedTemporaryFile(
            delete=False,
            dir=str(self.output_dir),
            prefix="audio_",
            suffix=f"_{safe_filename}",
        )
        video_temp = Path(video_tmp_file.name)
        audio_temp = Path(audio_tmp_file.name)
        video_tmp_file.close()
        audio_tmp_file.close()

        try:
            if self._is_cancelled():
                self._set_download_error("Download cancelled")
                return None

            # Download video
            if not self._download_file(video_url, video_temp):
                return None

            # Try to download audio from the list of possible URLs
            has_audio = False

            if not unique_audio_urls:
                self._log_debug("No audio URLs could be constructed")
            else:
                for i, try_url in enumerate(unique_audio_urls):
                    self._log_debug(f"Trying audio URL {i + 1}/{len(unique_audio_urls)}: {try_url}")
                    if self._download_file(try_url, audio_temp):
                        if audio_temp.stat().st_size > 0:
                            self._log_debug(
                                f"Audio downloaded successfully ({audio_temp.stat().st_size} bytes)"
                            )
                            has_audio = True
                            break
                        self._log_debug("Audio file empty, trying next URL")
                    else:
                        self._log_debug("Audio download failed, trying next URL")

            if self._is_cancelled():
                self._set_download_error("Download cancelled")
                return None

            if has_audio:
                # Try to merge video and audio using ffmpeg
                merge_success = self._merge_video_audio(video_temp, audio_temp, filepath)

                if merge_success:
                    # Success! Clean up temp files and return
                    return filepath
                else:
                    # Merge failed, fall back to video only
                    logger.warning(
                        "ffmpeg merge failed for %s, saving video without audio",
                        filename,
                    )
                    if self._last_download_error is None:
                        self._set_download_error("ffmpeg merge failed; saved video without audio")
                    video_temp.rename(filepath)
                    return filepath
            else:
                # No audio stream available
                if unique_audio_urls:
                    logger.warning(
                        "All %d audio URL(s) failed for %s; saving video without audio",
                        len(unique_audio_urls),
                        filename,
                    )
                else:
                    logger.debug("No audio stream found for %s", filename)
                video_temp.rename(filepath)
                return filepath

        except (requests.RequestException, OSError) as e:
            self._set_download_error(f"Error downloading video: {e}")
            logger.error("Error downloading video %s: %s", filename, e)
            return None
        finally:
            # Clean up temp files if they still exist
            try:
                if video_temp.exists():
                    video_temp.unlink()
                if audio_temp.exists():
                    audio_temp.unlink()
            except OSError as e:
                logger.warning("Failed to clean up temporary video files for %s: %s", filename, e)

    def _merge_video_audio(self, video_path: Path, audio_path: Path, output_path: Path) -> bool:
        """Merge video and audio streams using ffmpeg.

        Args:
            video_path: Path to video file
            audio_path: Path to audio file
            output_path: Path for merged output

        Returns:
            True if merge successful, False otherwise
        """
        if self._is_cancelled():
            self._set_download_error("Download cancelled")
            return False

        try:
            # Use ffmpeg to merge streams
            # -i video -i audio -c:v copy -c:a aac
            subprocess.run(
                [
                    "ffmpeg",
                    "-i",
                    str(video_path),
                    "-i",
                    str(audio_path),
                    "-c:v",
                    "copy",
                    "-c:a",
                    "aac",
                    "-y",  # Overwrite output file if exists
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            return True
        except FileNotFoundError:
            self._set_download_error("ffmpeg not found; saved video without audio")
            logger.warning("ffmpeg not found. Install ffmpeg to download videos with audio.")
            return False
        except subprocess.CalledProcessError as e:
            self._set_download_error(f"ffmpeg merge failed: {e.stderr}")
            logger.warning("ffmpeg merge failed: %s", e.stderr)
            return False

    def download_gallery(self, post: Submission, base_filename: str) -> list[Path]:
        """Download all images from a Reddit gallery.

        Args:
            post: PRAW Submission object with gallery
            base_filename: Base filename for gallery items

        Returns:
            List of paths to downloaded files
        """
        downloaded: list[Path] = []

        if not hasattr(post, "media_metadata") or not post.media_metadata:
            return downloaded

        media_metadata: dict[str, Any] = post.media_metadata
        gallery_items: list[tuple[str, Any]] = []
        gallery_data = getattr(post, "gallery_data", None)

        if isinstance(gallery_data, dict) and isinstance(gallery_data.get("items"), list):
            for item in gallery_data["items"]:
                if not isinstance(item, dict):
                    continue
                media_id = item.get("media_id")
                if isinstance(media_id, str) and media_id in media_metadata:
                    gallery_items.append((media_id, media_metadata[media_id]))

        if not gallery_items:
            gallery_items = list(media_metadata.items())

        for index, (media_id, media_item) in enumerate(gallery_items, start=1):
            logger.debug(f"Processing gallery item {media_id}")
            if media_item.get("status") != "valid":
                logger.debug(
                    "Skipping gallery item %s with status %r",
                    media_id,
                    media_item.get("status"),
                )
                continue

            # Get the largest available image
            if "s" in media_item and "u" in media_item["s"]:
                image_url = media_item["s"]["u"]
            elif "p" in media_item and media_item["p"]:
                # Get the last (largest) preview
                image_url = media_item["p"][-1]["u"]
            else:
                logger.warning("Gallery item %s has no usable image URL; skipping", media_id)
                continue

            # Decode HTML entities in URL
            image_url = unescape(image_url)

            # Determine extension from mime type
            mime_type = media_item.get("m", "image/jpeg")
            ext = mime_type.split("/")[-1]
            if ext == "jpeg":
                ext = "jpg"

            filename = f"{base_filename}_{index}.{ext}"
            filepath = self.download_image(image_url, filename)

            if filepath:
                downloaded.append(filepath)

        return downloaded

    def download_post_media(self, post: Submission) -> list[DownloadResult]:
        """Download all media from a Reddit post.

        Args:
            post: PRAW Submission object

        Returns:
            List of DownloadResult objects
        """
        results: list[DownloadResult] = []
        media_type = self._get_media_type(post)

        # Generate base filename from post author and ID
        author = post.author.name if post.author else "deleted"
        base_filename = f"{author}_{post.id}"

        if media_type == MediaType.NONE:
            # No media to download
            return results

        elif media_type == MediaType.IMAGE:
            # Download single image
            url = post.url
            ext = self._extract_url_extension(url)
            filename = f"{base_filename}.{ext}"

            media_info = self._create_media_info(post, MediaType.IMAGE, filename)
            filepath = self.download_image(url, filename)
            results.append(
                self._create_download_result(
                    filepath,
                    media_info,
                    self._last_download_error or "Image download failed",
                )
            )

        elif media_type == MediaType.VIDEO:
            # Download video
            filename = f"{base_filename}.mp4"
            media_info = self._create_media_info(post, MediaType.VIDEO, filename)
            filepath = self.download_video(post, base_filename)
            results.append(
                self._create_download_result(
                    filepath,
                    media_info,
                    self._last_download_error or "Video download failed",
                )
            )

        elif media_type == MediaType.GALLERY:
            # Download gallery
            downloaded_files = self.download_gallery(post, base_filename)

            for filepath in downloaded_files:
                media_info = self._create_media_info(post, MediaType.GALLERY, filepath.name)
                results.append(self._create_download_result(filepath, media_info))

            # If no files were downloaded from gallery
            if not downloaded_files:
                logger.warning(
                    "No valid images could be downloaded from gallery in post %s", post.id
                )
                results.append(
                    self._create_download_result(None, None, "No valid images found in gallery")
                )

        elif media_type == MediaType.EXTERNAL:
            # For external links, we'll try to download if it looks like a direct image link
            url = post.url
            url_path = urlparse(url).path.lower()
            if any(url_path.endswith(ext) for ext in self.IMAGE_EXTENSIONS):
                ext = self._extract_url_extension(url)
                filename = f"{base_filename}.{ext}"

                media_info = self._create_media_info(post, MediaType.EXTERNAL, filename)
                filepath = self.download_image(url, filename)
                results.append(
                    self._create_download_result(
                        filepath,
                        media_info,
                        self._last_download_error or "External image download failed",
                    )
                )
            else:
                # External link that we can't handle
                logger.debug("Skipping unsupported external link for post %s: %s", post.id, url)
                results.append(
                    self._create_download_result(None, None, f"Unsupported external link: {url}")
                )

        return results
