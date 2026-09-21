"""Bluetooth Low Energy (BLE) GATT provisioning server for MicroPython (Issue #60).

Implements BLE peripheral advertising and GATT service/characteristics for wireless
configuration from a companion Android application.
"""

try:
    import ubluetooth as bluetooth  # type: ignore[import-not-found]
except ImportError:
    try:
        import bluetooth  # type: ignore[no-redef]
    except ImportError:
        bluetooth = None  # type: ignore[assignment]

try:
    import ujson as json  # type: ignore[import-not-found]
except ImportError:
    import json  # type: ignore[no-redef]

try:
    import utime as time  # type: ignore[import-not-found]
except ImportError:
    import time  # type: ignore[no-redef]

# IRQ constants for MicroPython BLE
_IRQ_CENTRAL_CONNECT = 1
_IRQ_CENTRAL_DISCONNECT = 2
_IRQ_GATTS_WRITE = 3

# Service and characteristic 128-bit UUIDs
SERVICE_UUID_STR = "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
CHAR_CONFIG_UUID_STR = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"
CHAR_STATUS_UUID_STR = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
CHAR_COMMAND_UUID_STR = "6e400004-b5a3-f393-e0a9-e50e24dcca9e"


def mask_token(token: str) -> str:
    """Mask sensitive authentication token for secure BLE readout."""
    if not token:
        return ""
    if len(token) <= 6:
        return "******"
    return f"{token[:2]}****{token[-2:]}"


def build_advertising_payload(
    name: str | None = None,
    service_uuid: object | None = None,
    appearance: int = 0,
    include_flags: bool = True,
) -> bytearray:
    """Build standard BLE GAP advertising payload bytearray.

    In BLE legacy advertising, advertising packets and scan response packets
    are strictly capped at 31 bytes each.
    """
    payload = bytearray()

    def _append(ad_type: int, data: bytes | bytearray) -> None:
        payload.append(len(data) + 1)
        payload.append(ad_type)
        payload.extend(data)

    if include_flags:
        # Flags: 0x06 = General Discoverable Mode + BR/EDR Not Supported
        _append(0x01, b"\x06")

    if appearance:
        _append(0x19, bytes([appearance & 0xFF, (appearance >> 8) & 0xFF]))

    if service_uuid is not None:
        raw_uuid = bytes(service_uuid)  # type: ignore[arg-type]
        if len(raw_uuid) == 2:
            _append(0x03, raw_uuid)
        elif len(raw_uuid) == 16:
            _append(0x07, raw_uuid)

    if name:
        _append(0x09, name.encode("utf-8"))

    return payload


