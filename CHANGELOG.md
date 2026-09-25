# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.31.16] - 2026-09-25

### Fixed
- Fixed Web Configurator `writeConfig` exceeding 512-byte GATT write limit during save (`#121`):
  - In `tools/web-config/js/app.js`:
    - Defined and exported `DEFAULT_CALL_REPLY_CALLER_TEXT` and `DEFAULT_CALL_NOTIFY_ADMIN_TEXT`.
    - Omitted default unchanged call notification text templates from the save payload, reducing default save payload to ~250 bytes.
  - In `tools/web-config/js/ble.js`:
    - Implemented automatic key-value chunking in `writeConfig(configObj)` so that whenever a configuration payload exceeds 450 bytes (e.g., when the user configures custom text in multiple fields), it is transparently split into smaller sequential GATT writes (<= 400 bytes each).
    - Prevents Chrome Web Bluetooth from throwing `Failed to execute 'writeValueWithResponse' on 'BluetoothRemoteGATTCharacteristic': Value can't exceed 512 bytes.`
  - In `tests/test_web_config_contract.py`:
    - Added synchronization and chunking contract tests for default call notification templates and chunked GATT writes.

## [0.31.15] - 2026-09-25

### Fixed
- Fixed 512-byte GATT attribute truncation during config read and START_OPERATIONS timeout (`#119`):
  - In `firmware/ble_config.py`:
    - Compacted `safe_cfg` serialization by omitting default call notification text templates (`DEFAULT_CALL_REPLY_CALLER_TEXT` and `DEFAULT_CALL_NOTIFY_ADMIN_TEXT`) when unchanged, reducing config JSON payload to ~280 bytes (well below the 512-byte GATT limit).
    - Added `bluetooth.FLAG_READ` to `char_command` and configured GATT buffer sizes explicitly to 512 bytes with overwrite mode (`append=False`).
    - Fixed connection handle tracking on GATT writes (`self.conn_handle = conn_handle`) and explicitly passed `conn_handle` to command response notifications.
    - Added dynamic payload size trimming in `notify_command_response` so oversized responses (such as `GET_LOGS`) never exceed GATT notification limits.
  - In `firmware/main.py`:
    - Updated `START_OPERATIONS` command handler to reset `last_outbox_poll`, `last_inbox_check`, and `last_heartbeat` timers to the current time, preventing immediate heavy WiFi HTTPS operations from colliding with the BLE radio response.
    - Capped default `GET_LOGS` count to 15 (max 30) to keep initial responses compact.
  - In `tools/web-config/`:
    - In `js/app.js`: Sequenced `loadActiveConfig()` and `fetchInitialLogs()` sequentially on BLE connection instead of concurrently, avoiding Web Bluetooth GATT operation collision errors.
    - In `js/app.js`: Preserved default call notification template strings when omitted from read config JSON.
    - In `js/ble.js`: Increased command response timeouts (`sendCommand`, `startOperations`, `stopOperations` to 20000ms; `getLogs` to 15000ms).

## [0.31.14] - 2026-09-25

### Added
- Hardware interrupt (`Pin.irq`) support for BOOT button (GPIO 0) (`#117`):
  - In `firmware/button.py`:
    - Configured hardware interrupt with `Pin.irq(trigger=Pin.IRQ_FALLING, ...)` on the BOOT button for instant, zero-delay press detection.
    - Implemented zero-allocation ISR (`_on_irq`) with hardware debounce timing to comply with MicroPython hard-ISR constraints.
    - Added scheduled dispatch via `micropython.schedule()` and flag-based fallback so presses occurring during blocking TLS/HTTPS network calls are never missed.
    - Maintained full backward compatibility with polling-based workflows.
  - In `tests/mocks/micropython_mocks.py`:
    - Added IRQ trigger constants and `MockPin.irq()` / `MockPin.trigger_irq()` simulation.
  - In `tests/test_firmware_button.py`:
    - Added unit tests for hardware interrupt registration, debouncing, and detection of brief button presses during simulated blocking execution.

## [0.31.13] - 2026-09-25

