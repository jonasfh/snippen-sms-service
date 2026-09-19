# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.27.0] - 2026-09-19

### Added
- Added passive serial monitor (`deploy -f` / `monitor`) and physical hardware reset in `scripts/deploy_firmware.py` (`#79`):
  - Stream live serial stdout (`tail -f`) after reset via `deploy -f` / `deploy --follow` without interrupting MicroPython execution.
  - Added standalone `monitor` subcommand (`python scripts/deploy_firmware.py monitor`) for viewing logs anytime.
  - Separated `-v` (`--verbose`) for verbose logging and `-f` (`--follow`) for log streaming.
  - Added physical hardware reset (`reset --hard`) by pulsing the ESP32 `EN` pin via serial RTS line.
  - Added self-healing recovery to `deploy`: automatically triggers RTS reset pulse and retries if the initial raw REPL handshake fails.
  - Added automatic Dev Container virtualenv site-packages inclusion for resilient execution.
- Added button diagnostic tools (`#79`):
  - Created on-device test `firmware/test_button.py` for physical press, short press, and 3s long press verification.
  - Created host diagnostic runner `scripts/test_button_live.py`.

### Changed
- Improved button responsiveness in `firmware/main.py`: replaced 1-second blocking sleep in main loop with 50ms sliced polling (`#79`).

## [0.26.0] - 2026-09-19

### Fixed
- Fixed MicroPython BLE GATT buffer truncation (`#77`):
  - Increased characteristic buffer size to 1024 bytes via `ble.gatts_set_buffer(handle, 1024)` in `firmware/ble_config.py`, preventing 20-byte default truncation on config writes (`syntax error in JSON`) and command responses.
  - Configured 512-byte MTU capacity (`ble.config(mtu=512)`) on server startup for high-throughput packet exchanges.
  - Added `gatts_set_buffer` mock to `MockBLE` in `tests/mocks/micropython_mocks.py`.
- Optimized WiFi scanning in `firmware/wifi.py` (`#77`):
  - Limited scan output to the top 10 strongest unique networks (`max_results=10`) and filtered out weak signals (< -85 dBm).
  - Keeps BLE notification JSON payloads compact (~250 bytes), ensuring reliable delivery over BLE within MTU limits.
- Improved error telemetry in `tools/web-config/js/ble.js` with raw payload logging upon JSON parse failures (`#77`).

## [0.25.0] - 2026-09-19

### Added
- Implemented automated GitHub Pages deployment workflow `.github/workflows/deploy-pages.yml` (`#73`):
  - Automatically builds and deploys `tools/web-config/` to GitHub Pages (`https://jonasfh.github.io/snippen-sms-service/`) upon pushes to `main`.
- Created comprehensive user and developer guide `docs/BLE_WEB_CONFIG.md` (`#73`):
  - Provisioning instructions for Android Chrome, Desktop Chrome/Edge, and iOS (Bluefy).
  - PWA home screen installation, offline caching, and troubleshooting.
- Updated documentation in `README.md`, `DEV_README.md`, and `docs/README.md` with links to the live web app and deployment guide (`#73`).

## [0.24.0] - 2026-09-19

### Added
- Implemented mobile-first Web Bluetooth configuration UI and PWA manifest (`#72`):
  - `tools/web-config/index.html`: Responsive, touch-friendly interface for BLE gateway configuration and diagnostics.
  - `tools/web-config/css/styles.css`: Dark mode design system with Inter typography, card micro-interactions, signal strength bars, and loading states.
  - `tools/web-config/js/app.js`: Application controller managing connection, WiFi scanning, connection verification, token masking, and live telemetry updates.
  - Built-in **Simulator Mode** toggle allowing full UI testing and demonstration in any browser without Bluetooth hardware.
  - PWA support with `manifest.json`, offline caching service worker `sw.js`, and SVG icon asset `assets/icon.svg` allowing "Add to Home Screen" on mobile devices.
- Updated agent instructions in `AGENTS.md` to clarify that running full Python test suites is not required when iteratively developing frontend/web assets in `tools/web-config/`.

## [0.23.0] - 2026-09-19

