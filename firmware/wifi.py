"""MicroPython WiFi manager for Lilygo T-Call ESP32 (Issue #61).

Handles WiFi scanning, connection verification, and network management.
"""

try:
    import network  # type: ignore[import-not-found]
except ImportError:
    network = None  # type: ignore[assignment]

try:
    import utime as time  # type: ignore[import-not-found]
except ImportError:
    import time  # type: ignore[no-redef]


def get_wlan() -> object | None:
    """Return initialized STA_IF WLAN interface."""
    if network is None:
        return None
    wlan = network.WLAN(network.STA_IF)
    if not wlan.active():
        wlan.active(True)
    return wlan


def scan_networks(max_results: int = 10, min_rssi: int = -85) -> list[dict]:
    """Scan for available 2.4 GHz WiFi networks.

    Args:
        max_results: Maximum number of networks to return (default 10).
        min_rssi: Minimum signal strength in dBm to filter out unusable/distant networks.

    Returns:
        List of dicts sorted by RSSI descending:
        [{"ssid": "MyWiFi", "rssi": -55, "auth": 3}, ...]
    """
    wlan = get_wlan()
    if wlan is None:
        print("[wifi] Warning: network.WLAN interface unavailable.")
        return []

    # If STA is currently in a connecting state, disconnect first so radio can scan all channels
    if hasattr(wlan, "isconnected") and not wlan.isconnected():
        try:
            wlan.disconnect()
            if hasattr(time, "sleep_ms"):
                time.sleep_ms(150)
            else:
                time.sleep(0.15)
        except Exception:  # noqa: BLE001, S110
            pass

    print("[wifi] Scanning 2.4 GHz WiFi channels (1-13)...")
    try:
        raw_results = wlan.scan()
        print(f"[wifi] Scan completed: found {len(raw_results)} access points")
    except Exception as exc:  # noqa: BLE001
        print(f"[wifi] Error during network scan: {exc}")
        return []

    networks: list[dict] = []
    seen_ssids: set[str] = set()

    for item in raw_results:
        if len(item) < 4:
            continue
        ssid_raw = item[0]
        if isinstance(ssid_raw, (bytes, bytearray)):
            ssid = ssid_raw.decode("utf-8", "ignore").strip()
        else:
            ssid = str(ssid_raw).strip()

        if not ssid or ssid in seen_ssids:
            continue
        seen_ssids.add(ssid)

        rssi = item[3]
        auth_mode = item[4] if len(item) > 4 else 0

        networks.append(
            {
                "ssid": ssid,
                "rssi": rssi,
                "auth": auth_mode,
            }
        )

    # Sort networks with highest signal strength (less negative RSSI) first
    networks.sort(key=lambda x: x.get("rssi", -100), reverse=True)

    # Filter out weak signals (< min_rssi) to keep BLE payload compact, unless all are weak
    filtered = [n for n in networks if n.get("rssi", -100) >= min_rssi]
    if filtered:
        networks = filtered

    return networks[:max_results]


def test_connection(ssid: str, password: str = "", timeout_sec: int = 15) -> dict:
    """Test connection to WiFi access point without permanently changing network state.

    Returns:
        dict with status ('ok' or 'failed'), connection flag, and assigned IP if successful.
    """
    wlan = get_wlan()
    if wlan is None:
        return {"status": "error", "connected": False, "message": "network.WLAN is unavailable"}

    if not ssid:
        return {"status": "error", "connected": False, "message": "SSID cannot be empty"}

    print(f"[wifi] Testing connection to SSID '{ssid}' (timeout {timeout_sec}s)...")
    was_connected = wlan.isconnected()
    if was_connected:
        wlan.disconnect()

    wlan.connect(ssid, password)
    start = time.time()
    while not wlan.isconnected() and (time.time() - start) < timeout_sec:
        time.sleep(0.5)

    if wlan.isconnected():
        ip, mask, gateway, dns = wlan.ifconfig()
        print(f"[wifi] Connection test successful. Assigned IP: {ip}")
        return {
            "status": "ok",
            "connected": True,
            "ssid": ssid,
            "ip": ip,
            "netmask": mask,
            "gateway": gateway,
            "dns": dns,
        }

    status_code = wlan.status() if hasattr(wlan, "status") else 0
    print(f"[wifi] Connection test failed (status code: {status_code})")
    return {
        "status": "failed",
        "connected": False,
        "ssid": ssid,
        "error_code": status_code,
        "message": "Connection timed out or credentials invalid",
    }


def connect_wifi(ssid: str, password: str = "", timeout_sec: int = 20) -> bool:
    """Connect to configured WiFi network for active gateway operation."""
    wlan = get_wlan()
    if wlan is None:
        return False

    if not ssid:
        print("[wifi] Error: No WiFi SSID configured.")
        return False

    if wlan.isconnected():
        print(f"[wifi] Already connected. IP: {wlan.ifconfig()[0]}")
        return True

    print(f"[wifi] Connecting to '{ssid}'...")
    wlan.connect(ssid, password)
    start = time.time()
    while not wlan.isconnected() and (time.time() - start) < timeout_sec:
        time.sleep(1)

    if wlan.isconnected():
        print(f"[wifi] Connected successfully! IP: {wlan.ifconfig()[0]}")
        return True

    print("[wifi] Failed to connect within timeout.")
    return False


def is_connected() -> bool:
    """Check if WiFi station interface is active and connected."""
    if network is None:
        return False
    try:
        wlan = network.WLAN(network.STA_IF)
        return wlan.isconnected()
    except Exception:  # noqa: BLE001
        return False


def start_connect(ssid: str, password: str = "") -> bool:
    """Initiate WiFi connection in background without blocking."""
    wlan = get_wlan()
    if wlan is None or not ssid:
        return False
    if wlan.isconnected():
        return True
    try:
        wlan.connect(ssid, password)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[wifi] Non-blocking connect error: {exc}")
        return False


def ensure_connected(ssid: str, password: str = "", timeout_sec: int = 15) -> bool:
    """Ensure WiFi is connected, connecting synchronously if currently disconnected."""
    if is_connected():
        return True
    return connect_wifi(ssid, password, timeout_sec=timeout_sec)
