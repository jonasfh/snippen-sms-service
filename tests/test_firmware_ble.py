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
    assert mock_ble._is_advertising is False

    # Server can be safely restarted without recreating or re-registering
    assert server.start() is True
    assert mock_ble._is_advertising is True

    # Full deactivation if requested
    server.stop(deactivate=True)
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
    assert read_back["call_forwarding_number"] == "+4792830575"
    assert read_back["call_reject_enabled"] is True


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


def test_ble_server_notify_log(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config

    mock_ble = MockBLE()
    server = ble_config.BLEConfigServer(ble=mock_ble)
    server.start()

    # Nothing notified if no central connected
    server.notify_log("[main] Booting up")
    assert mock_ble.gatts_read(server.handle_logs) == b""

    # Connect central
    mock_ble.simulate_connect(conn_handle=3)
    server.notify_log("[main] Hello over BLE")
    assert mock_ble.gatts_read(server.handle_logs) == b"[main] Hello over BLE"


def test_gateway_app_ble_live_operations_and_logs(mpy_env: MicroPythonEnvironment) -> None:
    import ble_config
    import main

    mock_ble = MockBLE()
    server = ble_config.BLEConfigServer(ble=mock_ble)
    app = main.GatewayApp(config={"wifi_ssid": "TestSSID"}, ble_server=server)
    app.setup()

    # Enter provisioning mode
    app.enter_provisioning_mode(reason="test")
    assert app.is_provisioning_mode is True
    assert app.live_operations_active is False

    # Check telemetry
    telemetry = app.get_telemetry_status()
    assert telemetry["status"] == "provisioning"
    assert telemetry["live_operations"] is False

    # Start live operations command
    res_start = app.on_ble_command("START_OPERATIONS", {})
    assert res_start["status"] == "ok"
    assert res_start["live_operations"] is True
    assert app.live_operations_active is True

    # Log some messages
    print("[modem] Testing AT command")
    print("[api] Polled outbox")

    # Fetch logs via command
    res_logs = app.on_ble_command("GET_LOGS", {"count": 10})
    assert res_logs["status"] == "ok"
    assert any("[modem] Testing AT command" in line for line in res_logs["lines"])
    assert any("[api] Polled outbox" in line for line in res_logs["lines"])

    # Pause operations command
    res_pause = app.on_ble_command("STOP_OPERATIONS", {})
    assert res_pause["status"] == "ok"
    assert res_pause["live_operations"] is False
    assert app.live_operations_active is False

    # Clear logs command
    res_clear = app.on_ble_command("CLEAR_LOGS", {})
    assert res_clear["status"] == "ok"
    res_logs_after = app.on_ble_command("GET_LOGS", {})
    # Only the print from executing GET_LOGS command itself should be present
    assert len(res_logs_after["lines"]) <= 1
    if res_logs_after["lines"]:
        assert "GET_LOGS" in res_logs_after["lines"][0]


def test_ble_server_config_payload_stays_under_gatt_limit(mpy_env: MicroPythonEnvironment) -> None:
    """Verify that default config JSON payload stays well below 512-byte GATT attribute limit (Issue #119)."""
    import ble_config

    mock_ble = MockBLE()
    server = ble_config.BLEConfigServer(
        ble=mock_ble,
        config={
            "wifi_ssid": "Snippen-WiFi-Network",
            "snippen_api_base_url": "https://vestreholmensameie.no/wp-json/snippen/v1/sms",
            "snippen_api_token": "snip_tok_secret_value_12345",
            "outbox_poll_interval_sec": 5,
            "inbox_check_interval_sec": 5,
            "call_forwarding_number": "+4792830575",
            "call_forwarding_enabled": True,
            "call_reject_enabled": True,
            "call_notify_admin_enabled": True,
            "call_reply_caller_enabled": True,
            "call_reply_caller_text": ble_config.DEFAULT_CALL_REPLY_CALLER_TEXT,
            "call_notify_admin_text": ble_config.DEFAULT_CALL_NOTIFY_ADMIN_TEXT,
        },
    )
    server.start()

    raw_bytes = mock_ble.gatts_read(server.handle_config)
    assert len(raw_bytes) <= 500
    assert len(raw_bytes) < 400, f"Payload unexpectedly large: {len(raw_bytes)} bytes"

    parsed = json.loads(raw_bytes.decode("utf-8"))
    assert parsed["wifi_ssid"] == "Snippen-WiFi-Network"
    # Default text templates omitted to save GATT space
    assert "call_reply_caller_text" not in parsed
    assert "call_notify_admin_text" not in parsed

    # When user configures custom text, it should be included
    server.config["call_reply_caller_text"] = "Egendefinert svar til innringer."
    server.update_config_characteristic(server.config)

    raw_custom = mock_ble.gatts_read(server.handle_config)
    assert len(raw_custom) <= 500
    parsed_custom = json.loads(raw_custom.decode("utf-8"))
    assert parsed_custom["call_reply_caller_text"] == "Egendefinert svar til innringer."


def test_ble_server_command_oversized_response_truncation(mpy_env: MicroPythonEnvironment) -> None:
    """Verify that oversized command responses (like GET_LOGS) are trimmed to <= 500 bytes (Issue #119)."""
    import ble_config

    mock_ble = MockBLE()
    server = ble_config.BLEConfigServer(ble=mock_ble)
    server.start()
    server.conn_handle = 3

    # Generate huge response with 50 lines (each 60 chars = ~3000 bytes)
    huge_lines = [
        f"[{i:02d}] 2026-09-25T20:00:{i:02d} System event occurred on cellular modem"
        for i in range(50)
    ]
    huge_response = {"cmd": "GET_LOGS", "status": "ok", "lines": huge_lines}

    server.notify_command_response(huge_response, conn_handle=3)

    raw_resp = mock_ble.gatts_read(server.handle_command)
    assert len(raw_resp) <= 500, f"Response exceeds 500 bytes: {len(raw_resp)}"

    # Ensure it remains valid JSON
    decoded = json.loads(raw_resp.decode("utf-8"))
    assert decoded["cmd"] == "GET_LOGS"
    assert decoded["status"] == "ok"
    assert isinstance(decoded["lines"], list)
    assert len(decoded["lines"]) > 0


def test_gateway_app_start_operations_defers_polling(mpy_env: MicroPythonEnvironment) -> None:
    """Verify START_OPERATIONS resets timers so immediate polling does not block BLE (Issue #119)."""
    import ble_config
    import main
    import utime as time

    mock_ble = MockBLE()
    server = ble_config.BLEConfigServer(ble=mock_ble)
    app = main.GatewayApp(config={"wifi_ssid": "TestSSID"}, ble_server=server)
    app.setup()
    app.last_outbox_poll = 0
    app.last_inbox_check = 0

    before_time = time.time()
    res = app.on_ble_command("START_OPERATIONS", {})
    assert res["status"] == "ok"
    assert app.live_operations_active is True
    assert app.last_outbox_poll >= before_time
    assert app.last_inbox_check >= before_time
