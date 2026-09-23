"""In-memory circular log buffer and stdout/stderr stream redirector for MicroPython (Issue #89).

Captures standard output (print statements) and exceptions into a ring buffer
while preserving USB serial console output, enabling wireless log streaming over BLE.
"""

import sys


class LogStreamRedirector:
    """Stream wrapper that captures stdout and stderr into a bounded circular buffer."""

    def __init__(self, max_lines: int = 100, on_line_callback: object | None = None) -> None:
        self.max_lines = max_lines
        self.on_line_callback = on_line_callback
        self.lines: list[str] = []
        self._partial_line = ""
        self.original_stdout = getattr(sys, "stdout", None)
        self.original_stderr = getattr(sys, "stderr", None)
        self.installed = False
        self._using_dupterm = False

    def install(self) -> None:
        """Redirect stdout/stderr through this redirector using uos.dupterm or sys.stdout."""
        if self.installed:
            return

        # 1. MicroPython bare-metal / ESP32 port: uos.dupterm
        try:
            import uos  # type: ignore[import-not-found]

            if hasattr(uos, "dupterm"):
                uos.dupterm(self)
                self.installed = True
                self._using_dupterm = True
                return
        except Exception:  # noqa: BLE001, S110
            pass

        # 2. CPython / Unix MicroPython port: sys.stdout
        if hasattr(sys, "stdout"):
            try:
                self.original_stdout = sys.stdout
                self.original_stderr = getattr(sys, "stderr", None)
                sys.stdout = self
                sys.stderr = self
                self.installed = True
            except Exception:  # noqa: BLE001, S110
                pass

    def uninstall(self) -> None:
        """Restore original sys.stdout and sys.stderr streams or unregister dupterm."""
        if not self.installed:
            return

        if self._using_dupterm:
            try:
                import uos  # type: ignore[import-not-found]

                if hasattr(uos, "dupterm"):
                    uos.dupterm(None)
            except Exception:  # noqa: BLE001, S110
                pass
            self._using_dupterm = False

        if hasattr(sys, "stdout") and self.original_stdout is not None:
            try:
                sys.stdout = self.original_stdout
                if self.original_stderr is not None:
                    sys.stderr = self.original_stderr
            except Exception:  # noqa: BLE001, S110
                pass

        self.installed = False

    def readinto(self, buf: bytearray) -> int | None:
        """Stream input method for uos.dupterm (output-only stream)."""
        return None

    def set_callback(self, callback: object | None) -> None:
        """Update or register the line notification callback."""
        self.on_line_callback = callback

    def write(self, text: bytes | str) -> int:
        """Write string chunk to original stdout and buffer complete lines."""
        if isinstance(text, (bytes, bytearray)):
            try:
                str_text = text.decode("utf-8")
            except Exception:  # noqa: BLE001
                str_text = str(text)
        else:
            str_text = str(text)

        # In sys.stdout mode, forward to original stdout
        if (
            not self._using_dupterm
            and self.original_stdout is not None
            and self.original_stdout is not self
        ):
            try:
                self.original_stdout.write(str_text)
            except Exception:  # noqa: BLE001, S110
                pass

        if not str_text:
            return len(text)

        self._partial_line += str_text
        while "\n" in self._partial_line:
            line, self._partial_line = self._partial_line.split("\n", 1)
            line = line.rstrip("\r")
            if len(self.lines) >= self.max_lines:
                self.lines.pop(0)
            self.lines.append(line)

            if callable(self.on_line_callback):
                try:
                    self.on_line_callback(line)
                except Exception:  # noqa: BLE001, S110
                    pass

        return len(text)

    def flush(self) -> None:
        """Flush original stream if supported."""
        if self.original_stdout is not None and hasattr(self.original_stdout, "flush"):
            try:
                self.original_stdout.flush()
            except Exception:  # noqa: BLE001, S110
                pass

    def get_lines(self, count: int | None = None) -> list[str]:
        """Return cached log lines up to count entries."""
        if count is None or count <= 0:
            return list(self.lines)
        return list(self.lines[-count:])

    def clear(self) -> None:
        """Clear the in-memory line buffer."""
        self.lines = []
        self._partial_line = ""


_global_logger: LogStreamRedirector | None = None


def get_logger(max_lines: int = 100) -> LogStreamRedirector:
    """Get or create singleton log redirector instance."""
    global _global_logger
    if _global_logger is None:
        _global_logger = LogStreamRedirector(max_lines=max_lines)
    return _global_logger


def setup_logger(
    max_lines: int = 100, on_line_callback: object | None = None
) -> LogStreamRedirector:
    """Initialize, install, and return singleton log redirector."""
    logger = get_logger(max_lines=max_lines)
    if on_line_callback is not None:
        logger.set_callback(on_line_callback)
    logger.install()
    return logger
