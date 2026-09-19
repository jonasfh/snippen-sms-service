"""Unit tests for WiFi and API diagnostic scripts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import test_api_ping
import test_modem_live
import test_wifi


def test_wifi_script_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["test_wifi.py", "--dry-run", "--port", "/dev/ttyACM0"],
    )
    ret = test_wifi.main()
    assert ret == 0


def test_api_ping_script_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["test_api_ping.py", "--dry-run", "--port", "/dev/ttyACM0"],
    )
    ret = test_api_ping.main()
    assert ret == 0


def test_modem_script_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["test_modem_live.py", "--dry-run", "--port", "/dev/ttyACM0"],
    )
    ret = test_modem_live.main()
    assert ret == 0


def test_wifi_find_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        test_wifi.glob, "glob", lambda pat: ["/dev/ttyACM0"] if "ACM" in pat else []
    )
    port = test_wifi.find_default_port()
    assert port == "/dev/ttyACM0"


def test_api_ping_find_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        test_api_ping.glob, "glob", lambda pat: ["/dev/ttyACM0"] if "ACM" in pat else []
    )
    port = test_api_ping.find_default_port()
    assert port == "/dev/ttyACM0"


def test_modem_find_default_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        test_modem_live.glob, "glob", lambda pat: ["/dev/ttyACM0"] if "ACM" in pat else []
    )
    port = test_modem_live.find_default_port()
    assert port == "/dev/ttyACM0"