### Added
- Implemented Web Bluetooth (PWA) client engine `tools/web-config/js/ble.js` (`#71`):
  - `SnippenBLEClient`: Full Web Bluetooth GATT client handling device discovery (`Snippen-SMS-*`), connection lifecycle, and GATT characteristic communications.
  - Config characteristic (`6e400002`): Reading active config and writing JSON payloads.
  - Status characteristic (`6e400003`): Subscribing to streaming device status and telemetry notifications.
  - Command characteristic (`6e400004`): Dispatches commands with Promise-based response matching (`scanWifi`, `testWifi`, `applyAndExit`).
  - `MockSnippenBLEClient`: Built-in simulator for offline preview, UI prototyping, and automated browser testing.
- Added browser test runner `tools/web-config/test/test.html` for client engine verification (`#71`).
- Added Python contract test `tests/test_web_config_contract.py` verifying GATT UUIDs, commands, and token masking parity between MicroPython firmware and the Web BLE client (`#71`).

## [0.22.0] - 2026-09-19

### Added
- Automated MicroPython bytecode compilation and syntax validation test suite `tests/test_firmware_micropython_syntax.py` (`#69`):
  - Validates that every `.py` file in `firmware/` compiles cleanly to `.mpy` bytecode using the official MicroPython `mpy-cross` compiler.
  - Verifies AST across all firmware files to ensure no forbidden imports (`__future__`) are present.
  - Tests negative scenarios ensuring unsupported syntax (e.g. PEP 448 `{**dict}` unpacking) is caught automatically before merge.
- Added `mpy-cross>=1.20.0` as a standard development dependency in `pyproject.toml` (`#69`).

## [0.21.2] - 2026-09-19

### Fixed
- Fixed MicroPython `SyntaxError: invalid syntax` in `firmware/test_ble_provisioning.py` and `firmware/main.py` caused by PEP 448 dictionary unpacking (`{**res}`) inside dictionary literals (`#67`).

## [0.21.1] - 2026-09-19

### Fixed
- Removed `from __future__ import annotations` across MicroPython firmware files (`firmware/ble_config.py`, `firmware/wifi.py`, `firmware/test_ble_provisioning.py`) resolving `ImportError: no module named '__future__'` on device boot (`#65`).
- Split BLE legacy advertising into `adv_data` (Flags + Complete Local Name) and `resp_data` (128-bit Service UUID) in `firmware/ble_config.py`, staying strictly within the 31-byte BLE limit and resolving `BLE_HS_EMSGSIZE` (-18) error (`#65`).
- Added 31-byte advertising payload limit validation to `MockBLE.gap_advertise` in `tests/mocks/micropython_mocks.py` to prevent regressions (`#65`).
- Added `test_ble_provisioning.py` to deployment tool `scripts/deploy_firmware.py` (`#65`).
- Clarified hardware LED functions (PMU, Modem VCC, NETLIGHT) and status logging in `docs/BLE_MANUAL_TESTING.md` (`#65`).

## [0.21.0] - 2026-09-19

### Added
- Implemented MicroPython WiFi scanner, connection testing, and STA management module `firmware/wifi.py` (`#61`):
  - `scan_networks()`: Scans nearby 2.4 GHz WiFi networks using `network.WLAN(network.STA_IF).scan()`, deduplicating SSIDs and sorting by signal strength (RSSI).
  - `test_connection()`: Connects temporarily to verify credentials without altering permanent state, returning assigned IP or detailed error code.
  - `connect_wifi()`: Connection manager with timeout and status reporting for operational gateway loops.
- Implemented persistent JSON configuration storage in `firmware/config.py` (`save_config()`) allowing overrides written via BLE or local files to be saved to flash (`#61`).
- Connected BLE provisioning interface in `firmware/main.py` (`GatewayApp`) (`#61`):
  - `SCAN_WIFI` command executes on-device WiFi scan and returns network list over BLE.
  - `TEST_WIFI` command verifies credentials and reports IP address or error over BLE.
  - `APPLY_AND_EXIT` and config writes persist settings to `config.json` before returning to normal loop.
  - Streamed real-time telemetry (WiFi status, IP, 4G cellular RSSI/dBm, network registration) via BLE Status characteristic.
