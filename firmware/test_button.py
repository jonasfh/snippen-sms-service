"""Interactive on-device test for BOOT button (GPIO 0).

Tests debouncing, short press, and 3-second long-press detection in real time.
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
    print("  1. Press and hold the BOOT button (GPIO 0).")
    print("  2. Watch the live timer count up to 3.0 seconds.")
    print("  3. Release after <3s to test SHORT PRESS.")
    print("  4. Hold >=3s to test LONG PRESS.")
    print("  5. Press Ctrl+C in terminal to stop.")
    print("-" * 64)

    if Pin is not None:
        raw_pin = Pin(pin_id, Pin.IN, Pin.PULL_UP)
        initial_val = raw_pin.value()
        print(
            f"Initial raw pin state: {initial_val} ({'RELEASED (HIGH)' if initial_val == 1 else 'PRESSED (LOW)'})"
        )
        if initial_val == 0:
            print("⚠️  Warning: Pin is LOW on startup. If button is not held, check pinout.")

    long_pressed = False
    short_pressed = False

    def on_long() -> None:
        nonlocal long_pressed
        long_pressed = True
        print("\n🎉 [EVENT] >>> LONG-PRESS DETECTED (>= 3.0s)! <<<")

    def on_short() -> None:
        nonlocal short_pressed
        short_pressed = True
        print("\n⚡ [EVENT] >>> SHORT-PRESS DETECTED (< 3.0s)! <<<")

    handler = ButtonHandler(
        pin_id=pin_id,
        long_press_ms=3000,
        debounce_ms=50,
        active_low=True,
        on_long_press=on_long,
        on_short_press=on_short,
    )

    last_down = False
    press_start = 0

    try:
        while True:
            # Poll button handler
            handler.poll()

            is_down = handler.is_down()
            if is_down and not last_down:
                last_down = True
                press_start = time.time()
                print("\n[BUTTON] Pressed down! Holding...", end="")
            elif is_down and last_down:
                elapsed = time.time() - press_start
                # Print dot progress every second
                if int(elapsed * 2) != int((elapsed - 0.05) * 2):
                    print(f" {elapsed:.1f}s", end="")
            elif not is_down and last_down:
                last_down = False
                print(" -> Released.")

            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\n[test_button] Test finished.")


if __name__ == "__main__":
    run_button_test()
