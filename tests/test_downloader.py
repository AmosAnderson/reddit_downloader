"""Tests for MediaDownloader helpers."""

from pathlib import Path
from unittest.mock import MagicMock, patch

from reddit_downloader.downloader import MediaDownloader
from reddit_downloader.types import MediaType


class TestExtractUrlExtension:
    """Tests for MediaDownloader._extract_url_extension."""

    def test_handles_query_parameters(self, tmp_path: Path) -> None:
        downloader = MediaDownloader(tmp_path)
        url = "https://i.redd.it/example_image.PNG?width=640&crop=smart"

        assert downloader._extract_url_extension(url) == "png"

    def test_returns_default_when_missing_suffix(self, tmp_path: Path) -> None:
        downloader = MediaDownloader(tmp_path)
        url = "https://i.redd.it/abcdefg"

        assert downloader._extract_url_extension(url, default="bin") == "bin"

    def test_normalizes_uppercase_suffix(self, tmp_path: Path) -> None:
        downloader = MediaDownloader(tmp_path)
        url = "https://example.com/video.MP4"

        assert downloader._extract_url_extension(url) == "mp4"


class TestMediaDownloaderInit:
    """Test MediaDownloader initialization."""

    def test_init_creates_directory(self, tmp_path: Path) -> None:
        """Test directory creation on init."""
        output_dir = tmp_path / "new_dir"
        assert not output_dir.exists()

        downloader = MediaDownloader(output_dir)

        assert output_dir.exists()
        assert downloader.output_dir == output_dir

    def test_init_with_verbose(self, tmp_path: Path) -> None:
        """Test initialization with verbose flag."""
        downloader = MediaDownloader(tmp_path, verbose=True)

        assert downloader._verbose is True


class TestSanitizeFilename:
    """Test _sanitize_filename method."""

    def test_removes_invalid_characters(self, tmp_path: Path) -> None:
        """Test removing invalid filesystem characters."""
        downloader = MediaDownloader(tmp_path)
        filename = 'test<>:"/\\|?*file.jpg'

        result = downloader._sanitize_filename(filename)

        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert '"' not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_limits_length(self, tmp_path: Path) -> None:
        """Test filename length limiting."""
        downloader = MediaDownloader(tmp_path)
        filename = "a" * 300

        result = downloader._sanitize_filename(filename)

        assert len(result) <= 200


class TestConstructAudioUrl:
    """Test _construct_audio_url method."""

    def test_replaces_video_variant_with_audio(self, tmp_path: Path) -> None:
        """Test replacing video DASH variant with audio."""
        downloader = MediaDownloader(tmp_path)
        base_url = "https://v.redd.it/abc123/DASH_720.mp4"

        result = downloader._construct_audio_url(base_url, "DASH_audio.mp4")

        assert result == "https://v.redd.it/abc123/DASH_audio.mp4"


class TestGetMediaType:
    """Test _get_media_type method."""

    def test_text_post(self, tmp_path: Path) -> None:
        """Test identifying text-only post."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = True

        result = downloader._get_media_type(mock_post)

        assert result == MediaType.NONE

    def test_gallery_post(self, tmp_path: Path) -> None:
        """Test identifying gallery post."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = False
        mock_post.is_gallery = True

        result = downloader._get_media_type(mock_post)

        assert result == MediaType.GALLERY

    def test_video_post(self, tmp_path: Path) -> None:
        """Test identifying video post."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = False
        mock_post.is_gallery = False
        mock_post.is_video = True

        result = downloader._get_media_type(mock_post)

        assert result == MediaType.VIDEO

    def test_image_post_jpg(self, tmp_path: Path) -> None:
        """Test identifying image post."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = False
        mock_post.is_video = False
        mock_post.is_gallery = False
        mock_post.url = "https://example.com/image.jpg"

        result = downloader._get_media_type(mock_post)

        assert result == MediaType.IMAGE

    def test_external_link(self, tmp_path: Path) -> None:
        """Test identifying external link."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = False
        mock_post.is_video = False
        mock_post.is_gallery = False
        mock_post.url = "https://imgur.com/abc123"

        result = downloader._get_media_type(mock_post)

        assert result == MediaType.EXTERNAL


class TestDownloadFile:
    """Test _download_file method."""

    @patch("reddit_downloader.downloader.requests.Session")
    def test_successful_download(self, mock_session_class: MagicMock, tmp_path: Path) -> None:
        """Test successful file download."""
        downloader = MediaDownloader(tmp_path)

        # Mock the session and response
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.headers.get.return_value = None
        mock_response.iter_content.return_value = [b"test data"]
        mock_session.get.return_value.__enter__.return_value = mock_response
        mock_session_class.return_value = mock_session

        # Re-initialize downloader to use mocked session
        downloader = MediaDownloader(tmp_path)

        filepath = tmp_path / "test.jpg"
        result = downloader._download_file("https://example.com/test.jpg", filepath)

        assert result is True
        assert filepath.exists()

    @patch("reddit_downloader.downloader.requests.Session")
    def test_failed_download(self, mock_session_class: MagicMock, tmp_path: Path) -> None:
        """Test failed file download."""
        from requests import RequestException

        mock_session = MagicMock()
        mock_session.get.side_effect = RequestException("Network error")
        mock_session_class.return_value = mock_session

        downloader = MediaDownloader(tmp_path)

        filepath = tmp_path / "test.jpg"
        result = downloader._download_file("https://example.com/test.jpg", filepath)

        assert result is False
        assert not filepath.exists()


class TestDownloadImage:
    """Test download_image method."""

    @patch.object(MediaDownloader, "_download_file")
    def test_successful_image_download(
        self, mock_download: MagicMock, tmp_path: Path
    ) -> None:
        """Test successful image download."""
        downloader = MediaDownloader(tmp_path)
        mock_download.return_value = True

        result = downloader.download_image("https://example.com/test.jpg", "test.jpg")

        assert result is not None
        assert result.name == "test.jpg"
        mock_download.assert_called_once()

    @patch.object(MediaDownloader, "_download_file")
    def test_failed_image_download(
        self, mock_download: MagicMock, tmp_path: Path
    ) -> None:
        """Test failed image download."""
        downloader = MediaDownloader(tmp_path)
        mock_download.return_value = False

        result = downloader.download_image("https://example.com/test.jpg", "test.jpg")

        assert result is None


class TestDownloadVideo:
    """Test download_video method."""

    @patch.object(MediaDownloader, "_download_file")
    @patch.object(MediaDownloader, "_merge_video_audio")
    def test_download_video_no_media(
        self, mock_merge: MagicMock, mock_download: MagicMock, tmp_path: Path
    ) -> None:
        """Test video download with no media."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.media = None

        result = downloader.download_video(mock_post, "test")

        assert result is None

    @patch.object(MediaDownloader, "_download_file")
    @patch.object(MediaDownloader, "_merge_video_audio")
    def test_download_video_no_reddit_video(
        self, mock_merge: MagicMock, mock_download: MagicMock, tmp_path: Path
    ) -> None:
        """Test video download with no reddit_video key."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.media = {"other": "data"}

        result = downloader.download_video(mock_post, "test")

        assert result is None

    @patch.object(MediaDownloader, "_download_file")
    @patch.object(MediaDownloader, "_merge_video_audio")
    def test_download_video_only(
        self, mock_merge: MagicMock, mock_download: MagicMock, tmp_path: Path
    ) -> None:
        """Test video download without audio."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.media = {
            "reddit_video": {"fallback_url": "https://v.redd.it/abc123/DASH_720.mp4"}
        }

        def download_side_effect(url: str, path: Path) -> bool:
            if "DASH_720.mp4" in url:
                # Create the file
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("video data")
                return True
            return False

        mock_download.side_effect = download_side_effect

        result = downloader.download_video(mock_post, "test")

        assert result is not None
        assert result.name == "test.mp4"


