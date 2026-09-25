"""Button input handler with hardware interrupts and debouncing for MicroPython (Issue #59, #83, #117)."""

try:
    import utime as time
except ImportError:
    import time

try:
    import micropython
except ImportError:
    micropython = None

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
    """Monitors a digital input pin for debounced button presses with hardware IRQ support (Issue #83, #117)."""

    def __init__(
        self,
        pin_id: int = 0,
        long_press_ms: int = 3000,  # Deprecated (Issue #83), retained for compatibility
        debounce_ms: int = 50,
        active_low: bool = True,
        on_press: object | None = None,
        on_long_press: object | None = None,
        on_short_press: object | None = None,
        pin: object | None = None,
        enable_irq: bool = True,
    ) -> None:
        self.pin_id = pin_id
        self.long_press_ms = long_press_ms
        self.debounce_ms = debounce_ms
        self.active_low = active_low
        self.on_press = on_press
        self.on_long_press = on_long_press
        self.on_short_press = on_short_press
        self.enable_irq = enable_irq

        if pin is not None:
            self.pin = pin
        elif Pin is not None:
            pull = getattr(Pin, "PULL_UP", 1) if active_low else getattr(Pin, "PULL_DOWN", 2)
            self.pin = Pin(pin_id, getattr(Pin, "IN", 0), pull)
        else:
            self.pin = None

        self._is_pressed = False
        self._last_raw_val = None
        self._last_raw_change_ms = 0
        self._irq_triggered = False
        self._last_irq_ms = 0

        # Attach hardware interrupt if supported (Issue #117)
        if self.pin is not None and enable_irq and hasattr(self.pin, "irq"):
            trigger = (
                getattr(Pin, "IRQ_FALLING", 2) if active_low else getattr(Pin, "IRQ_RISING", 1)
            )
            try:
                self.pin.irq(trigger=trigger, handler=self._on_irq)
            except Exception as exc:  # noqa: BLE001
                print(f"[button] Warning: Failed to attach hardware IRQ: {exc}")

    def _on_irq(self, pin: object = None) -> None:
        """Hardware interrupt service routine (ISR) for button press (Issue #117).

        Kept strictly minimal with zero heap allocations to satisfy hard ISR constraints.
        """
        now = _get_ticks_ms()
        if _ticks_diff(now, self._last_irq_ms) >= self.debounce_ms:
            self._last_irq_ms = now
            self._irq_triggered = True
            if micropython is not None and hasattr(micropython, "schedule"):
                try:
                    micropython.schedule(self._scheduled_irq_dispatch, 0)
                except Exception:  # noqa: BLE001, S110
                    pass

    def _scheduled_irq_dispatch(self, _arg: int = 0) -> None:
        """Dispatch button callbacks scheduled by hardware interrupt (Issue #117)."""
        if self._irq_triggered:
            self._irq_triggered = False
            self._is_pressed = self.is_down()
            self._trigger_callbacks()

    def _trigger_callbacks(self) -> None:
        """Execute registered button press callbacks."""
        if callable(self.on_press):
            self.on_press()
        if callable(self.on_short_press):
            self.on_short_press()
        if callable(self.on_long_press):
            self.on_long_press()

    def is_down(self) -> bool:
        """Return True if button is currently physically pressed down."""
        if self.pin is None:
            return False
        val = self.pin.value()
        return val == 0 if self.active_low else val == 1

    def poll(self, now_ms: int | None = None) -> str | None:
        """Poll button state, perform debouncing, and trigger callbacks on press (Issue #83, #117).

        Returns:
            'press' when a valid debounced press transition occurs,
            or None if no state transition completed.
        """
        if self.pin is None:
            return None

        # Check if hardware interrupt flagged a press while CPU was busy
        if self._irq_triggered:
            self._irq_triggered = False
            self._is_pressed = self.is_down()
            self._trigger_callbacks()
            return "press"

        if now_ms is None:
            now_ms = _get_ticks_ms()

        raw_val = self.pin.value()
        raw_pressed = raw_val == 0 if self.active_low else raw_val == 1

        # Check raw pin change for debouncing
        if raw_val != self._last_raw_val:
            self._last_raw_val = raw_val
            self._last_raw_change_ms = now_ms

        event: str | None = None
        # Only process state change after debounce_ms has passed steadily
        if _ticks_diff(now_ms, self._last_raw_change_ms) >= self.debounce_ms:
            if raw_pressed and not self._is_pressed:
                # Button transitioned to pressed (debounced)
                self._is_pressed = True
                event = "press"
                self._trigger_callbacks()
            elif not raw_pressed and self._is_pressed:
                # Button transitioned to released (debounced)
                self._is_pressed = False

        return event
