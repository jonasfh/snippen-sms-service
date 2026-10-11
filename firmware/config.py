"""Configuration module for Snippen SMS Gateway on Lilygo T-Call A7670E (MicroPython)."""

try:
    import ujson as json
except ImportError:
    import json

# Hardware Profiles (Issue #127)
BOARD_PROFILES = {
    "lilygo_t_call_a7670e": {
        "name": "Lilygo T-Call A7670E",
        "pin_modem_power": 12,
        "pin_modem_reset": 5,
        "pin_modem_pwrkey": 4,
        "pin_modem_tx": 26,
        "pin_modem_rx": 25,
        "pin_boot_button": 0,
        "modem_uart_id": 1,
        "modem_baudrate": 115200,
        "modem_uart_timeout_ms": 2000,
        "modem_pwrkey_pulse_ms": 1500,
        "modem_boot_wait_sec": 6,
    },
}

DEFAULT_BOARD_PROFILE = "lilygo_t_call_a7670e"

# Hardware Pinout (Default: Lilygo T-Call A7670E)
PIN_MODEM_POWER = 12  # VCC Power Rail: Set HIGH to power modem
PIN_MODEM_RESET = 5  # Reset: Active-low internally, hold HIGH during operation
PIN_MODEM_PWRKEY = 4  # PWRKEY: Pulse HIGH for 1.5s to turn modem on
PIN_MODEM_TX = 26  # ESP32 TX -> Modem RX
PIN_MODEM_RX = 25  # ESP32 RX -> Modem TX

# Modem UART settings
MODEM_UART_ID = 1
MODEM_BAUDRATE = 115200
MODEM_UART_TIMEOUT_MS = 2000
MODEM_PWRKEY_PULSE_MS = 1500
MODEM_BOOT_WAIT_SEC = 6
MODEM_CMD_TIMEOUT_MS = 2000
MODEM_SMS_TIMEOUT_MS = 15000
MODEM_SIM_PIN = ""
SMS_AUTO_DELETE = True
SMS_CHUNK_DELAY_MS = 500
SMS_MULTIPART_TIMEOUT_SEC = 30

# WiFi Settings
WIFI_SSID = ""
WIFI_PASSWORD = ""
WIFI_CONNECT_TIMEOUT_SEC = 20

# Snippen Booking API Settings
SNIPPEN_API_BASE_URL = "https://vestreholmensameie.no/wp-json/snippen/v1"
SNIPPEN_API_TOKEN = ""

# Polling & Operation Loop Timers
OUTBOX_POLL_INTERVAL_SEC = 5
LONG_POLL_TIMEOUT_SEC = 25
INBOX_CHECK_INTERVAL_SEC = 30  # Fallback poll interval; SMS are processed immediately via +CMTI URC
HEARTBEAT_INTERVAL_SEC = 30
WATCHDOG_TIMEOUT_SEC = 60

# Physical Button & BLE Provisioning Settings (Issue #59)
PIN_BOOT_BUTTON = 0  # BOOT Button on ESP32 (active-low, pull-up)
BUTTON_LONG_PRESS_MS = 3000  # Milliseconds to trigger long-press event
BUTTON_DEBOUNCE_MS = 50  # Milliseconds for debounce filtering
PROVISIONING_TIMEOUT_SEC = 300  # 5 minutes provisioning mode timeout

# Call Forwarding Settings (Issue #110)
CALL_FORWARDING_NUMBER = "+4792830575"
CALL_FORWARDING_ENABLED = True

# Call Rejection & SMS Alerts Settings (Issue #113)
CALL_REJECT_ENABLED = True
CALL_NOTIFY_ADMIN_ENABLED = True
CALL_REPLY_CALLER_ENABLED = True
CALL_REPLY_CALLER_TEXT = (
    "Dette nummeret er en automatisert SMS-sentral for Snippen Booking og tar ikke imot samtaler. "
    "Send SMS eller ring leieansvarlig på 92830575."
)
CALL_NOTIFY_ADMIN_TEXT = "Ubesvart anrop til Snippen SMS-gateway fra {caller}."

# Firmware OTA Settings (Issue #129, #130)
OTA_REPO = "jonasfh/snippen-sms-service"
OTA_BUNDLE_URL = ""
OTA_STABILITY_TIMEOUT_SEC = 30
OTA_CHECK_ON_BOOT = True


