"""Unit tests for firmware/main.py application loop."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from tests.mocks.micropython_mocks import MicroPythonEnvironment, MockUART


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    Path("ota_failed.json").unlink(missing_ok=True)
    Path("ota_pending.json").unlink(missing_ok=True)
    sys.modules.pop("main", None)
    yield env
    Path("ota_failed.json").unlink(missing_ok=True)
    Path("ota_pending.json").unlink(missing_ok=True)
    env.uninstall()
    sys.modules.pop("main", None)


def test_gateway_app_setup(mpy_env: MicroPythonEnvironment) -> None:
    import main

    mock_uart = MockUART(1)
    app = main.GatewayApp(uart=mock_uart)
    assert app.setup() is True
    assert app.uart is mock_uart


def test_gateway_app_ticks(mpy_env: MicroPythonEnvironment) -> None:
    import main

    inbox_calls = 0
    outbox_calls = 0
    heartbeat_calls = 0

    class TestApp(main.GatewayApp):
        def process_inbox(self) -> int:
            nonlocal inbox_calls
            inbox_calls += 1
            return 0

        def poll_outbox(self) -> int:
            nonlocal outbox_calls
            outbox_calls += 1
            return 0

        def heartbeat(self) -> None:
            nonlocal heartbeat_calls
            heartbeat_calls += 1

    app = TestApp(
        config={
            "inbox_check_interval_sec": 1,
            "outbox_poll_interval_sec": 1,
            "heartbeat_interval_sec": 1,
        }
    )

    # Initial tick
    app.tick()
    assert inbox_calls == 1
    assert outbox_calls == 1
    assert heartbeat_calls == 1
    assert app.cycle_count == 1


def test_gateway_app_run_bounded(mpy_env: MicroPythonEnvironment) -> None:
    import main

    app = main.GatewayApp()
    app.run(max_cycles=3)
    assert app.cycle_count == 3
    assert app.running is False


def test_gateway_app_stop(mpy_env: MicroPythonEnvironment) -> None:
    import main

    app = main.GatewayApp()
    app.running = True
    app.stop()
    assert app.running is False


def test_gateway_app_process_inbox_with_modem(mpy_env: MicroPythonEnvironment) -> None:
    import main

    mock_uart = MockUART(1)
    mock_uart.auto_responses = {
        "AT+CMGF=1": b"OK\r\n",
        'AT+CSCS="GSM"': b"OK\r\n",
        'AT+CMGL="ALL"': (
            b'+CMGL: 1,"REC UNREAD","+4799999999",,"26/09/19,17:05:00+08"\r\n'
            b"Hei fra test!\r\nOK\r\n"
        ),
        "AT+CMGD=1": b"OK\r\n",
        "AT+CSQ": b"+CSQ: 20,0\r\nOK\r\n",
        "AT+CREG?": b"+CREG: 0,1\r\nOK\r\n",
    }

    app = main.GatewayApp(uart=mock_uart)
    app.setup()
    assert app.modem is not None

    count = app.process_inbox()
    assert count == 1

    # Heartbeat check
    app.heartbeat()


def test_gateway_app_auto_enters_provisioning_when_unconfigured(
    mpy_env: MicroPythonEnvironment,
) -> None:
    import main

    # Missing wifi_ssid and token
    app = main.GatewayApp(config={"wifi_ssid": "", "snippen_api_token": ""})
    assert app.setup() is True
    assert app.is_provisioning_mode is True


def test_gateway_app_configured_starts_in_normal_mode(
    mpy_env: MicroPythonEnvironment,
) -> None:
    import main

    app = main.GatewayApp(config={"wifi_ssid": "SnippenGuest", "snippen_api_token": "secret-tok"})
    assert app.setup() is True
    assert app.is_provisioning_mode is False


def test_gateway_app_enters_provisioning_when_button_held_at_boot(
    mpy_env: MicroPythonEnvironment,
) -> None:
    import button
    import main

    from tests.mocks.micropython_mocks import MockPin

    mock_pin = MockPin(pin_id=0, value=0)  # Pin 0 is held down (LOW)
    btn = button.ButtonHandler(pin=mock_pin, active_low=True)

    app = main.GatewayApp(
        config={"wifi_ssid": "SnippenGuest", "snippen_api_token": "secret-tok"},
        button=btn,
    )
    assert app.setup() is True
    assert app.is_provisioning_mode is True


def test_gateway_app_button_press_toggles_provisioning(
    mpy_env: MicroPythonEnvironment,
) -> None:
    import main

    app = main.GatewayApp(config={"wifi_ssid": "SnippenGuest", "snippen_api_token": "secret-tok"})
    app.setup()
    assert app.is_provisioning_mode is False

    # First short press activates provisioning mode (Issue #83)
    app.on_boot_button_press()
    assert app.is_provisioning_mode is True

    # Second press deactivates provisioning mode
    app.on_boot_button_press()
    assert app.is_provisioning_mode is False


def test_gateway_app_button_long_press_backward_compat(
    mpy_env: MicroPythonEnvironment,
) -> None:
    import main

    app = main.GatewayApp(config={"wifi_ssid": "SnippenGuest", "snippen_api_token": "secret-tok"})
    app.setup()
    assert app.is_provisioning_mode is False

    # on_boot_long_press alias still activates and toggles
    app.on_boot_long_press()
    assert app.is_provisioning_mode is True

    app.on_boot_long_press()
    assert app.is_provisioning_mode is False


def test_gateway_app_provisioning_timeout(mpy_env: MicroPythonEnvironment) -> None:
    import main

    app = main.GatewayApp(
        config={
            "wifi_ssid": "SnippenGuest",
            "snippen_api_token": "secret-tok",
            "provisioning_timeout_sec": 300,
        }
    )
    app.setup()
    app.enter_provisioning_mode()
    assert app.is_provisioning_mode is True

    # Fast-forward time past 300 seconds
    mpy_env.mock_time.sleep(301)
    app.tick()
    assert app.is_provisioning_mode is False


def test_gateway_app_suspends_polling_during_provisioning(
    mpy_env: MicroPythonEnvironment,
) -> None:
    import main

    inbox_polled = False
    outbox_polled = False

    class TestApp(main.GatewayApp):
        def process_inbox(self) -> int:
            nonlocal inbox_polled
            inbox_polled = True
            return 0

        def poll_outbox(self) -> int:
            nonlocal outbox_polled
            outbox_polled = True
            return 0

    app = TestApp(
        config={
            "wifi_ssid": "SnippenGuest",
            "snippen_api_token": "secret-tok",
            "inbox_check_interval_sec": 1,
            "outbox_poll_interval_sec": 1,
            "provisioning_timeout_sec": 300,
        }
    )
    app.setup()
    app.enter_provisioning_mode()

    # Tick during provisioning mode
    app.tick()
    assert inbox_polled is False
    assert outbox_polled is False

    # Exit provisioning mode and tick again
    app.exit_provisioning_mode()
    app.tick()
    assert inbox_polled is True
    assert outbox_polled is True


def test_gateway_app_ble_server_lifecycle_and_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mpy_env: MicroPythonEnvironment,
) -> None:
    import main

    monkeypatch.chdir(tmp_path)
    app = main.GatewayApp(config={"wifi_ssid": "OldSSID", "snippen_api_token": "old_token"})
    app.setup()
    assert app.ble_server is not None
    assert app.ble_server.is_running is False

    # Enter provisioning mode -> BLE server starts
    app.enter_provisioning_mode()
    assert app.ble_server.is_running is True

    # Simulate BLE config write callback with empty token (should retain existing)
    app.config["snippen_api_token"] = "keep_this_token"
    app.on_ble_config_received({"wifi_ssid": "UpdatedSSID", "snippen_api_token": ""})
    assert app.config["wifi_ssid"] == "UpdatedSSID"
    assert app.config["snippen_api_token"] == "keep_this_token"

    # Simulate BLE config write with new non-empty token
    app.on_ble_config_received({"snippen_api_token": "new_token_456"})
    assert app.config["snippen_api_token"] == "new_token_456"

    # Simulate BLE command APPLY_AND_EXIT
    res = app.on_ble_command("APPLY_AND_EXIT", {})
    assert res["status"] == "ok"
    assert app.is_provisioning_mode is False
    assert app.ble_server.is_running is False


def test_gateway_app_handle_incoming_call(mpy_env: MicroPythonEnvironment) -> None:
    import main

    sent_messages: list[tuple[str, str]] = []

    class MockModem:
        def send_sms(self, recipient: str, text: str) -> tuple[bool, str]:
            sent_messages.append((recipient, text))
            return True, "1"

    app = main.GatewayApp(
        config={
            "call_notify_admin_enabled": True,
            "call_forwarding_number": "+4792830575",
            "call_reply_caller_enabled": True,
            "call_reply_caller_text": "Autosvar til {caller}.",
            "call_notify_admin_text": "Ubesvart anrop fra {caller}.",
        }
    )
    app.modem = MockModem()  # type: ignore[assignment]

    # First call: triggers admin notification and caller reply
    app.handle_incoming_call("+4790000000")
    assert len(sent_messages) == 2
    assert sent_messages[0][0] == "+4792830575"
    assert "fra +4790000000" in sent_messages[0][1]
    assert sent_messages[1][0] == "+4790000000"

    # Immediate second call from same caller: should be debounced
    sent_messages.clear()
    app.handle_incoming_call("+4790000000")
    assert len(sent_messages) == 0


def test_gateway_app_poll_incoming_calls_integrated(mpy_env: MicroPythonEnvironment) -> None:
    import main

    calls_handled: list[str] = []

    class MockModem:
        def check_incoming_call(self) -> str | None:
            return "+4791111111"

    app = main.GatewayApp()
    app.modem = MockModem()  # type: ignore[assignment]
    app.handle_incoming_call = lambda caller: calls_handled.append(caller)  # type: ignore[assignment]

    app.poll_incoming_calls()
    assert calls_handled == ["+4791111111"]


def test_gateway_app_poll_incoming_sms_integrated(mpy_env: MicroPythonEnvironment) -> None:
    import main

    inbox_processed = 0

    class MockModem:
        def __init__(self) -> None:
            self._has_sms = True

        def check_incoming_sms(self) -> bool:
            if self._has_sms:
                self._has_sms = False
                return True
            return False

    app = main.GatewayApp()
    app.modem = MockModem()  # type: ignore[assignment]

    def mock_process_inbox() -> int:
        nonlocal inbox_processed
        inbox_processed += 1
        return 1

    app.process_inbox = mock_process_inbox  # type: ignore[assignment]

    app.poll_incoming_sms()
    assert inbox_processed == 1

    # Second call should not trigger process_inbox since no new indication
    app.poll_incoming_sms()
    assert inbox_processed == 1


def test_boot_ota_trigger_when_enabled(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify boot OTA update is triggered on Wi-Fi connect when ota_check_on_boot is True (Issue #130)."""
    import main
    import wifi

    app = main.GatewayApp(
        config={
            "wifi_ssid": "TestSSID",
            "snippen_api_token": "valid_token",
            "ota_check_on_boot": True,
        }
    )
    app.setup()

    # Simulate Wi-Fi connected
    monkeypatch.setattr(wifi, "is_connected", lambda: True)

    check_calls: list[str] = []
    perform_calls: list[bool] = []

    class FakeOTAClient:
        def __init__(self, config: dict | None = None) -> None:
            pass

        def check_for_update(self, url: str | None = None, force: bool = False) -> dict:
            check_calls.append("checked")
            return {"update_available": True, "version": "0.32.0", "message": "New version"}

        def perform_ota(
            self, url: str | None = None, force: bool = False, restart: bool = True
        ) -> bool:
            perform_calls.append(restart)
            return True

    import ota

    monkeypatch.setattr(ota, "OTAClient", FakeOTAClient)

    # First tick with Wi-Fi connected triggers boot OTA check
    app.tick()
    assert len(check_calls) == 1
    assert len(perform_calls) == 1
    assert app.boot_ota_checked is True

    # Subsequent tick does not re-trigger boot OTA check
    app.tick()
    assert len(check_calls) == 1


