"""MicroPython on-device WiFi connection diagnostic test."""

try:
    import utime as time
except ImportError:
    import time

import network

try:
    from config import load_config
except ImportError:

    def load_config():  # type: ignore[misc]
        return {}


def run_wifi_test() -> bool:
    """Execute WiFi connection test on ESP32."""
    cfg = load_config()
    ssid = cfg.get("wifi_ssid", "")
    password = cfg.get("wifi_password", "")
    timeout_sec = cfg.get("wifi_connect_timeout_sec", 20)

    print("========================================")
    print(" Lilygo ESP32 WiFi Diagnostic Test")
    print("========================================")

    if not ssid:
        print("❌ FEIL: wifi_ssid er ikke konfigurert!")
        print("Vennligst opprett firmware/config_local.py eller config.local.py")
        print("med WIFI_SSID og WIFI_PASSWORD.")
        return False

    print(f"Konfigurert SSID: {ssid}")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("Allerede tilkoblet!")
    else:
        print(f"Kobler til WiFi '{ssid}' (timeout {timeout_sec}s)...", end="")
        wlan.connect(ssid, password)

        start = time.time()
        while not wlan.isconnected() and (time.time() - start) < timeout_sec:
            print(".", end="")
            time.sleep(1)
        print()

    if wlan.isconnected():
        ip, mask, gateway, dns = wlan.ifconfig()
        print("✅ WiFi-tilkobling VELLYKKET!")
        print(f"   IP-adresse:   {ip}")
        print(f"   Nettmaske:    {mask}")
        print(f"   Gateway:      {gateway}")
        print(f"   DNS-tjener:   {dns}")
        return True

    status = wlan.status()
    print(f"❌ Kunne ikke koble til WiFi (status: {status}).")
    print("Tips:")
    print(" - Sjekk at SSID og passord er stavet riktig.")
    print(" - Sjekk at nettverket er 2.4 GHz (ESP32 støtter ikke 5 GHz WiFi).")
    return False


if __name__ == "__main__":
    run_wifi_test()
