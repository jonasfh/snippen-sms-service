# Snippen SMS Gateway (Lilygo T-Call A7670E)

Toveis SMS-gateway for bookingsystemet på Snippen grendehus, bygget på Lilygo T-Call A7670E (ESP32-mikrokontroller med SimCom A7670E 4G/LTE-modem).

---

## 1. Maskinvarekrav og Strømforsyning (Kritisk!)

LTE-modemet (A7670E) trekker brå strømpulser (transienter) på opptil **2A** under boot, radiosjekk og SMS-sending.
* **Under utvikling på PC/laptop:** Må kobles til via en **aktiv USB-hub** (med egen 5V 2A–3A / 15W strømadapter). Standard USB-porter på datamaskiner leverer ofte kun 500 mA, noe som fører til brownout og feilen `+CME ERROR: SIM not inserted`.
* **Frittstående drift:** Benytt en stabil 5V / 2A–3A USB-strømforsyning (f.eks. Raspberry Pi USB-C strømforsyning eller mobillader).

---

## 2. Installasjon av verktøy (Ubuntu / Linux)

### Virtuelt miljø og pakker
Sett opp et virtuelt Python-miljø og installer `esptool` og `mpremote`:

```bash
# Opprett og aktiver et virtuelt miljø
python3 -m venv env
source env/bin/activate

# Installer esptool (flashing) og mpremote (REPL / filoverføring)
pip install esptool mpremote
```

### Serieport-rettigheter (Linux Host)
Gi brukeren tilgang til serieportene:

```bash
sudo usermod -aG dialout $USER
newgrp dialout
```

### Utvikling i Dev Container (Docker)
For at containeren skal få tilgang til USB-serieporter dynamisk fra Linux-hosten:
1. `.devcontainer/devcontainer.json` må ha `runArgs`: `["--privileged", "-v", "/dev:/dev"]`.
2. Brukeren `vscode` må legges til i `dialout`-gruppen (`sudo usermod -aG dialout vscode`).
3. `esptool`, `mpremote` og `pyserial` er inkludert i prosjektets `dev`-avhengigheter i `pyproject.toml`.

---

## 3. Finne enhet (Device Info)

Koble Lilygo-kortet via den aktive huben og finn tildelt enhetssti:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM*
```
*(Dukker normalt opp som `/dev/ttyACM0` eller `/dev/ttyUSB0`)*.

Verifiser kontakt mot brikken:

```bash
esptool.py --port /dev/ttyACM0 chip_id
```

---

## 4. Flashing av MicroPython

Benyttet firmware: `ESP32_GENERIC-SPIRAM-20260824-v1.29.0.bin` (støtter ESP32 med eksternt PSRAM).

1. Tøm eksisterende flashminne:
   ```bash
   esptool.py --port /dev/ttyACM0 erase_flash
   ```

2. Flash MicroPython:
   ```bash
   esptool.py --port /dev/ttyACM0 --baud 460800 write_flash -z 0x1000 ESP32_GENERIC-SPIRAM-20260824-v1.29.0.bin
   ```

---

## 5. Kople til MicroPython REPL

Koble til det interaktive MicroPython-skallet:

```bash
mpremote connect /dev/ttyACM0 repl
```

* **Avslutte REPL:** Trykk `Ctrl` + `]`
* **Avbryte kjørende skript:** Trykk `Ctrl` + `C`

---

## 6. Verifisert Pinout (Lilygo T-Call A7670)

| Funksjon | GPIO-pin | Beskrivelse |
| :--- | :--- | :--- |
| **Modem VCC (Power)** | `GPIO 12` | Må settes `HIGH (1)` for å mate strømskinnen til modemet |
| **Modem Reset** | `GPIO 5` | Aktiv lav internt, holdes `HIGH (1)` ved drift |
| **Modem PWRKEY** | `GPIO 4` | Pulses `HIGH (1)` i 1,5 sek for å slå på modemet |
| **ESP32 TX (Modem RX)**| `GPIO 26` | Seriedata ut fra ESP32 |
| **ESP32 RX (Modem TX)**| `GPIO 25` | Seriedata inn til ESP32 |

---

## 7. Oppstart og Diagnostikk i REPL

Lim inn følgende kode i REPL (`>>>`) for å starte modemet og verifisere SIM-status og dekning:

```python
import time
from machine import UART, Pin

