"""Unit tests for scripts/deploy_firmware.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import deploy_firmware


def test_find_default_port_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(deploy_firmware.glob, "glob", lambda pat: [])
    port = deploy_firmware.find_default_port()
    assert port is None


def test_find_default_port_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_glob(pat: str) -> list[str]:
        if "ACM" in pat:
            return ["/dev/ttyACM0"]
        return []

    monkeypatch.setattr(deploy_firmware.glob, "glob", fake_glob)
    port = deploy_firmware.find_default_port()
    assert port == "/dev/ttyACM0"


def test_build_mpremote_base_cmd() -> None:
    cmd_no_port = deploy_firmware.build_mpremote_base_cmd(None)
    assert cmd_no_port == [sys.executable, "-m", "mpremote"]

    cmd_with_port = deploy_firmware.build_mpremote_base_cmd("/dev/ttyACM0")
    assert cmd_with_port == [sys.executable, "-m", "mpremote", "connect", "/dev/ttyACM0"]


def test_deploy_firmware_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Setup mock repo root with firmware directory and files
    firmware_dir = tmp_path / "firmware"
    firmware_dir.mkdir()
    (firmware_dir / "boot.py").write_text("# boot", encoding="utf-8")
    (firmware_dir / "main.py").write_text("# main", encoding="utf-8")
    (firmware_dir / "config.py").write_text("# config", encoding="utf-8")
    (firmware_dir / "modem.py").write_text("# modem", encoding="utf-8")

    ret = deploy_firmware.deploy_firmware(
        repo_root=tmp_path,
        port="/dev/ttyACM0",
        include_config=False,
        do_reset=True,
        dry_run=True,
    )
    assert ret == 0


def test_deploy_firmware_batch_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    firmware_dir = tmp_path / "firmware"
    firmware_dir.mkdir()
    (firmware_dir / "boot.py").write_text("# boot", encoding="utf-8")
    (firmware_dir / "main.py").write_text("# main", encoding="utf-8")
    (firmware_dir / "logger.py").write_text("# logger", encoding="utf-8")

    captured_cmds: list[list[str]] = []

    def fake_run_mpremote(cmd: list[str], dry_run: bool = False) -> int:
        captured_cmds.append(cmd)
        return 0

    monkeypatch.setattr(deploy_firmware, "run_mpremote_command", fake_run_mpremote)
    monkeypatch.setattr(deploy_firmware, "hardware_reset_device", lambda port: 0)

    ret = deploy_firmware.deploy_firmware(
        repo_root=tmp_path,
        port="/dev/ttyACM0",
        include_config=False,
        do_reset=True,
        dry_run=False,
    )
    assert ret == 0
    # Exactly 1 batch cp command should be executed
    assert len(captured_cmds) == 1
    cmd = captured_cmds[0]
    assert "cp" in cmd
    assert str(firmware_dir / "boot.py") in cmd
    assert str(firmware_dir / "main.py") in cmd
    assert str(firmware_dir / "logger.py") in cmd
    assert cmd[-1] == ":"


def test_deploy_firmware_missing_dir(tmp_path: Path) -> None:
    # Empty dir without firmware/
    ret = deploy_firmware.deploy_firmware(
        repo_root=tmp_path,
        port="/dev/ttyACM0",
        dry_run=True,
    )
    assert ret == 1


def test_main_cli_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["deploy_firmware.py", "--dry-run", "deploy", "--port", "/dev/ttyACM0"],
    )
    ret = deploy_firmware.main()
    assert ret == 0


def test_main_cli_subcommands(monkeypatch: pytest.MonkeyPatch) -> None:
    for subcmd in ["ls", "repl", "reset"]:
        monkeypatch.setattr(
            sys,
            "argv",
            ["deploy_firmware.py", "--dry-run", subcmd, "--port", "/dev/ttyACM0"],
        )
        assert deploy_firmware.main() == 0

    monkeypatch.setattr(
        sys,
        "argv",
        ["deploy_firmware.py", "--dry-run", "run", "test.py", "--port", "/dev/ttyACM0"],
    )
    assert deploy_firmware.main() == 0
