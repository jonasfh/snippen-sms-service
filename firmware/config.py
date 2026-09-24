"""Configuration module for Snippen SMS Gateway on Lilygo T-Call A7670E (MicroPython)."""

try:
    import ujson as json
except ImportError:
    import json

# Hardware Pinout (Lilygo T-Call A7670E)
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
INBOX_CHECK_INTERVAL_SEC = 5
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


def get_default_config() -> dict:
    """Return dictionary of default system configuration."""
    return {
        "pin_modem_power": PIN_MODEM_POWER,
        "pin_modem_reset": PIN_MODEM_RESET,
        "pin_modem_pwrkey": PIN_MODEM_PWRKEY,
        "pin_modem_tx": PIN_MODEM_TX,
        "pin_modem_rx": PIN_MODEM_RX,
        "modem_uart_id": MODEM_UART_ID,
        "modem_baudrate": MODEM_BAUDRATE,
        "modem_uart_timeout_ms": MODEM_UART_TIMEOUT_MS,
        "modem_pwrkey_pulse_ms": MODEM_PWRKEY_PULSE_MS,
        "modem_boot_wait_sec": MODEM_BOOT_WAIT_SEC,
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
        "pin_boot_button": PIN_BOOT_BUTTON,
        "button_long_press_ms": BUTTON_LONG_PRESS_MS,
        "button_debounce_ms": BUTTON_DEBOUNCE_MS,
        "provisioning_timeout_sec": PROVISIONING_TIMEOUT_SEC,
        "call_forwarding_number": CALL_FORWARDING_NUMBER,
        "call_forwarding_enabled": CALL_FORWARDING_ENABLED,
    }


def load_config(config_path: str = "config.json") -> dict:
    """Load configuration with overrides from config_local.py, config.local.py, or config.json if available."""
    cfg = get_default_config()

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
