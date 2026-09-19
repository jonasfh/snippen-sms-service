"""Unit tests for firmware/modem.py SimCom A7670E modem driver."""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from tests.mocks.micropython_mocks import MicroPythonEnvironment, MockUART


@pytest.fixture
def mpy_env() -> Generator[MicroPythonEnvironment]:
    env = MicroPythonEnvironment()
    env.install()
    sys.modules.pop("modem", None)
    yield env
    env.uninstall()
    sys.modules.pop("modem", None)


def test_normalize_phone_number() -> None:
    from modem import normalize_phone_number

    assert normalize_phone_number("+4799999999") == "+4799999999"
    assert normalize_phone_number("99999999") == "+4799999999"
    assert normalize_phone_number(" 99 99 99 99 ") == "+4799999999"
    assert normalize_phone_number("004799999999") == "+4799999999"
    assert normalize_phone_number("+47-99-99-99-99") == "+4799999999"
    assert normalize_phone_number("+46701234567") == "+46701234567"

    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_phone_number("   ")


def test_parse_cmgl_header() -> None:
    from modem import parse_cmgl_header

    # Standard SimCom header with empty alpha
    h1 = '+CMGL: 1,"REC UNREAD","+4799999999",,"26/09/19,17:05:00+08"'
    res1 = parse_cmgl_header(h1)
    assert res1 is not None
    assert res1["index"] == 1
    assert res1["status"] == "REC UNREAD"
    assert res1["sender"] == "+4799999999"
    assert res1["timestamp"] == "26/09/19,17:05:00+08"

    # Header with alpha contact name
    h2 = '+CMGL: 2,"REC READ","+4712345678","Jon","26/09/19,18:00:00+08"'
    res2 = parse_cmgl_header(h2)
    assert res2 is not None
    assert res2["index"] == 2
    assert res2["status"] == "REC READ"
    assert res2["sender"] == "+4712345678"
    assert res2["timestamp"] == "26/09/19,18:00:00+08"

    # Invalid header
    assert parse_cmgl_header("NOT A CMGL HEADER") is None
    assert parse_cmgl_header("+CMGL: INVALID") is None


def test_modem_init_success(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        "AT": b"OK\r\n",
        "ATE0": b"OK\r\n",
        "AT+CMGF=1": b"OK\r\n",
        'AT+CSCS="GSM"': b"OK\r\n",
        "AT+CPIN?": b"+CPIN: READY\r\n\r\nOK\r\n",
    }

    driver = ModemDriver(uart=uart)
    assert driver.init_modem() is True


def test_modem_init_with_pin_unlock(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    pin_unlocked = False

    def responder(data: bytes) -> bytes | None:
        nonlocal pin_unlocked
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd == "AT" or cmd == "ATE0" or cmd == "AT+CMGF=1" or cmd == 'AT+CSCS="GSM"':
            return b"OK\r\n"
        if cmd == "AT+CPIN?":
            if pin_unlocked:
                return b"+CPIN: READY\r\n\r\nOK\r\n"
            return b"+CPIN: SIM PIN\r\n\r\nOK\r\n"
        if cmd == 'AT+CPIN="0129"':
            pin_unlocked = True
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart, config={"modem_sim_pin": "0129"})
    assert driver.init_modem() is True
    assert pin_unlocked is True