# 1. Definer kontroll-pinner
pwr_on = Pin(12, Pin.OUT)
rst = Pin(5, Pin.OUT)
pwrkey = Pin(4, Pin.OUT)

# 2. Skru på strøm og kjør PWRKEY-puls
rst.value(1)
pwr_on.value(1)
time.sleep_ms(100)

pwrkey.value(1)
time.sleep_ms(1500)
pwrkey.value(0)

print("Venter på boot...")
time.sleep(6)

# 3. Konfigurer UART
uart = UART(1, baudrate=115200, tx=Pin(26), rx=Pin(25), timeout=2000)


def cmd(c, wait=400):
    uart.read()
    uart.write((c + "\r\n").encode())
    time.sleep_ms(wait)
    res = uart.read()
    print(f"{c} -> {res.decode('utf-8', 'ignore').strip() if res else 'None'}")


# 4. Sjekk modem og SIM-status
cmd("ATI")  # Modell & IMEI (f.eks. A7670E-FASE)
cmd("AT+CPIN?")  # Returnerer '+CPIN: SIM PIN' (hvis låst) eller '+CPIN: READY'
cmd('AT+CPIN="0129"')  # Tast inn PIN-kode ved behov
time.sleep(2)
cmd("AT+CCID")  # Leser SIM-kortets ICCID
cmd("AT+CSQ")  # Signalstyrke (> 10-12 er bra, f.eks. 20-21 er utmerket)
cmd("AT+CREG?")  # Registrering (+CREG: 0,1 betyr registrert på hjemmenett)
cmd("AT+COPS?")  # Aktiv teleoperatør (f.eks. Telia Norge: "24202", 4G: 7)
```

### Deaktivere PIN-kodelås permanent (Anbefalt)
For at modemet automatisk skal koble seg til 4G etter strømbrudd eller reboot:
1. Lås opp SIM: `AT+CPIN="<pin>"`
2. Sjekk gjeldende låsstatus: `AT+CLCK="SC",2` (`+CLCK: 1` betyr aktiv)
3. Deaktiver PIN-lås: `AT+CLCK="SC",0,"<pin>"` (returnerer `OK`)
4. Verifiser at lås er deaktivert: `AT+CLCK="SC",2` (skal nå returnere `+CLCK: 0`)

---

## 8. Lese og sende SMS via AT-kommandoer

### Sende SMS (Verifisert sekvens)
```python
def send_sms(number, text):
    uart.read()
    # Sett tekstmodus og tegnsett
    cmd("AT+CMGF=1")
    cmd('AT+CSCS="GSM"')

    # Start sending mot mottakernummer
    uart.write(f'AT+CMGS="{number}"\r\n'.encode())

    # Vent på '>' prompt fra modemet
    prompt_found = False
    for _ in range(20):
        time.sleep_ms(100)
        data = uart.read()
        if data and b">" in data:
            prompt_found = True
            break

    # Send meldingstekst avsluttet med Ctrl+Z (\x1A)
    uart.write((text + "\x1a").encode())

    # Vent på leveringsbekreftelse (+CMGS: <id> og OK)
    full_res = ""
    for _ in range(20):
        time.sleep_ms(500)
        data = uart.read()
        if data:
            full_res += data.decode("utf-8", "ignore")
            if "OK" in full_res or "ERROR" in full_res:
                break
    print("Send-status:", full_res.strip())


