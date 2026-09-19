"""MicroPython modem driver module for SimCom A7670E on Lilygo T-Call (UART1).

Handles AT command communication, outbound/inbound SMS dispatch, SIM memory
management, signal quality, and cellular network registration.
"""

try:
    import utime as time
except ImportError:
    import time


def _ticks_ms() -> int:
    """Return current millisecond tick counter."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def _ticks_diff(t1: int, t2: int) -> int:
    """Return difference between two millisecond tick values (t1 - t2)."""
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(t1, t2)
    return t1 - t2


def normalize_phone_number(number: str) -> str:
    """Normalize a phone number string to E.164 international format."""
    s = str(number).strip()
    for ch in (" ", "-", ".", "(", ")", "/"):
        s = s.replace(ch, "")

    if s.startswith("00"):
        s = "+" + s[2:]

    # Norwegian 8-digit mobile number shorthand
    if len(s) == 8 and s.isdigit():
        s = "+47" + s

    if not s:
        raise ValueError("Phone number cannot be empty")
    return s


def parse_cmgl_header(line: str) -> dict | None:
    """Parse a +CMGL response header line in SMS text mode.

    Format: +CMGL: <index>,"<stat>","<oa>",[<alpha>],"<scts>"
    Example: +CMGL: 1,"REC UNREAD","+4799999999",,"26/09/19,17:05:00+08"
    """
    if not line.startswith("+CMGL:"):
        return None

    header = line[6:].strip()
    first_comma = header.find(",")
    if first_comma == -1:
        return None

    try:
        index = int(header[:first_comma].strip())
    except ValueError:
        return None

    tokens: list[str] = []
    in_quote = False
    cur: list[str] = []

    for char in header[first_comma:]:
        if char == '"':
            if in_quote:
                tokens.append("".join(cur))
                cur.clear()
                in_quote = False
            else:
                in_quote = True
        elif in_quote:
            cur.append(char)

    if len(tokens) < 2:
        return None

    status = tokens[0]
    sender = tokens[1]
    timestamp = tokens[-1] if len(tokens) >= 3 else ""

    return {
        "index": index,
        "status": status,
        "sender": sender,
        "timestamp": timestamp,
    }


class ModemDriver:
    """Driver for SimCom A7670E 4G/LTE cellular modem interfacing over UART."""

    def __init__(self, uart: object | None = None, config: dict | None = None) -> None:
        self.config = config if config is not None else {}
        self.uart = uart
        if self.uart is None:
            try:
                import boot

                self.uart = boot.modem_uart
                if self.uart is None:
                    self.uart = boot.init_uart(self.config)
            except Exception as exc:  # noqa: BLE001
                print(f"[modem] Warning: Unable to acquire UART from boot module: {exc}")

    def flush_input(self) -> None:
        """Clear any buffered unread incoming bytes from the UART interface."""
        if self.uart is None:
            return
        try:
            while True:
                available = getattr(self.uart, "any", lambda: 0)()
                if available:
                    self.uart.read(available)
                else:
                    chunk = self.uart.read()
                    if not chunk:
                        break
        except Exception:  # noqa: BLE001, S110
            pass

    def write_raw(self, data: bytes | str) -> int:
        """Write raw bytes or string to modem UART."""
        if self.uart is None:
            return 0
        if isinstance(data, str):
            data = data.encode("utf-8")
        return self.uart.write(data)

    def _read_response(
        self,
        timeout_ms: int = 2000,
        stop_tokens: tuple[str, ...] = ("OK", "ERROR", "+CME ERROR", "+CMS ERROR"),
    ) -> tuple[bool, list[str]]:
        """Read lines from UART until a stop token is encountered or timeout expires."""
        if self.uart is None:
            return False, []

        lines: list[str] = []
        start = _ticks_ms()
        success = False

        while _ticks_diff(_ticks_ms(), start) < timeout_ms:
            raw_line = self.uart.readline()
            if raw_line:
                decoded = raw_line.decode("utf-8", "ignore").strip()
                if decoded:
                    lines.append(decoded)
                    for token in stop_tokens:
                        if decoded == token or decoded.startswith(token):
                            if decoded == "OK":
                                success = True
                            return success, lines
            else:
                time.sleep_ms(20)

        # Timeout reached
        success = any(line == "OK" for line in lines)
        return success, lines

    def send_cmd(
        self,
        cmd: str,
        timeout_ms: int = 2000,
        stop_tokens: tuple[str, ...] = ("OK", "ERROR", "+CME ERROR", "+CMS ERROR"),
    ) -> tuple[bool, list[str]]:
        """Send an AT command and wait for response."""
        self.flush_input()
        self.write_raw(cmd + "\r\n")
        return self._read_response(timeout_ms=timeout_ms, stop_tokens=stop_tokens)

    def check_at(self, retries: int = 3, delay_ms: int = 500) -> bool:
        """Ping modem with AT command until responsive."""
        for _ in range(retries):
            success, _ = self.send_cmd("AT", timeout_ms=1000)
            if success:
                return True
            time.sleep_ms(delay_ms)
        return False

    def init_modem(self) -> bool:
        """Initialize modem into standard operational state (echo off, text mode, GSM charset)."""
        if not self.check_at(retries=4, delay_ms=500):
            print("[modem] Error: Modem not responding to AT commands.")
            return False

        # Disable command echo (ATE0)
        self.send_cmd("ATE0", timeout_ms=1000)

        # Set SMS text mode (AT+CMGF=1)
        ok_cmgf, _ = self.send_cmd("AT+CMGF=1", timeout_ms=1000)
        if not ok_cmgf:
            print("[modem] Warning: Failed to set SMS text mode (AT+CMGF=1).")

        # Set character set to GSM (AT+CSCS="GSM")
        ok_cscs, _ = self.send_cmd('AT+CSCS="GSM"', timeout_ms=1000)
        if not ok_cscs:
            print('[modem] Warning: Failed to set character set (AT+CSCS="GSM").')

        # Check SIM PIN state
        pin_code = self.config.get("modem_sim_pin", "")
        _, cpin_lines = self.send_cmd("AT+CPIN?", timeout_ms=2000)
        cpin_resp = " ".join(cpin_lines)
        if "SIM PIN" in cpin_resp and pin_code:
            print("[modem] SIM is PIN-locked. Authenticating with configured PIN...")
            ok_pin, _ = self.send_cmd(f'AT+CPIN="{pin_code}"', timeout_ms=3000)
            if not ok_pin:
                print("[modem] Error: Failed to unlock SIM with PIN.")
                return False
            time.sleep_ms(1000)

        return True

    def send_sms(
        self, phone_number: str, text: str, timeout_ms: int = 15000
    ) -> tuple[bool, str | None]:
        """Send outbound SMS over cellular modem.

        Returns (True, message_reference) on success, or (False, error_reason) on failure.
        """
        if self.uart is None:
            return False, "UART not initialized"

        try:
            target_number = normalize_phone_number(phone_number)
        except ValueError as err:
            return False, f"Invalid phone number: {err}"

        self.flush_input()

        # Initiate SMS command
        self.write_raw(f'AT+CMGS="{target_number}"\r\n')

        # Wait for '>' prompt
        prompt_found = False
        start = _ticks_ms()
        while _ticks_diff(_ticks_ms(), start) < 3000:
            chunk = self.uart.read(getattr(self.uart, "any", lambda: 1)() or 1)
            if chunk:
                if b">" in chunk:
                    prompt_found = True
                    break
                if b"ERROR" in chunk:
                    return False, "Modem rejected AT+CMGS command"
            time.sleep_ms(50)

        if not prompt_found:
            return False, "Timeout waiting for '>' prompt"

        # Transmit message body terminated by Ctrl+Z (\x1A)
        self.write_raw(text + "\x1a")

        # Wait for delivery confirmation (+CMGS: <id> and OK)
        success, lines = self._read_response(
            timeout_ms=timeout_ms,
            stop_tokens=("OK", "ERROR", "+CMS ERROR", "+CME ERROR"),
        )

        msg_ref = None
        for line in lines:
            if "+CMGS:" in line:
                parts = line.split(":", 1)
                if len(parts) > 1:
                    msg_ref = parts[1].strip()
                break

        if success or msg_ref is not None:
            return True, msg_ref if msg_ref else "OK"

        error_line = next((line for line in lines if "ERROR" in line), "Unknown send failure")
        return False, error_line

    def read_inbound_sms(self, delete_after_read: bool = True) -> list[dict]:
        """Read unread/received SMS messages from SIM card storage.

        When delete_after_read is True, messages are deleted immediately with
        AT+CMGD to prevent SIM memory overflow.
        """
        if self.uart is None:
            return []

        # Ensure text mode and GSM charset
        self.send_cmd("AT+CMGF=1", timeout_ms=1000)
        self.send_cmd('AT+CSCS="GSM"', timeout_ms=1000)

        # Read all stored messages
        _, lines = self.send_cmd('AT+CMGL="ALL"', timeout_ms=4000)

        messages: list[dict] = []
        current_msg: dict | None = None
        body_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("+CMGL:"):
                if current_msg is not None:
                    current_msg["body"] = "\n".join(body_lines).strip()
                    messages.append(current_msg)
                    body_lines = []

                current_msg = parse_cmgl_header(stripped)
            elif current_msg is not None:
                if stripped in ("OK", "ERROR") or stripped.startswith(("+CMS ERROR", "+CME ERROR")):
                    continue
                body_lines.append(line.rstrip("\r\n"))

        if current_msg is not None:
            current_msg["body"] = "\n".join(body_lines).strip()
            messages.append(current_msg)

        # Delete read messages from SIM memory to avoid overflow
        if delete_after_read:
            for msg in messages:
                self.delete_sms(msg["index"])

        return messages

    def delete_sms(self, index: int) -> bool:
        """Delete an SMS message from SIM memory at specified storage index."""
        success, _ = self.send_cmd(f"AT+CMGD={index}", timeout_ms=2000)
        return success

    def get_signal_quality(self) -> dict | None:
        """Query received signal quality (AT+CSQ).

        Returns dict with rssi, ber, and estimated dbm, or None on failure.
        """
        success, lines = self.send_cmd("AT+CSQ", timeout_ms=2000)
        if not success:
            return None

        for line in lines:
            if line.startswith("+CSQ:"):
                parts = line[5:].strip().split(",")
                if len(parts) >= 2:
                    try:
                        rssi = int(parts[0].strip())
                        ber = int(parts[1].strip())
                        dbm = (-113 + 2 * rssi) if (0 <= rssi <= 31) else None
                        return {"rssi": rssi, "ber": ber, "dbm": dbm}
                    except ValueError:
                        return None
        return None

    def get_network_registration(self) -> dict | None:
        """Query cellular network registration status (AT+CREG?)."""
        success, lines = self.send_cmd("AT+CREG?", timeout_ms=2000)
        if not success:
            return None

        stat_descriptions = {
            0: "Not registered, searching inactive",
            1: "Registered, home network",
            2: "Not registered, searching",
            3: "Registration denied",
            4: "Unknown",
            5: "Registered, roaming",
        }

        for line in lines:
            if line.startswith("+CREG:"):
                parts = line[6:].strip().split(",")
                if len(parts) >= 2:
                    try:
                        stat = int(parts[1].strip())
                        return {
                            "stat": stat,
                            "registered": stat in (1, 5),
                            "roaming": stat == 5,
                            "description": stat_descriptions.get(stat, "Unknown"),
                        }
                    except ValueError:
                        return None
        return None

    def get_modem_info(self) -> dict:
        """Query basic hardware identity (ATI) and SIM card identity (AT+CCID)."""
        info: dict[str, str] = {}
        _, ati_lines = self.send_cmd("ATI", timeout_ms=2000)
        content_lines = [l for l in ati_lines if l != "OK" and not l.startswith("ERROR")]
        if content_lines:
            info["model"] = " ".join(content_lines)

        _, ccid_lines = self.send_cmd("AT+CCID", timeout_ms=2000)
        for line in ccid_lines:
            if line.startswith("+CCID:") or (line.isdigit() and len(line) >= 15):
                info["iccid"] = line.replace("+CCID:", "").strip()
                break
        return info
