# Testmiljø: `picobell.no` (ProISP) og Lokal Testing (`jonas-mac.local`)

Denne guiden beskriver to komplementære måter å teste `snippen-sms-service` (Lilygo T-Call A7670E) skikkelig på:

1. **Del 1 – `picobell.no/snippen-test/` (ProISP):** En fast, alltid-tilgjengelig HTTPS-instans for langtids- og produksjonslik testing (TLS, ProISP-webhotell, 4G/SIM).
2. **Del 2 – `jonas-mac.local:8081` (Lokal Ubuntu 26.04 + Docker):** Rask daglig utviklingstesting over lokalt WiFi direkte mot din lokale `snippen-booking`-container.

---

## Del 1: Sette opp WordPress + `snippen-booking` på `picobell.no` (ProISP)

Siden `picobell.no` ligger på ProISP med gyldig SSL-sertifikat, får du en permanent HTTPS-adresse som ikke utløper, og Lilygo-enheten kan stå i veggen i flere dager uten at PC-en din er på.

### 1.1 Installer ren WordPress i undermappe
1. Logg inn i ProISP kontrollpanel (cPanel).
2. Opprett en ny WordPress-installasjon i undermappen `/snippen-test` (via Softaculous / WordPress Manager), slik at adressen blir:
   `https://picobell.no/snippen-test/`
3. Bekreft at **HTTPS** er aktivert (Let's Encrypt / AutoSSL i cPanel).

### 1.2 Viktige WordPress-innstillinger (må gjøres én gang)
1. **Permalenker:** Gå til *Innstillinger → Permalenker* og velg **Innleggsnavn** (`/%postname%/`).
   - *Hvorfor:* Uten pene permalenker svarer ikke `/wp-json/snippen/v1/sms/...` som forventet.
2. **Last opp og aktiver `snippen-booking`:**
   - Bygg en fersk zip fra `snippen-booking`-repoet (se punkt 1.3), og last den opp under *Utvidelser → Legg til ny → Last opp utvidelse*.
3. **Konfigurer SMS Gateway i pluginen:**
   - Gå til *Snippen Booking → Innstillinger*.
   - Sett aktiv varslingsleverandør til **Snippen SMS Service (Gateway)**.
   - Sett **SMS Service API-token** til et valgfritt, sterkt test-token (f.eks. en tilfeldig streng uten mellomrom).
   - Lagre innstillingene.

### 1.3 Enkel oppdateringsrutine for uferdige plugin-bygg
Når du gjør endringer lokalt i `snippen-booking` og vil teste dem på `picobell.no` (uten å lage GitHub-release):

1. Kjør fra roten av `snippen-booking`:
   ```bash
   ./dev package
   ```
   Dette bygger `build/snippen-booking-dev.zip` med riktig mappestruktur (`snippen-booking/booking-plugin.php`).
2. Åpne WordPress Admin på `https://picobell.no/snippen-test/wp-admin/`.
3. Gå til *Utvidelser → Legg til ny → Last opp utvidelse*, velg `build/snippen-booking-dev.zip` og trykk **Installer nå**.
4. WordPress oppdager at utvidelsen allerede finnes og viser knappen **«Erstatt gjeldende med opplastet»** — klikk denne for å oppdatere på sekunder.

### 1.4 Pek Lilygo ESP32 til `picobell.no`
Bruk [Web Bluetooth Configurator](https://jonasfh.github.io/snippen-sms-service/) (eller `firmware/config_local.py`) og sett:
- **API Base URL:** `https://picobell.no/snippen-test/wp-json/snippen/v1`
- **API Token:** Det samme tokenet du la inn i WordPress på `picobell.no`.

Verifiser fra PC via `curl` før du tester på enheten:
```bash
curl -H "Authorization: Bearer <DITT_TOKEN>" \
  "https://picobell.no/snippen-test/wp-json/snippen/v1/sms/outbox"
```
Forventet svar: `200 OK` med JSON (f.eks. `{"messages":[]}` eller `[]`).

---

## Del 2: Lokal testing via `jonas-mac.local:8081` (Ubuntu 26.04)

Når du utvikler lokalt og vil at den fysiske Lilygo-enheten skal snakke direkte med din lokale Docker-instans uten internett-tunnel:

### 2.1 Sjekk `.local` (Avahi / mDNS) på Ubuntu
På Ubuntu 26.04 kjører `avahi-daemon` som standard og annonserer maskinnavnet som `<hostname>.local`. Sjekk at det er aktivt:
```bash
hostname && systemctl is-active avahi-daemon
```
Hvis maskinen heter `jonas-mac`, er adressen på lokalt WiFi `jonas-mac.local`.

### 2.2 Start den lokale Docker-stacken
Fra `snippen-testing` (eller `./dev up` i `snippen-booking`):
```bash
./dev up
```
Dette starter `snippen-booking` på port `8081` (`0.0.0.0:8081`) med standard test-token `test-integration-token`.

### 2.3 Konfigurer Lilygo mot `jonas-mac.local`
Sett følgende på Lilygo-enheten (via BLE Web Configurator eller `config_local.py`):
- **API Base URL:** `http://jonas-mac.local:8081/wp-json/snippen/v1`
- **API Token:** `test-integration-token`

> [!NOTE]
> Firmwaren (`firmware/mdns_resolve.py`) slår automatisk opp `*.local`-adresser via multicast UDP (`224.0.0.251:5353`) og skriver om URL-en til lokal IP med `Host: jonas-mac.local:8081`-header, slik at dette fungerer selv om ESP32-ens innebygde DNS ikke støtter `.local`.

### 2.4 Kjør ping-test over USB
Koble til Lilygo med USB-C og kjør fra `snippen-sms-service`:
```bash
./dev mpremote run firmware/test_api.py
```
Forventet resultat: `✅ Autentisering og kommunikasjon mot Snippen Booking er VELLYKKET!`.

### 2.5 Vanlige feilkilder lokalt
- **Brannmur (UFW):** Hvis `ufw` er aktivert på Ubuntu, åpne port `8081` på lokalt nett: `sudo ufw allow 8081/tcp`.
- **WiFi Client/AP Isolation:** Sørg for at Lilygo og `jonas-mac` er på samme WiFi-nettverk (ikke gjestenett med klientisolering).

---

## Del 3: Feilsøkingssjekkliste for `vestreholmensameie.no`

Hvis en test-booking på `vestreholmensameie.no` ikke kommer gjennom som SMS:

1. **Sjekk utboks-status i WordPress:** Står meldingen fast som `queued` i *Snippen SMS Inbox*? Da har ikke Lilygo klart å polle `GET /wp-json/snippen/v1/sms/outbox`.
2. **Test endepunktet fra PC med `curl`:** Verifiser at `https://vestreholmensameie.no/wp-json/snippen/v1/sms/outbox` svarer `200 OK` med ditt `Bearer`-token.
3. **Les live-logg fra Lilygo:** Koble til med USB-C og kjør `./dev mpremote` (eller sjekk diagnostikk i BLE Web Configurator) for å se om det er WiFi-feil, `401/403` token-feil, TLS-feil, eller SIM/4G-feil (`CSQ` / PIN-kode).
