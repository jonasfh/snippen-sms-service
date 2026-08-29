"""Unit tests for the project formatter utility."""

from pathlib import Path
import sys

# Add scripts directory to path to import format module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import format as formatter


def test_format_text_file(tmp_path: Path):
    test_file = tmp_path / "sample.md"

    # Test removing trailing spaces, duplicate trailing newlines, and ensuring single trailing newline
    test_file.write_text("Line 1   \nLine 2\t  \n\n\n", encoding="utf-8")
    assert formatter.format_text_file(test_file) is True

    content = test_file.read_text(encoding="utf-8")
    assert content == "Line 1\nLine 2\n"

    # Second pass should not modify already clean file
    assert formatter.format_text_file(test_file) is False


def test_format_text_file_missing_trailing_newline(tmp_path: Path):
    test_file = tmp_path / "sample_no_newline.txt"
    test_file.write_text("No newline at end", encoding="utf-8")
    assert formatter.format_text_file(test_file) is True

    content = test_file.read_text(encoding="utf-8")
    assert content == "No newline at end\n"