# Eksempel:
# send_sms("+47XXXXXXXX", "Testmelding fra Snippen SMS Gateway")
```

> [!NOTE]
> **Tegnsett og emojis i tekstmodus (`AT+CSCS="GSM"`):**
> I standard GSM-7 tekstmodus støttes ikke 4-bytes UTF-8 emojis (f.eks. 🤖). Forsøk på å sende emojis eller meldinger over 160 tegn i ren tekstmodus gir feilen `+CMS ERROR: SMS size more than expected`. For bookingbekreftelser og koder bør meldinger holdes i ren ASCII/GSM-7 (eller benytte PDU/UCS-2 modus dersom spesialtegn er strengt nødvendig).

### Lese SMS
```python
# Sett SMS til tekstmodus og tegnsett
cmd("AT+CMGF=1")
cmd('AT+CSCS="GSM"')

# Les alle meldinger
cmd('AT+CMGL="ALL"')

# Les kun melding med indeks 1
cmd("AT+CMGR=1")

# Slett melding 1 for å unngå at SIM-minnet fylles opp
cmd("AT+CMGD=1")
```

---

## 9. Målarkitektur: Standalone IoT Gateway (Uten Raspberry Pi)

Lilygo T-Call A7670E fungerer som en **100% frittstående SMS-gateway** plugget rett i en standard 5V USB-lader i veggen på Snippen grendehus:

```
[ Snippen Booking (WordPress) ]
  https://vestreholmensameie.no/wp-json/snippen/v1/
        ▲                       │
        │ Inbound SMS (POST)    │ Long-poll Outbox (GET)
        │ Delivery status       │
        │                       ▼
┌───────────────────────────────────────────────┐
│     Lilygo T-Call A7670E (Standalone IoT)     │
│                                               │
│  ┌─────────────────────────────────────────┐  │
│  │               ESP32 MCU                 │  │
│  │  - WiFi Manager (Auto-reconnect)        │  │
│  │  - Snippen REST API Client (HTTPS)      │  │
│  │  - Outbox Long-Polling Loop             │  │
│  │  - Inbound Delivery Forwarder           │  │
│  │  - AT Command Engine & SIM Manager      │  │
│  │  - Watchdog & Health Monitor            │  │
│  └──────────────────┬──────────────────────┘  │
│                     │ UART (GPIO 26/25)       │
│  ┌──────────────────▼──────────────────────┐  │
│  │         SimCom A7670E 4G LTE            │  │
│  │  - Power: GPIO 12 / Reset: GPIO 5       │  │
│  │  - PWRKEY: GPIO 4                       │  │
│  │  - Cellular SMS Transmission (Telia 4G) │  │
│  └──────────────────┬──────────────────────┘  │
└─────────────────────┼─────────────────────────┘
                      │
              [ Cellular Network ]
                      │
               [ End User / Guest ]
```

### Hovedprinsipper for firmwaren:
1. **Frittstående drift:** Krever ingen ekstern PC eller Raspberry Pi. Ingen Linux OS-oppdateringer, ingen SD-kortfeil, og minimalt strømforbruk (~1W).
2. **WiFi mot Sameiets nettside:** Kobler seg på det lokale trådløse nettverket på Snippen grendehus og kommuniserer med `https://vestreholmensameie.no` over kryptert HTTPS.
3. **Long Polling for utgående meldinger:** ESP32-en sender en "hanging GET" (med f.eks. 20-30 sekunders timeout) mot Snippen Booking sitt outbox-endepunkt. Så fort en SMS opprettes i WordPress, returnerer kallet umiddelbart, og ESP32 sender meldingen ut over 4G på brøkdelen av et sekund.
4. **Umiddelbar levering av innkommende meldinger:** Når en gjest svarer på en SMS, leses meldingen ut fra SIM-minnet over UART, postes direkte til `/wp-json/snippen/v1/sms/inbound`, og slettes deretter fra SIM-kortet for å unngå at minnet fylles opp.
5. **All forretningslogikk i WordPress:** ESP32 utfører kun maskinvare-oppgaver (WiFi-forbindelse, API-kall og SMS-transport). All bookinglogikk, adgangskoder, og gjestedialog håndteres av Snippen Booking-pluginet.

