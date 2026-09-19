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
        self.modem = None
        self.is_provisioning_mode = False
        self.provisioning_started_at = 0
        self.running = False
        self.cycle_count = 0
        self.last_heartbeat = 0
        self.last_inbox_check = 0
        self.last_outbox_poll = 0

    def enter_provisioning_mode(self, reason: str = "manual") -> None:
        """Switch gateway into BLE provisioning mode (Issue #59, #60)."""
        if self.is_provisioning_mode:
            return
        print(f"[main] Entering provisioning mode (reason: {reason})...")
        self.is_provisioning_mode = True
        self.provisioning_started_at = time.time()
        if self.ble_server is not None and not self.ble_server.is_running:
            self.ble_server.update_config_characteristic(self.config)
            self.ble_server.start()

    def exit_provisioning_mode(self, reason: str = "manual") -> None:
        """Exit BLE provisioning mode and resume normal gateway loop (Issue #59, #60)."""
        if not self.is_provisioning_mode:
            return
        print(f"[main] Exiting provisioning mode (reason: {reason})...")
        self.is_provisioning_mode = False
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
                networks = wifi.scan_networks()
                return {"cmd": "SCAN_WIFI", "status": "ok", "networks": networks}
            return {"cmd": "SCAN_WIFI", "status": "error", "message": "WiFi module unavailable"}

        if cmd == "TEST_WIFI":
            ssid = payload.get("wifi_ssid") or self.config.get("wifi_ssid", "")
            password = payload.get("wifi_password") or self.config.get("wifi_password", "")
            if wifi is not None:
                res = wifi.test_connection(ssid, password)
                return {"cmd": "TEST_WIFI", **res}
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

        return {"cmd": cmd, "status": "ok"}

    def get_telemetry_status(self) -> dict:
        """Compile real-time operational status for BLE telemetry reporting (Issue #61)."""
        status: dict = {
            "status": "provisioning" if self.is_provisioning_mode else "running",
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

        return status

    def on_boot_long_press(self) -> None:
        """Callback when BOOT button (GPIO 0) is held for >= 3 seconds."""
        print("[main] BOOT button long-press detected.")
        if self.is_provisioning_mode:
            self.exit_provisioning_mode(reason="button_toggle")
        else:
            self.enter_provisioning_mode(reason="button_long_press")

    def setup(self) -> bool:
        """Verify hardware state and setup subsystem connections."""
        print("[main] Initializing Snippen SMS Gateway application...")

        # Initialize physical BOOT button handler
        if self.button is None and ButtonHandler is not None:
            btn_pin = self.config.get("pin_boot_button", 0)
            long_press_ms = self.config.get("button_long_press_ms", 3000)
            debounce_ms = self.config.get("button_debounce_ms", 50)
            try:
                self.button = ButtonHandler(
                    pin_id=btn_pin,
                    long_press_ms=long_press_ms,
                    debounce_ms=debounce_ms,
                    on_long_press=self.on_boot_long_press,
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

        # If UART not provided, try to obtain from boot module
        if self.uart is None:
            try:
                import boot

                self.uart = boot.modem_uart
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

        # Check if device is unconfigured or if BOOT button is held at boot
        wifi_ssid = self.config.get("wifi_ssid", "")
        api_token = self.config.get("snippen_api_token", "")
        if not wifi_ssid or not api_token:
            self.enter_provisioning_mode(reason="unconfigured")
        elif self.button is not None and self.button.is_down():
            self.enter_provisioning_mode(reason="boot_button_pressed")

        return True

    def process_inbox(self) -> int:
        """Poll incoming SMS from SIM card (Issue #50)."""
        if self.modem is None:
            return 0
        try:
            auto_delete = self.config.get("sms_auto_delete", True)
            messages = self.modem.read_inbound_sms(delete_after_read=auto_delete)
            if messages:
                print(f"[main] Received {len(messages)} inbound SMS from SIM storage.")
                for msg in messages:
                    print(f"[main] Inbound SMS from {msg.get('sender')}: {msg.get('body')}")
            return len(messages)
        except Exception as exc:  # noqa: BLE001
            print(f"[main] Error processing inbox: {exc}")
            return 0

    def poll_outbox(self) -> int:
        """Poll outbound SMS from Snippen Booking API (stub hook for Issue #52)."""
        # HTTPS long-polling loop implemented in Issue #52
        return 0

    def heartbeat(self) -> None:
        """Log diagnostic status and perform health maintenance."""
        print(f"[main] Heartbeat tick - cycle #{self.cycle_count}")
        if self.modem is not None:
            try:
                sig = self.modem.get_signal_quality()
                if sig and sig.get("dbm") is not None:
                    print(f"[main] Cellular signal: RSSI {sig['rssi']} ({sig['dbm']} dBm)")
                reg = self.modem.get_network_registration()
                if reg:
                    print(f"[main] Cellular network: {reg.get('description', 'Unknown')}")
            except Exception as exc:  # noqa: BLE001
                print(f"[main] Modem status check error during heartbeat: {exc}")

    def tick(self) -> None:
        """Execute one iteration of the gateway event loop."""
        self.cycle_count += 1
        now = time.time()

        # Poll physical button state
        if self.button is not None:
            self.button.poll()

        # Handle provisioning mode lifecycle
        if self.is_provisioning_mode:
            if self.ble_server is not None:
                self.ble_server.poll(now)
                if self.ble_server.conn_handle is not None and (self.cycle_count % 5 == 0):
                    self.ble_server.notify_status(self.get_telemetry_status())
            timeout_sec = self.config.get("provisioning_timeout_sec", 300)
            if now - self.provisioning_started_at >= timeout_sec:
                self.exit_provisioning_mode(reason="timeout")
            return

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

                time.sleep(1)
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
