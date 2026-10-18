# Developer Documentation - Snippen SMS Service

## Architecture Overview

`snippen-sms-service` is a Python service designed to handle SMS communications for `snippen-booking`.

### Directory Layout

```
snippen-sms-service/
├── .devcontainer/            # Dev Container configuration (Python 3.14)
├── .agents/                  # Agent guidelines (Architecture, Testing, common-agent-instructions submodule)
├── docs/                     # System documentation & architecture guides
│   ├── README.md             # Documentation overview
│   ├── BLE_WEB_CONFIG.md     # User and deployment guide for Web Bluetooth PWA
│   ├── BLE_MANUAL_TESTING.md # Manual testing guide for BLE provisioning via nRF Connect
│   ├── README_LILYGO.md      # Standalone Lilygo T-Call A7670E guide & pinout
│   ├── architecture.md       # High-level architecture, provider abstraction & flows
│   └── snippen_booking_api_spec.md # WordPress REST API spec & implementation tasks
├── firmware/                 # MicroPython standalone gateway firmware
│   ├── ble_config.py         # Bluetooth Low Energy (BLE) GATT provisioning server
│   ├── boot.py               # Hardware init, modem power rail & UART1 configuration
│   ├── button.py             # BOOT button (GPIO 0) debounced input with hardware IRQ support
│   ├── config.py             # Hardware pinouts, timers & API settings
│   ├── config.example.py     # Local config overrides template
│   ├── logger.py             # In-memory circular log buffer & stdout/stderr stream redirector
│   ├── modem.py              # SimCom A7670E modem driver (AT engine, SMS, SIM memory)
│   ├── main.py               # Main application loop coordinating WiFi, API & SMS
│   ├── wifi.py               # WiFi scanning, connection verification & STA manager
│   ├── test_api.py           # On-device Snippen API ping test
│   ├── test_ble_provisioning.py # On-device interactive manual test for BLE provisioning
│   ├── test_modem.py         # On-device cellular modem and SIM memory diagnostic test
│   └── test_wifi.py          # On-device WiFi connection test
├── scripts/                  # Development & formatting utilities
│   ├── build_release.py      # Release packaging, firmware bundle generator & checksum utility
│   ├── deploy_firmware.py    # Automated firmware deployment via mpremote
│   ├── format.py             # Whitespace & file formatting tool
│   ├── test_api_ping.py      # Host runner for API authentication ping
│   ├── test_ble_live.py      # Host runner for interactive on-device BLE provisioning test
│   ├── test_modem_live.py    # Host runner for live modem & SIM diagnostics
│   ├── test_wifi.py          # Host runner for on-device WiFi testing
│   └── validate_pr.py        # PR SemVer & changelog validation tool
├── tools/                    # Companion configuration and testing tools
│   └── web-config/           # Web Bluetooth (PWA) configuration app
│       ├── index.html        # Mobile-first web configurator interface
│       ├── manifest.json     # PWA manifest for Android installation
│       ├── sw.js             # Offline caching service worker
│       ├── css/styles.css    # Responsive styles and dark theme
│       ├── js/app.js         # UI application controller
│       ├── js/ble.js         # Core Web BLE GATT client engine & mock client
│       └── test/test.html    # Browser-based test suite for BLE client

├── src/
│   └── snippen_sms/          # Application package
│       ├── __init__.py       # Package version & exports
│       ├── client.py         # Snippen API HTTP client & error handling
│       ├── config.py         # Gateway configuration settings
│       ├── context.py        # Booking context resolution & conversational session management
│       ├── gateway.py        # GatewayService lifecycle, send/receive orchestration & run loop
│       ├── main.py           # Entry point & CLI runner
│       ├── migrations/       # SQLite database migration system
│       │   ├── __init__.py   # Migration exports
│       │   ├── runner.py     # MigrationRunner & Migration class
│       │   └── sql/          # Sequential SQL migration files
│       ├── models.py         # Message domain models and enums
│       ├── providers/        # SMS provider abstraction layer
│       │   ├── __init__.py   # Provider exports & factory registry
│       │   ├── base.py       # SmsProvider ABC, SendResult, IncomingMessage
│       │   ├── http.py       # HttpSmsProvider for HTTP SMS gateways & fake-provider
│       │   ├── memory.py     # InMemorySmsProvider for testing & simulation
│       │   └── mock.py       # MockSmsProvider for mock messaging & auto-replies
│       ├── storage.py        # SQLite persistent storage repository
│       ├── sync.py           # Two-way sync engine coordinating storage & Snippen API
│       └── updater.py        # GitHub release checking and self-update management
├── tests/
│   ├── conftest.py           # Pytest fixtures
│   ├── test_build_release.py # Release build & checksum calculation tests
│   ├── test_client.py        # SnippenClient HTTP client tests
│   ├── test_context.py       # Booking context resolution & dialogue session tests
│   ├── test_fake_provider_e2e.py # End-to-end integration tests with fake SMS provider
│   ├── test_format.py        # Formatter tests
│   ├── test_gateway.py       # GatewayService lifecycle & provider integration tests
│   ├── test_http_provider.py # HttpSmsProvider unit tests
│   ├── test_main.py          # Unit tests
│   ├── test_migrations.py    # Database migration unit & integration tests
│   ├── test_mock_provider.py # Mock SMS provider and factory tests
│   ├── test_providers.py     # SMS provider abstraction unit tests
│   ├── test_storage.py       # SQLite message storage unit & integration tests
│   ├── test_sync.py          # SyncService coordination & retry tests
│   ├── test_updater.py       # GitHub release version checking & updater unit tests
│   └── test_validate_pr.py   # PR validation tests
├── .dockerignore             # Docker build context exclusions
├── Dockerfile                # Production container image definition (Python 3.14-slim)
├── pyproject.toml            # Python packaging and dependency config
├── README.md                 # User documentation
├── DEV_README.md             # Developer documentation
└── CHANGELOG.md              # Project history
```