def get_default_config(board_profile: str = DEFAULT_BOARD_PROFILE) -> dict:
    """Return dictionary of default system configuration for specified board profile."""
    profile_key = board_profile if board_profile in BOARD_PROFILES else DEFAULT_BOARD_PROFILE
    profile = BOARD_PROFILES[profile_key]
    return {
        "board_profile": profile_key,
        "pin_modem_power": profile["pin_modem_power"],
        "pin_modem_reset": profile["pin_modem_reset"],
        "pin_modem_pwrkey": profile["pin_modem_pwrkey"],
        "pin_modem_tx": profile["pin_modem_tx"],
        "pin_modem_rx": profile["pin_modem_rx"],
        "modem_uart_id": profile["modem_uart_id"],
        "modem_baudrate": profile["modem_baudrate"],
        "modem_uart_timeout_ms": profile["modem_uart_timeout_ms"],
        "modem_pwrkey_pulse_ms": profile["modem_pwrkey_pulse_ms"],
        "modem_boot_wait_sec": profile["modem_boot_wait_sec"],
        "modem_cmd_timeout_ms": MODEM_CMD_TIMEOUT_MS,
        "modem_sms_timeout_ms": MODEM_SMS_TIMEOUT_MS,
        "modem_sim_pin": MODEM_SIM_PIN,
        "sms_auto_delete": SMS_AUTO_DELETE,
        "sms_chunk_delay_ms": SMS_CHUNK_DELAY_MS,
        "sms_multipart_timeout_sec": SMS_MULTIPART_TIMEOUT_SEC,
        "wifi_ssid": WIFI_SSID,
        "wifi_password": WIFI_PASSWORD,
        "wifi_connect_timeout_sec": WIFI_CONNECT_TIMEOUT_SEC,
        "snippen_api_base_url": SNIPPEN_API_BASE_URL,
        "snippen_api_token": SNIPPEN_API_TOKEN,
        "outbox_poll_interval_sec": OUTBOX_POLL_INTERVAL_SEC,
        "long_poll_timeout_sec": LONG_POLL_TIMEOUT_SEC,
        "inbox_check_interval_sec": INBOX_CHECK_INTERVAL_SEC,
        "heartbeat_interval_sec": HEARTBEAT_INTERVAL_SEC,
        "watchdog_timeout_sec": WATCHDOG_TIMEOUT_SEC,
        "pin_boot_button": profile["pin_boot_button"],
        "button_long_press_ms": BUTTON_LONG_PRESS_MS,
        "button_debounce_ms": BUTTON_DEBOUNCE_MS,
        "provisioning_timeout_sec": PROVISIONING_TIMEOUT_SEC,
        "call_forwarding_number": CALL_FORWARDING_NUMBER,
        "call_forwarding_enabled": CALL_FORWARDING_ENABLED,
        "call_reject_enabled": CALL_REJECT_ENABLED,
        "call_notify_admin_enabled": CALL_NOTIFY_ADMIN_ENABLED,
        "call_reply_caller_enabled": CALL_REPLY_CALLER_ENABLED,
        "call_reply_caller_text": CALL_REPLY_CALLER_TEXT,
        "call_notify_admin_text": CALL_NOTIFY_ADMIN_TEXT,
        "ota_repo": OTA_REPO,
        "ota_bundle_url": OTA_BUNDLE_URL,
        "ota_stability_timeout_sec": OTA_STABILITY_TIMEOUT_SEC,
        "ota_check_on_boot": OTA_CHECK_ON_BOOT,
    }


def load_config(config_path: str = "config.json") -> dict:
    """Load configuration with overrides from config_local.py, config.local.py, or config.json if available."""
    # First detect if a specific board_profile is requested
    detected_profile = DEFAULT_BOARD_PROFILE

    try:
        import config_local  # type: ignore[import-not-found]

        if hasattr(config_local, "BOARD_PROFILE"):
            detected_profile = getattr(config_local, "BOARD_PROFILE")  # noqa: B009
        elif hasattr(config_local, "board_profile"):
            detected_profile = getattr(config_local, "board_profile")  # noqa: B009
    except Exception:  # noqa: BLE001, S110
        pass

    try:
        with open("config.local.py") as f:
            code = f.read()
        local_scope = {}
        exec(code, local_scope)  # noqa: S102
        if "BOARD_PROFILE" in local_scope:
            detected_profile = local_scope["BOARD_PROFILE"]
        elif "board_profile" in local_scope:
            detected_profile = local_scope["board_profile"]
    except Exception:  # noqa: BLE001, S110
        pass

    try:
        with open(config_path, "r") as f:
            overrides = json.load(f)
            if isinstance(overrides, dict):
                for k, v in overrides.items():
                    if k.lower() == "board_profile" and isinstance(v, str):
                        detected_profile = v
    except Exception:  # noqa: BLE001, S110
        pass

    cfg = get_default_config(detected_profile)

    # Attempt 1: Load overrides from config_local module if present
    try:
        import config_local  # type: ignore[import-not-found]

        for key in cfg:
            upper_key = key.upper()
            if hasattr(config_local, upper_key):
                cfg[key] = getattr(config_local, upper_key)
            elif hasattr(config_local, key):
                cfg[key] = getattr(config_local, key)
    except Exception:  # noqa: BLE001, S110
        pass

    # Attempt 2: Load overrides from config.local.py file if present
    try:
        with open("config.local.py") as f:
            code = f.read()
        local_scope = {}
        exec(code, local_scope)  # noqa: S102
        for key in cfg:
            upper_key = key.upper()
            if upper_key in local_scope:
                cfg[key] = local_scope[upper_key]
            elif key in local_scope:
                cfg[key] = local_scope[key]
    except Exception:  # noqa: BLE001, S110
        pass

    # Attempt 3: Load overrides from config.json if present
    try:
        with open(config_path, "r") as f:
            overrides = json.load(f)
            if isinstance(overrides, dict):
                for k, v in overrides.items():
                    key_lower = k.lower()
                    if key_lower in cfg:
                        cfg[key_lower] = v
                    elif k in cfg:
                        cfg[k] = v
    except Exception:  # noqa: BLE001, S110
        pass

    return cfg


def save_config(updates: dict, config_path: str = "config.json") -> bool:
    """Safely persist configuration overrides to JSON file on device flash (Issue #61)."""
    valid_keys = get_default_config()
    existing: dict = {}

    # Load existing overrides if present
    try:
        with open(config_path, "r") as f:
            content = json.load(f)
            if isinstance(content, dict):
                existing = content
    except Exception:  # noqa: BLE001
        existing = {}

    # Merge verified updates
    for k, v in updates.items():
        k_lower = k.lower()
        if k_lower in valid_keys:
            existing[k_lower] = v

    # Write back to config file
    try:
        with open(config_path, "w") as f:
            json.dump(existing, f)
        print(f"[config] Saved configuration overrides to {config_path}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[config] Error saving configuration to {config_path}: {exc}")
        return False
