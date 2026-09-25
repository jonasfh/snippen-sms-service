"""Unit tests for firmware/button.py MicroPython button handler (Issue #59, #83)."""

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
    press_calls = 0

    def on_press() -> None:
        nonlocal press_calls
        press_calls += 1

    handler = button.ButtonHandler(
        pin=mock_pin,
        debounce_ms=50,
        on_press=on_press,
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

    assert press_calls == 0


def test_button_single_press_triggers_immediately(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    press_count = 0

    def on_press() -> None:
        nonlocal press_count
        press_count += 1

    handler = button.ButtonHandler(
        pin=mock_pin,
        debounce_ms=50,
        on_press=on_press,
    )

    # Button pressed down at t=1000
    mock_pin.value(0)
    handler.poll(now_ms=1000)

    # Before debounce completes: no event
    assert handler.poll(now_ms=1040) is None
    assert press_count == 0

    # At t=1050 (debounce_ms=50 elapsed): immediate press event!
    evt = handler.poll(now_ms=1050)
    assert evt == "press"
    assert press_count == 1
    assert handler._is_pressed is True


def test_button_no_repeated_activations_while_held(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    press_count = 0

    def on_press() -> None:
        nonlocal press_count
        press_count += 1

    handler = button.ButtonHandler(
        pin=mock_pin,
        debounce_ms=50,
        on_press=on_press,
    )

    # Press and debounce
    mock_pin.value(0)
    handler.poll(now_ms=1000)
    assert handler.poll(now_ms=1060) == "press"
    assert press_count == 1

    # Keep holding the button for seconds: no additional events or callbacks
    for t in (1100, 1500, 2000, 3000, 4000, 5000):
        assert handler.poll(now_ms=t) is None
        assert press_count == 1


def test_button_resets_after_release(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    press_count = 0

    def on_press() -> None:
        nonlocal press_count
        press_count += 1

    handler = button.ButtonHandler(
        pin=mock_pin,
        debounce_ms=50,
        on_press=on_press,
    )

    # First press
    mock_pin.value(0)
    handler.poll(now_ms=1000)
    handler.poll(now_ms=1060)
    assert press_count == 1
    assert handler._is_pressed is True

    # Released at t=1200
    mock_pin.value(1)
    handler.poll(now_ms=1200)

    # Debounce release passes at t=1260
    handler.poll(now_ms=1260)
    assert handler._is_pressed is False

    # Second press at t=2000
    mock_pin.value(0)
    handler.poll(now_ms=2000)
    evt = handler.poll(now_ms=2060)
    assert evt == "press"
    assert press_count == 2


def test_button_backward_compatibility_callbacks(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    short_calls = 0
    long_calls = 0

    def on_short() -> None:
        nonlocal short_calls
        short_calls += 1

    def on_long() -> None:
        nonlocal long_calls
        long_calls += 1

    handler = button.ButtonHandler(
        pin=mock_pin,
        long_press_ms=3000,
        debounce_ms=50,
        on_short_press=on_short,
        on_long_press=on_long,
    )

    mock_pin.value(0)
    handler.poll(now_ms=1000)
    evt = handler.poll(now_ms=1060)
    assert evt == "press"
    assert short_calls == 1
    assert long_calls == 1


def test_button_no_pin_handled_gracefully(mpy_env: MicroPythonEnvironment) -> None:
    import button

    handler = button.ButtonHandler(pin=None)
    handler.pin = None
    assert handler.is_down() is False
    assert handler.poll() is None


def test_button_hardware_irq_attached_and_triggered(mpy_env: MicroPythonEnvironment) -> None:
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    press_count = 0

    def on_press() -> None:
        nonlocal press_count
        press_count += 1

    handler = button.ButtonHandler(
        pin=mock_pin,
        debounce_ms=50,
        on_press=on_press,
        enable_irq=True,
    )

    assert mock_pin.irq_handler is not None
    assert mock_pin.irq_trigger == MockPin.IRQ_FALLING

    # Trigger hardware interrupt directly
    mock_pin.trigger_irq()
    assert handler._irq_triggered is True

    # Next poll consumes interrupt event and invokes callback
    evt = handler.poll()
    assert evt == "press"
    assert press_count == 1
    assert handler._irq_triggered is False


def test_button_hardware_irq_catches_quick_press_during_blocking_work(
    mpy_env: MicroPythonEnvironment,
) -> None:
    """Verify that a brief click during simulated network blocking is captured."""
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    press_count = 0

    def on_press() -> None:
        nonlocal press_count
        press_count += 1

    handler = button.ButtonHandler(
        pin=mock_pin,
        debounce_ms=50,
        on_press=on_press,
        enable_irq=True,
    )

    # User clicks button briefly (pin falls low, IRQ fires, pin releases high)
    mock_pin.value(0)
    mock_pin.trigger_irq()
    mock_pin.value(1)  # Released before CPU ever ran poll()

    # CPU returns from blocking call seconds later and runs poll()
    evt = handler.poll()
    assert evt == "press"
    assert press_count == 1


def test_button_hardware_irq_debounced(mpy_env: MicroPythonEnvironment) -> None:
    """Verify rapid glitch interrupts within debounce_ms window are debounced."""
    import button

    mock_pin = MockPin(pin_id=0, value=1)
    press_count = 0

    def on_press() -> None:
        nonlocal press_count
        press_count += 1

    handler = button.ButtonHandler(
        pin=mock_pin,
        debounce_ms=50,
        on_press=on_press,
        enable_irq=True,
    )

    # First IRQ at t=0
    mock_pin.trigger_irq()
    assert handler._irq_triggered is True

    # Rapid glitch IRQs within 10ms
    mock_pin.trigger_irq()
    mock_pin.trigger_irq()

    # Consume
    assert handler.poll() == "press"
    assert press_count == 1

    # Immediate subsequent poll without new valid IRQ yields None
    assert handler.poll() is None
    assert press_count == 1
