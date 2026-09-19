"""Main application event loop for Snippen SMS Gateway on Lilygo T-Call A7670E (MicroPython).

Coordinates WiFi connectivity, Snippen REST API polling, and cellular SMS processing.
"""

try:
    import utime as time
except ImportError:
    import time

try:
    from config import load_config
except ImportError:

    def load_config():  # type: ignore[misc]
        return {}


try:
    from modem import ModemDriver
except ImportError:
    ModemDriver = None


class GatewayApp:
    """MicroPython SMS Gateway coordinator."""

    def __init__(self, config: dict | None = None, uart: object | None = None) -> None:
        self.config = config if config is not None else load_config()
        self.uart = uart
        self.modem = None
        self.running = False
        self.cycle_count = 0
        self.last_heartbeat = 0
        self.last_inbox_check = 0
        self.last_outbox_poll = 0

    def setup(self) -> bool:
        """Verify hardware state and setup subsystem connections."""
        print("[main] Initializing Snippen SMS Gateway application...")

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
