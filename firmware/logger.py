"""In-memory circular log buffer and print interceptor for MicroPython and CPython (Issue #89, #99).

Captures standard output (print statements) into a bounded ring buffer
while preserving hardware serial console output, enabling wireless log streaming over BLE.
"""

import builtins
import sys


class LogStreamRedirector:
    """Log collector that captures print statements into a bounded circular buffer."""

    def __init__(self, max_lines: int = 100, on_line_callback: object | None = None) -> None:
        self.max_lines = max_lines
        self.on_line_callback = on_line_callback
        self.lines: list[str] = []
        self._partial_line = ""
        self.original_print = builtins.print
        self.original_stdout = getattr(sys, "stdout", None)
        self.installed = False

    def install(self) -> None:
        """Intercept builtins.print and sys.stdout to buffer all log statements."""
        if self.installed:
            return

        self.original_print = builtins.print

        def intercepted_print(*args: object, **kwargs: object) -> None:
            sep = kwargs.get("sep", " ")
            try:
                line = sep.join(str(a) for a in args)
            except Exception:  # noqa: BLE001
                line = str(args)

            self._append_line(line)
            self.original_print(*args, **kwargs)

        builtins.print = intercepted_print
        self.installed = True

    def uninstall(self) -> None:
        """Restore original builtins.print."""
        if not self.installed:
            return

        builtins.print = self.original_print
        self.installed = False

    def _append_line(self, line: str) -> None:
        """Append line to internal ring buffer and notify registered callback."""
        if len(self.lines) >= self.max_lines:
            self.lines.pop(0)
        self.lines.append(line)

        if callable(self.on_line_callback):
            try:
                self.on_line_callback(line)
            except Exception:  # noqa: BLE001, S110
                pass

    def set_callback(self, callback: object | None) -> None:
        """Update or register the line notification callback."""
        self.on_line_callback = callback

    def write(self, text: bytes | bytearray | str) -> int:
        """Write string or byte chunk to original stdout and buffer complete lines."""
        if isinstance(text, (bytes, bytearray)):
            try:
                str_text = text.decode("utf-8")
            except Exception:  # noqa: BLE001
                str_text = str(text)
        else:
            str_text = str(text)

        if (
            self.original_stdout is not None
            and self.original_stdout is not self
            and hasattr(self.original_stdout, "write")
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
            self._append_line(line)

        return len(text)

    def flush(self) -> None:
        """Flush original stdout stream if supported."""
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