For high-level system architecture, communication flows, and boundaries, see [docs/architecture.md](file:///workspaces/snippen-sms-service/docs/architecture.md).

## Development Setup

1. **Prerequisites**: Python 3.14+ and `pip`.
2. **Environment & Dependencies**:
   - In **Dev Container**, the virtual environment is automatically set up at `/home/vscode/.venv` (outside the workspace root) to prevent collisions with host OS environments.
   - For local CLI development outside container:
     ```bash
     python -m venv ~/.venv
     source ~/.venv/bin/activate
     pip install -e ".[dev]"
     ```
3. **Testing, Linting, Formatting, Building & PR Validation**:
   ```bash
   # Run test suite
   pytest

   # Run BLE Web Config client contract tests
   pytest tests/test_web_config_contract.py

   # Run lint checks
   ruff check .

   # Format files & cleanup whitespace / newlines
   python scripts/format.py

   # Build distribution packages and generate SHA-256 checksums
   python scripts/build_release.py

   # Deploy firmware to Lilygo ESP32 via mpremote
   python scripts/deploy_firmware.py deploy [--include-config]

   # Validate PR version bump and changelog
   python scripts/validate_pr.py --base origin/main
   ```

## Manual & End-to-End Testing with Fake SMS Provider

To test the complete SMS messaging cycle (outbound dispatch, inbound message injection, polling, and deduplication) between `snippen-sms-service` and the fake SMS provider in `snippen-testing`:

### 1. Launch the Fake SMS Provider
From the `snippen-testing` workspace:
```bash
cd /workspaces/snippen-testing
npm start
# Listens on http://127.0.0.1:3000
```

### 2. Start the SMS Gateway Service
From the `snippen-sms-service` workspace:
```bash
cd /workspaces/snippen-sms-service
snippen-sms run --provider fake --provider-url http://127.0.0.1:3000 --log-level DEBUG
```

### 3. Send Outbound SMS (CLI & Inspection)
Send an outbound SMS message:
```bash
snippen-sms send --to "+4799887766" --message "Din adgangskode er 4821" --provider fake --provider-url http://127.0.0.1:3000
```
Inspect outbound messages stored in the fake provider:
```bash
curl "http://127.0.0.1:3000/messages?direction=outbound"
```

### 4. Inject Inbound SMS & Verify Ingestion
Inject a simulated inbound SMS reply:
```bash
curl -X POST "http://127.0.0.1:3000/messages/inbound" \
  -H "Content-Type: application/json" \
  -d '{"from": "+4799887766", "text": "Hei, adgangskoden virket fint!"}'
```
Observe the `snippen-sms-service` logs as it polls the fake provider (`GET /messages?direction=inbound`), ingests the message into the local SQLite database, and resolves any active booking context.

Clear provider state when needed:
```bash
curl -X DELETE "http://127.0.0.1:3000/messages"
```

## MicroPython Firmware Architecture (Lilygo T-Call A7670E)

The standalone cellular gateway runs MicroPython on the Lilygo T-Call A7670E ESP32 board located in `firmware/`:

- **Character Encoding & Multipart SMS (`firmware/sms_encoding.py`)**:
  - Automatically identifies whether an outbound message fits in the GSM 03.38 7-bit character set.
  - Plain GSM-7 / ASCII messages are transmitted in standard text mode up to 160 characters.
  - Messages containing emojis (e.g. 🤖) or unsupported unicode characters are dynamically encoded in UCS-2 (UTF-16BE hex with surrogate pairs), switching the modem to `AT+CSCS="UCS2"` and preventing `CMS ERROR`.
  - Inbound SMS bodies and sender numbers received in UCS-2 hex are transparently decoded into UTF-8 strings preserving emojis and Norwegian letters (æ, ø, å).
  - **Outbound Concatenation & Chunking (`ModemDriver.send_sms` & `split_sms_body`)**:
    - Messages exceeding single SMS limits (160 chars for GSM-7, 70 code units for UCS-2) are segmented into ordered chunks (153 chars for GSM-7, 67 code units for UCS-2) respecting word boundaries and surrogate pair safety.
    - Multipart messages are dispatched via `AT+CMGSEX="<recipient>",<ref>,<part>,<total>` with a shared revolving message reference, allowing receiving handsets (iOS / Android) to automatically concatenate all parts into a single seamless message.
    - If `AT+CMGSEX` is rejected by the modem, it automatically falls back to standard sequential `AT+CMGS` with configurable delay (`sms_chunk_delay_ms`).
  - **Inbound Reassembly (`InboundReassembler` & PDU mode)**:
    - Firmware configures cellular event notifications via `AT+CNMI=2,1,0,0,0` (Issue #115) to receive immediate `+CMTI` Unsolicited Result Codes (URC) when a new SMS arrives on the SIM, triggering instant inbox processing (< 50ms) rather than relying solely on polling. A fallback poll interval (`inbox_check_interval_sec`, default 30s) acts as a safety net.
    - Firmware reads inbound SMS using 3GPP PDU mode (`AT+CMGF=0`, `AT+CMGL=4`), extracting User Data Headers (UDH, 8-bit & 16-bit reference) and unpacking GSM 7-bit septets with fill bits. This ensures 100% accurate concatenation and preserves Norwegian characters (æ, ø, å).
    - Falls back to text mode (`AT+CMGF=1`) and text indicator detection `(1/2)` if PDU mode is unsupported.
    - Buffers parts per sender in memory, reassembles complete messages in proper order, deletes raw segments immediately from SIM storage with `AT+CMGD` to prevent SIM overflow, and releases timed-out partial segments (`sms_multipart_timeout_sec`) safely.
    - In the Python gateway (`snippen_sms.reassembler`), `InboundReassembler` buffers provider messages and `reassemble_stored_messages()` ensures all stored multipart segments are merged into 1 single unified message before forwarding to WordPress (`POST /sms/inbox`), with all constituent IDs acknowledged.


- **REST API Synchronization (`firmware/snippen_api.py`)**:
  - Connects securely to the Snippen Booking WordPress REST endpoints (`https://vestreholmensameie.no/wp-json/snippen/v1/sms`) using Bearer token authentication (`Authorization: Bearer <token>` and `X-API-Key: <token>`).
  - Periodically polls pending outbound messages from `GET /sms/outbox` and dispatches them via the cellular modem.
  - Reports transmission outcomes (`sent` with modem message ID or `failed` with diagnostic error message) via `POST /sms/outbox/status`.
  - Forwards newly received incoming SMS directly to the WordPress inbox via `POST /sms/inbox`.

- **System Health, Watchdog & Recovery (`firmware/main.py`)**:
  - **Hardware Watchdog (`machine.WDT`)**: Configurable hardware watchdog (default 60s timeout) fed on every tick of the event loop. Continues feeding during BLE provisioning mode.
  - **Modem Health & Recovery**: Performs periodic AT heartbeats (`AT`, `AT+CSQ`, `AT+CREG?`). If the modem fails 3 consecutive health checks, a hardware power-cycle sequence (`boot.power_cycle_modem()`) is executed via GPIO 12/5/4 to restore the cellular radio.
  - **Memory Management**: Periodic `gc.collect()` in the main event loop, free heap monitoring, and aggressive garbage collection if free memory drops below 20 KB.
  - **Non-blocking WiFi Reconnect**: Automatic background reconnection with exponential backoff without stalling the main loop or starving the hardware watchdog.

- **Call Handling, Forwarding & Rejection (`firmware/modem.py` & `firmware/main.py`)**:
  - **Network Call Forwarding (`AT+CCFC`)**: Configures unconditional call forwarding (CFU via `AT+CCFC=0,3,"<target>",145`) during modem initialization. If supported by the SIM/carrier, incoming calls are rerouted entirely in the carrier network without local handling.
  - **Local Call Rejection (`AT+CHUP`)**: When network CFU is unsupported (e.g. prepaid SIMs), the modem automatically presents caller ID (`AT+CLIP=1`), intercepts incoming calls (`RING` / `+CLIP`), and immediately rejects them using `AT+CHUP`.
  - **SMS Notifications & Auto-Reply**:
    - Dispatches an automated SMS alert to the administrator (`+4792830575`) with caller ID and timestamp.
    - Sends an automated SMS reply to the caller informing them that the line is an automated SMS gateway for Snippen Booking.
    - Built-in 30-second debounce prevents notification storms from repeated attempts.
  - **BLE Web Configurator Support**: All parameters (forwarding enable, target number, call reject toggle, admin alert toggle, caller reply toggle, and custom SMS message templates) are configurable wirelessly via the Web Configurator (PWA) and persisted in `config.json`.
- **Hardware Profiles & Versioning (`firmware/version.py` & `firmware/config.py`)**:
  - **Version Source**: `firmware/version.py` defines `FIRMWARE_VERSION`, which is synchronized with `src/snippen_sms/__init__.py` and validated by CI (`scripts/validate_pr.py`).
  - **Board Profiles (`BOARD_PROFILES`)**: Supported boards and their respective GPIO mappings and timings are centralized in `firmware/config.py`:
    - `lilygo_t_call_a7670e` (default production profile):
      - `pin_modem_power`: GPIO 12 (VCC power rail)
      - `pin_modem_reset`: GPIO 5
      - `pin_modem_pwrkey`: GPIO 4
      - `pin_modem_tx`: GPIO 26
      - `pin_modem_rx`: GPIO 25
      - `pin_boot_button`: GPIO 0
      - `modem_uart_id`: UART 1 (115200 baud)
  - **Setting Board Profile**: Specify `"board_profile": "lilygo_t_call_a7670e"` in `config.json` or `config_local.py`.
  - **Telemetry Exposure**: Active `firmware_version` and `board_profile` are reported in real-time via `get_telemetry_status()` over BLE GATT and displayed on the Web Configurator (`tools/web-config`).

### Firmware OTA Packaging (`firmware_bundle.json`)

To enable LilyGO boards to upgrade firmware over Wi-Fi with minimal resource overhead, the release pipeline bundles all production MicroPython files into a single, unified JSON release artifact (`firmware_bundle.json`):

- **Single HTTPS Request**: Eliminates the overhead of 10+ separate TLS handshakes on memory-constrained microcontrollers by delivering all files in one payload.
- **Security & File Filtering**:
  - **Included Production Files**: `boot.py`, `main.py`, `modem.py`, `wifi.py`, `ble_config.py`, `button.py`, `config.py`, `logger.py`, `ota.py`, `rate_limiter.py`, `sms_encoding.py`, `snippen_api.py`, `version.py`.
  - **Excluded Files**: Sensitive local files (`config.json`, `config_local.py`, `config.local.py`, `*local*.py`), templates (`config.example.py`), test/diagnostic scripts (`test_*.py`), and Python cache artifacts (`__pycache__`).
- **Bundle Format**:
  ```json
  {
    "version": "0.31.21",
    "tag": "v0.31.21",
    "created_at": "2026-10-11T08:00:00Z",
    "total_files": 12,
    "total_bytes": 165174,
    "files": {
      "boot.py": {
        "sha256": "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945",
        "size": 6730,
        "content": "# ... UTF-8 code content ..."
      },
      "main.py": {
        "sha256": "...",
        "size": 29061,
        "content": "# ... UTF-8 code content ..."
      }
    }
  }
  ```
- **Integrity Verification**: Each individual file contains a SHA-256 checksum for post-write flash verification, and the bundle itself is verified against its entry in `checksums.txt`.
- **ESP32 Memory Constraints**: Total bundle payload size (~165 KB) and single-file sizes (max ~35 KB) are kept well within ESP32 RAM buffering limits.

### MicroPython OTA Engine & Safe Rollback (`firmware/ota.py` & `firmware/boot.py`)

The standalone cellular gateway includes an integrated, fail-safe Over-The-Air (OTA) client engine designed for zero-risk upgrades without the possibility of bricking the remote device:

1. **Pre-flight & Wi-Fi Check**:
   - Ensures Wi-Fi connection is established using credentials from `config.json` before attempting download.
   - Streams/fetches `firmware_bundle.json` directly from GitHub Releases or configured `ota_bundle_url` / `ota_repo`, supporting HTTP 301/302 redirects.
2. **In-Memory Integrity & Version Verification**:
   - Validates bundle structure, metadata, and version strictly against current `FIRMWARE_VERSION` (prevents downgrade unless explicitly forced).
   - Validates that sensitive files (`config.json`, `config_local.py`, `*local*.py`) and path traversal strings (`..`, `/`) are not present.
   - Calculates SHA-256 checksums for **all** bundled files in memory before modifying a single file on flash storage.
3. **Staging (`<file>.new`) & Flash Verification**:
   - Each file is initially written to a staging file with the `.new` suffix (e.g. `main.py.new`).
   - Immediately reads back the written bytes from flash and re-verifies the SHA-256 hash. If any mismatch or write error occurs, all `.new` files are purged and the live system remains untouched.
4. **Atomic Activation & Backup (`<file>.bak`)**:
   - Existing production files are backed up to `<file>.bak` (e.g. `main.py.bak`).
   - Atomically swaps `<file>.new` into place via `os.rename()`.
   - Writes `ota_pending.json` tracking the pending version and `boot_attempts: 0`.
5. **Fail-safe Boot & Automatic Safe Mode Rollback (`firmware/boot.py`)**:
   - At power-on or reset, `boot.py` inspects `ota_pending.json`.
   - On first boot after update (`boot_attempts == 0`), increments `boot_attempts` to 1.
   - If the device crashes, hits an unhandled exception, or is reset by the hardware watchdog before `main.py` confirms stability, the next boot sees `boot_attempts >= 1`.
   - `boot.py` immediately initiates automatic rollback: restores all files from `<file>.bak`, cleans up `.new` artifacts, purges `ota_pending.json`, records the failed version in `ota_failed.json` (boot-loop guard), and boots the known-stable previous firmware version.
6. **Health Confirmation (`firmware/main.py`)**:
   - Once `main.py` runs stably for 30 seconds (`ota_stability_timeout_sec`), `ota.confirm_healthy()` is invoked.
   - Deletes all `.bak` backup files, clears `ota_pending.json`, and clears `ota_failed.json`, officially marking the upgrade as permanent.
7. **Boot Check Trigger & Boot-Loop Guard (`firmware/main.py` & `firmware/config.py`)**:
   - When `ota_check_on_boot: true` (default in production), the gateway automatically checks for newer releases on GitHub as soon as Wi-Fi connects after boot.
   - If a newer release exists, the gateway performs OTA and restarts seamlessly.
   - If a version previously failed and was rolled back, the boot-loop guard blocks automatic retry for that version unless explicitly overridden with `force=True`.
8. **Companion App & BLE Control**:
   - The Web Configurator companion app can trigger OTA checks (`CHECK_OTA`) and OTA deployment (`ota_update` / `START_OTA`) wirelessly over BLE GATT, returning real-time status and telemetry (`ota_pending`).
   - The Web UI automatically checks GitHub Releases in the browser and displays a banner when updates are ready.

#### OTA Troubleshooting & Recovery

| Issue | Likely Cause | Resolution |
| :--- | :--- | :--- |
| **Download fails with HTTP 302** | GitHub release redirect | `ota.OTAClient` follows redirects automatically up to 3 hops. Verify Wi-Fi internet access. |
| **Upgrade rejected with "not newer"** | Bundle version <= current version | Build new release with bumped SemVer or use `force=True` for manual diagnostic reflashing. |
| **Upgrade skipped by boot-loop guard** | Version recently failed / rolled back | Fix issue in a new release tag or override with `force=True` via BLE or command. |
| **Device rolls back on reboot** | Crash or watchdog reset before 30s | Device booted into Safe Mode and restored from `.bak`. Inspect `/logs` via BLE or serial console. |
| **Configuration reset after OTA** | Should never occur | Sensitive files (`config.json`, `config_local.py`) are strictly blacklisted from the bundle and staging engine. |

### Web Configurator Development & Local Server (`tools/web-config/`)

To develop or test the Web Bluetooth Configurator interface locally without deploying to GitHub Pages:

1. **Start the local HTTP server**:
   ```bash
   python -m http.server 8080 --directory tools/web-config
   ```
2. **Access in browser**:
   Navigate to `http://localhost:8080/` in Google Chrome or Microsoft Edge. Web Bluetooth is natively supported on `localhost` without requiring HTTPS.
3. **Local OTA testing**:
   When testing Over-The-Air firmware updates locally against the physical board, generate a test bundle:
   ```bash
   python scripts/build_release.py --skip-package --version 0.32.0 --tag v0.32.0 --dist-dir tools/web-config --no-clean
   ```
   Then provide `http://<host-ip>:8080/firmware_bundle.json` in the custom bundle URL field of the Web Configurator.



## CI/CD Workflows

- **PR Validator (`.github/workflows/pr-validator.yml`)**:
  - Triggers on pull requests targeting `main`.
  - Runs formatting check (`python scripts/format.py`), ruff linting, and pytest test suite.
  - Verifies that package version conforms to Semantic Versioning and is strictly greater than the latest release git tag.
  - Verifies that `CHANGELOG.md` contains an entry for the version.
- **Deploy & Release Tagging (`.github/workflows/deploy.yml`)**:
  - Triggers on push to `main` (merges).
  - Automatically tags release with `v<version>` if the tag does not already exist.
  - Builds `.whl` and `.tar.gz` package distributions, generates `firmware_bundle.json`, and calculates SHA-256 hashes in `checksums.txt` using `python scripts/build_release.py`.
  - Publishes a formal GitHub Release attaching all build distributions, `firmware_bundle.json`, and `checksums.txt`.
