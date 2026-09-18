"""MicroPython on-device Snippen API connectivity test."""

import network

try:
    import urequests as requests
except ImportError:
    try:
        import requests
    except ImportError:
        requests = None  # type: ignore[assignment]

try:
    from config import load_config
except ImportError:

    def load_config():  # type: ignore[misc]
        return {}


def run_api_test() -> bool:
    """Execute Snippen API ping test from ESP32."""
    cfg = load_config()
    api_url = cfg.get("snippen_api_base_url", "https://vestreholmensameie.no/wp-json/snippen/v1")
    token = cfg.get("snippen_api_token", "")

    print("========================================")
    print(" Lilygo ESP32 Snippen API Ping Test")
    print("========================================")

    # 1. Check WiFi status
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        print("❌ FEIL: ESP32 er ikke tilkoblet WiFi!")
        print("Kjør 'python scripts/test_wifi.py' først for å koble til nettverket.")
        return False

    ip = wlan.ifconfig()[0]
    print(f"WiFi er tilkoblet (IP: {ip}).")
    print(f"Mål-URL: {api_url}")

    if requests is None:
        print("❌ FEIL: 'urequests'-modulen er ikke tilgjengelig.")
        return False

    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-API-Key"] = token

    try:
        outbox_url = api_url.rstrip("/") + "/sms/outbox"
        print(f"Sender GET-forespørsel mot beskyttet endepunkt: {outbox_url}...")
        res = requests.get(outbox_url, headers=headers)
        print(f"Statuskode: {res.status_code}")
        text = res.text[:200]
        print(f"Svar (første 200 tegn): {text}")
        if res.status_code == 200:
            print("✅ Autentisering og kommunikasjon mot Snippen Booking er VELLYKKET!")
            print("   Token ble godkjent av WordPress, og utboksen er tilgjengelig.")
            return True
        elif res.status_code in (401, 403):
            print("❌ Autentisering FEIL: Token ble avvist av serveren (HTTP 401/403).")
            return False

        print(f"⚠️ Uventet statuskode fra server: {res.status_code}")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Tilkoblingsfeil mot {api_url}: {exc}")
        print("Tips ved lokal testing med tunnel:")
        print(" - Er Cloudflare-tunnelen eller ngrok aktiv på maskinen din?")
        print(" - Er URL-en i config_local.py oppdatert med riktig tunnel-adresse?")
        return False


if __name__ == "__main__":
    run_api_test()