def test_modem_init_failure_unresponsive(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    # No responses fed -> times out
    driver = ModemDriver(uart=uart)
    assert driver.init_modem() is False


def test_send_sms_success(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)

    def responder(data: bytes) -> bytes | None:
        if b"AT+CMGS=" in data:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            return b"\r\n+CMGS: 42\r\n\r\nOK\r\n"
        return None

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    success, ref = driver.send_sms("+4799999999", "Hei fra Snippen!")

    assert success is True
    assert ref == "42"


def test_send_sms_prompt_timeout(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    # UART does not emit '>' prompt
    uart.auto_responses = {"AT+CMGS": b"ERROR\r\n"}

    driver = ModemDriver(uart=uart)
    success, err = driver.send_sms("+4799999999", "Test")

    assert success is False
    assert "rejected" in err.lower() or "timeout" in err.lower()


def test_send_sms_cms_error(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)

    def responder(data: bytes) -> bytes | None:
        if b"AT+CMGS=" in data:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            return b"\r\n+CMS ERROR: 302\r\n"
        return None

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    success, err = driver.send_sms("99999999", "Melding")

    assert success is False
    assert "+CMS ERROR" in err


def test_send_sms_invalid_number(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    driver = ModemDriver(uart=uart)
    success, err = driver.send_sms("   ", "Test")
    assert success is False
    assert "Invalid phone number" in err


def test_read_inbound_sms_with_auto_delete(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    deleted_indices: list[int] = []

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd == "AT+CMGF=1" or cmd == 'AT+CSCS="GSM"':
            return b"OK\r\n"
        if cmd == 'AT+CMGL="ALL"':
            return (
                b'+CMGL: 1,"REC UNREAD","+4799999999",,"26/09/19,17:05:00+08"\r\n'
                b"Hei Snippen, kan jeg leie grendehuset?\r\n"
                b'+CMGL: 2,"REC READ","+4711111111",,"26/09/19,17:10:00+08"\r\n'
                b"Linje 1\r\nLinje 2 i melding\r\n"
                b"OK\r\n"
            )
        if cmd.startswith("AT+CMGD="):
            idx = int(cmd.split("=")[1].strip())
            deleted_indices.append(idx)
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    messages = driver.read_inbound_sms(delete_after_read=True)

    assert len(messages) == 2
    assert messages[0]["index"] == 1
    assert messages[0]["sender"] == "+4799999999"
    assert messages[0]["body"] == "Hei Snippen, kan jeg leie grendehuset?"
    assert messages[0]["status"] == "REC UNREAD"

    assert messages[1]["index"] == 2
    assert messages[1]["sender"] == "+4711111111"
    assert messages[1]["body"] == "Linje 1\nLinje 2 i melding"

    # Verify both messages were immediately deleted from SIM storage
    assert deleted_indices == [1, 2]


def test_read_inbound_sms_no_delete(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    deleted_indices: list[int] = []

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd == 'AT+CMGL="ALL"':
            return (
                b'+CMGL: 5,"REC UNREAD","+4799999999",,"26/09/19,17:05:00+08"\r\n'
                b"Enkel melding\r\n"
                b"OK\r\n"
            )
        if cmd.startswith("AT+CMGD="):
            idx = int(cmd.split("=")[1].strip())
            deleted_indices.append(idx)
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    messages = driver.read_inbound_sms(delete_after_read=False)

    assert len(messages) == 1
    assert messages[0]["index"] == 5
    assert deleted_indices == []


def test_delete_sms(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        "AT+CMGD=1": b"OK\r\n",
        "AT+CMGD=2": b"ERROR\r\n",
    }

    driver = ModemDriver(uart=uart)
    assert driver.delete_sms(1) is True
    assert driver.delete_sms(2) is False


def test_get_signal_quality(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        "AT+CSQ": b"+CSQ: 22,0\r\n\r\nOK\r\n",
    }

    driver = ModemDriver(uart=uart)
    sig = driver.get_signal_quality()
    assert sig is not None
    assert sig["rssi"] == 22
    assert sig["ber"] == 0
    assert sig["dbm"] == -69  # -113 + 2 * 22 = -69 dBm


def test_get_signal_quality_failure(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        "AT+CSQ": b"ERROR\r\n",
    }

    driver = ModemDriver(uart=uart)
    assert driver.get_signal_quality() is None


def test_get_network_registration(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        "AT+CREG?": b"+CREG: 0,1\r\n\r\nOK\r\n",
    }

    driver = ModemDriver(uart=uart)
    reg = driver.get_network_registration()
    assert reg is not None
    assert reg["stat"] == 1
    assert reg["registered"] is True
    assert reg["roaming"] is False
    assert "home" in reg["description"].lower()


def test_get_network_registration_roaming(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        "AT+CREG?": b"+CREG: 0,5\r\n\r\nOK\r\n",
    }

    driver = ModemDriver(uart=uart)
    reg = driver.get_network_registration()
    assert reg is not None
    assert reg["stat"] == 5
    assert reg["registered"] is True
    assert reg["roaming"] is True


def test_get_modem_info(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        "ATI": b"SIMCOM_A7670E\r\nModel: A7670E-FASE\r\nOK\r\n",
        "AT+CCID": b"+CCID: 89470000000000000000\r\nOK\r\n",
    }

    driver = ModemDriver(uart=uart)
    info = driver.get_modem_info()
    assert "A7670E" in info.get("model", "")
    assert info.get("iccid") == "89470000000000000000"


def test_run_modem_diagnostic_script(
    mpy_env: MicroPythonEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_uart = MockUART(1)
    mock_uart.auto_responses = {
        "AT": b"OK\r\n",
        "ATE0": b"OK\r\n",
        "AT+CMGF=1": b"OK\r\n",
        'AT+CSCS="GSM"': b"OK\r\n",
        "AT+CPIN?": b"+CPIN: READY\r\nOK\r\n",
        "ATI": b"SIMCOM_A7670E\r\nOK\r\n",
        "AT+CCID": b"+CCID: 89470000000000000000\r\nOK\r\n",
        "AT+CSQ": b"+CSQ: 21,0\r\nOK\r\n",
        "AT+CREG?": b"+CREG: 0,1\r\nOK\r\n",
        'AT+CMGL="ALL"': b"OK\r\n",
    }

    import boot

    monkeypatch.setattr(boot, "modem_uart", mock_uart)
    sys.modules.pop("test_modem", None)
    import test_modem

    monkeypatch.setattr(test_modem.boot, "modem_uart", mock_uart)

    assert test_modem.run_modem_test() is True


def test_send_sms_with_emojis_ucs2(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    commands_received: list[str] = []

    def responder(data: bytes) -> bytes | None:
        cmd_str = data.decode("utf-8", errors="ignore")
        commands_received.append(cmd_str)

        if 'AT+CSCS="UCS2"' in cmd_str:
            return b"OK\r\n"
        if 'AT+CSCS="GSM"' in cmd_str:
            return b"OK\r\n"
        if "AT+CMGS=" in cmd_str:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            return b"\r\n+CMGS: 99\r\n\r\nOK\r\n"
        return None

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    success, ref = driver.send_sms("+4799999999", "Hei 🤖 fra Snippen!")

    assert success is True
    assert ref == "99"

    # Verify that UCS-2 mode was selected, number was hex-encoded, body was hex-encoded, and GSM mode was restored
    all_traffic = "".join(commands_received)
    assert 'AT+CSCS="UCS2"' in all_traffic
    # Phone number +4799999999 in UCS-2 hex
    assert "002B00340037" in all_traffic
    # Emoji 🤖 (D83EDD16) in UCS-2 hex
    assert "D83EDD16" in all_traffic
    # Mode restored to GSM
    assert 'AT+CSCS="GSM"' in all_traffic


def test_read_inbound_sms_ucs2_decoding(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver
    from sms_encoding import encode_ucs2_hex

    uart = MockUART(1)

    # Inbound message with Norwegian letters and emoji encoded in UCS-2 hex
    sender_raw = "+4798765432"
    body_plain = "Hei! Koden er mottatt 🤖. Hilsen fra Snippen, vi ses i kveld! ÆØÅ æøå"
    body_hex = encode_ucs2_hex(body_plain)

    cmgl_response = (
        f'+CMGL: 1,"REC UNREAD","{sender_raw}",,"26/09/19,19:30:00+08"\r\n{body_hex}\r\nOK\r\n'
    )

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd == 'AT+CMGL="ALL"':
            return cmgl_response.encode("utf-8")
        if cmd.startswith("AT+CMGD="):
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    messages = driver.read_inbound_sms(delete_after_read=False)

    assert len(messages) == 1
    assert messages[0]["index"] == 1
    assert messages[0]["sender"] == sender_raw
    assert messages[0]["body"] == body_plain
