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
