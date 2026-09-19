"""Unit tests for firmware configuration module."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

# Ensure firmware/ is in sys.path for importing firmware modules directly
FIRMWARE_DIR = Path(__file__).resolve().parent.parent / "firmware"
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

import config


def test_get_default_config() -> None:
    cfg = config.get_default_config()
    assert isinstance(cfg, dict)
    assert cfg["pin_modem_power"] == 12
    assert cfg["pin_modem_reset"] == 5
    assert cfg["pin_modem_pwrkey"] == 4
    assert cfg["pin_modem_tx"] == 26
    assert cfg["pin_modem_rx"] == 25
    assert cfg["modem_uart_id"] == 1
    assert cfg["modem_baudrate"] == 115200
    assert cfg["modem_pwrkey_pulse_ms"] == 1500
    assert cfg["modem_boot_wait_sec"] == 6
    assert "https://vestreholmensameie.no" in cfg["snippen_api_base_url"]
    assert cfg["outbox_poll_interval_sec"] == 5
    assert cfg["inbox_check_interval_sec"] == 5
    assert cfg["modem_cmd_timeout_ms"] == 2000
    assert cfg["modem_sms_timeout_ms"] == 15000
    assert cfg["modem_sim_pin"] == ""
    assert cfg["sms_auto_delete"] is True


def test_load_config_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "config_local", None)
    monkeypatch.chdir(tmp_path)
    non_existent = tmp_path / "non_existent_config.json"
    loaded = config.load_config(str(non_existent))
    assert loaded["pin_modem_power"] == 12
    assert loaded["wifi_ssid"] == ""


def test_load_config_json_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "config_local", None)
    monkeypatch.chdir(tmp_path)
    json_path = tmp_path / "test_config.json"
    data = {
        "wifi_ssid": "Test-WiFi",
        "wifi_password": "MySecretPassword",
        "outbox_poll_interval_sec": 10,
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")

    loaded = config.load_config(str(json_path))
    assert loaded["wifi_ssid"] == "Test-WiFi"
    assert loaded["wifi_password"] == "MySecretPassword"
    assert loaded["outbox_poll_interval_sec"] == 10
    # Unoverridden should remain defaults
    assert loaded["pin_modem_power"] == 12


def test_load_config_module_overrides(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_local = types.ModuleType("config_local")
    fake_local.WIFI_SSID = "Module-WiFi"  # type: ignore[attr-defined]
    fake_local.HEARTBEAT_INTERVAL_SEC = 60  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "config_local", fake_local)

    non_existent = tmp_path / "non_existent.json"
    loaded = config.load_config(str(non_existent))
    assert loaded["wifi_ssid"] == "Module-WiFi"
    assert loaded["heartbeat_interval_sec"] == 60


def test_load_config_dot_local_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Ensure config_local is not in sys.modules
    monkeypatch.delitem(sys.modules, "config_local", raising=False)
    monkeypatch.chdir(tmp_path)

    dot_local = tmp_path / "config.local.py"
    dot_local.write_text(
        'WIFI_SSID = "Dot-Local-WiFi"\nLONG_POLL_TIMEOUT_SEC = 50\n', encoding="utf-8"
    )

    loaded = config.load_config(str(tmp_path / "non_existent.json"))
    assert loaded["wifi_ssid"] == "Dot-Local-WiFi"
    assert loaded["long_poll_timeout_sec"] == 50
