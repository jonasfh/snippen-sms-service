"""Integration contract test between MicroPython firmware BLE server and Web BLE client (Issue #71).

Ensures that UUIDs, command identifiers, and token masking conventions in
tools/web-config/js/ble.js stay perfectly synchronized with firmware/ble_config.py.
"""

import re
from pathlib import Path

from firmware.ble_config import (
    CHAR_COMMAND_UUID_STR,
    CHAR_CONFIG_UUID_STR,
    CHAR_LOGS_UUID_STR,
    CHAR_STATUS_UUID_STR,
    SERVICE_UUID_STR,
    mask_token,
)


def _extract_js_constant(js_content: str, const_name: str) -> str:
    """Extract a string constant defined in JavaScript via regex."""
    match = re.search(rf"export\s+const\s+{const_name}\s*=\s*['\"]([^'\"]+)['\"];", js_content)
    assert match is not None, f"Constant {const_name} not found in JavaScript"
    return match.group(1)


REPO_ROOT = Path(__file__).resolve().parent.parent
JS_PATH = REPO_ROOT / "tools" / "web-config" / "js" / "ble.js"


def test_ble_web_config_file_exists() -> None:
    """Ensure tools/web-config/js/ble.js exists and is accessible."""
    assert JS_PATH.is_file(), f"File {JS_PATH} does not exist"
    assert JS_PATH.stat().st_size > 0


def test_ble_uuid_constants_synchronized() -> None:
    """Verify that GATT Service and Characteristic UUIDs in JS match firmware."""
    js_content = JS_PATH.read_text(encoding="utf-8")

    js_service_uuid = _extract_js_constant(js_content, "SERVICE_UUID")
    js_char_config = _extract_js_constant(js_content, "CHAR_CONFIG_UUID")
    js_char_status = _extract_js_constant(js_content, "CHAR_STATUS_UUID")
    js_char_command = _extract_js_constant(js_content, "CHAR_COMMAND_UUID")
    js_char_logs = _extract_js_constant(js_content, "CHAR_LOGS_UUID")

    assert js_service_uuid == SERVICE_UUID_STR
    assert js_char_config == CHAR_CONFIG_UUID_STR
    assert js_char_status == CHAR_STATUS_UUID_STR
    assert js_char_command == CHAR_COMMAND_UUID_STR
    assert js_char_logs == CHAR_LOGS_UUID_STR


def test_ble_commands_synchronized() -> None:
    """Verify that all commands handled by firmware are present in ble.js."""
    js_content = JS_PATH.read_text(encoding="utf-8")

    expected_commands = [
        "SCAN_WIFI",
        "TEST_WIFI",
        "APPLY_AND_EXIT",
        "START_OPERATIONS",
        "STOP_OPERATIONS",
        "GET_LOGS",
        "CLEAR_LOGS",
    ]
    for cmd in expected_commands:
        assert f"'{cmd}'" in js_content or f'"{cmd}"' in js_content, (
            f"Command {cmd} missing from tools/web-config/js/ble.js"
        )


def test_mask_token_parity() -> None:
    """Verify masking logic parity with test samples."""
    test_cases = [
        ("", ""),
        ("a", "******"),
        ("123456", "******"),
        ("1234567", "12****67"),
        ("super_secret_token_123", "su****23"),
    ]
    for raw, expected in test_cases:
        assert mask_token(raw) == expected


def test_default_call_texts_synchronized() -> None:
    """Verify that default call reply/notification texts match between firmware and app.js (Issue #121)."""
    from firmware.ble_config import (
        DEFAULT_CALL_NOTIFY_ADMIN_TEXT,
        DEFAULT_CALL_REPLY_CALLER_TEXT,
    )

    app_js_path = REPO_ROOT / "tools" / "web-config" / "js" / "app.js"
    app_js_content = app_js_path.read_text(encoding="utf-8")

    # Verify constants are defined in app.js
    assert DEFAULT_CALL_REPLY_CALLER_TEXT in app_js_content
    assert DEFAULT_CALL_NOTIFY_ADMIN_TEXT in app_js_content


def test_write_config_chunking_contract() -> None:
    """Verify that config object chunking keeps each write payload <= 400 bytes (Issue #121)."""
    import json

    full_config = {
        "wifi_ssid": "Snippen-Long-Network-Name-12345",
        "wifi_password": "super-long-wifi-wpa2-psk-passphrase-value",
        "snippen_api_base_url": "https://vestreholmensameie.no/wp-json/snippen/v1/sms",
        "snippen_api_token": "snip_tok_abcdefghijklmnopqrstuvwxyz0123456789",
        "outbox_poll_interval_sec": 5,
        "inbox_check_interval_sec": 30,
        "call_forwarding_number": "+4792830575",
        "call_forwarding_enabled": True,
        "call_reject_enabled": True,
        "call_notify_admin_enabled": True,
        "call_notify_admin_text": "Egendefinert varseltekst til administrator om ubesvart anrop fra {caller}.",
        "call_reply_caller_enabled": True,
        "call_reply_caller_text": (
            "Egendefinert lang autosvartekst til innringer som overskrider standardlengden "
            "og tester at oppdelingen i mindre GATT-pakker fungerer uten feil under lagring."
        ),
    }

    # Simulate chunking logic from ble.js
    chunks: list[dict] = []
    current_chunk: dict = {}
    for k, v in full_config.items():
        test_chunk = {**current_chunk, k: v}
        encoded = json.dumps(test_chunk).encode("utf-8")
        if len(encoded) > 400 and current_chunk:
            chunks.append(current_chunk)
            current_chunk = {k: v}
        else:
            current_chunk[k] = v
    if current_chunk:
        chunks.append(current_chunk)

    # Every chunk must be <= 400 bytes, well within GATT 512-byte limit
    for chunk in chunks:
        payload_len = len(json.dumps(chunk).encode("utf-8"))
        assert payload_len <= 400, f"Chunk exceeded 400 bytes: {payload_len}"

    # Merging all chunks together must reconstruct the full configuration
    merged = {}
    for chunk in chunks:
        merged.update(chunk)
    assert merged == full_config
