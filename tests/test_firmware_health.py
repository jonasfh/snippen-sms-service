"""Unit tests for firmware/main.py system health, watchdog, WiFi recovery, and REST sync."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from tests.mocks.micropython_mocks import MicroPythonEnvironment, MockResponse, MockUART


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    sys.modules.pop("main", None)
    sys.modules.pop("snippen_api", None)
    sys.modules.pop("modem", None)
    sys.modules.pop("boot", None)
    yield env
    env.uninstall()
    sys.modules.pop("main", None)
    sys.modules.pop("snippen_api", None)
    sys.modules.pop("modem", None)
    sys.modules.pop("boot", None)


def test_watchdog_initialization_and_feeding(mpy_env: MicroPythonEnvironment) -> None:
    import main

    app = main.GatewayApp(
        config={
            "wifi_ssid": "SnippenGuest",
            "snippen_api_token": "secret-token",
            "enable_watchdog": True,
            "watchdog_timeout_ms": 30000,
        }
    )
    assert app.setup() is True
    assert app.wdt is not None
    assert app.wdt.feed_count == 0

    # Each tick must feed the watchdog
    app.tick()
    assert app.wdt.feed_count == 1
    app.tick()
    assert app.wdt.feed_count == 2


def test_watchdog_feeds_during_provisioning_mode(mpy_env: MicroPythonEnvironment) -> None:
    import main

    app = main.GatewayApp(
        config={
            "wifi_ssid": "SnippenGuest",
            "snippen_api_token": "secret-token",
            "enable_watchdog": True,
        }
    )
    app.setup()
    app.enter_provisioning_mode()
    assert app.is_provisioning_mode is True

    # Watchdog must still be fed while in provisioning mode
    app.tick()
    assert app.wdt.feed_count == 1


def test_inbound_sms_forwarding_to_snippen_booking(mpy_env: MicroPythonEnvironment) -> None:
    import main
    import wifi

    uart = MockUART(1)
    uart.auto_responses = {
        "AT+CMGF=1": b"OK\r\n",
        'AT+CSCS="GSM"': b"OK\r\n",
        'AT+CMGL="ALL"': (
            b'+CMGL: 1,"REC UNREAD","+4799999999",,"26/09/19,17:05:00+08"\r\n'
            b"Hei, vi ankommer kl 18:00\r\nOK\r\n"
        ),
        "AT+CMGD=1": b"OK\r\n",
    }

    # Connect WiFi mock
    wifi.connect_wifi("SnippenGuest", "pwd")

    posted_messages = []

    def mock_post(url, headers, data=None, **kw):
        import json

        payload = json.loads(data)
        posted_messages.extend(payload.get("messages", []))
        return MockResponse(200, json_data={"success": True})

    mpy_env.mock_urequests.post_handler = mock_post

    app = main.GatewayApp(
        uart=uart,
        config={
            "wifi_ssid": "SnippenGuest",
            "snippen_api_token": "valid-token",
            "enable_watchdog": False,
        },
    )
    app.setup()

    count = app.process_inbox()
    assert count == 1
    assert len(posted_messages) == 1
    assert posted_messages[0]["sender"] == "+4799999999"
    assert posted_messages[0]["body"] == "Hei, vi ankommer kl 18:00"


def test_outbox_polling_dispatch_and_status_reporting(mpy_env: MicroPythonEnvironment) -> None:
    import main
    import wifi

    # Outbound SMS from Snippen Booking
    mpy_env.mock_urequests.get_handler = lambda url, headers, **kw: MockResponse(
        status_code=200,
        json_data={
            "messages": [
                {
                    "id": 105,
                    "recipient": "+4791234567",
                    "body": "Din adgangskode til Snippen er 4321 🤖",
                    "sender": "Snippen",
                }
            ]
        },
    )

    reported_statuses = []

    def mock_post(url, headers, data=None, **kw):
        import json

        payload = json.loads(data)
        reported_statuses.extend(payload.get("statuses", []))
        return MockResponse(200, json_data={"success": True, "updated": 1})

    mpy_env.mock_urequests.post_handler = mock_post

    uart = MockUART(1)

    def modem_responder(data: bytes) -> bytes | None:
        if b"AT+CMGS=" in data:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            return b"\r\n+CMGS: 88\r\n\r\nOK\r\n"
        return b"OK\r\n"

    uart.responder = modem_responder

    # Ensure WiFi is connected
    wifi.connect_wifi("SnippenGuest", "pwd")

    app = main.GatewayApp(
        uart=uart,
        config={
            "wifi_ssid": "SnippenGuest",
            "snippen_api_token": "secret-token",
            "enable_watchdog": False,
        },
    )
    app.setup()

    count = app.poll_outbox()
    assert count == 1
    assert len(reported_statuses) == 1
    assert reported_statuses[0]["external_id"] == "105"
    assert reported_statuses[0]["status"] == "sent"
    assert reported_statuses[0]["modem_message_id"] == "88"


def test_modem_recovery_on_consecutive_heartbeat_failures(
    mpy_env: MicroPythonEnvironment,
) -> None:
    import boot
    import main

    power_cycled = False

    def mock_power_cycle(cfg=None):
        nonlocal power_cycled
        power_cycled = True
        new_uart = MockUART(1)
        new_uart.auto_responses = {
            "AT": b"OK\r\n",
            "ATE0": b"OK\r\n",
            "AT+CMGF=1": b"OK\r\n",
            'AT+CSCS="GSM"': b"OK\r\n",
        }
        return new_uart

    boot.power_cycle_modem = mock_power_cycle

    # Mock UART that fails AT commands
    stalled_uart = MockUART(1)
    stalled_uart.auto_responses = {}  # No responses, times out

    app = main.GatewayApp(
        uart=stalled_uart,
        config={
            "wifi_ssid": "SnippenGuest",
            "snippen_api_token": "tok",
            "enable_watchdog": False,
        },
    )
    app.setup()

    # Heartbeat 1: failure 1
    app.heartbeat()
    assert app.consecutive_modem_failures == 1
    assert power_cycled is False

    # Heartbeat 2: failure 2
    app.heartbeat()
    assert app.consecutive_modem_failures == 2
    assert power_cycled is False

    # Heartbeat 3: failure 3 -> triggers power-cycle recovery!
    app.heartbeat()
    assert power_cycled is True
    assert app.consecutive_modem_failures == 0


def test_free_heap_telemetry_reporting(mpy_env: MicroPythonEnvironment) -> None:
    import main

    app = main.GatewayApp(
        config={"wifi_ssid": "SnippenGuest", "snippen_api_token": "tok", "enable_watchdog": False}
    )
    app.setup()
    status = app.get_telemetry_status()

    # Telemetry includes basic keys
    assert status["status"] == "running"
    assert status["wifi_ssid"] == "SnippenGuest"
    assert "cycle_count" in status
