"""Example local configuration overrides for Lilygo T-Call A7670E gateway.

Copy this file to `config_local.py` or write to `config.json` on the ESP32 filesystem.
"""

WIFI_SSID = "Snippen-WiFi"
WIFI_PASSWORD = "SecretWiFiPassword"

SNIPPEN_API_BASE_URL = "https://vestreholmensameie.no/wp-json/snippen/v1"
SNIPPEN_API_TOKEN = "your-bearer-or-api-token-here"

OUTBOX_POLL_INTERVAL_SEC = 5
LONG_POLL_TIMEOUT_SEC = 25
INBOX_CHECK_INTERVAL_SEC = 5
HEARTBEAT_INTERVAL_SEC = 30

# Call Forwarding (Issue #110)
CALL_FORWARDING_NUMBER = "+4792830575"
CALL_FORWARDING_ENABLED = True
