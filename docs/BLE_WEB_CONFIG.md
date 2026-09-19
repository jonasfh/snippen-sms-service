# Snippen Gateway Web Configurator (PWA) Brukerveiledning

**Snippen Gateway Web Configurator** er en nettleserbasert applikasjon (Progressive Web App - PWA) som bruker **Web Bluetooth API** for trådløs konfigurasjon, provisjonering og diagnostikk av Snippen SMS Gateway (Lilygo T-Call A7670E ESP32).

---

## 🌐 Tilgang og URL

Webappen er automatisk publisert på GitHub Pages og tilgjengelig over sikker HTTPS:

🔗 **[https://jonasfh.github.io/snippen-sms-service/](https://jonasfh.github.io/snippen-sms-service/)**

---

## 📱 Støttede enheter og nettlesere

Web Bluetooth er en W3C-standard som støttes direkte i Chromium-baserte nettlesere:

| Plattform | Anbefalt nettleser | Støtte | Merknad |
| :--- | :--- | :--- | :--- |
| **Android** | **Google Chrome** | **Full støtte** | Krever at Bluetooth og posisjon/enhetstillatelser er tillatt i nettleseren. Kan installeres som app på startskjermen. |
| **Windows / macOS / Linux** | **Chrome / Edge / Opera** | **Full støtte** | Krever innebygd Bluetooth eller USB Bluetooth-adapter på PC-en. |
| **iOS (iPhone / iPad)** | **Bluefy** / **WebBLE** | **Støttet via app** | Apple støtter ikke Web Bluetooth i Safari. Installer gratisappen *Bluefy* fra App Store og åpne URL-en der. |

> [!NOTE]
> Webappen har også en innebygd **Simulator-modus** (bryter oppe til høyre) som gjør det mulig å utforske grensesnittet og teste alle funksjoner uten fysisk maskinvare eller Bluetooth-støtte.

---

## 🚀 Steg-for-steg provisjonering

### Steg 1: Sett Lilygo ESP32 i konfigurasjonsmodus
1. Sørg for at Lilygo-kortet er koblet til strøm.
2. Hold inne **`BOOT`-knappen (GPIO 0)** på kortet i **3 sekunder**.
3. Enheten starter BLE-annonsering under navnet `Snippen-SMS-XXXX` (der `XXXX` er de 4 siste sifrene i MAC-adressen).

*(Under utvikling kan du også starte BLE direkte ved å kjøre `python scripts/test_ble_live.py` over USB).*

### Steg 2: Åpne nettsiden og koble til
1. Åpne **[https://jonasfh.github.io/snippen-sms-service/](https://jonasfh.github.io/snippen-sms-service/)** i Chrome på Android eller PC.
2. Sørg for at **Simulator-bryteren** er slått **av** (for ekte Bluetooth).
3. Trykk på **«Koble til Gateway»**.
4. Nettleserens innebygde Bluetooth-velger åpnes. Velg enheten **`Snippen-SMS-XXXX`** og trykk **Par / Koble til**.
5. Statuspillen oppe skifter til grønn **«Tilkoblet: Snippen-SMS-XXXX»**, og alle skjemaer aktiveres. Eksisterende oppsett leses automatisk ut av enheten.

### Steg 3: Skann og test WiFi
1. I seksjonen **WiFi Oppsett**, trykk på knappen **«Skann WiFi»**.
2. ESP32 utfører et trådløst søk på 2.4 GHz-båndet og returnerer listen over tilgjengelige nettverk med signalstyrke (RSSI) og sikkerhetslås.
3. Velg ønsket SSID fra dropdown-menyen (eller skriv det inn manuelt).
4. Skriv inn nettverkspassordet (trykk på 👁️ for å bekrefte at passordet er rett).
5. Trykk på **«Test WiFi-forbindelse»**.
   - ESP32 vil nå forsøke å koble seg opp mot aksesspunktet midlertidig.
   - Ved suksess vises en grønn statusboks med tildelt IP-adresse (f.eks. `192.168.1.142`).

### Steg 4: Konfigurer Snippen API og intervaller
1. I seksjonen **Snippen API Innstillinger**, oppgi URL-en til Snippen Booking-endepunktet (f.eks. `https://snippen.no/wp-json/snippen/v1`).
2. Oppgi API Bearer Token (dersom tokenet allerede er lagret, vises det maskert av sikkerhetshensyn, f.eks. `se****99`).
3. Juster polle-intervall for utdataboks og innboks ved behov (standard: 5 sekunder).

### Steg 5: Lagre og start gatewayen
1. Trykk på den store blå knappen nederst: **«🚀 Lagre og Start Gateway»**.
2. De nye innstillingene skrives atomisk over BLE og lagres permanent til `config.json` på ESP32-ens flashminne.
3. Lilygo-kortet slår av Bluetooth-radioen (`APPLY_AND_EXIT`) og starter normal bakgrunnsdrift for SMS-provisjonering.
4. Nettsiden bekrefter lagringen og kobler fra.

---

## 📲 Installer som app på Android (PWA)

Webappen er en fullverdig PWA og kan installeres på telefonen:
1. Åpne siden i Chrome på telefonen.
2. Trykk på de tre prikkene (meny) øverst til høyre i Chrome.
3. Velg **«Legg til på startskjerm»** (eller trykk på banneret som dukker opp).
4. Appen får nå et eget Snippen-ikon på hjemskjermen, åpnes i fullskjerm uten nettleserlinje, og lagres i offline-cache via service worker (`sw.js`).

---

## 🔍 Feilsøking

### «Web Bluetooth er ikke støttet i denne nettleseren»
- Sørg for at du bruker **Google Chrome** eller **Microsoft Edge**.
- På iPhone/iPad: Bruk gratisappen **Bluefy** fra App Store.
- På Linux: Noen eldre Chrome-versjoner krever at flagget `#enable-web-bluetooth` aktiveres i `chrome://flags`.

### «Finner ikke enheten ved søk»
- Sørg for at Lilygo ESP32 er i BLE-modus. Hold `BOOT`-knappen inne i 3 sekunder. Hvis enheten har stått inaktiv i over 5 minutter, vil BLE-serveren automatisk slå seg av for å spare strøm; trykk og hold `BOOT` på nytt.
- Kontroller at Bluetooth og Posisjon/Enheter i nærheten er aktivert på telefonen eller PC-en.

### «Tilkobling feilet eller brutt»
- ESP32 tillater kun én tilkoblet sentral (telefon/PC) om gangen. Hvis du har koblet til via f.eks. *nRF Connect*, koble fra den før du kobler til fra webappen.
