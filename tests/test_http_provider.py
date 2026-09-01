"""Unit tests for HttpSmsProvider."""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from snippen_sms.providers.base import IncomingMessage, SendResult
from snippen_sms.providers.http import HttpSmsProvider


class MockHttpHandler(BaseHTTPRequestHandler):
    """Mock HTTP handler simulating remote SMS HTTP provider."""

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        content_len = int(self.headers.get("Content-Length", 0))
        post_body = self.rfile.read(content_len).decode("utf-8")
        payload = json.loads(post_body) if post_body else {}

        if parsed.path == "/messages/outbound":
            if payload.get("to") == "+4700000000_FAIL":
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Simulated provider internal error"}')
                return
            elif payload.get("to") == "+4700000000_BAD":
                self.send_response(400)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Invalid recipient phone number"}')
                return

            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response_obj = {
                "id": "prov-msg-12345",
                "direction": "outbound",
                "to": payload.get("to"),
                "from": payload.get("from", "Snippen"),
                "text": payload.get("text"),
                "status": "sent",
                "createdAt": "2026-09-01T12:00:00Z",
            }
            self.wfile.write(json.dumps(response_obj).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        if parsed.path == "/messages" and qs.get("direction") == ["inbound"]:
            if self.headers.get("X-Trigger-Error") == "500":
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"error": "Internal server error"}')
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response_obj = {
                "messages": [
                    {
                        "id": "inbound-msg-1",
                        "direction": "inbound",
                        "from": "+4799887766",
                        "to": "Snippen",
                        "text": "Hei, adgangskode mottatt",
                        "status": "received",
                        "createdAt": "2026-09-01T12:30:00Z",
                    },
                    {
                        "id": "inbound-msg-2",
                        "direction": "inbound",
                        "from": "+4711223344",
                        "to": "Snippen",
                        "text": "Takk!",
                        "status": "received",
                        "createdAt": "2026-09-01T12:35:00Z",
                    },
                ],
                "count": 2,
            }
            self.wfile.write(json.dumps(response_obj).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        """Suppress stdout log messages during test run."""


@pytest.fixture
def mock_server():
    """Start local mock HTTP server for testing HttpSmsProvider."""
    server = HTTPServer(("127.0.0.1", 0), MockHttpHandler)
    port = server.server_port
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{port}"
    yield base_url
    server.shutdown()
    server.server_close()


def test_http_provider_send_sms_success(mock_server: str):
    async def _test():
        provider = HttpSmsProvider(base_url=mock_server, timeout_seconds=3.0)
        await provider.open()

        result: SendResult = await provider.send_sms(
            recipient="+4799887766",
            body="Adgangskode: 1234",
        )

        assert result.success is True
        assert result.message_id == "prov-msg-12345"
        assert result.error_message is None

        await provider.close()

    asyncio.run(_test())


def test_http_provider_send_sms_bad_request(mock_server: str):
    async def _test():
        provider = HttpSmsProvider(base_url=mock_server, timeout_seconds=3.0)
        await provider.open()

        result: SendResult = await provider.send_sms(
            recipient="+4700000000_BAD",
            body="Invalid recipient test",
        )

        assert result.success is False
        assert result.message_id is None
        assert "HTTP 400" in (result.error_message or "")

        await provider.close()

    asyncio.run(_test())


def test_http_provider_send_sms_server_error(mock_server: str):
    async def _test():
        provider = HttpSmsProvider(base_url=mock_server, timeout_seconds=3.0)
        await provider.open()

        result: SendResult = await provider.send_sms(
            recipient="+4700000000_FAIL",
            body="Internal error test",
        )

        assert result.success is False
        assert result.message_id is None
        assert "HTTP 500" in (result.error_message or "")

        await provider.close()

    asyncio.run(_test())


def test_http_provider_send_sms_connection_refused():
    async def _test():
        # Use unused port where no server is running
        provider = HttpSmsProvider(base_url="http://127.0.0.1:59999", timeout_seconds=1.0)
        result = await provider.send_sms(recipient="+4799887766", body="Test")

        assert result.success is False
        assert result.message_id is None
        assert result.error_message is not None

    asyncio.run(_test())


def test_http_provider_receive_sms_success(mock_server: str):
    async def _test():
        provider = HttpSmsProvider(base_url=mock_server, timeout_seconds=3.0)
        await provider.open()

        messages: list[IncomingMessage] = await provider.receive_sms()

        assert len(messages) == 2
        assert messages[0].sender == "+4799887766"
        assert messages[0].body == "Hei, adgangskode mottatt"
        assert messages[0].provider_message_id == "inbound-msg-1"
        assert messages[1].sender == "+4711223344"
        assert messages[1].body == "Takk!"
        assert messages[1].provider_message_id == "inbound-msg-2"

        await provider.close()

    asyncio.run(_test())


def test_http_provider_receive_sms_connection_failure():
    async def _test():
        provider = HttpSmsProvider(base_url="http://127.0.0.1:59999", timeout_seconds=1.0)
        messages = await provider.receive_sms()
        assert messages == []

    asyncio.run(_test())
