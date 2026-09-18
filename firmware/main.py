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


class GatewayApp:
    """MicroPython SMS Gateway coordinator."""

    def __init__(self, config: dict | None = None, uart: object | None = None) -> None:
        self.config = config if config is not None else load_config()
        self.uart = uart
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

        return True

    def process_inbox(self) -> int:
        """Poll incoming SMS from SIM card (stub hook for Issue #50)."""
        # Detailed AT command parsing implemented in Issue #50
        return 0

    def poll_outbox(self) -> int:
        """Poll outbound SMS from Snippen Booking API (stub hook for Issue #52)."""
        # HTTPS long-polling loop implemented in Issue #52
        return 0

    def heartbeat(self) -> None:
        """Log diagnostic status and perform health maintenance."""
        print(f"[main] Heartbeat tick - cycle #{self.cycle_count}")

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