### Added
- Event-driven inbound SMS via `AT+CNMI` URC and simplified Web Configurator interface (`#115`):
  - In `firmware/modem.py`:
    - Configured cellular modem SMS event notifications with `AT+CNMI=2,1,0,0,0` during `init_modem()`.
    - Added `_poll_urc()` to reliably demultiplex voice call URC (`RING`, `+CLIP`) and incoming SMS indications (`+CMTI:`) from UART streams without dropping events.
    - Added `check_incoming_sms()` to detect `+CMTI` notifications and trigger instant processing.
    - Captured asynchronous `+CMTI` indications received during active AT command responses.
  - In `firmware/main.py`:
    - Added `poll_incoming_sms()` to check for incoming SMS indications and trigger `process_inbox()` immediately (<50ms response time).
    - Integrated `poll_incoming_sms()` into `tick()` and the 50ms fast sleep loop.
    - Updated `inbox_check_interval_sec` default to 30 seconds as a fallback safety net.
  - In `tools/web-config/`:
    - Removed `inbox-interval` input field from `index.html` to eliminate confusing configuration for end users.
    - Clarified `poll-interval` label and helper text for outbox polling.
    - Updated `tools/web-config/js/app.js` to handle optional `inbox-interval` cleanly.
  - In `docs/architecture.md` and `DEV_README.md`:
    - Documented event-driven inbound SMS architecture, `+CMTI` URC handling, and fallback polling timers.

## [0.31.12] - 2026-09-24

### Added
- Automated incoming call rejection (`AT+CHUP`) and SMS alerts with Web Configurator integration (`#113`):
  - In `firmware/config.py` and `firmware/config.example.py`:
    - Added `CALL_REJECT_ENABLED`, `CALL_NOTIFY_ADMIN_ENABLED`, `CALL_REPLY_CALLER_ENABLED`, `CALL_REPLY_CALLER_TEXT`, and `CALL_NOTIFY_ADMIN_TEXT` settings.
  - In `firmware/modem.py`:
    - Enabled Caller ID presentation (`AT+CLIP=1`) during `init_modem()`.
    - Added `parse_clip_header()` to extract normalized E.164 phone numbers from URC lines.
    - Added `reject_call()` to terminate incoming/active voice calls with `AT+CHUP`.
    - Added `check_incoming_call()` to inspect UART buffer for `RING` / `+CLIP` and reject calls automatically.
  - In `firmware/main.py`:
    - Integrated `poll_incoming_calls()` into main tick and the 50ms sleep loop for near-instant call interception.
    - Added `handle_incoming_call()` with 30-second debounce per caller, sending automated SMS alerts to administrator and auto-reply SMS to caller.
  - In `firmware/ble_config.py` and `tools/web-config/`:
    - Added an "Anropshåndtering & Viderekobling" configuration card to the BLE Web Configurator (PWA).
    - Synchronized all call parameters across BLE GATT characteristic read/write, mock client, and web app UI.
  - In `DEV_README.md`:
    - Documented call handling, network forwarding, local rejection, and PWA configuration options.

## [0.31.11] - 2026-09-24

### Added
- Unconditional call forwarding (CFU) for incoming voice calls on LilyGO T-Call (`#110`):
  - In `firmware/config.py` and `firmware/config.example.py`:
    - Added `CALL_FORWARDING_NUMBER = "+4792830575"` and `CALL_FORWARDING_ENABLED = True` as default configuration constants.
    - Included fields in `get_default_config()` with support for JSON and local config overrides.
  - In `firmware/modem.py`:
    - Added `configure_call_forwarding()` to register and enable unconditional call forwarding via `AT+CCFC=0,3,"<number>",145`.
    - Added `query_call_forwarding()` for status querying via `AT+CCFC=0,2`.
    - Added automatic call forwarding setup during `init_modem()` with graceful error handling to preserve SMS gateway operations.
  - In `DEV_README.md`:
    - Documented call forwarding behavior, configuration options, and network-side routing architecture.

## [0.31.10] - 2026-09-24

