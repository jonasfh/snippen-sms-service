# Manual Testveiledning: BLE Provisioning med nRF Connect for Mobile

Dette dokumentet beskriver hvordan du tester Bluetooth Low Energy (BLE) konfigurasjon og provisjonering av Snippen SMS Gateway (Lilygo T-Call A7670E ESP32) fra en smarttelefon ved hjelp av standardappen **nRF Connect for Mobile** (tilgjengelig for Android og iOS).

---

## 1. Forberedelser og Oppstart

### Alternativ A: Kjøre interaktiv test direkte
Koble Lilygo ESP32 til PC-en med USB-kabel og kjør:

```bash
python scripts/test_ble_live.py
```
Dette kopierer de nyeste firmware-modulene over og starter den interaktive BLE-serveren med utvidet logging i terminalen.

### Alternativ B: Teste normal gateway-kjøring
Hvis hele firmwaren er deployet (`python scripts/deploy_firmware.py deploy`):
1. Hold inne **`BOOT`-knappen (GPIO 0)** på Lilygo-kortet i **3 sekunder**.
2. Terminalen/LED indikerer at enheten har gått inn i provisioning-modus og har startet BLE-annonsering.

---

## 2. BLE Service og Karakteristikker

| Navn | UUID | Tillatelser | Beskrivelse |
| :--- | :--- | :--- | :--- |
| **Snippen Provisioning Service** | `6e400001-b5a3-f393-e0a9-e50e24dcca9e` | Primary Service | Hovedtjeneste for oppsett |
| **Config Characteristic** | `6e400002-b5a3-f393-e0a9-e50e24dcca9e` | **Read / Write** | Lese aktiv config (maskert token) og skrive nye innstillinger |
| **Status Characteristic** | `6e400003-b5a3-f393-e0a9-e50e24dcca9e` | **Read / Notify** | Sanntidstelemetri (tilkobling, IP, 4G-signalstyrke) |
| **Command Characteristic** | `6e400004-b5a3-f393-e0a9-e50e24dcca9e` | **Write / Notify** | Sende kommandoer (`SCAN_WIFI`, `TEST_WIFI`, etc.) og motta svar |

---

## 3. Steg-for-steg testing i nRF Connect

### Steg 1: Skann og koble til
1. Åpne **nRF Connect** på telefonen og velg fanen **SCANNER**.
2. Finn enheten som heter **`Snippen-SMS-XXXX`** (der `XXXX` er de siste 4 tegnene i MAC-adressen).
3. Trykk på **CONNECT**.

### Steg 2: Aktiver Notifications (Varsler)
1. Finn tjenesten med UUID som starter på `6e400001-...`.
2. Trykk på **tre små piler / Subscribe-ikonet** ved siden av:
   - **Status Characteristic** (`6e400003-...`)
   - **Command Characteristic** (`6e400004-...`)
3. Dette sikrer at telefonen din mottar asynkrone svar og telemetri fra ESP32-en.

### Steg 3: Test WiFi-skanning (`SCAN_WIFI`)
1. Trykk på **Pil opp (Write)** på **Command Characteristic** (`6e400004-...`).
2. Velg **UTF-8** som datatype og skriv inn:
   ```json
   {"cmd": "SCAN_WIFI"}
   ```
3. Trykk **SEND**.
4. **Forventet resultat**:
   - ESP32 utfører en scanning av 2.4 GHz WiFi-nettverk.
   - En BLE notification sendes tilbake på Command-karakteristikken med listen over nettverk, f.eks.:
     ```json
     {"cmd":"SCAN_WIFI","status":"ok","networks":[{"ssid":"SnippenGuest","rssi":-55,"auth":3},{"ssid":"Hjemmenett","rssi":-72,"auth":4}]}
     ```

### Steg 4: Test lesing og skriving av konfigurasjon
1. Trykk på **Pil ned (Read)** på **Config Characteristic** (`6e400002-...`).
   - Se at du mottar JSON med gjeldende oppsett, der `snippen_api_token` er maskert (f.eks. `se****99`).
2. Trykk på **Pil opp (Write)** på Config-karakteristikken, velg **UTF-8**, og send inn nye innstillinger:
   ```json
   {"wifi_ssid":"MittNettverk","wifi_password":"MittHemmeligePassord","snippen_api_token":"test_token_abc123"}
   ```
3. **Forventet resultat**:
   - ESP32 mottar verdiene, lagrer dem umiddelbart til `config.json` på flashminnet, og oppdaterer config-karakteristikken.

### Steg 5: Test WiFi-tilkobling (`TEST_WIFI`)
1. Trykk på **Pil opp (Write)** på **Command Characteristic** (`6e400004-...`).
2. Send:
   ```json
   {"cmd": "TEST_WIFI", "wifi_ssid": "MittNettverk", "wifi_password": "MittHemmeligePassord"}
   ```
3. **Forventet resultat**:
   - ESP32 kobler seg midlertidig opp mot aksesspunktet og verifiserer signal og passord.
   - En notification sendes tilbake med status og tildelt IP-adresse:
     ```json
     {"cmd":"TEST_WIFI","status":"ok","connected":true,"ssid":"MittNettverk","ip":"192.168.1.142"}
     ```

### Steg 6: Lagre og gå tilbake til normal gateway-drift (`APPLY_AND_EXIT`)
1. På **Command Characteristic**, send:
   ```json
   {"cmd": "APPLY_AND_EXIT"}
   ```
2. **Forventet resultat**:
   - Konfigurasjonen flushes til `config.json`.
   - BLE slås helt av (`ble.active(False)`).
   - Enheten kobler automatisk til WiFi og gjenopptar SMS-polling og normal gateway-drift!
