"""Button input handler with debouncing and long-press detection for MicroPython (Issue #59)."""

try:
    import utime as time
except ImportError:
    import time

try:
    from machine import Pin
except ImportError:
    Pin = None


def _get_ticks_ms() -> int:
    """Return current millisecond timestamp across MicroPython and CPython."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def _ticks_diff(t1: int, t2: int) -> int:
    """Calculate elapsed milliseconds handling MicroPython ticks wraparound."""
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(t1, t2)
    return t1 - t2


class ButtonHandler:
    """Monitors a digital input pin for debounced short and long presses."""

    def __init__(
        self,
        pin_id: int = 0,
        long_press_ms: int = 3000,
        debounce_ms: int = 50,
        active_low: bool = True,
        on_long_press: object | None = None,
        on_short_press: object | None = None,
        pin: object | None = None,
    ) -> None:
        self.pin_id = pin_id
        self.long_press_ms = long_press_ms
        self.debounce_ms = debounce_ms
        self.active_low = active_low
        self.on_long_press = on_long_press
        self.on_short_press = on_short_press

        if pin is not None:
            self.pin = pin
        elif Pin is not None:
            pull = Pin.PULL_UP if active_low else Pin.PULL_DOWN
            self.pin = Pin(pin_id, Pin.IN, pull)
        else:
            self.pin = None

        self._is_pressed = False
        self._press_start_ms = 0
        self._long_press_triggered = False
        self._last_raw_val = None
        self._last_raw_change_ms = 0

    def is_down(self) -> bool:
        """Return True if button is currently physically pressed down."""
        if self.pin is None:
            return False
        val = self.pin.value()
        return val == 0 if self.active_low else val == 1

    def poll(self, now_ms: int | None = None) -> str | None:
        """Poll button state, perform debouncing, and trigger callbacks if events occur.

        Returns:
            'long_press' when held >= long_press_ms,
            'short_press' when released before long_press_ms,
            or None if no state transition event completed.
        """
        if self.pin is None:
            return None

        if now_ms is None:
            now_ms = _get_ticks_ms()

        raw_val = self.pin.value()
        raw_pressed = raw_val == 0 if self.active_low else raw_val == 1

        # Check raw pin change for debouncing
        if raw_val != self._last_raw_val:
            self._last_raw_val = raw_val
            self._last_raw_change_ms = now_ms

        # Only process state change after debounce_ms has passed steadily
        event: str | None = None
        if _ticks_diff(now_ms, self._last_raw_change_ms) >= self.debounce_ms:
            if raw_pressed and not self._is_pressed:
                # Button transitioned to pressed (debounced)
                self._is_pressed = True
                self._press_start_ms = now_ms
                self._long_press_triggered = False
            elif not raw_pressed and self._is_pressed:
                # Button transitioned to released (debounced)
                self._is_pressed = False
                if not self._long_press_triggered:
                    duration = _ticks_diff(now_ms, self._press_start_ms)
                    if duration >= self.debounce_ms:
                        if callable(self.on_short_press):
                            self.on_short_press()
                        event = "short_press"
                self._long_press_triggered = False

        # If currently held down, check for long press threshold
        if self._is_pressed and not self._long_press_triggered:
            held_duration = _ticks_diff(now_ms, self._press_start_ms)
            if held_duration >= self.long_press_ms:
                self._long_press_triggered = True
                if callable(self.on_long_press):
                    self.on_long_press()
                return "long_press"

        return event
