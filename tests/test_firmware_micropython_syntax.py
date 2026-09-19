"""Automated MicroPython compilation and syntax validation tests for ESP32 firmware."""

from __future__ import annotations

import ast
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"


def get_firmware_python_files() -> list[Path]:
    """Return all Python source files in the firmware directory."""
    assert FIRMWARE_DIR.is_dir(), f"Firmware directory not found: {FIRMWARE_DIR}"
    files = sorted(FIRMWARE_DIR.glob("*.py"))
    assert len(files) > 0, "No Python files found in firmware directory"
    return files


def get_mpy_cross_cmd() -> list[str]:
    """Locate mpy-cross binary or python module invocation."""
    # Check if mpy-cross is in PATH
    which_mpy = shutil.which("mpy-cross")
    if which_mpy:
        return [which_mpy]

    # Check in venv bin
    venv_mpy = Path(sys.prefix) / "bin" / "mpy-cross"
    if venv_mpy.exists():
        return [str(venv_mpy)]

    # Check as python module: python -m mpy_cross
    try:
        import mpy_cross  # noqa: F401

        return [sys.executable, "-m", "mpy_cross"]
    except ImportError:
        pass

    pytest.skip("mpy-cross compiler is not installed in the environment")


@pytest.mark.parametrize("py_file", get_firmware_python_files(), ids=lambda p: p.name)
def test_firmware_file_compiles_with_mpy_cross(py_file: Path, tmp_path: Path) -> None:
    """Validate that every firmware file compiles to valid MicroPython bytecode without syntax errors."""
    mpy_cmd = get_mpy_cross_cmd()
    output_mpy = tmp_path / f"{py_file.stem}.mpy"

    cmd = [*mpy_cmd, "-o", str(output_mpy), str(py_file)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert res.returncode == 0, (
        f"MicroPython syntax/compilation error in {py_file.name}:\n{res.stderr}\n{res.stdout}"
    )
    assert output_mpy.exists(), f"Failed to generate compiled .mpy for {py_file.name}"


@pytest.mark.parametrize("py_file", get_firmware_python_files(), ids=lambda p: p.name)
def test_firmware_file_has_no_future_imports(py_file: Path) -> None:
    """Verify firmware files do not import __future__, which is unsupported on MicroPython."""
    source = py_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_file))

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            pytest.fail(
                f"Found unsupported 'from __future__ import ...' in MicroPython firmware file: {py_file.name} (line {node.lineno})"
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "__future__":
                    pytest.fail(
                        f"Found unsupported 'import __future__' in MicroPython firmware file: {py_file.name} (line {node.lineno})"
                    )


def test_mpy_cross_catches_unsupported_dict_unpacking(tmp_path: Path) -> None:
    """Verify that mpy-cross catches PEP 448 dict unpacking syntax unsupported on MicroPython."""
    mpy_cmd = get_mpy_cross_cmd()
    bad_code = tmp_path / "bad_syntax.py"
    bad_code.write_text("res = {'a': 1}\nout = {'cmd': 'TEST', **res}\n", encoding="utf-8")

    out_mpy = tmp_path / "bad.mpy"
    cmd = [*mpy_cmd, "-o", str(out_mpy), str(bad_code)]
    res = subprocess.run(cmd, capture_output=True, text=True, check=False)

    assert res.returncode != 0
    assert "SyntaxError" in res.stderr
