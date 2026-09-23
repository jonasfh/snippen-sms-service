"""Unit tests for firmware/boot.py hardware initialization."""

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

from tests.mocks.micropython_mocks import MicroPythonEnvironment


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    # If boot was already imported, remove it so it can be cleanly imported
    sys.modules.pop("boot", None)
    yield env
    env.uninstall()
    sys.modules.pop("boot", None)


def test_power_on_modem(mpy_env: MicroPythonEnvironment) -> None:
    import boot

    pwr, rst, pwrkey = boot.power_on_modem()

    assert pwr.pin_id == 12
    assert rst.pin_id == 5
    assert pwrkey.pin_id == 4

    # Pin values: VCC is 1 (on), Reset is 1 (inactive), PWRKEY ends at 0 (pulse finished)
    assert pwr.value() == 1
    assert rst.value() == 1
    assert pwrkey.value() == 0

    # PWRKEY value history: should have had a 1 pulse then 0
    assert 1 in pwrkey.value_history
    assert pwrkey.value_history[-1] == 0

    # Sleep history verification: 100ms pause, 1500ms pulse, 6s boot wait (7600ms total, fed in <=250ms chunks)
    sleeps = mpy_env.mock_time.sleep_history
    total_ms = sum(arg if kind == "sleep_ms" else int(arg * 1000) for kind, arg in sleeps)
    assert total_ms == 7600
    assert ("sleep_ms", 100) in sleeps
    assert ("sleep_ms", 250) in sleeps


def test_sleep_ms_feeding_wdt(mpy_env: MicroPythonEnvironment) -> None:
    import boot
    import machine

    wdt = machine.WDT()
    assert wdt.feed_count == 0

    boot.sleep_ms_feeding_wdt(1000)
    # 1000ms / 250ms = 4 chunks = 4 feeds
    assert wdt.feed_count == 4


def test_init_uart(mpy_env: MicroPythonEnvironment) -> None:
    import boot

    uart = boot.init_uart()
    assert uart.uart_id == 1
    assert uart.baudrate == 115200
    assert uart.timeout == 2000
    assert uart.tx.pin_id == 26
    assert uart.rx.pin_id == 25


def test_boot_sequence_success(mpy_env: MicroPythonEnvironment) -> None:
    import boot

    res = boot.boot()
    assert res is True
    assert boot.modem_uart is not None
    assert boot.modem_uart.baudrate == 115200


def test_boot_sequence_failure(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    import boot

    def failing_power_on(*args: object, **kwargs: object) -> None:
        raise OSError("GPIO fault")

    monkeypatch.setattr(boot, "power_on_modem", failing_power_on)

    res = boot.boot()
    assert res is False
