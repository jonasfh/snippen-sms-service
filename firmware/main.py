"""Main application event loop for Snippen SMS Gateway on Lilygo T-Call A7670E (MicroPython).

Coordinates WiFi connectivity, Snippen REST API polling, and cellular SMS processing.
"""

try:
    import utime as time
except ImportError:
    import time

try:
    from config import load_config, save_config
except ImportError:

    def load_config():  # type: ignore[misc]
        return {}

    def save_config(updates, config_path="config.json"):  # type: ignore[misc]
        return True


try:
    import gc
except ImportError:
    gc = None

try:
    import machine
except ImportError:
    machine = None

try:
    import boot
except ImportError:
    boot = None

try:
    from modem import ModemDriver
except ImportError:
    ModemDriver = None

try:
    from button import ButtonHandler
except ImportError:
    ButtonHandler = None

try:
    from ble_config import BLEConfigServer
except ImportError:
    BLEConfigServer = None

try:
    import wifi
except ImportError:
    wifi = None

try:
    from snippen_api import SnippenApiClient
except ImportError:
    SnippenApiClient = None

try:
    from logger import setup_logger
except ImportError:
    setup_logger = None


class GatewayApp:
    """MicroPython SMS Gateway coordinator."""

    def __init__(
        self,
        config: dict | None = None,
        uart: object | None = None,
        button: object | None = None,
        ble_server: object | None = None,
    ) -> None:
        self.config = config if config is not None else load_config()
        self.uart = uart
        self.button = button
        self.ble_server = ble_server
        if setup_logger is not None:
            try:
                self.logger = setup_logger(max_lines=100)
            except Exception as exc:  # noqa: BLE001
                print(f"[main] Warning: Failed to setup logger: {exc}")
                self.logger = None
        else:
            self.logger = None
        if (
            self.logger is not None
            and self.ble_server is not None
            and hasattr(self.ble_server, "notify_log")
        ):
            self.logger.set_callback(self.ble_server.notify_log)
        self.modem = None
        self.api_client = None
        self.wdt = None
        self.is_provisioning_mode = False
        self.live_operations_active = True
        self.provisioning_started_at = 0
        self.running = False
        self.cycle_count = 0
        self.last_heartbeat = 0
        self.last_inbox_check = 0
        self.last_outbox_poll = 0
        self.last_wifi_reconnect = 0
        self.wifi_backoff_sec = 5
        self.consecutive_modem_failures = 0

    def enter_provisioning_mode(self, reason: str = "manual") -> None:
        """Switch gateway into BLE provisioning mode (Issue #59, #60, #87)."""
        if self.is_provisioning_mode:
            return
        print(f"[main] Entering provisioning mode (reason: {reason})...")
        self.is_provisioning_mode = True
        self.live_operations_active = False
        self.provisioning_started_at = time.time()
        # Abort any background WiFi connecting attempt to free the radio for BLE & scanning
        if wifi is not None and not wifi.is_connected():
            try:
                wlan = wifi.get_wlan()
                if wlan is not None and hasattr(wlan, "disconnect"):
                    wlan.disconnect()
            except Exception:  # noqa: BLE001, S110
                pass

        if self.ble_server is not None and not self.ble_server.is_running:
            try:
                self.ble_server.update_config_characteristic(self.config)
                self.ble_server.start()
            except Exception as exc:  # noqa: BLE001
                print(f"[main] Warning: Failed to start BLE server: {exc}")

    def exit_provisioning_mode(self, reason: str = "manual") -> None:
        """Exit BLE provisioning mode and resume normal gateway loop (Issue #59, #60)."""
        if not self.is_provisioning_mode:
            return
        print(f"[main] Exiting provisioning mode (reason: {reason})...")
        self.is_provisioning_mode = False
        self.live_operations_active = True
        if self.ble_server is not None and self.ble_server.is_running:
            self.ble_server.stop()

    def on_ble_config_received(self, new_config: dict) -> None:
        """Callback when companion app writes new configuration parameters (Issue #60, #61)."""
        print(f"[main] Configuration received via BLE: {list(new_config.keys())}")
        self.config.update(new_config)
        save_config(new_config)

    def on_ble_command(self, cmd: str, payload: dict) -> dict:
        """Callback when companion app sends a remote control command (Issue #60, #61)."""
        print(f"[main] Command received via BLE: {cmd}")
        if cmd == "SCAN_WIFI":
            if wifi is not None:
                print("[main] Initiating WiFi scan on request from companion app...")
                networks = wifi.scan_networks()
                print(f"[main] Returning {len(networks)} WiFi networks over BLE")
                return {"cmd": "SCAN_WIFI", "status": "ok", "networks": networks}
            return {"cmd": "SCAN_WIFI", "status": "error", "message": "WiFi module unavailable"}

        if cmd == "TEST_WIFI":
            ssid = payload.get("wifi_ssid") or self.config.get("wifi_ssid", "")
            password = payload.get("wifi_password") or self.config.get("wifi_password", "")
            if wifi is not None:
                res = wifi.test_connection(ssid, password)
                resp = {"cmd": "TEST_WIFI"}
                resp.update(res)
                return resp
            return {"cmd": "TEST_WIFI", "status": "error", "message": "WiFi module unavailable"}

        if cmd in ("APPLY_AND_EXIT", "SAVE_CONFIG"):
            save_config(self.config)
            if cmd == "APPLY_AND_EXIT":
                self.exit_provisioning_mode(reason="command")
                return {
                    "cmd": cmd,
                    "status": "ok",
                    "message": "Saved configuration and exited provisioning mode",
                }
            return {"cmd": cmd, "status": "ok", "message": "Configuration saved to flash"}

        if cmd == "GET_STATUS":
            return {"cmd": cmd, "status": "ok", "telemetry": self.get_telemetry_status()}

        if cmd in ("START_OPERATIONS", "RESUME_OPERATIONS"):
            self.live_operations_active = True
            print("[main] Live gateway operations started over BLE.")
            return {
                "cmd": cmd,
                "status": "ok",
                "live_operations": True,
                "message": "Gateway operations active with live BLE monitoring",
            }

        if cmd in ("STOP_OPERATIONS", "PAUSE_OPERATIONS"):
            self.live_operations_active = False
            print("[main] Live gateway operations paused over BLE.")
            return {
                "cmd": cmd,
                "status": "ok",
                "live_operations": False,
                "message": "Gateway operations paused for provisioning",
            }

        if cmd == "GET_LOGS":
            count = 50
            if isinstance(payload, dict) and "count" in payload:
                try:
                    count = int(payload["count"])
                except (ValueError, TypeError):
                    pass
            lines = self.logger.get_lines(count) if self.logger is not None else []
            return {
                "cmd": "GET_LOGS",
                "status": "ok",
                "lines": lines,
            }

        if cmd == "CLEAR_LOGS":
            if self.logger is not None:
                self.logger.clear()
            return {"cmd": "CLEAR_LOGS", "status": "ok"}

        return {"cmd": cmd, "status": "ok"}

    def get_telemetry_status(self) -> dict:
        """Compile real-time operational status for BLE telemetry reporting (Issue #61)."""
        status: dict = {
            "status": "provisioning" if self.is_provisioning_mode else "running",
            "live_operations": self.live_operations_active,
            "cycle_count": self.cycle_count,
            "wifi_ssid": self.config.get("wifi_ssid", ""),
        }
        try:
            import network

            wlan = network.WLAN(network.STA_IF)
            status["wifi_connected"] = wlan.isconnected()
            if wlan.isconnected():
                ip, _mask, gw, _dns = wlan.ifconfig()
                status["ip"] = ip
                status["gateway"] = gw
        except Exception:  # noqa: BLE001, S110
            pass

        if self.modem is not None:
            try:
                sig = self.modem.get_signal_quality()
                if sig:
                    status["cellular_rssi"] = sig.get("rssi")
                    status["cellular_dbm"] = sig.get("dbm")
                reg = self.modem.get_network_registration()
                if reg:
                    status["cellular_net"] = reg.get("description", "Unknown")
            except Exception:  # noqa: BLE001, S110
                pass

        if gc is not None and hasattr(gc, "mem_free"):
            try:
                status["free_heap"] = gc.mem_free()
            except Exception:  # noqa: BLE001, S110
                pass

        return status

    def on_boot_button_press(self) -> None:
        """Callback when BOOT button (GPIO 0) is pressed (Issue #83)."""
        print("[main] BOOT button press detected.")
        if self.is_provisioning_mode:
            self.exit_provisioning_mode(reason="button_toggle")
        else:
            self.enter_provisioning_mode(reason="button_press")

    def on_boot_long_press(self) -> None:
        """Backward-compatible alias for on_boot_button_press."""
        self.on_boot_button_press()

    def setup(self) -> bool:
        """Verify hardware state and setup subsystem connections."""
        print("[main] Initializing Snippen SMS Gateway application...")

        # Initialize physical BOOT button handler
        if self.button is None and ButtonHandler is not None:
            btn_pin = self.config.get("pin_boot_button", 0)
            debounce_ms = self.config.get("button_debounce_ms", 50)
            try:
                self.button = ButtonHandler(
                    pin_id=btn_pin,
                    debounce_ms=debounce_ms,
                    on_press=self.on_boot_button_press,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[main] Warning: Failed to initialize BOOT button on GPIO {btn_pin}: {exc}")

        # Initialize BLE provisioning server
        if self.ble_server is None and BLEConfigServer is not None:
            timeout_sec = self.config.get("provisioning_timeout_sec", 300)
            try:
                self.ble_server = BLEConfigServer(
                    config=self.config,
                    timeout_sec=timeout_sec,
                    on_command=self.on_ble_command,
                    on_config_received=self.on_ble_config_received,
                    on_timeout=lambda: self.exit_provisioning_mode(reason="timeout"),
                )
            except Exception as exc:  # noqa: BLE001
                print(f"[main] Warning: Failed to initialize BLE config server: {exc}")

        if (
            self.logger is not None
            and self.ble_server is not None
            and hasattr(self.ble_server, "notify_log")
        ):
            self.logger.set_callback(self.ble_server.notify_log)

        # If UART not provided, try to obtain from boot module
        if self.uart is None:
            try:
                import boot

                self.uart = getattr(boot, "modem_uart", None)
                if self.uart is None and hasattr(boot, "init_uart"):
                    self.uart = boot.init_uart(self.config)
            except (ImportError, AttributeError):
                pass

        if self.uart is None:
            print("[main] Warning: Modem UART is not initialized.")
        else:
            print("[main] Modem UART connection verified.")

        if ModemDriver is not None and self.uart is not None:
            self.modem = ModemDriver(uart=self.uart, config=self.config)
            if not self.modem.init_modem():
                print("[main] Warning: Modem AT initialization reported errors.")
            else:
                print("[main] Modem AT engine initialized successfully.")

        # Initialize hardware watchdog (Issue #53)
        enable_wdt = self.config.get("enable_watchdog", True)
        if enable_wdt and machine is not None and hasattr(machine, "WDT"):
            wdt_timeout = self.config.get("watchdog_timeout_ms", 60000)
            try:
                self.wdt = machine.WDT(timeout=wdt_timeout)
                print(f"[main] Hardware watchdog enabled ({wdt_timeout}ms timeout).")
            except Exception as exc:  # noqa: BLE001
                print(f"[main] Warning: Failed to initialize hardware watchdog: {exc}")

        # Initialize Snippen REST API client (Issue #52)
        if self.api_client is None and SnippenApiClient is not None:
            api_url = self.config.get(
                "snippen_api_base_url", "https://vestreholmensameie.no/wp-json/snippen/v1"
            )
            api_token = self.config.get("snippen_api_token", "")
            self.api_client = SnippenApiClient(base_url=api_url, api_token=api_token)

        # Check if device is unconfigured or if BOOT button is held at boot
        wifi_ssid = self.config.get("wifi_ssid", "")
        wifi_pwd = self.config.get("wifi_password", "")
        api_token = self.config.get("snippen_api_token", "")
        if not wifi_ssid or not api_token:
            self.enter_provisioning_mode(reason="unconfigured")
        elif self.button is not None and self.button.is_down():
            self.enter_provisioning_mode(reason="boot_button_pressed")
        elif wifi_ssid and wifi is not None and not wifi.is_connected():
            print(f"[main] Initiating WiFi connection to '{wifi_ssid}'...")
            wifi.start_connect(wifi_ssid, wifi_pwd)

        return True

    def process_inbox(self) -> int:
        """Poll incoming SMS from SIM card and forward to Snippen Booking (Issue #50, #52)."""
        if self.modem is None:
            return 0
        try:
            auto_delete = self.config.get("sms_auto_delete", True)
            messages = self.modem.read_inbound_sms(delete_after_read=auto_delete)
            if messages:
                print(f"[main] Received {len(messages)} inbound SMS from SIM storage.")
                for msg in messages:
                    print(f"[main] Inbound SMS from {msg.get('sender')}: {msg.get('body')}")
                if self.api_client is not None and wifi is not None and wifi.is_connected():
                    ok = self.api_client.report_inbound_sms(messages)
                    if ok:
                        print(f"[main] Forwarded {len(messages)} inbound SMS to Snippen Booking.")
                    else:
                        print("[main] Warning: Failed to forward inbound SMS to Snippen Booking.")
            return len(messages)
        except Exception as exc:  # noqa: BLE001
            print(f"[main] Error processing inbox: {exc}")
            return 0

    def poll_outbox(self) -> int:
        """Poll outbound SMS from Snippen Booking API and transmit over cellular modem (Issue #52)."""
        if self.api_client is None or self.modem is None:
            return 0
        if wifi is not None and not wifi.is_connected():
            return 0

        try:
            limit = self.config.get("outbox_batch_limit", 5)
            messages = self.api_client.fetch_outbox(limit=limit)
            if not messages:
                return 0

            print(f"[main] Fetched {len(messages)} pending outbound SMS from Snippen Booking.")
            statuses: list[dict] = []
            for msg in messages:
                raw_id = msg.get("id") or msg.get("external_id")
                msg_id = str(raw_id) if raw_id is not None else ""
                recipient = msg.get("recipient", "")
                body = msg.get("body", "")
                print(f"[main] Transmitting outbound SMS #{msg_id} to {recipient}...")

                success, ref_or_err = self.modem.send_sms(recipient, body)
                if success:
                    print(f"[main] Outbound SMS #{msg_id} delivered (ref: {ref_or_err}).")
                    statuses.append(
                        {
                            "external_id": msg_id,
                            "status": "sent",
                            "modem_message_id": str(ref_or_err) if ref_or_err else "OK",
                        }
                    )
                else:
                    print(f"[main] Outbound SMS #{msg_id} transmission failed: {ref_or_err}")
                    statuses.append(
                        {
                            "external_id": msg_id,
                            "status": "failed",
                            "error_message": str(ref_or_err),
                        }
                    )

            if statuses:
                self.api_client.report_outbox_status(statuses)
            return len(messages)
        except Exception as exc:  # noqa: BLE001
            print(f"[main] Error polling outbox: {exc}")
            return 0

    def heartbeat(self) -> None:
        """Log diagnostic status and perform health maintenance (Issue #53)."""
        print(f"[main] Heartbeat tick - cycle #{self.cycle_count}")

        # Memory garbage collection and heap telemetry
        if gc is not None:
            gc.collect()
            if hasattr(gc, "mem_free"):
                free_bytes = gc.mem_free()
                print(f"[health] Memory: Free heap {free_bytes} bytes")
                if free_bytes < 20480:
                    print("[health] Warning: Free heap low (<20KB). Performing aggressive GC.")
                    gc.collect()

        # Modem health check & recovery
        if self.modem is not None:
            modem_ok = self.modem.check_at(retries=2, delay_ms=300)
            if not modem_ok:
                self.consecutive_modem_failures += 1
                print(
                    f"[health] Warning: Modem AT ping failed (consecutive failures: {self.consecutive_modem_failures})."
                )
                if self.consecutive_modem_failures >= 3:
                    print(
                        "[health] Modem unresponsive for 3 consecutive checks. Initiating hardware power-cycle..."
                    )
                    if boot is not None and hasattr(boot, "power_cycle_modem"):
                        try:
                            self.uart = boot.power_cycle_modem(self.config)
                            if ModemDriver is not None:
                                self.modem = ModemDriver(uart=self.uart, config=self.config)
                                self.modem.init_modem()
                        except Exception as exc:  # noqa: BLE001
                            print(f"[health] Error during modem power-cycle recovery: {exc}")
                    self.consecutive_modem_failures = 0
            else:
                self.consecutive_modem_failures = 0
                try:
                    sig = self.modem.get_signal_quality()
                    if sig and sig.get("dbm") is not None:
                        print(f"[main] Cellular signal: RSSI {sig['rssi']} ({sig['dbm']} dBm)")
                    reg = self.modem.get_network_registration()
                    if reg:
                        print(f"[main] Cellular network: {reg.get('description', 'Unknown')}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[main] Modem signal query error during heartbeat: {exc}")

    def tick(self) -> None:
        """Execute one iteration of the gateway event loop."""
        self.cycle_count += 1
        now = time.time()

        # Feed hardware watchdog (Issue #53)
        if self.wdt is not None and hasattr(self.wdt, "feed"):
            self.wdt.feed()

        # Periodic garbage collection to maintain stable heap
        if gc is not None and (self.cycle_count % 10 == 0):
            gc.collect()

        # Poll physical button state
        if self.button is not None:
            self.button.poll()

        # Handle provisioning mode lifecycle
        if self.is_provisioning_mode:
            if self.ble_server is not None:
                self.ble_server.poll(now)
                if self.ble_server.conn_handle is not None and (self.cycle_count % 5 == 0):
                    self.ble_server.notify_status(self.get_telemetry_status())
            if not self.live_operations_active:
                timeout_sec = self.config.get("provisioning_timeout_sec", 300)
                if self.ble_server is not None and self.ble_server.conn_handle is not None:
                    self.provisioning_started_at = now
                elif now - self.provisioning_started_at >= timeout_sec:
                    self.exit_provisioning_mode(reason="timeout")
                return
            if self.ble_server is not None and self.ble_server.conn_handle is not None:
                self.provisioning_started_at = now

        # Non-blocking WiFi reconnect check (Issue #52, #53)
        if wifi is not None and not wifi.is_connected():
            if now - self.last_wifi_reconnect >= self.wifi_backoff_sec:
                self.last_wifi_reconnect = now
                ssid = self.config.get("wifi_ssid", "")
                pwd = self.config.get("wifi_password", "")
                if ssid:
                    wifi.start_connect(ssid, pwd)
                    self.wifi_backoff_sec = min(60, self.wifi_backoff_sec * 2)
        elif wifi is not None and wifi.is_connected():
            self.wifi_backoff_sec = 5

        # Check inbox interval
        inbox_interval = self.config.get("inbox_check_interval_sec", 5)
        if now - self.last_inbox_check >= inbox_interval:
            self.process_inbox()
            self.last_inbox_check = now

        # Poll outbox interval
        outbox_interval = self.config.get("outbox_poll_interval_sec", 5)
        if now - self.last_outbox_poll >= outbox_interval:
            self.poll_outbox()
            self.last_outbox_poll = now

        # Heartbeat interval
        hb_interval = self.config.get("heartbeat_interval_sec", 30)
        if now - self.last_heartbeat >= hb_interval:
            self.heartbeat()
            self.last_heartbeat = now

    def run(self, max_cycles: int | None = None) -> None:
        """Run the main event loop."""
        if not self.setup():
            print("[main] Application setup failed. Exiting.")
            return

        self.running = True
        print("[main] Gateway event loop started.")

        try:
            while self.running:
                self.tick()

                if max_cycles is not None and self.cycle_count >= max_cycles:
                    print(f"[main] Reached max cycles ({max_cycles}). Stopping loop.")
                    break

                # Sleep in 50ms slices while polling button for instant response
                prev_mode = self.is_provisioning_mode
                for _ in range(20):
                    if not self.running:
                        break
                    if self.button is not None:
                        self.button.poll()
                    if self.is_provisioning_mode != prev_mode:
                        break
                    time.sleep(0.05)
        except KeyboardInterrupt:
            print("\n[main] Keyboard interrupt received. Stopping event loop.")
        except Exception as exc:  # noqa: BLE001
            print(f"[main] Unhandled exception in event loop: {exc}")
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop event loop gracefully."""
        self.running = False
        print("[main] Gateway application stopped.")


def main() -> None:
    """Entry point for MicroPython execution."""
    app = GatewayApp()
    app.run()


# Execute main application loop upon run
if __name__ == "__main__":
    main()
