"""Unit tests for firmware/button.py MicroPython button handler."""

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

from tests.mocks.micropython_mocks import MicroPythonEnvironment, MockPin


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    sys.modules.pop("button", None)
    yield env
    env.uninstall()
    sys.modules.pop("button", None)


def test_button_init_default(mpy_env: MicroPythonEnvironment) -> None:
    import button

    handler = button.ButtonHandler(pin_id=0, long_press_ms=3000, debounce_ms=50)
    assert handler.pin_id == 0
    assert handler.long_press_ms == 3000
    assert handler.debounce_ms == 50
    assert handler.active_low is True
    assert handler.pin is not None
    assert isinstance(handler.pin, MockPin)
    assert handler.pin.pull == MockPin.PULL_UP


def test_button_is_down(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)  # Released (pull-up)
    handler = button.ButtonHandler(pin=mock_pin, active_low=True)

    assert handler.is_down() is False

    mock_pin.value(0)  # Pressed down
    assert handler.is_down() is True

    # Active high test
    handler_ah = button.ButtonHandler(pin=mock_pin, active_low=False)
    assert handler_ah.is_down() is False
    mock_pin.value(1)
    assert handler_ah.is_down() is True


def test_button_debounce_ignores_glitches(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    short_calls = 0
    long_calls = 0

    handler = button.ButtonHandler(
        pin=mock_pin,
        long_press_ms=1000,
        debounce_ms=50,
        on_short_press=lambda: None,
        on_long_press=lambda: None,
    )

    # Initial state
    assert handler.poll(now_ms=1000) is None

    # Glitch: pin goes LOW for only 20 ms
    mock_pin.value(0)
    assert handler.poll(now_ms=1020) is None

    # Pin bounces back to HIGH before debounce_ms
    mock_pin.value(1)
    assert handler.poll(now_ms=1030) is None
    assert handler.poll(now_ms=1100) is None

    assert short_calls == 0
    assert long_calls == 0


def test_button_short_press(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    short_pressed = False

    def on_short() -> None:
        nonlocal short_pressed
        short_pressed = True

    handler = button.ButtonHandler(
        pin=mock_pin,
        long_press_ms=1000,
        debounce_ms=50,
        on_short_press=on_short,
    )

    # Start at t=1000, button released
    handler.poll(now_ms=1000)

    # Button pressed down at t=1010
    mock_pin.value(0)
    handler.poll(now_ms=1010)

    # Debounce period passes at t=1070
    handler.poll(now_ms=1070)
    assert handler._is_pressed is True

    # Button released at t=1200 (held for 130ms, less than long_press 1000ms)
    mock_pin.value(1)
    handler.poll(now_ms=1200)

    # Debounce release period passes at t=1260
    evt = handler.poll(now_ms=1260)
    assert evt == "short_press"
    assert short_pressed is True


def test_button_long_press_detection(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    long_pressed = False
    short_pressed = False

    def on_long() -> None:
        nonlocal long_pressed
        long_pressed = True

    def on_short() -> None:
        nonlocal short_pressed
        short_pressed = True

    handler = button.ButtonHandler(
        pin=mock_pin,
        long_press_ms=3000,
        debounce_ms=50,
        on_long_press=on_long,
        on_short_press=on_short,
    )

    # t=1000: button down
    mock_pin.value(0)
    handler.poll(now_ms=1000)

    # t=1060: debounced press confirmed
    handler.poll(now_ms=1060)
    assert handler._is_pressed is True

    # t=3000: held for 1940 ms (< 3000 ms) -> no event yet
    evt = handler.poll(now_ms=3000)
    assert evt is None
    assert long_pressed is False

    # t=4070: held for 3010 ms (>= 3000 ms) -> long_press event!
    evt = handler.poll(now_ms=4070)
    assert evt == "long_press"
    assert long_pressed is True

    # Subsequent poll while still held down does not re-trigger
    assert handler.poll(now_ms=4500) is None

    # Released at t=5000
    mock_pin.value(1)
    handler.poll(now_ms=5000)

    # Debounce release passes at t=5060 -> should NOT trigger short press
    evt = handler.poll(now_ms=5060)
    assert evt is None
    assert short_pressed is False


def test_button_no_pin_handled_gracefully(mpy_env: MicroPythonEnvironment) -> None:
    import button

    handler = button.ButtonHandler(pin=None)
    handler.pin = None
    assert handler.is_down() is False
    assert handler.poll() is None
