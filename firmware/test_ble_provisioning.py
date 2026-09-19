"""On-device interactive manual test for BLE provisioning (Issue #61).

Allows manual end-to-end testing with generic BLE scanner apps like nRF Connect for Mobile.
Run on device via:
    python scripts/test_ble_live.py [--port /dev/ttyACM0]
    or
    python scripts/deploy_firmware.py run firmware/test_ble_provisioning.py
"""

try:
    import utime as time  # type: ignore[import-not-found]
except ImportError:
    import time  # type: ignore[no-redef]

try:
    import wifi
    from ble_config import (
        CHAR_COMMAND_UUID_STR,
        CHAR_CONFIG_UUID_STR,
        CHAR_STATUS_UUID_STR,
        SERVICE_UUID_STR,
        BLEConfigServer,
    )
    from button import ButtonHandler
    from config import load_config, save_config
except ImportError as exc:
    print(f"[test_ble] Import error: {exc}")


def run_manual_ble_test() -> None:
    """Run interactive manual BLE provisioning test on Lilygo ESP32."""
    cfg = load_config()

    print("================================================================")
    print("      Snippen SMS Gateway - BLE Provisioning Manual Test        ")
    print("================================================================")

    def on_command(cmd: str, payload: dict) -> dict:
        print(f"\n[BLE-CMD] Received command: '{cmd}' (payload: {payload})")
        if cmd == "SCAN_WIFI":
            print("[BLE-CMD] Initiating WiFi scan...")
            networks = wifi.scan_networks()
            print(f"[BLE-CMD] Found {len(networks)} networks:")
            for n in networks:
                print(f"   - {n.get('ssid')} (RSSI: {n.get('rssi')} dBm, Auth: {n.get('auth')})")
            return {"cmd": "SCAN_WIFI", "status": "ok", "networks": networks}

        if cmd == "TEST_WIFI":
            ssid = payload.get("wifi_ssid") or cfg.get("wifi_ssid", "")
            password = payload.get("wifi_password") or cfg.get("wifi_password", "")
            print(f"[BLE-CMD] Testing WiFi connection to '{ssid}'...")
            res = wifi.test_connection(ssid, password)
            print(f"[BLE-CMD] Result: {res.get('status')} (IP: {res.get('ip', 'none')})")
            return {"cmd": "TEST_WIFI", **res}

        if cmd in ("APPLY_AND_EXIT", "SAVE_CONFIG"):
            print("[BLE-CMD] Saving configuration to config.json...")
            save_config(cfg)
            return {"cmd": cmd, "status": "ok", "message": "Configuration saved"}

        return {"cmd": cmd, "status": "ok"}

    def on_config_received(new_cfg: dict) -> None:
        print(f"\n[BLE-CFG] Received configuration write: {new_cfg}")
        cfg.update(new_cfg)
        save_config(new_cfg)
        print("[BLE-CFG] Config saved to config.json successfully.")

    server = BLEConfigServer(
        config=cfg,
        timeout_sec=600,  # 10 minutes for manual testing
        on_command=on_command,
        on_config_received=on_config_received,
    )

    if not server.start():
        print("❌ FEIL: Kunne ikke starte BLE-server.")
        return

    # Button handler
    btn = ButtonHandler(
        pin_id=cfg.get("pin_boot_button", 0),
        on_long_press=lambda: print("\n[BUTTON] BOOT button long-press detected!"),
        on_short_press=lambda: print("\n[BUTTON] BOOT button short click detected!"),
    )

    print("\n✅ BLE Provisioning Server kjører!")
    print(f"📡 Enhetsnavn (Local Name):    {server.device_name}")
    print(f"🔗 Service UUID:               {SERVICE_UUID_STR}")
    print(f"⚙️  Config Characteristic:     {CHAR_CONFIG_UUID_STR} (Read/Write)")
    print(f"📊 Status Characteristic:     {CHAR_STATUS_UUID_STR} (Read/Notify)")
    print(f"🎮 Command Characteristic:    {CHAR_COMMAND_UUID_STR} (Write/Notify)")
    print("\n---------------- Instruksjoner for testing i nRF Connect ----------------")
    print("1. Åpne 'nRF Connect for Mobile' på telefonen din.")
    print(f"2. Søk etter enheten '{server.device_name}' og trykk 'Connect'.")
    print(f"3. Finn servicen ({SERVICE_UUID_STR}).")
    print(f"4. Trykk på pilene (Subscribe) for Status ({CHAR_STATUS_UUID_STR[:8]}...)")
    print(f"   og Command ({CHAR_COMMAND_UUID_STR[:8]}...) for å motta svar.")
    print("5. Test WiFi-scan:")
    print("   Skriv UTF-8 streng til Command-karakteristikken:")
    print('   {"cmd":"SCAN_WIFI"}')
    print("   Se at listen over WiFi-nettverk varsles tilbake som JSON!")
    print("6. Test konfigurasjon:")
    print("   Les Config-karakteristikken for å se maskert token.")
    print("   Skriv JSON til Config-karakteristikken med wifi_ssid og wifi_password.")
    print("7. Trykk Ctrl+C i terminalen for å avslutte testen.")
    print("-------------------------------------------------------------------------\n")

    try:
        cycle = 0
        while True:
            cycle += 1
            btn.poll()
            server.poll()

            # Stream telemetry every 5 seconds if connected
            if server.conn_handle is not None and (cycle % 10 == 0):
                server.notify_status({"status": "connected", "cycle": cycle, "alive": True})

            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n[test_ble] Stopper BLE server...")
    finally:
        server.stop()
        print("[test_ble] Test avsluttet.")


if __name__ == "__main__":
    run_manual_ble_test()