class BLEConfigServer:
    """MicroPython BLE GATT peripheral server for wireless gateway provisioning."""

    def __init__(
        self,
        ble: object | None = None,
        config: dict | None = None,
        timeout_sec: int = 300,
        on_command: object | None = None,
        on_config_received: object | None = None,
        on_timeout: object | None = None,
    ) -> None:
        self.ble = ble
        self.config = config if config is not None else {}
        self.timeout_sec = timeout_sec
        self.on_command = on_command
        self.on_config_received = on_config_received
        self.on_timeout = on_timeout

        self.is_running = False
        self.conn_handle: int | None = None
        self.last_activity_time = 0
        self.device_name = "Snippen-SMS"

        self.handle_config: int | None = None
        self.handle_status: int | None = None
        self.handle_command: int | None = None
        self._services_registered = False

    def _get_ble(self) -> object | None:
        if self.ble is not None:
            return self.ble
        if bluetooth is not None and hasattr(bluetooth, "BLE"):
            self.ble = bluetooth.BLE()
        return self.ble

    def _register_services(self) -> bool:
        ble = self._get_ble()
        if ble is None:
            return False

        if self._services_registered:
            return True

        service_uuid = bluetooth.UUID(SERVICE_UUID_STR)
        char_config = (
            bluetooth.UUID(CHAR_CONFIG_UUID_STR),
            bluetooth.FLAG_READ | bluetooth.FLAG_WRITE,
        )
        char_status = (
            bluetooth.UUID(CHAR_STATUS_UUID_STR),
            bluetooth.FLAG_READ | bluetooth.FLAG_NOTIFY,
        )
        char_command = (
            bluetooth.UUID(CHAR_COMMAND_UUID_STR),
            bluetooth.FLAG_WRITE | bluetooth.FLAG_NOTIFY,
        )

        service = (service_uuid, (char_config, char_status, char_command))
        ((self.handle_config, self.handle_status, self.handle_command),) = (
            ble.gatts_register_services((service,))
        )
        # Increase characteristic buffer sizes from default 20 bytes to 1024 bytes
        # to prevent payload truncation on incoming writes and outgoing notifications.
        for h in (self.handle_config, self.handle_status, self.handle_command):
            if hasattr(ble, "gatts_set_buffer"):
                try:
                    ble.gatts_set_buffer(h, 1024)
                except Exception:  # noqa: BLE001, S110
                    pass
        self._services_registered = True
        return True

    def _start_advertising(self) -> None:
        """Start or resume BLE GAP advertising with split payloads to respect 31-byte limit."""
        ble = self._get_ble()
        if ble is None:
            return
        service_uuid = bluetooth.UUID(SERVICE_UUID_STR)
        adv_payload = build_advertising_payload(name=self.device_name, include_flags=True)
        resp_payload = build_advertising_payload(service_uuid=service_uuid, include_flags=False)
        ble.gap_advertise(250000, adv_data=adv_payload, resp_data=resp_payload, connectable=True)

    def start(self) -> bool:
        """Activate BLE, register services, and begin advertising."""
        ble = self._get_ble()
        if ble is None:
            print("[ble] Error: MicroPython bluetooth.BLE is unavailable.")
            return False

        if self.is_running:
            return True

        print("[ble] Starting BLE GATT provisioning server...")
        try:
            if hasattr(ble, "active") and not ble.active():
                ble.active(True)
        except Exception:  # noqa: BLE001, S110
            pass

        self._register_services()

        # Increase MTU capacity if supported by BLE stack
        try:
            ble.config(mtu=512)
        except Exception:  # noqa: BLE001, S110
            pass

        # Derive unique device name from MAC address if available
        try:
            mac = ble.config("mac")
            if isinstance(mac, tuple) and len(mac) >= 2 and isinstance(mac[1], (bytes, bytearray)):
                mac_bytes = mac[1]
                suffix = f"{mac_bytes[-2]:02X}{mac_bytes[-1]:02X}"
                self.device_name = f"Snippen-SMS-{suffix}"
        except Exception:  # noqa: BLE001
            self.device_name = "Snippen-SMS"

        try:
            ble.config(gap_name=self.device_name)
        except Exception:  # noqa: BLE001, S110
            pass

        try:
            ble.irq(self._irq_handler)
        except Exception:  # noqa: BLE001, S110
            pass

        # Set initial characteristic values
        self.update_config_characteristic(self.config)
        self.notify_status({"status": "ready", "device": self.device_name})

        # Begin advertising with split payloads
        self._start_advertising()

        self.is_running = True
        self.last_activity_time = time.time()
        print(f"[ble] Advertising as '{self.device_name}' on UUID {SERVICE_UUID_STR}")
        return True

    def stop(self, deactivate: bool = False) -> None:
        """Stop advertising and disconnect centrals without resetting BLE stack (Issue #87)."""
        ble = self._get_ble()
        if ble is None or not self.is_running:
            return

        print("[ble] Stopping BLE provisioning server...")
        try:
            ble.gap_advertise(None)
        except Exception:  # noqa: BLE001, S110
            pass

        if self.conn_handle is not None and hasattr(ble, "gap_disconnect"):
            try:
                ble.gap_disconnect(self.conn_handle)
            except Exception:  # noqa: BLE001, S110
                pass

        self.is_running = False
        self.conn_handle = None

        if deactivate:
            try:
                ble.active(False)
                self._services_registered = False
            except Exception:  # noqa: BLE001, S110
                pass
        print("[ble] BLE server stopped.")

    def _irq_handler(self, event: int, data: tuple) -> None:
        """Handle MicroPython BLE IRQ callback events."""
        self.last_activity_time = time.time()

        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _addr_type, _addr = data[0], data[1], data[2]
            self.conn_handle = conn_handle
            print(f"[ble] Central connected (handle: {conn_handle})")
            self.notify_status({"status": "connected", "conn_handle": conn_handle})

        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle = data[0]
            print(f"[ble] Central disconnected (handle: {conn_handle})")
            if self.conn_handle == conn_handle:
                self.conn_handle = None

            # Resume advertising if still running
            if self.is_running and self.ble is not None:
                self._start_advertising()

        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data[0], data[1]
            self._handle_write(conn_handle, value_handle)

    def _handle_write(self, conn_handle: int, value_handle: int) -> None:
        ble = self._get_ble()
        if ble is None:
            return

        raw_bytes = ble.gatts_read(value_handle)
        try:
            text = raw_bytes.decode("utf-8").strip()
        except Exception:  # noqa: BLE001
            text = ""

        if value_handle == self.handle_config:
            self._process_config_write(text)
        elif value_handle == self.handle_command:
            self._process_command_write(conn_handle, text)

    def _process_config_write(self, text: str) -> None:
        try:
            payload = json.loads(text)
        except Exception as exc:  # noqa: BLE001
            print(f"[ble] Error parsing JSON config write: {exc}")
            return

        print(f"[ble] Received configuration write: {list(payload.keys())}")
        if callable(self.on_config_received):
            self.on_config_received(payload)

        # Update local config reference and characteristic
        self.config.update(payload)
        self.update_config_characteristic(self.config)

    def _process_command_write(self, conn_handle: int, text: str) -> None:
        cmd_name = text
        cmd_payload = {}
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "cmd" in parsed:
                cmd_name = parsed["cmd"]
                cmd_payload = parsed
        except Exception:  # noqa: BLE001, S110
            pass

        print(f"[ble] Received command '{cmd_name}'")
        response = None
        if callable(self.on_command):
            try:
                response = self.on_command(cmd_name, cmd_payload)
            except Exception as exc:  # noqa: BLE001
                response = {"cmd": cmd_name, "status": "error", "message": str(exc)}

        if response is not None:
            self.notify_command_response(response)

    def update_config_characteristic(self, cfg: dict) -> None:
        """Update read value of config characteristic with sensitive keys masked."""
        ble = self._get_ble()
        if ble is None or self.handle_config is None:
            return

        safe_cfg = {
            "wifi_ssid": cfg.get("wifi_ssid", ""),
            "snippen_api_base_url": cfg.get("snippen_api_base_url", ""),
            "snippen_api_token": mask_token(cfg.get("snippen_api_token", "")),
            "outbox_poll_interval_sec": cfg.get("outbox_poll_interval_sec", 5),
            "inbox_check_interval_sec": cfg.get("inbox_check_interval_sec", 5),
        }
        json_data = json.dumps(safe_cfg)
        ble.gatts_write(self.handle_config, json_data)

    def notify_status(self, status: dict) -> None:
        """Write and notify device status to connected central."""
        ble = self._get_ble()
        if ble is None or self.handle_status is None:
            return

        json_data = json.dumps(status)
        ble.gatts_write(self.handle_status, json_data)
        if self.conn_handle is not None:
            try:
                ble.gatts_notify(self.conn_handle, self.handle_status, json_data)
            except Exception as exc:  # noqa: BLE001
                print(f"[ble] Failed to notify status: {exc}")

    def notify_command_response(self, response: dict | str) -> None:
        """Send command result notification back to connected central."""
        ble = self._get_ble()
        if ble is None or self.handle_command is None:
            return

        payload_str = json.dumps(response) if isinstance(response, dict) else str(response)
        ble.gatts_write(self.handle_command, payload_str)
        if self.conn_handle is not None:
            try:
                ble.gatts_notify(self.conn_handle, self.handle_command, payload_str)
            except Exception as exc:  # noqa: BLE001
                print(f"[ble] Failed to notify command response: {exc}")

    def poll(self, now: float | None = None) -> None:
        """Poll server lifecycle and check inactivity timeout."""
        if not self.is_running:
            return

        if now is None:
            now = time.time()

        # Inactivity timeout applies only when no central is actively connected
        if self.conn_handle is None and (now - self.last_activity_time) >= self.timeout_sec:
            print(f"[ble] Provisioning inactivity timeout ({self.timeout_sec}s) reached.")
            if callable(self.on_timeout):
                self.on_timeout()
            self.stop()