- Added interactive on-device manual test script `firmware/test_ble_provisioning.py` and host-side launcher `scripts/test_ble_live.py` for testing with generic BLE tools (`#61`).
- Added comprehensive manual test guide `docs/BLE_MANUAL_TESTING.md` for testing with nRF Connect for Mobile (`#61`).
- Added `wifi.py` to deployment tool `scripts/deploy_firmware.py` (`#61`).
- Added comprehensive unit tests in `tests/test_firmware_provisioning.py` and expanded `tests/test_diagnostic_scripts.py` (`#61`).

## [0.20.0] - 2026-09-19

### Added
- Implemented MicroPython Bluetooth Low Energy (BLE) GATT provisioning server and advertising engine `firmware/ble_config.py` (`#60`):
  - Broadcasts BLE advertisement payload with device name `Snippen-SMS-<HEX>` (derived from MAC address) and custom Service UUID (`6e400001-b5a3-f393-e0a9-e50e24dcca9e`).
  - Config Characteristic (Read / Write): Reads active configuration with secret API tokens masked, and receives updated JSON configuration chunks.
  - Status Characteristic (Read / Notify): Real-time telemetry reporting connection status and operational state to companion Android apps.
  - Command Characteristic (Write / Notify): Receives remote commands (`SCAN_WIFI`, `TEST_WIFI`, `APPLY_AND_EXIT`) and streams back notification responses.
  - Inactivity Timeout: Automatically shuts down BLE advertising after 5 minutes of inactivity when no central is connected to conserve RAM and avoid 2.4 GHz radio coexistence conflicts.
- Integrated `BLEConfigServer` into `firmware/main.py` (`GatewayApp`) to activate upon entering provisioning mode and cleanly shut down upon exit (`#60`).
- Added `MockBLE` and `MockUUID` to `tests/mocks/micropython_mocks.py` providing complete host-side BLE simulation (`#60`).
- Added `ble_config.py` to deployment tool `scripts/deploy_firmware.py` (`#60`).
- Added comprehensive unit test suite in `tests/test_firmware_ble.py` and expanded `tests/test_firmware_main.py` (`#60`).

## [0.19.0] - 2026-09-19

### Added
- Implemented MicroPython physical button handler `firmware/button.py` with input debouncing and configurable long-press detection (`#59`):
  - Configured BOOT button (`GPIO 0`) as active-low input with internal pull-up.
  - Implemented debouncing filtering transient contact bounce glitches.
  - Supported long-press threshold detection (default 3000 ms) and short-press event detection.
  - Added physical button held-at-boot detection (`is_down()`).
- Integrated provisioning state machine into `firmware/main.py` (`GatewayApp`) (`#59`):
  - Automatically enter provisioning mode on cold boot if `wifi_ssid` or `snippen_api_token` is unconfigured.
  - Automatically enter provisioning mode on cold boot if BOOT button is held down.
  - Toggle provisioning mode at runtime via 3-second long-press on BOOT button.
  - Added configurable provisioning timeout (default 300 seconds) returning device to normal gateway operation.
  - Suspended routine inbox and outbox polling loops while provisioning mode is active.
- Added button pinouts, debouncing, and provisioning parameters to `firmware/config.py` (`#59`).
- Added `button.py` to deployment tool `scripts/deploy_firmware.py` (`#59`).
- Updated `MockPin` in `tests/mocks/micropython_mocks.py` to default pull-up input pins to logic level 1 (`#59`).
- Added comprehensive unit tests in `tests/test_firmware_button.py` and expanded `tests/test_firmware_main.py` (`#59`).

## [0.18.0] - 2026-09-19

