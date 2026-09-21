"""Interactive on-device test for BOOT button (GPIO 0) (Issue #59, #83).

Tests debouncing and single-press detection for BLE activation in real time.
Run with:
    python scripts/test_button_live.py
"""

import sys

try:
    import utime as time
except ImportError:
    import time

try:
    from machine import Pin
except ImportError:
    Pin = None

try:
    from button import ButtonHandler
except ImportError:
    print("[test_button] Error: button.py module not found.")
    sys.exit(1)


def run_button_test(pin_id: int = 0) -> None:
    """Run live interactive button test on Lilygo ESP32."""
    print("=" * 64)
    print("        Lilygo ESP32 - BOOT Button Interactive Test             ")
    print("=" * 64)
    print(f"Monitoring GPIO {pin_id} (active LOW with internal pull-up)...")
    print("Instructions:")
    print("  1. Press the BOOT button (GPIO 0).")
    print("  2. Verify that any short press immediately triggers the press event.")
    print("  3. Hold the button down and verify it does NOT trigger repeatedly.")
    print("  4. Press Ctrl+C in terminal to stop.")
    print("-" * 64)

    if Pin is not None:
        raw_pin = Pin(pin_id, Pin.IN, Pin.PULL_UP)
        initial_val = raw_pin.value()
        print(
            f"Initial raw pin state: {initial_val} ({'RELEASED (HIGH)' if initial_val == 1 else 'PRESSED (LOW)'})"
        )
        if initial_val == 0:
            print("⚠️  Warning: Pin is LOW on startup. If button is not held, check pinout.")

    press_count = 0

    def on_press() -> None:
        nonlocal press_count
        press_count += 1
        print(f"\n🎉 [EVENT] >>> BUTTON PRESS #{press_count} DETECTED (BLE ACTIVATE) <<<")

    handler = ButtonHandler(
        pin_id=pin_id,
        debounce_ms=50,
        active_low=True,
        on_press=on_press,
    )

    last_down = False

    try:
        while True:
            # Poll button handler
            handler.poll()

            is_down = handler.is_down()
            if is_down and not last_down:
                last_down = True
                print("\n[BUTTON] Physical press detected...", end="")
            elif not is_down and last_down:
                last_down = False
                print(" -> Released.")

            time.sleep(0.05)
    except KeyboardInterrupt:
        print(f"\n[test_button] Test finished. Total presses detected: {press_count}")


if __name__ == "__main__":
    run_button_test()
