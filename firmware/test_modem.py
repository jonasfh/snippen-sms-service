"""MicroPython on-device cellular modem and SIM diagnostic test.

Executes AT handshake, queries modem model, SIM card ICCID, signal strength (CSQ),
cellular network registration (CREG), and reads current SIM SMS memory.
"""

try:
    import boot
except ImportError:
    boot = None

from config import load_config
from modem import ModemDriver


def run_modem_test() -> bool:
    """Execute cellular modem diagnostic test on Lilygo T-Call A7670E."""
    cfg = load_config()

    print("========================================")
    print(" Lilygo A7670E Cellular Modem Diagnostics")
    print("========================================")

    # 1. Hardware verification / power
    uart = None
    if boot is not None:
        try:
            if boot.modem_uart is None:
                print("[test_modem] Powering on modem via boot sequence...")
                boot.power_on_modem(cfg)
                uart = boot.init_uart(cfg)
            else:
                uart = boot.modem_uart
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ Boot initialization exception: {exc}")

    driver = ModemDriver(uart=uart, config=cfg)

    # 2. AT Communication Handshake
    print("[test_modem] Testing AT handshake with SimCom A7670E...", end="")
    if not driver.check_at(retries=5, delay_ms=500):
        print(" ❌ FEIL")
        print("Modemet svarer ikke på AT-kommandoer over UART.")
        print(
            "Sjekk at aktiv USB-hub leverer tilstrekkelig strøm (2A-3A) og at GPIO 12/5/4 er tilkoblet."
        )
        return False
    print(" ✅ OK")

    # 3. Initialize modem modes
    print("[test_modem] Konfigurerer ekko, SMS-tekstmodus og tegnsett...", end="")
    if driver.init_modem():
        print(" ✅ OK")
    else:
        print(" ⚠️ Advarsel under modem-init")

    # 4. Hardware Identity (ATI & CCID)
    info = driver.get_modem_info()
    model = info.get("model", "Ukjent")
    iccid = info.get("iccid", "Ikke tilgjengelig")
    print(f"   Modell:       {model}")
    print(f"   SIM ICCID:    {iccid}")

    # 5. Signal Quality (CSQ)
    sig = driver.get_signal_quality()
    if sig is not None:
        dbm_str = f"{sig['dbm']} dBm" if sig.get("dbm") is not None else "Ukjent"
        rssi = sig["rssi"]
        quality = (
            "Utmerket"
            if rssi >= 20
            else ("God" if rssi >= 12 else ("Svak" if rssi >= 6 else "Kritisk lav"))
        )
        print(f"   Signalstyrke: RSSI {rssi} ({dbm_str}) - {quality}")
    else:
        print("   Signalstyrke: ⚠️ Kunne ikke hente signal (AT+CSQ)")

    # 6. Network Registration (CREG)
    reg = driver.get_network_registration()
    if reg is not None:
        reg_status = (
            "✅ Tilkoblet mobilnettet" if reg["registered"] else "❌ Ikke registrert på nett"
        )
        print(f"   Nettstatus:   {reg_status} ({reg.get('description')})")
    else:
        print("   Nettstatus:   ⚠️ Kunne ikke hente nettregistrering (AT+CREG?)")

    # 7. SMS Memory Inspection
    print("[test_modem] Inspiserer SIM-kortets SMS-minne (uten sletting)...")
    try:
        messages = driver.read_inbound_sms(delete_after_read=False)
        print(f"   Meldinger på SIM-kort: {len(messages)} stk")
        for m in messages:
            print(f"   - [Indeks {m['index']}] Fra {m['sender']} ({m['timestamp']}): {m['body']}")
    except Exception as exc:  # noqa: BLE001
        print(f"   ⚠️ Feil ved lesing av SMS-minne: {exc}")

    print("========================================")
    print("✅ Modemdiagnostikk fullført.")
    print("========================================")
    return True


if __name__ == "__main__":
    run_modem_test()