### Added
- Implemented MicroPython cellular modem engine driver `firmware/modem.py` for SimCom A7670E over UART1 on Lilygo T-Call (`#50`):
  - AT command engine with non-blocking line reading, automatic echo suppression (`ATE0`), text mode configuration (`AT+CMGF=1`), and GSM charset selection (`AT+CSCS="GSM"`).
  - Outbound SMS delivery with phone number normalization, `>` prompt synchronization, Ctrl+Z transmission, and `+CMGS` message reference tracking.
  - Inbound SMS retrieval draining unread messages, parsing multi-line bodies, sender numbers, and timestamps.
  - Automatic SIM memory management deleting read messages (`AT+CMGD`) to prevent SIM storage overflow.
  - Diagnostic queries for signal quality (`AT+CSQ` with dBm calculation) and network registration (`AT+CREG?`).
- Added on-device modem diagnostic test `firmware/test_modem.py` and host-side runner `scripts/test_modem_live.py` (`#50`).
- Integrated `ModemDriver` into `firmware/main.py` (`GatewayApp`) for SIM inbox processing and heartbeat cellular status telemetry (`#50`).
- Enhanced deployment tool `scripts/deploy_firmware.py` to deploy `modem.py` (`#50`).
- Enhanced `MockUART` with scripted AT responses and automated response simulation in `tests/mocks/micropython_mocks.py` (`#50`).
- Added unit tests for modem driver and live diagnostic runner in `tests/test_firmware_modem.py` and `tests/test_diagnostic_scripts.py` (`#50`).

## [0.17.1] - 2026-09-18

### Added
- Added on-device WiFi connection test script `firmware/test_wifi.py` and host-side test runner `scripts/test_wifi.py` (`#56`).
- Added on-device Snippen API authentication ping test `firmware/test_api.py` and host-side test runner `scripts/test_api_ping.py` (`#56`).
- Added support for loading overrides from `config.local.py` alongside `config_local.py` in `firmware/config.py` and `scripts/deploy_firmware.py` (`#56`).
- Added `firmware/config.local.py`, `firmware/config_local.py`, and `firmware/config.json` to `.gitignore` to prevent secret leakage (`#56`).
- Added unit tests for diagnostic test runners in `tests/test_diagnostic_scripts.py` (`#56`).

## [0.17.0] - 2026-09-18

### Added
- MicroPython firmware foundation under `firmware/` for standalone Lilygo T-Call A7670E ESP32 gateway (`#49`):
  - `firmware/boot.py`: Autonomous cold-boot hardware initialization sequence (GPIO 12 power rail, GPIO 5 reset, GPIO 4 PWRKEY 1.5s pulse, and UART1 115200 baud).
  - `firmware/config.py`: Local and JSON configuration management with default GPIO pinouts, timers, WiFi, and Snippen REST API parameters.
  - `firmware/config.example.py`: Local configuration override template for device deployments.
  - `firmware/main.py`: Main `GatewayApp` coordination event loop with non-blocking ticks for inbox checking, outbox polling, and system heartbeat.
- Automated deployment tool `scripts/deploy_firmware.py` providing `deploy`, `ls`, `repl`, `reset`, and `run` commands utilizing `mpremote` (`#49`).
- Host-side MicroPython unit test mock framework in `tests/mocks/micropython_mocks.py` simulating `machine.Pin`, `machine.UART`, `machine.WDT`, `utime`, and `network.WLAN` (`#49`).
- Unit test suites covering firmware configuration, boot sequence, main loop, and automated deployment script (`#49`).

## [0.16.2] - 2026-09-18

### Added
- Added USB hardware device passthrough (`--privileged`, `/dev` bind mount) and `dialout` group configuration in `.devcontainer/devcontainer.json`.
- Added `esptool`, `mpremote`, and `pyserial` to development dependencies in `pyproject.toml`.
- Added standalone Lilygo T-Call A7670E documentation in `docs/README_LILYGO.md` with hardware pinout, AT command diagnostics, MicroPython flashing, permanent SIM PIN deactivation, and SMS verification.
- Added template environment file `default.env` and added `.env` to `.gitignore`.

### Changed
- Updated system architecture in `docs/architecture.md`, `README.md`, and `docs/README.md` to reflect the standalone Lilygo IoT gateway model utilizing WiFi HTTPS long-polling against Snippen Booking (`https://vestreholmensameie.no`) and cellular SMS dispatch over Telia 4G.

