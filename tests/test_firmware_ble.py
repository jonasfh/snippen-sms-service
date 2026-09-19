"""Unit tests for firmware/ble_config.py MicroPython BLE GATT server."""

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

from tests.mocks.micropython_mocks import MicroPythonEnvironment, MockBLE


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    sys.modules.pop("ble_config", None)
    yield env
    env.uninstall()
    sys.modules.pop("ble_config", None)


def test_mask_token(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config

    assert ble_config.mask_token("") == ""
    assert ble_config.mask_token("abc") == "******"
    assert ble_config.mask_token("123456") == "******"
    assert ble_config.mask_token("secret_token_1234") == "se****34"


def test_build_advertising_payload(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config
    import bluetooth

    service_uuid = bluetooth.UUID(ble_config.SERVICE_UUID_STR)

    # 1. Payload with flags and name
    adv_payload = ble_config.build_advertising_payload(
        name="Test-Device", appearance=0x0080, include_flags=True
    )
    assert isinstance(adv_payload, bytearray)
    assert len(adv_payload) <= 31
    # Check flags: len=2, type=1, flags=0x06
    assert adv_payload[0:3] == b"\x02\x01\x06"
    # Check appearance in payload
    assert b"\x03\x19\x80\x00" in adv_payload
    # Check complete local name (len=12 = 0x0c: 11 bytes name + 1 byte type)
    assert b"\x0c\x09Test-Device" in adv_payload

    # 2. Scan response payload with service UUID and no flags
    resp_payload = ble_config.build_advertising_payload(
        service_uuid=service_uuid, include_flags=False
    )
    assert isinstance(resp_payload, bytearray)
    assert len(resp_payload) <= 31
    assert b"\x01\x06" not in resp_payload
    # 128-bit UUID is 16 bytes + type + len = 18 bytes
    assert len(resp_payload) == 18


def test_ble_server_start_and_stop(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config

    mock_ble = MockBLE()
    server = ble_config.BLEConfigServer(
        ble=mock_ble,
        config={
            "wifi_ssid": "MyWiFi",
            "snippen_api_token": "sensitive_token_999",
            "snippen_api_base_url": "https://test.snippen.no",
        },
    )

    assert server.is_running is False
    assert server.start() is True
    assert server.is_running is True
    assert mock_ble.active() is True
    assert mock_ble._is_advertising is True
    # MAC suffix is derived from mock MAC b'\x12\x34\x56\x78\x9a\xbc' -> 9ABC
    assert server.device_name == "Snippen-SMS-9ABC"

    # Both advertising and scan response payloads must be within the 31-byte BLE limit
    assert mock_ble._adv_data is not None
    assert len(mock_ble._adv_data) <= 31
    assert b"Snippen-SMS-9ABC" in mock_ble._adv_data
    assert mock_ble._resp_data is not None
    assert len(mock_ble._resp_data) <= 31

    # Verify initial config characteristic value has masked token
    config_bytes = mock_ble.gatts_read(server.handle_config)
    config_data = json.loads(config_bytes.decode("utf-8"))
    assert config_data["wifi_ssid"] == "MyWiFi"
    assert config_data["snippen_api_token"] == "se****99"
    assert "sensitive" not in config_data["snippen_api_token"]

    server.stop()
    assert server.is_running is False
    assert mock_ble.active() is False
    assert mock_ble._is_advertising is False


def test_ble_server_central_connection_events(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config

    mock_ble = MockBLE()
    server = ble_config.BLEConfigServer(ble=mock_ble)
    server.start()

    # Simulate central connecting
    mock_ble.simulate_connect(conn_handle=5)
    assert server.conn_handle == 5

    # Check notification recorded on status handle
    status_bytes = mock_ble.gatts_read(server.handle_status)
    status_data = json.loads(status_bytes.decode("utf-8"))
    assert status_data["status"] == "connected"
    assert status_data["conn_handle"] == 5

    # Simulate disconnect
    mock_ble.simulate_disconnect(conn_handle=5)
    assert server.conn_handle is None
    # Advertising should resume
    assert mock_ble._is_advertising is True


def test_ble_server_config_write(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config

    mock_ble = MockBLE()
    received_config: dict = {}

    def on_cfg(cfg: dict) -> None:
        nonlocal received_config
        received_config = cfg

    server = ble_config.BLEConfigServer(
        ble=mock_ble,
        config={"wifi_ssid": "OldNet"},
        on_config_received=on_cfg,
    )
    server.start()
    mock_ble.simulate_connect(conn_handle=1)

    new_cfg = {
        "wifi_ssid": "NewOfficeWiFi",
        "wifi_password": "UltraSecretPassword",
        "snippen_api_token": "brand_new_token_123",
    }
    mock_ble.simulate_write(server.handle_config, json.dumps(new_cfg))

    assert received_config == new_cfg
    assert server.config["wifi_ssid"] == "NewOfficeWiFi"

    # Verify characteristic is updated with masked token
    read_back = json.loads(mock_ble.gatts_read(server.handle_config).decode("utf-8"))
    assert read_back["wifi_ssid"] == "NewOfficeWiFi"
    assert read_back["snippen_api_token"] == "br****23"


def test_ble_server_command_write_and_response(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config

    mock_ble = MockBLE()
    cmd_received = ""
    payload_received = {}

    def on_cmd(cmd: str, payload: dict) -> dict:
        nonlocal cmd_received, payload_received
        cmd_received = cmd
        payload_received = payload
        if cmd == "SCAN_WIFI":
            return {"cmd": "SCAN_WIFI", "status": "ok", "networks": ["Net1", "Net2"]}
        return {"cmd": cmd, "status": "unknown"}

    server = ble_config.BLEConfigServer(
        ble=mock_ble,
        on_command=on_cmd,
    )
    server.start()
    mock_ble.simulate_connect(conn_handle=2)

    # Write command payload
    mock_ble.simulate_write(
        server.handle_command, json.dumps({"cmd": "SCAN_WIFI", "filter": "2.4G"})
    )

    assert cmd_received == "SCAN_WIFI"
    assert payload_received.get("filter") == "2.4G"

    # Verify command response was notified
    resp_bytes = mock_ble.gatts_read(server.handle_command)
    resp_data = json.loads(resp_bytes.decode("utf-8"))
    assert resp_data["cmd"] == "SCAN_WIFI"
    assert resp_data["status"] == "ok"
    assert resp_data["networks"] == ["Net1", "Net2"]


def test_ble_server_inactivity_timeout(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config

    mock_ble = MockBLE()
    timed_out = False

    def on_timeout() -> None:
        nonlocal timed_out
        timed_out = True

    server = ble_config.BLEConfigServer(
        ble=mock_ble,
        timeout_sec=300,
        on_timeout=on_timeout,
    )
    server.start()
    assert server.is_running is True

    start_time = server.last_activity_time
    # Poll before timeout
    server.poll(now=start_time + 100)
    assert server.is_running is True
    assert timed_out is False

    # Poll after timeout without central connection
    server.poll(now=start_time + 301)
    assert server.is_running is False
    assert timed_out is True


def test_ble_server_connected_does_not_timeout(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config

    mock_ble = MockBLE()
    timed_out = False

    def on_timeout() -> None:
        nonlocal timed_out
        timed_out = True

    server = ble_config.BLEConfigServer(
        ble=mock_ble,
        timeout_sec=300,
        on_timeout=on_timeout,
    )
    server.start()
    mock_ble.simulate_connect(conn_handle=1)

    # Poll far past timeout when connected
    server.poll(now=server.last_activity_time + 600)
    assert server.is_running is True
    assert timed_out is False