### Fixed
- Fixed Norwegian character corruption (æ, ø, å) and UCS-2 text mode parameters on SimCom A7670E (`#109`):
  - In `firmware/sms_encoding.py`:
    - Added `is_ascii_gsm(text)` to identify characters that can be safely transmitted in 7-bit ASCII/GSM over UART.
    - Updated `split_sms_body(..., force_ucs2)` to partition messages containing non-ASCII characters (Norwegian æ, ø, å or emojis) into UCS-2 chunks (max 70 chars for single, max 67 chars per segment for multipart).
  - In `firmware/modem.py`:
    - Automatically configured `AT+CSMP=17,167,0,8` (DCS=8) and `AT+CSCS="UCS2"` whenever outbound messages contain non-ASCII characters.
    - Configured UCS-2 mode once per `send_sms()` transmission, preventing mid-message character set switching between concatenated segments.
    - Restored `AT+CSMP=17,167,0,0` and `AT+CSCS="GSM"` cleanly in `finally:` block.

## [0.31.9] - 2026-09-24

### Added
- Outbound concatenated (multipart) SMS using `AT+CMGSEX` on SimCom A7670E (`#107`):
  - In `firmware/modem.py`:
    - Updated `send_sms()` to split long messages without manual `(1/2)` indicators and assign a revolving reference ID (`_outbound_msg_ref`, 1–255).
    - Updated `_send_single_sms()` to transmit multi-part segments via `AT+CMGSEX="<dest>",<mr>,<part>,<total>`, instructing the cellular network and receiving handsets to concatenate parts into a single seamless message.
    - Added automatic fallback to standard `AT+CMGS` if `AT+CMGSEX` is unsupported or rejected.
    - Updated response parser to recognize both `+CMGS:` and `+CMGSEX:` message reference acknowledgments.
  - In `firmware/sms_encoding.py`:
    - Updated `split_sms_body()` to properly use `default_mp_limit` (153 chars GSM-7, 67 code units UCS-2) as the maximum payload per segment when `add_indicators=False`.

## [0.31.8] - 2026-09-24

### Fixed
- Fixed PDU read timeout and text-mode fallback for inbound multipart SMS (`#105`):
  - In `firmware/modem.py`:
    - Increased `AT+CMGL=4` PDU read timeout from 4000ms to 10000ms to accommodate 4+ second SIM memory retrieval times.
    - Repaired `read_inbound_sms()` to extract `+CMGL:` PDU lines regardless of final `OK` latency, preventing premature text-mode fallback.
    - Explicitly set `AT+CMGF=1` at the beginning of `_send_single_sms` to prevent mode collisions with PDU reading.
    - Added automated stripping of trailing `@` generated by the modem 7-bit septet fill-bits padding bug in text mode.
    - Added `_merge_text_mode_segments` fallback to merge 153-character / sentence-continuation chunks from the same sender as a safety net.
  - In `src/snippen_sms/reassembler.py`:
    - Added automated stripping of trailing `@` in `reassemble_stored_messages()`.
    - Added text-mode segment concatenation for standalone chunks (153 chars or sentence continuation) from the same sender.
  - In `firmware/sms_encoding.py`: Log detailed exception message if `decode_pdu` encounters malformed input.

## [0.31.7] - 2026-09-24

### Added
- Concatenated multipart SMS reassembly into a single unified inbound message (`#103`):
  - In `firmware/sms_encoding.py`: Added full 3GPP PDU decoding (`decode_pdu`) supporting SMS-DELIVER, GSM 7-bit septets unpacking with fill bits, UCS-2 decoding with surrogate pairs, and 8-bit & 16-bit reference User Data Header (UDH) extraction. Updated `InboundReassembler` to accept parsed UDH metadata directly and correctly concatenate multi-segment messages in sequential order.
  - In `firmware/modem.py`: Enhanced `read_inbound_sms` to prioritize PDU mode (`AT+CMGF=0`, `AT+CMGL=4`), preserving complete UDH headers and Norwegian characters (æ, ø, å) across multi-segment SMS before falling back to text mode (`AT+CMGF=1`). Fixed timestamp extraction in text mode when `CSDH=1` is active.
  - In `src/snippen_sms/reassembler.py`: Implemented Python gateway `InboundReassembler` and `reassemble_stored_messages()` helper supporting binary UDH, hex UDH, and text indicators `(1/2)`.
  - In `src/snippen_sms/gateway.py` and `src/snippen_sms/sync.py`: Integrated inbound reassembly into `GatewayService.poll_incoming_messages()` and `SyncService.sync_inbox()` ensuring only 1 unified message is transmitted to WordPress (`POST /wp-json/snippen/v1/sms/inbox`), with all local constituent message parts transitioned to `PROCESSED`.
  - In `src/snippen_sms/config.py`: Added `multipart_timeout_seconds` configuration parameter (`SNIPPEN_SMS_MULTIPART_TIMEOUT_SECONDS`).