def test_boot_ota_trigger_disabled_when_false(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify boot OTA update check is skipped when ota_check_on_boot is False (Issue #130)."""
    import main
    import wifi

    app = main.GatewayApp(
        config={
            "wifi_ssid": "TestSSID",
            "snippen_api_token": "valid_token",
            "ota_check_on_boot": False,
        }
    )
    app.setup()

    monkeypatch.setattr(wifi, "is_connected", lambda: True)

    check_called = False

    class FakeOTAClient:
        def __init__(self, config: dict | None = None) -> None:
            pass

        def check_for_update(self, url: str | None = None, force: bool = False) -> dict:
            nonlocal check_called
            check_called = True
            return {"update_available": True, "version": "0.32.0"}

    import ota

    monkeypatch.setattr(ota, "OTAClient", FakeOTAClient)

    app.tick()
    assert check_called is False
    assert app.boot_ota_checked is True


def test_boot_ota_retry_guard_prevents_infinite_loop(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify retry guard prevents auto-updating to a version that previously failed and rolled back (Issue #130)."""
    import ota

    # Simulate that v0.32.0 previously failed and was recorded
    ota.record_failed_version("0.32.0", reason="boot_rollback")
    assert ota.get_failed_version() == "0.32.0"

    # Bundle validation without force should fail
    sample_bundle = {
        "version": "0.32.0",
        "files": {
            "main.py": {
                "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "size": 0,
                "content": "",
            }
        },
    }
    valid, msg = ota.validate_bundle(sample_bundle, current_version="0.31.21", force=False)
    assert valid is False
    assert "boot-loop guard" in msg

    # Bundle validation with force=True should bypass guard
    valid_forced, _ = ota.validate_bundle(sample_bundle, current_version="0.31.21", force=True)
    assert valid_forced is True

    # Confirm healthy clears failed record
    ota.clear_failed_version()
    assert ota.get_failed_version() is None


def test_poll_outbox_reports_status_immediately_per_message(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify each outbound message status is reported immediately after sending (Issue #137)."""
    import main
    import wifi

    monkeypatch.setattr(wifi, "is_connected", lambda: True)

    app = main.GatewayApp(
        config={
            "wifi_ssid": "TestSSID",
            "snippen_api_token": "valid_token",
            "outbox_batch_limit": 5,
        }
    )

    reported_statuses: list[list[dict]] = []

    class MockApiClient:
        def fetch_outbox(self, limit: int = 5) -> list[dict]:
            return [
                {"id": 101, "recipient": "+4791111111", "body": "Melding 1"},
                {"id": 102, "recipient": "+4792222222", "body": "Melding 2"},
                {"id": 103, "recipient": "+4793333333", "body": "Melding 3"},
            ]

        def report_outbox_status(self, statuses: list[dict]) -> bool:
            reported_statuses.append(statuses)
            return True

    send_sms_calls: list[tuple[str, str]] = []

    class MockModem:
        def send_sms(self, recipient: str, body: str) -> tuple[bool, str]:
            send_sms_calls.append((recipient, body))
            if recipient == "+4792222222":
                return False, "NO CARRIER"
            return True, f"REF_{len(send_sms_calls)}"

    app.api_client = MockApiClient()
    app.modem = MockModem()

    processed_count = app.poll_outbox()

    assert processed_count == 3
    assert len(send_sms_calls) == 3

    # Must be reported immediately after each SMS (3 calls, each with exactly 1 status)
    assert len(reported_statuses) == 3

    # Message 1 delivered successfully
    assert reported_statuses[0] == [
        {"external_id": "101", "status": "sent", "modem_message_id": "REF_1"}
    ]

    # Message 2 transmission failed
    assert reported_statuses[1] == [
        {"external_id": "102", "status": "failed", "error_message": "NO CARRIER"}
    ]

    # Message 3 delivered successfully
    assert reported_statuses[2] == [
        {"external_id": "103", "status": "sent", "modem_message_id": "REF_3"}
    ]


def test_poll_outbox_resilient_when_reporting_fails(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify loop continues even if reporting a single status raises an exception (Issue #137)."""
    import main
    import wifi

    monkeypatch.setattr(wifi, "is_connected", lambda: True)

    app = main.GatewayApp(config={"wifi_ssid": "TestSSID", "snippen_api_token": "valid_token"})

    reported_statuses: list[list[dict]] = []

    class MockApiClient:
        def fetch_outbox(self, limit: int = 5) -> list[dict]:
            return [
                {"id": 201, "recipient": "+4791111111", "body": "Test 1"},
                {"id": 202, "recipient": "+4792222222", "body": "Test 2"},
            ]

        def report_outbox_status(self, statuses: list[dict]) -> bool:
            if statuses[0]["external_id"] == "201":
                raise RuntimeError("Network glitch")
            reported_statuses.append(statuses)
            return True

    class MockModem:
        def send_sms(self, recipient: str, body: str) -> tuple[bool, str]:
            return True, "OK"

    app.api_client = MockApiClient()
    app.modem = MockModem()

    processed_count = app.poll_outbox()
    assert processed_count == 2
    assert len(reported_statuses) == 1
    assert reported_statuses[0][0]["external_id"] == "202"


def test_poll_outbox_deduplication_cache(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that previously sent messages are deduplicated and not re-sent via modem (Issue #32)."""
    import main
    import wifi

    monkeypatch.setattr(wifi, "is_connected", lambda: True)

    app = main.GatewayApp(config={"wifi_ssid": "TestSSID", "snippen_api_token": "valid_token"})

    # Pre-seed recent_sent_ids with message ID 301 (sent in previous run/poll)
    app.recent_sent_ids.append("301")

    reported_statuses: list[list[dict]] = []

    class MockApiClient:
        def fetch_outbox(self, limit: int = 5) -> list[dict]:
            return [
                {"id": 301, "recipient": "+4791111111", "body": "Already sent"},
                {"id": 302, "recipient": "+4792222222", "body": "New message"},
            ]

        def report_outbox_status(self, statuses: list[dict]) -> bool:
            reported_statuses.append(statuses)
            return True

    modem_calls: list[tuple[str, str]] = []

    class MockModem:
        def send_sms(self, recipient: str, body: str) -> tuple[bool, str]:
            modem_calls.append((recipient, body))
            return True, "REF_302"

    app.api_client = MockApiClient()
    app.modem = MockModem()

    processed_count = app.poll_outbox()

    # Only 302 is newly processed by modem; 301 was deduplicated
    assert processed_count == 1
    assert len(modem_calls) == 1
    assert modem_calls[0] == ("+4792222222", "New message")

    # Both messages must have reported status back to Snippen Booking
    # (301 re-reported with DEDUP_CACHE, 302 reported with REF_302)
    assert len(reported_statuses) == 2
    assert reported_statuses[0] == [
        {"external_id": "301", "status": "sent", "modem_message_id": "DEDUP_CACHE"}
    ]
    assert reported_statuses[1] == [
        {"external_id": "302", "status": "sent", "modem_message_id": "REF_302"}
    ]
    assert "302" in app.recent_sent_ids


def test_poll_outbox_rate_limiter_suspends_sending(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify rate limiter circuit breaker halts outbox transmission without dropping messages (Issue #31)."""
    import main
    import wifi

    monkeypatch.setattr(wifi, "is_connected", lambda: True)

    app = main.GatewayApp(
        config={
            "wifi_ssid": "TestSSID",
            "snippen_api_token": "valid_token",
            "rate_limit_burst_max": 2,
            "rate_limit_burst_window_sec": 60,
        }
    )

    reported_statuses: list[list[dict]] = []

    class MockApiClient:
        def fetch_outbox(self, limit: int = 5) -> list[dict]:
            return [
                {"id": 401, "recipient": "+4791111111", "body": "Msg 1"},
                {"id": 402, "recipient": "+4792222222", "body": "Msg 2"},
                {"id": 403, "recipient": "+4793333333", "body": "Msg 3 (should be suspended)"},
            ]

        def report_outbox_status(self, statuses: list[dict]) -> bool:
            reported_statuses.append(statuses)
            return True

    modem_calls: list[tuple[str, str]] = []

    class MockModem:
        def send_sms(self, recipient: str, body: str) -> tuple[bool, str]:
            modem_calls.append((recipient, body))
            return True, f"REF_{len(modem_calls)}"

    app.api_client = MockApiClient()
    app.modem = MockModem()

    processed_count = app.poll_outbox()

    # Exactly 2 messages processed before burst limit suspended further sends
    assert processed_count == 2
    assert len(modem_calls) == 2
    assert len(reported_statuses) == 2
    assert app.rate_limiter.is_circuit_open is True


def test_incoming_call_rate_limiter(
    mpy_env: MicroPythonEnvironment,
) -> None:
    """Verify incoming call SMS alert and reply respect the rate limiter (Issue #31)."""
    import main

    app = main.GatewayApp(
        config={
            "call_notify_admin_enabled": True,
            "call_reply_caller_enabled": True,
            "call_forwarding_number": "+4792830575",
            "rate_limit_burst_max": 1,
            "rate_limit_burst_window_sec": 60,
        }
    )

    sent_sms: list[str] = []

    class MockModem:
        def send_sms(self, recipient: str, text: str) -> tuple[bool, str]:
            sent_sms.append(recipient)
            return True, "OK"

    app.modem = MockModem()

    # Pre-trip rate limiter
    app.rate_limiter.circuit_open_until = 9999999999.0
    app.rate_limiter.last_trip_reason = "Manual test trip"

    app.handle_incoming_call("+4799887766")

    # Because circuit is open, no SMS alerts are sent
    assert len(sent_sms) == 0


def test_ble_command_reset_rate_limiter(
    mpy_env: MicroPythonEnvironment,
) -> None:
    """Verify RESET_RATE_LIMITER command resets circuit breaker over BLE (Issue #31)."""
    import main

    app = main.GatewayApp()
    app.rate_limiter.circuit_open_until = 9999999999.0
    app.rate_limiter.last_trip_reason = "Test trip"
    assert app.rate_limiter.is_circuit_open is True

    res = app.on_ble_command("RESET_RATE_LIMITER")
    assert res["status"] == "ok"
    assert app.rate_limiter.is_circuit_open is False


def test_telemetry_reports_rate_limiter_status(
    mpy_env: MicroPythonEnvironment,
) -> None:
    """Verify get_telemetry_status includes rate limiter information (Issue #31)."""
    import main

    app = main.GatewayApp()
    telemetry = app.get_telemetry_status()

    assert "rate_limiter" in telemetry
    assert telemetry["rate_limiter"]["circuit_open"] is False
    assert telemetry["rate_limiter"]["history_count"] == 0
