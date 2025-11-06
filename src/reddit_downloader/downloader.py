"""Media downloader for Reddit posts."""

import re
import subprocess
from pathlib import Path
from typing import Any

import requests
from praw.models import Submission

from reddit_downloader.types import DownloadResult, MediaInfo, MediaType


class MediaDownloader:
    """Download media files from Reddit posts."""

    def __init__(self, output_dir: Path | str) -> None:
        """Initialize media downloader.

        Args:
            output_dir: Directory where media files will be saved
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

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

    def _extract_url_extension(self, url: str) -> str:
        """Extract file extension from URL.

        Args:
            url: URL to extract extension from

        Returns:
            File extension without the dot
        """
        return url.split(".")[-1].split("?")[0]

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

        # Check URL for image extensions
        url = post.url.lower()
        if any(url.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp")):
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
        try:
            response = requests.get(url, timeout=30, stream=True)
            response.raise_for_status()

            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
        except (requests.RequestException, OSError, IOError):
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
            return None

        # Get video URL from media dict
        media_dict: dict[str, Any] = post.media
        if "reddit_video" not in media_dict:
            return None

        reddit_video = media_dict["reddit_video"]
        video_url = reddit_video["fallback_url"]

        # Add .mp4 extension if not present
        if not filename.lower().endswith(".mp4"):
            filename = f"{filename}.mp4"

        safe_filename = self._sanitize_filename(filename)
        filepath = self.output_dir / safe_filename

        # Build list of possible audio URLs to try
        possible_audio_urls = []

        # Method 1: Check if audio_url is in the reddit_video dict
        if "audio_url" in reddit_video:
            possible_audio_urls.append(reddit_video["audio_url"])
            print(f"Debug: Found audio_url in metadata: {reddit_video['audio_url']}")

        # Method 2: Try HLS playlist URL
        if "hls_url" in reddit_video:
            base_url = reddit_video["hls_url"].rsplit("/", 1)[0]
            possible_audio_urls.append(f"{base_url}/DASH_audio.mp4")
            possible_audio_urls.append(f"{base_url}/DASH_audio_128.mp4")
            print("Debug: Adding HLS-based audio URLs")

        # Method 3: Construct from fallback URL by replacing DASH_xxx with DASH_audio
        # Try different audio quality levels and capitalizations
        audio_variants = [
            "DASH_audio_128.mp4",
            "DASH_AUDIO_128.mp4",
            "DASH_audio.mp4",
            "DASH_AUDIO.mp4",
        ]
        for variant in audio_variants:
            possible_audio_urls.append(self._construct_audio_url(video_url, variant))

        # Try the base URL structure without query params
        base_video_url = video_url.split("?")[0]
        if base_video_url != video_url:
            for variant in ["DASH_audio_128.mp4", "DASH_audio.mp4"]:
                possible_audio_urls.append(self._construct_audio_url(base_video_url, variant))

        # Remove duplicates while preserving order
        seen = set()
        unique_audio_urls = []
        for url in possible_audio_urls:
            if url not in seen and url != video_url:
                seen.add(url)
                unique_audio_urls.append(url)

        print(f"Debug: Video URL: {video_url}")
        print(f"Debug: Will try {len(unique_audio_urls)} audio URL(s)")

        # Download video stream
        video_temp = self.output_dir / f"temp_video_{safe_filename}"
        audio_temp = self.output_dir / f"temp_audio_{safe_filename}"

        try:
            # Download video
            if not self._download_file(video_url, video_temp):
                return None

            # Try to download audio from the list of possible URLs
            has_audio = False

            if not unique_audio_urls:
                print("Debug: No audio URLs could be constructed")
            else:
                for i, try_url in enumerate(unique_audio_urls):
                    print(f"Debug: Trying audio URL #{i + 1}/{len(unique_audio_urls)}: {try_url}")
                    if self._download_file(try_url, audio_temp):
                        if audio_temp.stat().st_size > 0:
                            print(
                                f"Debug: Audio downloaded successfully "
                                f"({audio_temp.stat().st_size} bytes)"
                            )
                            has_audio = True
                            break
                        else:
                            print("Debug: Empty file, trying next URL")
                    else:
                        print("Debug: Download failed, trying next URL")

            if has_audio and audio_temp.stat().st_size > 0:
                # Try to merge video and audio using ffmpeg
                merge_success = self._merge_video_audio(video_temp, audio_temp, filepath)

                if merge_success:
                    # Success! Clean up temp files and return
                    print("Debug: Video and audio merged successfully!")
                    return filepath
                else:
                    # Merge failed, fall back to video only
                    print(
                        f"Warning: ffmpeg merge failed for {filename}, saving video without audio"
                    )
                    video_temp.rename(filepath)
                    return filepath
            else:
                # No audio stream available
                print("Debug: No audio stream found or audio file is empty")
                video_temp.rename(filepath)
                return filepath

        except (requests.RequestException, OSError, IOError) as e:
            print(f"Error downloading video {filename}: {e}")
            return None
        finally:
            # Clean up temp files if they still exist
            try:
                if video_temp.exists():
                    video_temp.unlink()
                if audio_temp.exists():
                    audio_temp.unlink()
            except OSError:
                pass

    def _merge_video_audio(self, video_path: Path, audio_path: Path, output_path: Path) -> bool:
        """Merge video and audio streams using ffmpeg.

        Args:
            video_path: Path to video file
            audio_path: Path to audio file
            output_path: Path for merged output

        Returns:
            True if merge successful, False otherwise
        """
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
            print("Warning: ffmpeg not found. Install ffmpeg to download videos with audio.")
            return False
        except subprocess.CalledProcessError as e:
            print(f"Warning: ffmpeg merge failed: {e.stderr}")
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

        for index, (_media_id, media_item) in enumerate(media_metadata.items(), start=1):
            if media_item["status"] != "valid":
                continue

            # Get the largest available image
            if "s" in media_item and "u" in media_item["s"]:
                image_url = media_item["s"]["u"]
            elif "p" in media_item and media_item["p"]:
                # Get the last (largest) preview
                image_url = media_item["p"][-1]["u"]
            else:
                continue

            # Decode HTML entities in URL
            image_url = image_url.replace("&amp;", "&")

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
            results.append(self._create_download_result(filepath, media_info))

        elif media_type == MediaType.VIDEO:
            # Download video
            filename = f"{base_filename}.mp4"
            media_info = self._create_media_info(post, MediaType.VIDEO, filename)
            filepath = self.download_video(post, base_filename)
            results.append(
                self._create_download_result(filepath, media_info, "Video download failed")
            )

        elif media_type == MediaType.GALLERY:
            # Download gallery
            downloaded_files = self.download_gallery(post, base_filename)

            for _index, filepath in enumerate(downloaded_files, start=1):
                media_info = self._create_media_info(post, MediaType.GALLERY, filepath.name)
                results.append(self._create_download_result(filepath, media_info))

            # If no files were downloaded from gallery
            if not downloaded_files:
                results.append(
                    self._create_download_result(None, None, "No valid images found in gallery")
                )

        elif media_type == MediaType.EXTERNAL:
            # For external links, we'll try to download if it looks like a direct image link
            url = post.url
            if any(url.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif")):
                ext = self._extract_url_extension(url)
                filename = f"{base_filename}.{ext}"

                media_info = self._create_media_info(post, MediaType.EXTERNAL, filename)
                filepath = self.download_image(url, filename)
                results.append(self._create_download_result(filepath, media_info))
            else:
                # External link that we can't handle
                results.append(
                    self._create_download_result(None, None, f"Unsupported external link: {url}")
                )

        return results