## [0.31.6] - 2026-09-23

### Fixed
- Fixed MicroPython bare-metal `AttributeError: 'str' object has no attribute 'removesuffix'` when processing inbox messages (`#101`):
  - In `firmware/sms_encoding.py`: Replaced Python 3.9+ `str.removeprefix()` and `str.removesuffix()` in `parse_text_indicator` with MicroPython-compatible slicing (`rem[1:] if rem.startswith(...)` and `rem[:-1] if rem.endswith(...)`).
  - In `pyproject.toml`: Added `[tool.ruff.lint.per-file-ignores]` rule for `"firmware/*" = ["FURB188"]` so the linter does not enforce `str.removeprefix`/`str.removesuffix` on MicroPython firmware files.
  - In `tests/test_firmware_sms_encoding.py`: Added explicit test cases for plain text, single-word SMS, and indicators without colons.

## [0.31.5] - 2026-09-23

### Fixed
- Fixed real-time BLE log capture and PWA service worker caching (`#99`):
  - In `firmware/logger.py`: Intercept `builtins.print` to capture all print statements and exceptions in MicroPython and CPython without stream protocol conflicts or terminal lockups. Removed unsupported `from __future__ import annotations` for bare-metal MicroPython compatibility. Preserved physical USB UART serial console output while streaming logs over BLE.
  - In `tools/web-config/sw.js`: Switched from Cache-First to **Network-First** strategy with offline cache fallback, ensuring browser and mobile devices always fetch the latest web application assets when online. Updated cache name to `snippen-config-v0.31.5` and ensured immediate activation via `skipWaiting()` and `clients.claim()`.
  - In `tools/web-config/index.html` and `tools/web-config/js/app.js`: Added cache-busting query parameters (`?v=0.31.5`) to CSS and script resources and added proactive `registration.update()` on load.

## [0.31.4] - 2026-09-23

### Fixed
- Fixed hardware watchdog timeout during firmware deployment of large files (`#97`):
  - In `firmware/boot.py`: Implemented `_start_wdt_feed_timer()` using a periodic hardware timer (`machine.Timer(-1)`) running every 1000ms to continuously feed `machine.WDT()` across raw REPL, multi-second file transfers (`mpremote cp`), and idle states.
  - In `scripts/deploy_firmware.py`: Reordered `files_to_deploy` so essential boot and logging components (`boot.py`, `logger.py`, `config.py`) are transferred before the large `main.py` application file.
  - In `tests/mocks/micropython_mocks.py`: Added `MockTimer` to support virtual hardware timer simulation and added corresponding unit tests in `tests/test_firmware_boot.py`.

## [0.31.3] - 2026-09-23

### Fixed
- Fixed MicroPython bare-metal `AttributeError: module sys has no attribute stdout` in `firmware/logger.py` (`#95`):
  - Used safe `getattr(sys, "stdout", None)` and added MicroPython `uos.dupterm()` integration with `readinto()` implementation.
  - Allowed `write()` to accept both `bytes`/`bytearray` and `str` chunks.
  - Wrapped `setup_logger()` inside `GatewayApp.__init__` in `firmware/main.py` with exception handling to prevent application boot aborts.

## [0.31.2] - 2026-09-23

### Fixed
- Added fast-boot modem online check in `firmware/boot.py` to eliminate soft-reset raw REPL timeouts (`#93`):
  - Implemented `is_modem_online()` in `firmware/boot.py` which probes UART with `AT` before performing the 7.6-second power-on sequence.
  - Skips redundant PWRKEY pulsing and 6-second radio delays when the modem is already running (e.g. across soft resets or mpremote connections), reducing boot time to <150ms.
  - Preserved full cold-boot initialization when modem is unpowered or unresponsive.

