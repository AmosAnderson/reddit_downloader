"""Tests for outbound download URL security helpers."""

import socket
from unittest.mock import patch

import pytest

from reddit_downloader.security import validate_public_download_url


class TestValidatePublicDownloadUrl:
    """Tests for validate_public_download_url."""

    @patch("reddit_downloader.security.socket.getaddrinfo")
    def test_accepts_public_http_host(self, mock_getaddrinfo: object) -> None:
        """Test public HTTP(S) hosts are accepted."""
        mock_getaddrinfo.return_value = [  # type: ignore[attr-defined]
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 443)),
        ]

        validate_public_download_url("https://example.com/image.jpg")

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/image.jpg",
            "file:///etc/passwd",
            "https:///missing-host",
        ],
    )
    def test_rejects_malformed_or_unsupported_urls(self, url: str) -> None:
        """Test unsupported schemes and malformed URLs are rejected."""
        with pytest.raises(ValueError):
            validate_public_download_url(url)

    @patch("reddit_downloader.security.socket.getaddrinfo")
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.0.1",
            "169.254.169.254",
            "::1",
            "fc00::1",
        ],
    )
    def test_rejects_non_public_addresses(self, mock_getaddrinfo: object, address: str) -> None:
        """Test private, loopback, and link-local resolved addresses are rejected."""
        family = socket.AF_INET6 if ":" in address else socket.AF_INET
        mock_getaddrinfo.return_value = [  # type: ignore[attr-defined]
            (family, socket.SOCK_STREAM, 0, "", (address, 80)),
        ]

        with pytest.raises(ValueError, match="non-public"):
            validate_public_download_url("https://example.com/image.jpg")
