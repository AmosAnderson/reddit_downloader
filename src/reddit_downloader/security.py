"""Security helpers for validating outbound download URLs."""

import ipaddress
import socket
from urllib.parse import urlparse


def _is_public_ip(address: str) -> bool:
    """Return True when an IP address is safe for outbound public downloads."""

    ip = ipaddress.ip_address(address)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def validate_public_download_url(url: str) -> None:
    """Validate that a URL is safe to fetch as an outbound public download.

    Raises:
        ValueError: If the URL is malformed, uses an unsupported scheme, or resolves to a
            non-public IP address.
    """

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Download URL must use http or https")

    if not parsed.hostname:
        raise ValueError("Download URL must include a hostname")

    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        raise ValueError(f"Download URL hostname could not be resolved: {parsed.hostname}") from e

    if not addresses:
        raise ValueError(f"Download URL hostname could not be resolved: {parsed.hostname}")

    for *_, sockaddr in addresses:
        address = str(sockaddr[0])
        if not _is_public_ip(address):
            raise ValueError("Download URL resolves to a non-public IP address")