## [0.31.1] - 2026-09-23

### Fixed
- Fixed task watchdog (`mpy_machine_wdt`) crash during firmware deployment and batched file transfer (`#91`):
  - In `firmware/boot.py`: Implemented `sleep_ms_feeding_wdt()` and `_feed_wdt_if_active()` to feed the ESP32 hardware/task watchdog timer (`machine.WDT`) every 250ms during PWRKEY pulsing and modem boot initialization, preventing `task_wdt` timeouts across soft resets.
  - In `scripts/deploy_firmware.py`: Batched all firmware files into a single `mpremote cp <file1> <file2> ... :` invocation, avoiding repeated soft reset boot cycles and reducing deployment time from ~2 minutes to ~3 seconds.
  - Added `firmware/logger.py` to `files_to_deploy` in `scripts/deploy_firmware.py`.

## [0.31.0] - 2026-09-23

### Added
- Real-time logging and live operational monitoring over Bluetooth Low Energy (Web BLE) (`#89`):
  - Created `firmware/logger.py` (`LogStreamRedirector`) implementing a non-blocking in-memory circular ring buffer for MicroPython `sys.stdout` and `sys.stderr` while preserving hardware USB UART console monitoring.
  - Added new BLE GATT characteristic `CHAR_LOGS_UUID` (`6e400005-b5a3-f393-e0a9-e50e24dcca9e`) in `firmware/ble_config.py` with `READ` and `NOTIFY` support.
  - Added live gateway operations mode during BLE connections in `firmware/main.py`: commands `START_OPERATIONS` / `RESUME_OPERATIONS` and `STOP_OPERATIONS` / `PAUSE_OPERATIONS` allow running full background SMS transmission/reception and HTTP API polling while maintaining active BLE connectivity.
  - Added historical log retrieval (`GET_LOGS`) and buffer reset (`CLEAR_LOGS`) commands.
  - Implemented `CHAR_LOGS_UUID` subscription, event dispatching, and mock streaming in `tools/web-config/js/ble.js`.
  - Added **Lilygo Konsoll & Sanntidslogg** card in `tools/web-config/index.html` with monospace terminal display, live status badges, filter search, autoscroll toggle, clipboard copying, and live operations start/pause controls.

## [0.30.1] - 2026-09-21

### Fixed
- Fixed WiFi scanning blockage and BLE restart `ENODEV` error (`#87`):
  - In `firmware/wifi.py` (`scan_networks`): Disconnect background connection attempt (`wlan.disconnect()`) and allow radio settling time before scanning, preventing ESP-IDF `Wifi Internal State Error` when STA is in connecting state.
  - Added debug logging in `firmware/wifi.py` and `firmware/main.py` displaying channels scanned, access points discovered, and network counts returned over BLE.
  - In `firmware/main.py` (`enter_provisioning_mode`): Automatically abort background WiFi connection attempts when switching into BLE provisioning mode.
  - In `firmware/ble_config.py` (`stop`): Ceased calling `ble.active(False)` upon stopping advertising, preventing `[Errno 19] ENODEV` controller errors and invalid GATT service handles when re-entering provisioning mode.

## [0.30.0] - 2026-09-21

### Changed
- Simplified BOOT button handling and improved BLE provisioning activation responsiveness (`#83`):
  - Removed 3-second long-press requirement in `firmware/button.py` (`ButtonHandler`), allowing any debounced button press (50 ms) to trigger activation immediately.
  - Removed obsolete long-press timer variables (`_press_start_ms`, `_long_press_triggered`) and threshold checks.
  - Ensured single activation per physical press by debouncing input transitions and preventing repeated event triggers while the button is continuously held down.
  - Added `on_press` callback in `ButtonHandler` while retaining `on_short_press` and `on_long_press` as backward-compatible aliases.
  - Updated `firmware/main.py` (`GatewayApp`) to connect `on_boot_button_press` on button press.
  - Enhanced main event loop in `firmware/main.py` to immediately interrupt the 50ms sliced sleep loop upon provisioning mode state change, eliminating latency when entering or exiting BLE mode.
  - Updated on-device interactive button test `firmware/test_button.py` and `firmware/test_ble_provisioning.py` for single-press activation.
  - Updated documentation in `docs/README_LILYGO.md` and Web Bluetooth onboarding in `tools/web-config/index.html`.
  - Expanded unit test suite in `tests/test_firmware_button.py` and `tests/test_firmware_main.py`.