---

## 10. Firmware-struktur og Utviklingsflyt (`firmware/`)

MicroPython-firmwaren ligger i `firmware/` og er adskilt fra vertsbiblioteket `src/snippen_sms/`:

```
firmware/
├── ble_config.py      # BLE GATT provisioning-server og annonsering for trådløst oppsett
├── boot.py            # Maskinvareinit, modem power rail (GPIO 12), reset (GPIO 5), PWRKEY-puls (GPIO 4), UART1
├── button.py          # BOOT-knapp (GPIO 0) inngangshåndtering med debouncing og 3s langt trykk
├── config.py          # Systemoppsett, pinouts, tidsavbrudd og API-konfigurasjon
├── config.example.py  # Mal for lokale overstyringer (WiFi-passord og API-nøkkel)
├── modem.py           # SimCom A7670E modemdriver: AT-motor, SMS sending/mottak, signal (CSQ), CREG og SIM-minne
├── main.py            # GatewayApp-hovedløkke: WiFi-status, outbox-polling, SMS-sjekk og heartbeat
├── wifi.py            # WiFi scanning, tilkoblingsverifisering og nettverkshåndtering
├── test_api.py        # Diagnosetest for Snippen API autentisering
├── test_ble_provisioning.py # Interaktiv diagnosetest for BLE provisioning
├── test_modem.py      # Diagnosetest for A7670E cellular modem, dekning og SIM SMS-minne
└── test_wifi.py       # Diagnosetest for WiFi-tilkobling
```

Se også **[docs/BLE_MANUAL_TESTING.md](file:///workspaces/snippen-sms-service/docs/BLE_MANUAL_TESTING.md)** for en komplett steg-for-steg guide til manuell testing via mobilapper som nRF Connect.

### Automatisert Deployment med `mpremote`
Skriptet `scripts/deploy_firmware.py` automatiserer overføring og administrasjon via `mpremote`:

```bash
# 1. Installer / oppdater firmwarefiler på ESP32 (med automatisk soft-reset)
python scripts/deploy_firmware.py deploy

# 2. Deploy med egne lokale innstillinger (config_local.py eller config.json)
python scripts/deploy_firmware.py deploy --include-config

# 3. Inspiser filer på mikrokontrolleren
python scripts/deploy_firmware.py ls

# 4. Åpne MicroPython REPL interaktivt
python scripts/deploy_firmware.py repl

# 5. Nullstill mikrokontrolleren (soft eller hard reset)
python scripts/deploy_firmware.py reset
python scripts/deploy_firmware.py reset --hard

# 6. Testkjøre et skript på enheten uten permanent overføring
python scripts/deploy_firmware.py run firmware/main.py
```

### On-Device Diagnosetester mot Fysisk Maskinvare

Når Lilygo er koblet til via USB (`/dev/ttyACM0`), kan diagnostiske tester kjøres direkte mot mikrokontrolleren og 4G-modemet:

```bash
# Test 4G-modem, AT-kommunikasjon, signalstyrke (CSQ), nettregistrering (CREG) og SIM SMS-minne:
python scripts/test_modem_live.py

# Test WiFi-tilkobling mot lokalt nettverk:
python scripts/test_wifi.py

# Test REST API-kommunikasjon mot Snippen Booking:
python scripts/test_api_ping.py
```

### Automatiserte Tester og Mocks
Firmwarekoden er testet med standard `pytest` under CPython ved hjelp av mikrokontroller-mocking i `tests/mocks/micropython_mocks.py` (som mocker `machine.Pin`, `machine.UART`, `utime`, `network.WLAN` etc.):

```bash
pytest tests/test_firmware_*.py tests/test_diagnostic_scripts.py tests/test_deploy_firmware.py -v
```
