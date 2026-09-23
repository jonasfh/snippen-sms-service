"""Unit tests for firmware/logger.py in-memory log buffer and stdout/stderr redirector (Issue #89)."""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from firmware.logger import LogStreamRedirector, get_logger, setup_logger


def test_logger_line_buffering_and_capacity() -> None:
    """Verify that LogStreamRedirector buffers lines and enforces maximum capacity FIFO."""
    logger = LogStreamRedirector(max_lines=3)
    logger.write("Line 1\n")
    logger.write("Line 2\n")
    logger.write("Line 3\n")

    assert logger.get_lines() == ["Line 1", "Line 2", "Line 3"]

    # Writing 4th line should drop 1st
    logger.write("Line 4\r\n")
    assert logger.get_lines() == ["Line 2", "Line 3", "Line 4"]

    # Partial line write
    logger.write("Line 5 ")
    assert logger.get_lines() == ["Line 2", "Line 3", "Line 4"]
    logger.write("finished\n")
    assert logger.get_lines() == ["Line 3", "Line 4", "Line 5 finished"]


def test_logger_callback_invocation() -> None:
    """Verify that on_line_callback is triggered on complete lines."""
    captured: list[str] = []

    def cb(line: str) -> None:
        captured.append(line)

    logger = LogStreamRedirector(max_lines=10, on_line_callback=cb)
    logger.write("[wifi] Connecting to AP...\n[wifi] Connected!\n")

    assert captured == ["[wifi] Connecting to AP...", "[wifi] Connected!"]


def test_logger_callback_error_resilience() -> None:
    """Verify that failing callbacks do not raise or break writing."""

    def faulty_cb(line: str) -> None:
        raise RuntimeError("Callback explosion")

    logger = LogStreamRedirector(max_lines=10, on_line_callback=faulty_cb)
    written = logger.write("Safe line\n")
    assert written == len("Safe line\n")
    assert logger.get_lines() == ["Safe line"]


def test_logger_get_lines_slice() -> None:
    """Verify slicing with count parameter."""
    logger = LogStreamRedirector(max_lines=10)
    for i in range(1, 6):
        logger.write(f"Entry {i}\n")

    assert logger.get_lines(count=2) == ["Entry 4", "Entry 5"]
    assert len(logger.get_lines(count=100)) == 5
    assert len(logger.get_lines(count=0)) == 5


def test_logger_clear() -> None:
    """Verify clearing line buffer."""
    logger = LogStreamRedirector(max_lines=10)
    logger.write("Something\n")
    assert len(logger.get_lines()) == 1
    logger.clear()
    assert logger.get_lines() == []


def test_logger_install_and_uninstall() -> None:
    """Verify that install redirects sys.stdout and uninstall restores it."""
    orig_stdout = sys.stdout
    orig_stderr = sys.stderr

    logger = LogStreamRedirector(max_lines=5)
    try:
        logger.install()
        assert sys.stdout is logger
        assert sys.stderr is logger

        print("Testing print interception")
        assert logger.get_lines() == ["Testing print interception"]
    finally:
        logger.uninstall()
        assert sys.stdout is orig_stdout
        assert sys.stderr is orig_stderr


def test_get_logger_and_setup_logger_singleton() -> None:
    """Verify singleton lifecycle helpers."""
    l1 = get_logger(max_lines=50)
    l2 = get_logger()
    assert l1 is l2

    orig_stdout = sys.stdout
    try:
        l3 = setup_logger(max_lines=50)
        assert l3 is l1
        assert sys.stdout is l1
    finally:
        l1.uninstall()
        assert sys.stdout is orig_stdout
