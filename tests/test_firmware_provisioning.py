"""Unit tests for WiFi scanning, configuration persistence, and BLE telemetry (Issue #61)."""

from __future__ import annotations

import json
import sys
from collections.abc import Generator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from tests.mocks.micropython_mocks import MicroPythonEnvironment, MockUART


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    sys.modules.pop("wifi", None)
    sys.modules.pop("config", None)
    sys.modules.pop("main", None)
    yield env
    env.uninstall()
    sys.modules.pop("wifi", None)
    sys.modules.pop("config", None)
    sys.modules.pop("main", None)


def test_wifi_scan_networks(mpy_env: MicroPythonEnvironment) -> None:
    import network
    import wifi

    wlan = network.WLAN(network.STA_IF)
    wlan._scan_results = [
        (b"WeakNet", b"\x01\x02\x03\x04\x05\x06", 1, -85, 3, 0),
        (b"StrongNet", b"\x06\x05\x04\x03\x02\x01", 6, -50, 4, 0),
        (b"", b"\x00\x00\x00\x00\x00\x00", 11, -40, 0, 1),  # Hidden SSID
        (b"StrongNet", b"\x11\x22\x33\x44\x55\x66", 6, -52, 4, 0),  # Duplicate
    ]

    results = wifi.scan_networks()

    assert len(results) == 2
    # Sorted strongest first (-50 > -85)
    assert results[0]["ssid"] == "StrongNet"
    assert results[0]["rssi"] == -50
    assert results[0]["auth"] == 4

    assert results[1]["ssid"] == "WeakNet"
    assert results[1]["rssi"] == -85


def test_wifi_scan_networks_max_results_and_filter(mpy_env: MicroPythonEnvironment) -> None:
    import network
    import wifi

    wlan = network.WLAN(network.STA_IF)
    wlan._scan_results = [
        (f"Net-{i}".encode(), b"\x00" * 6, 1, -40 - i * 4, 3, 0) for i in range(20)
    ]

    results = wifi.scan_networks(max_results=5)
    assert len(results) == 5
    # Strongest first
    assert results[0]["ssid"] == "Net-0"
    assert results[0]["rssi"] == -40
    # No network weaker than -85 dBm if filtered
    for r in results:
        assert r["rssi"] >= -85


def test_wifi_test_connection_success(mpy_env: MicroPythonEnvironment) -> None:
    import wifi

    res = wifi.test_connection(ssid="SnippenGuest", password="testpass", timeout_sec=2)
    assert res["status"] == "ok"
    assert res["connected"] is True
    assert res["ssid"] == "SnippenGuest"
    assert res["ip"] == "192.168.1.100"


def test_wifi_test_connection_empty_ssid(mpy_env: MicroPythonEnvironment) -> None:
    import wifi

    res = wifi.test_connection(ssid="")
    assert res["status"] == "error"
    assert res["connected"] is False


def test_save_config_persists_to_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import config

    cfg_file = tmp_path / "custom_config.json"
    assert not cfg_file.exists()

    success = config.save_config(
        {
            "wifi_ssid": "PersistedSSID",
            "wifi_password": "PersistedPassword",
            "outbox_poll_interval_sec": 12,
            "invalid_dummy_key": "ignore_me",
        },
        config_path=str(cfg_file),
    )
    assert success is True
    assert cfg_file.exists()

    saved_data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert saved_data["wifi_ssid"] == "PersistedSSID"
    assert saved_data["wifi_password"] == "PersistedPassword"
    assert saved_data["outbox_poll_interval_sec"] == 12
    assert "invalid_dummy_key" not in saved_data

    # Load config with overrides
    loaded = config.load_config(config_path=str(cfg_file))
    assert loaded["wifi_ssid"] == "PersistedSSID"
    assert loaded["outbox_poll_interval_sec"] == 12


def test_main_ble_scan_wifi_command(mpy_env: MicroPythonEnvironment) -> None:
    import main

    app = main.GatewayApp()
    app.setup()

    res = app.on_ble_command("SCAN_WIFI", {})
    assert res["cmd"] == "SCAN_WIFI"
    assert res["status"] == "ok"
    assert "networks" in res
    assert len(res["networks"]) >= 1


def test_main_ble_test_wifi_command(mpy_env: MicroPythonEnvironment) -> None:
    import main

    app = main.GatewayApp()
    app.setup()

    res = app.on_ble_command("TEST_WIFI", {"wifi_ssid": "TestAP", "wifi_password": "pass"})
    assert res["cmd"] == "TEST_WIFI"
    assert res["status"] == "ok"
    assert res["connected"] is True
    assert res["ip"] == "192.168.1.100"


def test_main_ble_apply_and_exit_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mpy_env: MicroPythonEnvironment
) -> None:
    import main

    cfg_file = tmp_path / "config.json"
    monkeypatch.chdir(tmp_path)

    app = main.GatewayApp(config={"wifi_ssid": "AppliedNet", "snippen_api_token": "tok999"})
    app.setup()
    app.enter_provisioning_mode()
    assert app.is_provisioning_mode is True

    res = app.on_ble_command("APPLY_AND_EXIT", {})
    assert res["status"] == "ok"
    assert app.is_provisioning_mode is False
    assert cfg_file.exists()

    saved = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert saved["wifi_ssid"] == "AppliedNet"


def test_main_get_telemetry_status(mpy_env: MicroPythonEnvironment) -> None:
    import main

    mock_uart = MockUART(1)
    mock_uart.auto_responses = {
        "AT+CMGF=1": b"OK\r\n",
        'AT+CSCS="GSM"': b"OK\r\n",
        "AT+CSQ": b"+CSQ: 18,0\r\nOK\r\n",
        "AT+CREG?": b"+CREG: 0,1\r\nOK\r\n",
    }

    app = main.GatewayApp(
        config={"wifi_ssid": "SnippenNet", "snippen_api_token": "valid_token"},
        uart=mock_uart,
    )
    app.setup()

    telemetry = app.get_telemetry_status()
    assert telemetry["wifi_ssid"] == "SnippenNet"
    assert telemetry["cellular_rssi"] == 18
    assert telemetry["cellular_dbm"] == -77
    assert telemetry["cellular_net"] == "Registered, home network"
