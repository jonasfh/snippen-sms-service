"""Unit tests for SnippenClient HTTP API communication."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from snippen_sms.client import (
    SnippenApiError,
    SnippenAuthError,
    SnippenClient,
    SnippenNetworkError,
)
from snippen_sms.models import Message, MessageDirection, MessageStatus


def _create_mock_response(status: int = 200, data: dict | list | None = None) -> MagicMock:
    """Helper to create a mock urllib response context manager."""
    mock_resp = MagicMock()
    mock_resp.status = status
    body_str = json.dumps(data) if data is not None else ""
    mock_resp.read.return_value = body_str.encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp
    return mock_resp


def test_client_init() -> None:
    """Test client initialization and default settings."""
    client = SnippenClient(
        api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms/",
        api_token="secret-token-123",
        timeout_seconds=15.0,
    )
    assert client.api_url == "https://vestreholmensameie.no/wp-json/snippen/v1/sms"
    assert client.api_token == "secret-token-123"
    assert client.timeout_seconds == 15.0


def test_fetch_pending_outbox_success() -> None:
    """Test successful fetching of pending outbound SMS messages."""
    client = SnippenClient(
        api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms",
        api_token="token-abc",
    )

    mock_data = {
        "messages": [
            {
                "id": "ext-1",
                "recipient": "+4799999999",
                "body": "Your booking is confirmed.",
                "sender": "Snippen",
            },
            {
                "id": "ext-2",
                "recipient": "+4788888888",
                "body": "Reminder: check-in at 15:00.",
            },
        ]
    }

    mock_resp = _create_mock_response(status=200, data=mock_data)

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = client.fetch_pending_outbox()

        assert len(result) == 2
        assert result[0]["id"] == "ext-1"
        assert result[0]["recipient"] == "+4799999999"

        # Verify request structure and headers
        req: urllib.request.Request = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://vestreholmensameie.no/wp-json/snippen/v1/sms/outbox"
        assert req.get_method() == "GET"
        assert req.headers["Authorization"] == "Bearer token-abc"
        assert req.headers["X-api-key"] == "token-abc"


def test_fetch_pending_outbox_raw_list() -> None:
    """Test fetching outbox when backend returns a direct JSON array."""
    client = SnippenClient(api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms")
    mock_data = [{"id": "msg-10", "recipient": "+4712345678", "body": "Test message"}]
    mock_resp = _create_mock_response(status=200, data=mock_data)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        items = client.fetch_pending_outbox()
        assert len(items) == 1
        assert items[0]["id"] == "msg-10"


def test_report_inbound_messages_success() -> None:
    """Test reporting received inbound SMS messages to Snippen."""
    client = SnippenClient(
        api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms",
        api_token="test-token",
    )

    now = datetime.now(UTC)
    messages = [
        Message(
            id=1,
            direction=MessageDirection.INBOUND,
            sender="+4790000001",
            recipient="snippen-sms-service",
            body="JA",
            status=MessageStatus.RECEIVED,
            modem_message_id="modem-101",
            created_at=now,
        ),
        Message(
            id=2,
            direction=MessageDirection.INBOUND,
            sender="+4790000002",
            recipient="snippen-sms-service",
            body="NEI",
            status=MessageStatus.RECEIVED,
            modem_message_id="modem-102",
            created_at=now,
        ),
    ]

    mock_resp = _create_mock_response(status=200, data={"processed_ids": [1, 2]})

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        acked = client.report_inbound_messages(messages)
        assert acked == [1, 2]

        req: urllib.request.Request = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://vestreholmensameie.no/wp-json/snippen/v1/sms/inbox"
        assert req.get_method() == "POST"

        payload = json.loads(req.data.decode("utf-8"))
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["gateway_id"] == 1
        assert payload["messages"][0]["sender"] == "+4790000001"
        assert payload["messages"][0]["body"] == "JA"
        assert payload["messages"][0]["modem_message_id"] == "modem-101"


def test_report_inbound_messages_empty() -> None:
    """Test reporting empty inbound list does not trigger network calls."""
    client = SnippenClient(api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms")
    with patch("urllib.request.urlopen") as mock_urlopen:
        acked = client.report_inbound_messages([])
        assert acked == []
        mock_urlopen.assert_not_called()


def test_report_outbox_status_success() -> None:
    """Test reporting outbound message delivery statuses."""
    client = SnippenClient(
        api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms",
        api_token="token-xyz",
    )

    statuses = [
        {
            "external_id": "ext-1",
            "gateway_id": 42,
            "status": "sent",
            "error_message": None,
            "modem_message_id": "modem-99",
        }
    ]

    mock_resp = _create_mock_response(status=200, data={"status": "ok"})

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        success = client.report_outbox_status(statuses)
        assert success is True

        req: urllib.request.Request = mock_urlopen.call_args[0][0]
        assert req.full_url == "https://vestreholmensameie.no/wp-json/snippen/v1/sms/outbox/status"
        assert req.get_method() == "POST"
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["statuses"] == statuses


def test_auth_error_401() -> None:
    """Test that HTTP 401 Unauthorized raises SnippenAuthError."""
    client = SnippenClient(api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms")
    http_err = urllib.error.HTTPError(
        url="https://example.com",
        code=401,
        msg="Unauthorized",
        hdrs={},
        fp=io.BytesIO(b'{"error":"invalid_token"}'),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(SnippenAuthError) as exc_info:
            client.fetch_pending_outbox()
        assert "authentication failed" in str(exc_info.value)


def test_api_error_500() -> None:
    """Test that HTTP 500 Internal Server Error raises SnippenApiError."""
    client = SnippenClient(api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms")
    http_err = urllib.error.HTTPError(
        url="https://example.com",
        code=500,
        msg="Internal Server Error",
        hdrs={},
        fp=io.BytesIO(b"Database down"),
    )

    with patch("urllib.request.urlopen", side_effect=http_err):
        with pytest.raises(SnippenApiError) as exc_info:
            client.fetch_pending_outbox()
        assert exc_info.value.status_code == 500


def test_network_error_urlerror() -> None:
    """Test that network connection issues raise SnippenNetworkError."""
    client = SnippenClient(api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("Connection refused")):
        with pytest.raises(SnippenNetworkError) as exc_info:
            client.fetch_pending_outbox()
        assert "Network failure" in str(exc_info.value)


def test_network_error_timeout() -> None:
    """Test that timeout issues raise SnippenNetworkError."""
    client = SnippenClient(api_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms")
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Timed out")):
        with pytest.raises(SnippenNetworkError) as exc_info:
            client.fetch_pending_outbox()
        assert "Timeout" in str(exc_info.value)
