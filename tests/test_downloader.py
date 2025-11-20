"""Tests for MediaDownloader helpers."""

from reddit_downloader.downloader import MediaDownloader


class TestExtractUrlExtension:
    """Tests for MediaDownloader._extract_url_extension."""

    def test_handles_query_parameters(self, tmp_path) -> None:
        downloader = MediaDownloader(tmp_path)
        url = "https://i.redd.it/example_image.PNG?width=640&crop=smart"

        assert downloader._extract_url_extension(url) == "png"

    def test_returns_default_when_missing_suffix(self, tmp_path) -> None:
        downloader = MediaDownloader(tmp_path)
        url = "https://i.redd.it/abcdefg"

        assert downloader._extract_url_extension(url, default="bin") == "bin"

    def test_normalizes_uppercase_suffix(self, tmp_path) -> None:
        downloader = MediaDownloader(tmp_path)
        url = "https://example.com/video.MP4"

        assert downloader._extract_url_extension(url) == "mp4"
