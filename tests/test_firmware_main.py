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
    sys.modules.pop("main", None)
    yield env
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

    # Simulate BLE config write callback
    app.on_ble_config_received({"wifi_ssid": "UpdatedSSID"})
    assert app.config["wifi_ssid"] == "UpdatedSSID"

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
