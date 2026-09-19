"""Unit tests for firmware/snippen_api.py (Snippen REST API client for ESP32)."""

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from tests.mocks.micropython_mocks import MicroPythonEnvironment, MockResponse


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    sys.modules.pop("snippen_api", None)
    yield env
    env.uninstall()
    sys.modules.pop("snippen_api", None)


def test_build_url_and_headers(mpy_env: MicroPythonEnvironment) -> None:
    from snippen_api import SnippenApiClient

    client1 = SnippenApiClient(
        base_url="https://vestreholmensameie.no/wp-json/snippen/v1",
        api_token="test-secret-token",
    )
    assert (
        client1._build_url("outbox")
        == "https://vestreholmensameie.no/wp-json/snippen/v1/sms/outbox"
    )
    assert (
        client1._build_url("inbox") == "https://vestreholmensameie.no/wp-json/snippen/v1/sms/inbox"
    )
    assert (
        client1._build_url("outbox/status")
        == "https://vestreholmensameie.no/wp-json/snippen/v1/sms/outbox/status"
    )

    client2 = SnippenApiClient(
        base_url="https://vestreholmensameie.no/wp-json/snippen/v1/sms/",
        api_token="test-secret-token",
    )
    assert (
        client2._build_url("outbox")
        == "https://vestreholmensameie.no/wp-json/snippen/v1/sms/outbox"
    )

    headers = client1._get_headers()
    assert headers["Authorization"] == "Bearer test-secret-token"
    assert headers["X-API-Key"] == "test-secret-token"
    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/json"


def test_fetch_outbox_success(mpy_env: MicroPythonEnvironment) -> None:
    from snippen_api import SnippenApiClient

    mock_resp = MockResponse(
        status_code=200,
        json_data={
            "messages": [
                {
                    "id": 101,
                    "recipient": "+4799999999",
                    "body": "Din kode er 1234 🤖",
                    "sender": "Snippen",
                }
            ]
        },
    )
    mpy_env.mock_urequests.get_handler = lambda url, headers, **kw: mock_resp

    client = SnippenApiClient(api_token="valid-token")
    messages = client.fetch_outbox(limit=5)

    assert len(messages) == 1
    assert messages[0]["id"] == 101
    assert messages[0]["recipient"] == "+4799999999"
    assert mock_resp.closed is True
    assert client.consecutive_errors == 0


def test_fetch_outbox_auth_error(mpy_env: MicroPythonEnvironment) -> None:
    from snippen_api import SnippenApiClient

    mock_resp = MockResponse(status_code=401, text="Unauthorized")
    mpy_env.mock_urequests.get_handler = lambda url, headers, **kw: mock_resp

    client = SnippenApiClient(api_token="bad-token")
    messages = client.fetch_outbox()

    assert messages == []
    assert client.consecutive_errors == 1
    assert mock_resp.closed is True


def test_fetch_outbox_network_exception(mpy_env: MicroPythonEnvironment) -> None:
    from snippen_api import SnippenApiClient

    def fail_get(url, headers, **kw):
        raise OSError("Connection timed out")

    mpy_env.mock_urequests.get_handler = fail_get

    client = SnippenApiClient(api_token="valid-token")
    messages = client.fetch_outbox()

    assert messages == []
    assert client.consecutive_errors == 1


def test_report_outbox_status_success(mpy_env: MicroPythonEnvironment) -> None:
    from snippen_api import SnippenApiClient

    mock_resp = MockResponse(status_code=200, json_data={"success": True, "updated": 1})
    mpy_env.mock_urequests.post_handler = lambda url, headers, **kw: mock_resp

    client = SnippenApiClient(api_token="valid-token")
    statuses = [
        {
            "external_id": "101",
            "status": "sent",
            "modem_message_id": "ref-42",
        }
    ]
    ok = client.report_outbox_status(statuses)

    assert ok is True
    assert mock_resp.closed is True
    assert client.consecutive_errors == 0

    log = mpy_env.mock_urequests.requests_log
    assert len(log) == 1
    assert log[0]["method"] == "POST"
    assert "/outbox/status" in log[0]["url"]
    posted_data = json.loads(log[0]["data"])
    assert posted_data["statuses"] == statuses


def test_report_inbound_sms_success(mpy_env: MicroPythonEnvironment) -> None:
    from snippen_api import SnippenApiClient

    mock_resp = MockResponse(status_code=200, json_data={"success": True})
    mpy_env.mock_urequests.post_handler = lambda url, headers, **kw: mock_resp

    client = SnippenApiClient(api_token="valid-token")
    inbound_msgs = [
        {
            "sender": "+4799999999",
            "body": "Takk for koden! 🤖",
            "timestamp": "26/09/19,19:00:00+08",
        }
    ]
    ok = client.report_inbound_sms(inbound_msgs)

    assert ok is True
    assert mock_resp.closed is True
    assert client.consecutive_errors == 0

    log = mpy_env.mock_urequests.requests_log
    assert len(log) == 1
    assert log[0]["method"] == "POST"
    assert "/inbox" in log[0]["url"]
    posted_data = json.loads(log[0]["data"])
    assert posted_data["messages"] == inbound_msgs
