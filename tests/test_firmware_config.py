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
    assert cfg["inbox_check_interval_sec"] == 30
    assert cfg["modem_cmd_timeout_ms"] == 2000
    assert cfg["modem_sms_timeout_ms"] == 15000
    assert cfg["modem_sim_pin"] == ""
    assert cfg["sms_auto_delete"] is True
    assert cfg["pin_boot_button"] == 0
    assert cfg["button_long_press_ms"] == 3000
    assert cfg["button_debounce_ms"] == 50
    assert cfg["provisioning_timeout_sec"] == 300
    assert cfg["call_forwarding_number"] == "+4792830575"
    assert cfg["call_forwarding_enabled"] is True
    assert cfg["call_reject_enabled"] is True
    assert cfg["call_notify_admin_enabled"] is True
    assert cfg["call_reply_caller_enabled"] is True
    assert "{caller}" in cfg["call_notify_admin_text"]
    assert "92830575" in cfg["call_reply_caller_text"]
    assert cfg["ota_check_on_boot"] is True


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


def test_board_profiles_catalog() -> None:
    assert "lilygo_t_call_a7670e" in config.BOARD_PROFILES
    profile = config.BOARD_PROFILES["lilygo_t_call_a7670e"]
    assert profile["pin_modem_power"] == 12
    assert profile["pin_modem_reset"] == 5
    assert profile["pin_modem_pwrkey"] == 4
    assert profile["pin_modem_tx"] == 26
    assert profile["pin_modem_rx"] == 25
    assert profile["pin_boot_button"] == 0
    assert profile["modem_uart_id"] == 1
    assert profile["modem_baudrate"] == 115200


def test_get_default_config_board_profile() -> None:
    cfg = config.get_default_config()
    assert cfg["board_profile"] == "lilygo_t_call_a7670e"
    assert cfg["pin_modem_power"] == 12

    # Fallback when unknown profile is specified
    cfg_unknown = config.get_default_config("non_existent_profile")
    assert cfg_unknown["board_profile"] == "lilygo_t_call_a7670e"


def test_load_config_with_board_profile_in_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "config_local", None)
    monkeypatch.chdir(tmp_path)
    json_path = tmp_path / "test_config.json"
    data = {
        "board_profile": "lilygo_t_call_a7670e",
        "wifi_ssid": "Test-WiFi",
    }
    json_path.write_text(json.dumps(data), encoding="utf-8")

    loaded = config.load_config(str(json_path))
    assert loaded["board_profile"] == "lilygo_t_call_a7670e"
    assert loaded["wifi_ssid"] == "Test-WiFi"
    assert loaded["pin_modem_power"] == 12


def test_load_config_with_board_profile_in_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_local = types.ModuleType("config_local")
    fake_local.BOARD_PROFILE = "lilygo_t_call_a7670e"  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "config_local", fake_local)

    non_existent = tmp_path / "non_existent.json"
    loaded = config.load_config(str(non_existent))
    assert loaded["board_profile"] == "lilygo_t_call_a7670e"


def test_save_config_persists_board_profile(tmp_path: Path) -> None:
    json_path = tmp_path / "config.json"
    success = config.save_config({"board_profile": "lilygo_t_call_a7670e"}, str(json_path))
    assert success is True
    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["board_profile"] == "lilygo_t_call_a7670e"


def test_save_config_ignores_empty_sensitive_credentials(tmp_path: Path) -> None:
    """Ensure empty credentials in updates do not overwrite existing stored credentials (Issue #141)."""
    json_path = tmp_path / "config.json"
    initial_data = {
        "snippen_api_token": "my_secret_token_123",
        "wifi_password": "super_wifi_password",
        "wifi_ssid": "OldWiFi",
    }
    json_path.write_text(json.dumps(initial_data), encoding="utf-8")

    # Update with empty token and whitespace password
    updates = {
        "wifi_ssid": "NewWiFi",
        "snippen_api_token": "",
        "wifi_password": "   ",
    }
    success = config.save_config(updates, str(json_path))
    assert success is True

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    assert saved["wifi_ssid"] == "NewWiFi"
    assert saved["snippen_api_token"] == "my_secret_token_123"
    assert saved["wifi_password"] == "super_wifi_password"