## [0.16.1] - 2026-09-03

### Added
- Added `docker-outside-of-docker` devcontainer feature and Docker VS Code extension to `.devcontainer/devcontainer.json` to enable Docker host access and container management within dev environments (`#46`).

## [0.16.0] - 2026-09-03

### Added
- Production-ready `Dockerfile` based on `python:3.14-slim` with non-root user `appuser`, volume mount `/app/data`, and container `HEALTHCHECK` (`#44`).
- Container ignore configuration in `.dockerignore` excluding caches, tests, and temporary artifacts (`#44`).
- CLI subcommands `snippen-sms status` and `snippen-sms health` with optional `--json` format output and exit code reporting for container health inspection (`#44`).
- Automated startup migration tests on fresh SQLite database paths (`#44`).

### Changed
- Extended `README.md` and `DEV_README.md` with Docker build, run, and containerized integration testing instructions (`#44`).

## [0.15.0] - 2026-09-01

### Added
- Implemented `HttpSmsProvider` connecting `snippen-sms-service` to remote HTTP SMS providers and the `snippen-testing` fake SMS provider (`#42`).
- Registered `http`, `fake`, and `snippen-testing` aliases in `PROVIDER_REGISTRY` (`#42`).
- Added `SNIPPEN_SMS_PROVIDER_URL` and `SNIPPEN_SMS_PROVIDER_TIMEOUT` environment variable configurations and `--provider-url` CLI parameter (`#42`).
- Added `snippen-sms send` CLI command to directly send SMS messages via configured providers (`#42`).
- Added comprehensive unit tests in `tests/test_http_provider.py` and end-to-end integration tests in `tests/test_fake_provider_e2e.py` covering outbound delivery, inbound polling/deduplication, and failure handling (`#42`).

### Changed
- Updated `GatewayService` to pass provider configuration parameters (`provider_url`, `timeout_seconds`) when instantiating providers (`#42`).
- Extended documentation in `README.md` and `DEV_README.md` with step-by-step testing instructions using CLI and HTTP calls (`#42`).

## [0.14.0] - 2026-08-30

### Added
- Integrated `common-agent-instructions` git submodule under `.agents/common-agent-instructions` for technology-agnostic AI agent workflows, quality rules, documentation standards, and architectural guidelines (`#39`).

### Changed
- Refactored `AGENTS.md`, `.agents/ARCHITECTURE.md`, and `.agents/TESTING.md` to reference modular technology-agnostic guidelines in `common-agent-instructions` while retaining Python 3.14 and service-specific configurations (`#39`).
- Updated developer documentation in `DEV_README.md` to reflect submodule layout (`#39`).

### Removed
- Removed duplicate `.agents/DOCUMENTATION.md` and `.agents/WORKFLOW.md` files now centralized in `common-agent-instructions` submodule (`#39`).

## [0.13.0] - 2026-08-30

### Added
- Dynamic booking context resolution for incoming SMS messages (`#28`).
- Domain model `Booking` with formatted Norwegian presentation (`format_summary`) and timestamp tracking (`#28`).
- Domain model `ConversationContext` and `ConversationState` enum (`IDLE`, `AWAITING_SELECTION`, `RESOLVED`) (`#28`).
- Core resolution engine `BookingContextResolver` supporting automatic unambiguous single-booking association, multi-booking disambiguation prompts, and active session TTL continuation (`#28`).
- Robust natural-language and numeric selection parsing (`1`, `2`, `Nr 1`, `#2`, `første`, etc.) without rigid SMS commands (`#28`).
- SQLite database migration `0004_messages_booking_context.sql` adding `booking_id` and `conversation_id` columns to `messages` and creating `conversation_contexts` tracking table (`#28`).
- Persistence methods `get_conversation_context`, `save_conversation_context`, `delete_conversation_context`, and query helpers `list_messages_by_booking` and `list_messages_by_phone` in `MessageStorage` (`#28`).
- Client method `SnippenClient.fetch_bookings_for_phone()` for querying active reservations by phone number (`#28`).
- Inbound sync reporting transmitting resolved `booking_id` and `conversation_id` payloads to Snippen backend (`#28`).
- Integration of `BookingContextResolver` in `GatewayService` message ingestion loop and `SyncService` (`#28`).
- Configuration options `booking_resolution_enabled` and `conversation_ttl_seconds` in `GatewayConfig` (`#28`).
- Comprehensive unit and integration test suite in `tests/test_context.py` and extended storage/client/gateway tests (`#28`).
- Architecture documentation, sequence diagram, and WordPress REST API specification updated with context resolution endpoints (`#28`).

