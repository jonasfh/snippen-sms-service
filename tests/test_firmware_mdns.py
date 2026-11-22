"""Unit tests for firmware/mdns_resolve.py (.local mDNS A-record resolution)."""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

import mdns_resolve


def _build_fake_mdns_response(hostname: str, ip: str) -> bytes:
    """Construct a minimal DNS response with one A record using a compression pointer."""
    header = struct.pack(">HHHHHH", 0x0000, 0x8400, 1, 1, 0, 0)
    qname = bytearray()
    for label in hostname.rstrip(".").split("."):
        encoded = label.encode("utf-8")
        qname.append(len(encoded))
        qname.extend(encoded)
    qname.append(0)
    question = bytes(qname) + struct.pack(">HH", 1, 1)

    # Answer uses compression pointer 0xC00C pointing to offset 12 (the question name)
    octets = bytes(int(x) for x in ip.split("."))
    answer = struct.pack(">HHHIH", 0xC00C, 1, 1, 120, 4) + octets
    return header + question + answer


def test_parse_mdns_a_response() -> None:
    pkt = _build_fake_mdns_response("jonas-mac.local", "192.168.1.42")
    assert mdns_resolve._parse_mdns_a_response(pkt) == "192.168.1.42"


def test_resolve_mdns_caches_result() -> None:
    mdns_resolve._cache.clear()
    pkt = _build_fake_mdns_response("jonas-mac.local", "192.168.1.42")

    mock_sock = MagicMock()
    mock_sock.recvfrom.return_value = (pkt, ("192.168.1.42", 5353))

    with patch.object(mdns_resolve.socket, "socket", return_value=mock_sock):
        ip1 = mdns_resolve.resolve_mdns("jonas-mac.local")
        ip2 = mdns_resolve.resolve_mdns("jonas-mac.local")

    assert ip1 == "192.168.1.42"
    assert ip2 == "192.168.1.42"
    assert mock_sock.sendto.call_count == 1


def test_resolve_url_host_rewrites_http_local_and_sets_host_header() -> None:
    mdns_resolve._cache.clear()
    mdns_resolve._cache["jonas-mac.local"] = ("192.168.1.42", mdns_resolve._ticks_ms() + 30000)

    headers: dict[str, str] = {"Accept": "application/json"}
    resolved = mdns_resolve.resolve_url_host(
        "http://jonas-mac.local:8081/wp-json/snippen/v1/sms/outbox?limit=10",
        headers,
    )

    assert resolved == "http://192.168.1.42:8081/wp-json/snippen/v1/sms/outbox?limit=10"
    assert headers["Host"] == "jonas-mac.local:8081"


def test_resolve_url_host_ignores_https_and_public_hosts() -> None:
    headers: dict[str, str] = {}
    https_url = "https://picobell.no/snippen-test/wp-json/snippen/v1/sms/outbox"
    assert mdns_resolve.resolve_url_host(https_url, headers) == https_url
    assert "Host" not in headers

    local_https = "https://jonas-mac.local:8443/wp-json/snippen/v1/sms/outbox"
    assert mdns_resolve.resolve_url_host(local_https, headers) == local_https
    assert "Host" not in headers