class TestDownloadGallery:
    """Test download_gallery method."""

    @patch.object(MediaDownloader, "download_image")
    def test_download_gallery_success(
        self, mock_download_image: MagicMock, tmp_path: Path
    ) -> None:
        """Test successful gallery download."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.media_metadata = {
            "item1": {
                "status": "valid",
                "s": {"u": "https://example.com/image1.jpg"},
                "m": "image/jpeg",
            },
            "item2": {
                "status": "valid",
                "s": {"u": "https://example.com/image2.jpg"},
                "m": "image/jpeg",
            },
        }
        mock_download_image.return_value = tmp_path / "image.jpg"

        result = downloader.download_gallery(mock_post, "test")

        assert len(result) == 2
        assert mock_download_image.call_count == 2

    def test_download_gallery_no_metadata(self, tmp_path: Path) -> None:
        """Test gallery download with no metadata."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.media_metadata = None

        result = downloader.download_gallery(mock_post, "test")

        assert result == []


class TestDownloadPostMedia:
    """Test download_post_media method."""

    def test_download_post_no_media(self, tmp_path: Path) -> None:
        """Test downloading post with no media."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = True
        mock_post.author.name = "testuser"
        mock_post.id = "abc123"

        result = downloader.download_post_media(mock_post)

        assert result == []

    @patch.object(MediaDownloader, "download_image")
    def test_download_post_image(
        self, mock_download_image: MagicMock, tmp_path: Path
    ) -> None:
        """Test downloading post with image."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = False
        mock_post.is_video = False
        mock_post.is_gallery = False
        mock_post.url = "https://example.com/image.jpg"
        mock_post.author.name = "testuser"
        mock_post.id = "abc123"
        mock_post.title = "Test Post"

        mock_download_image.return_value = tmp_path / "testuser_abc123.jpg"

        result = downloader.download_post_media(mock_post)

        assert len(result) == 1
        assert result[0].success is True
        mock_download_image.assert_called_once()

    @patch.object(MediaDownloader, "download_video")
    def test_download_post_video(
        self, mock_download_video: MagicMock, tmp_path: Path
    ) -> None:
        """Test downloading post with video."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = False
        mock_post.is_video = True
        mock_post.is_gallery = False
        mock_post.url = "https://v.redd.it/abc123"
        mock_post.author.name = "testuser"
        mock_post.id = "abc123"
        mock_post.title = "Test Video"

        mock_download_video.return_value = tmp_path / "testuser_abc123.mp4"

        result = downloader.download_post_media(mock_post)

        assert len(result) == 1
        assert result[0].success is True

    @patch.object(MediaDownloader, "download_gallery")
    def test_download_post_gallery(
        self, mock_download_gallery: MagicMock, tmp_path: Path
    ) -> None:
        """Test downloading post with gallery."""
        downloader = MediaDownloader(tmp_path)
        mock_post = MagicMock()
        mock_post.is_self = False
        mock_post.is_gallery = True
        mock_post.author.name = "testuser"
        mock_post.id = "abc123"
        mock_post.title = "Test Gallery"

        mock_download_gallery.return_value = [
            tmp_path / "testuser_abc123_1.jpg",
            tmp_path / "testuser_abc123_2.jpg",
        ]

        result = downloader.download_post_media(mock_post)

        assert len(result) == 2
        assert all(r.success for r in result)