## [0.12.0] - 2026-08-30

### Added
- Two-way HTTP API synchronization between SMS Gateway and Snippen Booking (`#27`).
- Zero-dependency HTTP client `SnippenClient` with `Authorization: Bearer <token>` and `X-API-Key: <token>` authentication (`#27`).
- `SyncService` coordinating pending outbox polling, unhandled inbound message reporting, and outbound delivery status updates (`#27`).
- Outbox message deduplication by external Snippen ID to prevent duplicate SMS transmissions (`#27`).
- Inbound SMS acknowledgment lifecycle transitioning messages from `RECEIVED` to `PROCESSED` upon successful push (`#27`).
- Delivery status tracking updating `SENT` messages to `DELIVERED` once reported to Snippen (`#27`).
- Database schema migration `0003_messages_external_id.sql` adding `external_id` column and index to SQLite storage (`#27`).
- Configurable Snippen API settings (`snippen_api_url`, `snippen_api_token`, `sync_interval_seconds`, `sync_timeout_seconds`, `sync_enabled`) in `GatewayConfig` (`#27`).
- CLI subcommand `snippen-sms sync` for one-shot manual synchronization and diagnostic output (`#27`).
- Synchronization diagnostics and metrics (`snippen_api_url`, `sync_enabled`, `last_sync_time`, `last_sync_result`) in `GatewayService.get_status()` (`#27`).
- Comprehensive WordPress plugin REST API integration specification and tasks document in `docs/snippen_booking_api_spec.md` (`#27`).
- Comprehensive unit and integration test suites in `tests/test_client.py` and `tests/test_sync.py` (`#27`).

## [0.11.0] - 2026-08-30

### Added
- Inbound SMS message deduplication by provider/modem message identifier in `GatewayService.poll_incoming_messages()` (`#26`).
- Message status `MessageStatus.PROCESSED` for distinguishing unhandled incoming messages from processed ones (`#26`).
- Inbox querying and status transition helpers (`get_unprocessed_inbox`, `mark_inbox_processed`, `get_message_by_modem_id`) in `MessageStorage` and `GatewayService` (`#26`).
- Status filtering support for `MessageStorage.get_inbox()` and `MessageStorage.count_inbox()` (`#26`).
- Unprocessed inbox count reporting (`inbox_unprocessed`) in `GatewayService.get_status()` (`#26`).
- Database migration `0002_messages_modem_id_index.sql` adding performance index on `modem_message_id` (`#26`).
- Comprehensive unit and integration tests covering inbound message detection, deduplication, fault tolerance/temporary failure resilience, and unprocessed inbox lifecycle (`#26`).
- Updated system architecture documentation with inbound message lifecycle and deduplication flow (`#26`).

## [0.10.1] - 2026-08-30

### Fixed
- Fixed Dev Container base image tag in `.devcontainer/devcontainer.json` to valid MCR tag `mcr.microsoft.com/devcontainers/python:3.14-bookworm` (`#24`).

## [0.10.0] - 2026-08-29

### Changed
- Upgraded project runtime, Dev Container, dependencies, CI workflows, and documentation from Python 3.12 to Python 3.14 (`#17`).
- Updated `pyproject.toml` with `requires-python = ">=3.14"` and `target-version = "py314"` for Ruff (`#17`).
- Updated GitHub Actions workflows (`pr-validator.yml` and `deploy.yml`) to set up Python 3.14 runtime (`#17`).
- Updated `.devcontainer/devcontainer.json` base image to Python 3.14 (`#17`).
- Updated developer documentation, architecture guides, and agent guidelines for Python 3.14 (`#17`).