## [0.29.0] - 2026-09-21

### Added
- Outbound SMS chunking and inbound SMS reassembly for long messages (`#82`):
  - Added character count functions `gsm7_length` and `ucs2_length` in `firmware/sms_encoding.py`.
  - Added `split_sms_body` in `firmware/sms_encoding.py` to segment messages exceeding single SMS limits (160 characters for GSM-7 or 70 characters for UCS-2) into ordered chunks, respecting word/whitespace boundaries, surrogate pair boundaries, and prepending part indicators `(i/N) `.
  - Integrated automatic chunking in `ModemDriver.send_sms` (`firmware/modem.py`), transmitting parts sequentially with configurable inter-part delay (`sms_chunk_delay_ms`, default 500ms) and combining message references upon completion.
  - Added concatenated SMS detection supporting both GSM User Data Headers (8-bit and 16-bit UDH via `parse_udh`) and text-mode indicators (`parse_text_indicator` and `parse_multipart_info`).
  - Added `InboundReassembler` in `firmware/sms_encoding.py` to buffer and reassemble multipart incoming messages per sender, with configurable timeout handling (`sms_multipart_timeout_sec`, default 30s) to safely release partial segments without dropping data or leaking memory.
  - Updated `ModemDriver.read_inbound_sms` (`firmware/modem.py`) to delete raw segments from SIM storage immediately with `AT+CMGD` to prevent SIM overflow (`+CMS ERROR: 322`), passing messages through `InboundReassembler` before returning unified messages.

## [0.28.0] - 2026-09-19

### Added
- Supported character encodings for emojis and international characters (`#51`):
  - Created `firmware/sms_encoding.py` implementing GSM 03.38 7-bit character set validation (`is_gsm7`) and UCS-2 / UTF-16BE hex encoding/decoding (`encode_ucs2_hex`, `decode_ucs2_hex`, `is_ucs2_hex`, `decode_inbound_text`).
  - Added support for UTF-16 surrogate pairs (e.g. 🤖, 🎉) and international characters (Norwegian æ, ø, å).
  - Integrated dynamic UCS-2 switching in `firmware/modem.py` for outbound messages containing non-GSM characters, preventing `CMS ERROR: SMS size more than expected`.
  - Added transparent UCS-2 hex decoding for inbound SMS bodies and sender numbers.
- Implemented MicroPython HTTPS REST client and WiFi manager (`#52`):
  - Created `firmware/snippen_api.py` (`SnippenApiClient`) communicating with Snippen Booking REST API (`https://vestreholmensameie.no/wp-json/snippen/v1/sms`) with Bearer token authentication.
  - Implemented `fetch_outbox` for retrieving queued outbound SMS messages, cellular modem transmission, and delivery outcome reporting via `report_outbox_status` (`sent`/`failed`).
  - Implemented `report_inbound_sms` for forwarding newly received tenant SMS messages directly into the WordPress communication history.
  - Added non-blocking WiFi status checking and connection initiation (`is_connected`, `start_connect`, `ensure_connected`) in `firmware/wifi.py`.
- Implemented ESP32 system health, hardware watchdog, and recovery (`#53`):
  - Enabled ESP32 hardware watchdog (`machine.WDT`) with configurable timeout (default 60s), fed on every event loop tick and maintained during BLE provisioning mode.
  - Added cellular modem health monitoring in `firmware/main.py`: verifies AT responsiveness during heartbeat ticks and automatically triggers hardware power-cycle recovery (`boot.power_cycle_modem()`) if the modem becomes unresponsive for 3 consecutive checks.
  - Added `power_off_modem` and `power_cycle_modem` GPIO hardware sequencing in `firmware/boot.py`.
  - Added non-blocking WiFi auto-reconnection with exponential backoff on network dropouts.
  - Added memory management: periodic `gc.collect()`, free heap monitoring, and aggressive garbage collection when free heap drops below 20 KB.

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