## [0.9.0] - 2026-08-29

### Added
- Automated release packaging and checksum generation utility `scripts/build_release.py` (`#21`).
- Cryptographic SHA-256 integrity verification in `SoftwareUpdater.download_artifact()` against release `checksums.txt` (`#21`).
- Helper functions `calculate_sha256()` and `parse_checksums_file()` in `snippen_sms.updater` (`#21`).
- GitHub Actions deployment workflow (`.github/workflows/deploy.yml`) updated to build distributions and publish GitHub Releases with attached `.whl`, `.tar.gz`, and `checksums.txt` assets (`#21`).
- Comprehensive unit tests in `tests/test_build_release.py` and `tests/test_updater.py` (`#21`).
- Developer guide and architecture documentation updated with release build instructions and checksum verification flow (`#21`).

## [0.8.0] - 2026-08-29

### Added
- Automated GitHub release version checking and self-update facility with `SoftwareUpdater` in `snippen_sms.updater` (`#19`).
- `ReleaseInfo` and `UpdateCheckResult` domain dataclasses with SemVer comparison logic (`#19`).
- Configurable GitHub repository target (`github_repo` / `SNIPPEN_SMS_GITHUB_REPO`, defaulting to `jonasfh/snippen-sms-service`) (`#19`).
- Safe, non-looping startup version check and periodic background checks in `GatewayService` without blocking offline operation (`#19`).
- Release asset download (wheel `.whl` and tarball `.tar.gz`), pip upgrade execution, and post-upgrade SQLite database schema migrations (`#19`).
- CLI subcommands `snippen-sms check-update` and `snippen-sms update` for manual and automated maintenance (`#19`).
- Update availability reporting in `GatewayService.get_status()` (`#19`).
- Comprehensive unit and integration tests for GitHub release querying, version parsing, wheel installation, and CLI workflows (`#19`).
- System architecture and developer guides updated with release management and update sequence diagrams (`#19`).

## [0.7.0] - 2026-08-29

### Added
- Local transactional message outbox and inbox handling in `MessageStorage` and `GatewayService` (`#8`).
- Outbox persistence helper methods (`enqueue_outbox`, `get_pending_outbox`, `get_outbox`, `count_outbox`) in `MessageStorage` (`#8`).
- Inbox query and counting helpers (`get_inbox`, `count_inbox`) in `MessageStorage` (`#8`).
- Outbox batch processing (`process_outbox`) in `GatewayService` with sequential FIFO dispatch and reliable error handling without message loss (`#8`).
- Periodic outbox processing integrated into the `GatewayService.run()` execution loop alongside inbound polling (`#8`).
- Gateway status reporting for outbox and inbox metrics (`outbox_pending`, `outbox_total`, `inbox_total`) in `GatewayService.get_status()` (`#8`).
- Comprehensive unit and integration tests covering outbox enqueueing, batch dispatch, crash/error retention, service restart resilience, and inbox operations (`#8`).
- System architecture documentation updated with Outbox/Inbox patterns and sequence flow (`#8`).

## [0.6.0] - 2026-08-29

### Added
- Dedicated `MockSmsProvider` (and `MockSMSProvider` alias) in `snippen_sms.providers.mock` for hardware-free gateway development and testing (`#7`).
- Inbound SMS simulation utilities (`simulate_inbound`, `simulate_incoming`) and auto-reply trigger rules for interactive testing (`#7`).
- Configurable failure simulation for outbound message dispatch (`simulate_send_failure`) and inbound polling (`simulate_receive_failure`) (`#7`).
- Provider registry and factory `get_provider()` / `register_provider()` supporting dynamic provider instantiation (`#7`).
- Configurable SMS provider selection in `GatewayConfig` (`provider` field / `SNIPPEN_SMS_PROVIDER` env var) and `--provider` CLI argument in `main.py` (`#7`).
- Comprehensive unit and integration test suite in `tests/test_mock_provider.py` (`#7`).
- Updated system architecture and developer documentation with mock provider capabilities and configuration guides (`#7`).

## [0.5.0] - 2026-08-29

### Added
- SMS provider abstraction layer with `SmsProvider` abstract base class, `SendResult`, and `IncomingMessage` data structures (`#6`).
- Hardware-agnostic `InMemorySmsProvider` implementation for automated testing, simulation, and offline operation (`#6`).
- Provider integration in `GatewayService` with `send_sms()` dispatch, `poll_incoming_messages()` ingestion, and lifecycle hooks (`#6`).
- Polling of incoming SMS integrated into the `GatewayService.run()` main execution loop (`#6`).
- Provider health/type diagnostics reported in `GatewayService.get_status()` (`#6`).
- Comprehensive unit test suite in `tests/test_providers.py` and extended gateway tests in `tests/test_gateway.py` (`#6`).
- Updated system architecture documentation and diagrams detailing provider decoupling and flow (`#6`).

## [0.4.0] - 2026-08-29

### Added
- Database migration management system for embedded SQLite (`#13`).
- Lightweight, zero-dependency `MigrationRunner` and `Migration` dataclass in `snippen_sms.migrations` with atomic transactions, SHA-256 checksum tracking, and rollback on failure (`#13`).
- Persistent `schema_migrations` tracking table and `PRAGMA user_version` synchronization (`#13`).
- Initial migration script `0001_initial_messages_schema.sql` for creating `messages` table and performance indexes (`#13`).
- Automatic schema migration hook on `MessageStorage` and `GatewayService` initialization with baseline support for existing databases (`#13`).
- CLI subcommands `snippen-sms migrate` and `snippen-sms migrate-status` with target-version and custom database path flags (`#13`).
- Comprehensive unit and integration tests covering migration parsing, execution, error rollback, idempotency, baseline migration, and CLI workflows (`#13`).

## [0.3.0] - 2026-08-29

### Added
- Local SQLite message persistence with `MessageStorage` repository (`#5`).
- Domain models `Message`, `MessageDirection`, and `MessageStatus` with UTC timestamp tracking (`created_at`, `modified_at`) (`#5`).
- Persistent storage integration in `GatewayService` and configurable database path in `GatewayConfig` (`#5`).
- Comprehensive unit and integration test suite in `tests/test_storage.py` covering persistence, CRUD operations, filtering, pagination, and service restarts (`#5`).
- System architecture documentation and Mermaid data schema diagram for local message storage (`#5`).

## [0.2.0] - 2026-08-29

### Added
- Gateway application skeleton with `GatewayService` lifecycle management and run loop (`#4`).
- Configuration dataclass `GatewayConfig` supporting environment variable parsing (`#4`).
- CLI runner in `src/snippen_sms/main.py` and `snippen-sms` script entry point with graceful OS signal handling (`SIGINT`, `SIGTERM`) (`#4`).
- Comprehensive unit test suite for `GatewayService` lifecycle and configuration (`#4`).

## [0.1.0] - 2026-08-29

### Added
- Initial Python 3.12 project structure and Dev Container setup (`#1`).
- Package layout under `src/snippen_sms/` with main module and version declaration.
- `pyproject.toml` setup with pytest and ruff dev dependencies.
- Pytest unit testing suite and test configuration.
- Agent guidelines (`AGENTS.md` and `.agents/` docs) updated for Python ecosystem with continuous self-improvement protocols and mandatory documentation synchronization.
- High-level architecture documentation under `docs/architecture.md` and documentation hub in `docs/README.md` (`#3`).
- Updated `README.md` and `DEV_README.md` with system topology, project purpose, and documentation links (`#3`).
- Project-wide formatting utility (`scripts/format.py`) and agent instructions to enforce trailing whitespace removal and single EOF newline hygiene across all code, markdown, and text files.
- Semantic versioning configuration using standard setuptools dynamic package versioning (`#10`).
- PR Validator GitHub Actions workflow (`.github/workflows/pr-validator.yml`) and validation utility (`scripts/validate_pr.py`) to enforce valid SemVer bump, changelog presence, linting, and tests (`#10`).
- Deploy & Release Tagging GitHub Actions workflow (`.github/workflows/deploy.yml`) to automatically tag releases upon merging to main (`#10`).
