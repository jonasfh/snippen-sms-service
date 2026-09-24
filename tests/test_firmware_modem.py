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


def test_send_sms_multipart_gsm7_success(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    cmgsex_commands: list[str] = []
    payloads: list[str] = []
    msg_counter = 50

    def responder(data: bytes) -> bytes | None:
        nonlocal msg_counter
        data_str = data.decode("utf-8", errors="ignore")
        if "AT+CMGSEX=" in data_str:
            cmgsex_commands.append(data_str)
            return b"\r\n> "
        if "AT+CMGS=" in data_str:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            payloads.append(data_str)
            resp = f"\r\n+CMGSEX: {msg_counter}\r\n\r\nOK\r\n".encode()
            msg_counter += 1
            return resp
        return None

    uart.responder = responder
    driver = ModemDriver(uart=uart, config={"sms_chunk_delay_ms": 10})

    # Message exceeding 160 characters (pure GSM-7 ASCII)
    long_msg = (
        "Hei! Dette er en lang bookingbekreftelse fra Snippen grendehus for det kommende arrangementet. "
        "Doerkoden din er 9876 og gjelder fra fredag kl 15:00 til soendag kl 18:00. "
        "Ta vare paa koden! Velkommen skal dere vaere!"
    )
    assert len(long_msg) > 160

    success, ref = driver.send_sms("+4799999999", long_msg)

    assert success is True
    assert ref == "50,51"
    assert len(cmgsex_commands) == 2
    assert cmgsex_commands[0] == 'AT+CMGSEX="+4799999999",1,1,2\r\n'
    assert cmgsex_commands[1] == 'AT+CMGSEX="+4799999999",1,2,2\r\n'
    assert len(payloads) == 2
    # Seamless concatenation: no (1/2) prefix in payload
    assert "(1/2)" not in payloads[0]
    assert "(2/2)" not in payloads[1]
    # Reconstructed text without trailing ctrl-z matches original
    reconstructed = "".join(p[:-1] for p in payloads)
    assert reconstructed == long_msg


def test_send_sms_multipart_ucs2_with_norwegian(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    cmgsex_calls = 0
    csmp_set = False

    def responder(data: bytes) -> bytes | None:
        nonlocal cmgsex_calls, csmp_set
        data_str = data.decode("utf-8", errors="ignore")
        if "AT+CSMP=17,167,0,8" in data_str:
            csmp_set = True
            return b"OK\r\n"
        if "AT+CSMP=17,167,0,0" in data_str:
            return b"OK\r\n"
        if 'AT+CSCS="UCS2"' in data_str or 'AT+CSCS="GSM"' in data_str:
            return b"OK\r\n"
        if "AT+CMGSEX=" in data_str or "AT+CMGS=" in data_str:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            cmgsex_calls += 1
            return f"\r\n+CMGSEX: {70 + cmgsex_calls}\r\n\r\nOK\r\n".encode()
        return None

    uart.responder = responder
    driver = ModemDriver(uart=uart, config={"sms_chunk_delay_ms": 10})

    # Message with Norwegian characters exceeding 70 characters
    norwegian_msg = (
        "Hei! Din booking på Snippen er bekreftet. "
        "Dørkoden din er 4589 og er gyldig fra kl. 12:00. "
        "Ved spørsmål, ta kontakt med styret. Velkommen skal dere være!"
    )

    success, ref = driver.send_sms("+4799999999", norwegian_msg)
    assert success is True
    assert csmp_set is True
    assert cmgsex_calls > 1
    assert ref.startswith("71,72")


def test_send_sms_multipart_ucs2_with_emojis(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    cmgsex_calls = 0

    def responder(data: bytes) -> bytes | None:
        nonlocal cmgsex_calls
        data_str = data.decode("utf-8", errors="ignore")
        if "AT+CSMP=" in data_str:
            return b"OK\r\n"
        if 'AT+CSCS="UCS2"' in data_str or 'AT+CSCS="GSM"' in data_str:
            return b"OK\r\n"
        if "AT+CMGSEX=" in data_str or "AT+CMGS=" in data_str:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            cmgsex_calls += 1
            return f"\r\n+CMGSEX: {80 + cmgsex_calls}\r\n\r\nOK\r\n".encode()
        return None

    uart.responder = responder
    driver = ModemDriver(uart=uart, config={"sms_chunk_delay_ms": 10})

    # Long UCS-2 message with emojis exceeding 70 code units
    long_emoji_msg = (
        "Velkommen til Snippen! 🤖 Vi gleder oss til å ha dere på besøk. "
        "Husk at grendehuset skal være ryddet og vasket før utsjekk 🎉👍"
    )

    success, ref = driver.send_sms("+4799999999", long_emoji_msg)
    assert success is True
    assert cmgsex_calls == 2
    assert ref == "81,82"


def test_send_sms_multipart_cmgsex_fallback_to_cmgs(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    cmgs_calls = 0

    def responder(data: bytes) -> bytes | None:
        nonlocal cmgs_calls
        data_str = data.decode("utf-8", errors="ignore")
        if "AT+CMGSEX=" in data_str:
            return b"\r\nERROR\r\n"
        if "AT+CMGS=" in data_str:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            cmgs_calls += 1
            return f"\r\n+CMGS: {90 + cmgs_calls}\r\n\r\nOK\r\n".encode()
        return None

    uart.responder = responder
    driver = ModemDriver(uart=uart, config={"sms_chunk_delay_ms": 10})

    msg = "A" * 200
    success, ref = driver.send_sms("+4799999999", msg)
    assert success is True
    assert cmgs_calls == 2
    assert ref == "91,92"


def test_send_sms_multipart_failure_aborts_cleanly(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    call_count = 0

    def responder(data: bytes) -> bytes | None:
        nonlocal call_count
        if b"AT+CMGS=" in data:
            return b"\r\n> "
        if data.endswith(b"\x1a"):
            call_count += 1
            if call_count == 1:
                return b"\r\n+CMGS: 10\r\n\r\nOK\r\n"
            return b"\r\n+CMS ERROR: 500\r\n"
        return None

    uart.responder = responder
    driver = ModemDriver(uart=uart, config={"sms_chunk_delay_ms": 10})

    msg = "A" * 200
    success, err = driver.send_sms("+4799999999", msg)

    assert success is False
    assert "Chunk 2/2 failed" in err
    assert "+CMS ERROR: 500" in err


def test_read_inbound_sms_multipart_reassembly(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    deleted_indices: list[int] = []

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd == 'AT+CMGL="ALL"':
            return (
                '+CMGL: 10,"REC UNREAD","+4791234567",,"26/09/21,14:00:00+08"\r\n'
                "(1/2) Hei Snippen! Vi har et sporsmal angående "
                "\r\n"
                '+CMGL: 11,"REC UNREAD","+4791234567",,"26/09/21,14:00:05+08"\r\n'
                "(2/2) bord og stoler i lokalet.\r\n"
                "OK\r\n"
            ).encode()
        if cmd.startswith("AT+CMGD="):
            idx = int(cmd.split("=")[1].strip())
            deleted_indices.append(idx)
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    messages = driver.read_inbound_sms(delete_after_read=True)

    # Reassembled into 1 unified message
    assert len(messages) == 1
    assert messages[0]["sender"] == "+4791234567"
    assert (
        messages[0]["body"] == "Hei Snippen! Vi har et sporsmal angående bord og stoler i lokalet."
    )
    assert messages[0]["parts_count"] == 2

    # Both parts deleted from SIM memory
    assert 10 in deleted_indices
    assert 11 in deleted_indices


def test_read_inbound_sms_multipart_across_polling_cycles(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    cycle = 1
    deleted_indices: list[int] = []

    def responder(data: bytes) -> bytes | None:
        nonlocal cycle
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd == 'AT+CMGL="ALL"':
            if cycle == 1:
                return (
                    b'+CMGL: 1,"REC UNREAD","+4799990000",,"26/09/21,15:00:00+08"\r\n'
                    b"(1/2) Forste del av melding som kommer forst "
                    b"\r\nOK\r\n"
                )
            if cycle == 2:
                return (
                    b'+CMGL: 2,"REC UNREAD","+4799990000",,"26/09/21,15:00:10+08"\r\n'
                    b"(2/2)og her kommer andre del!\r\n"
                    b"OK\r\n"
                )
            return b"OK\r\n"
        if cmd.startswith("AT+CMGD="):
            idx = int(cmd.split("=")[1].strip())
            deleted_indices.append(idx)
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)

    # Cycle 1: Part 1 arrives on SIM
    msgs_cycle1 = driver.read_inbound_sms(delete_after_read=True)
    assert msgs_cycle1 == []  # Not complete yet
    assert 1 in deleted_indices  # Deleted from SIM to prevent memory leak

    # Cycle 2: Part 2 arrives on SIM
    cycle = 2
    msgs_cycle2 = driver.read_inbound_sms(delete_after_read=True)
    assert len(msgs_cycle2) == 1
    assert msgs_cycle2[0]["sender"] == "+4799990000"
    assert (
        msgs_cycle2[0]["body"] == "Forste del av melding som kommer forst og her kommer andre del!"
    )
    assert 2 in deleted_indices


def test_read_inbound_sms_multipart_timeout_release(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd == 'AT+CMGL="ALL"':
            return (
                b'+CMGL: 3,"REC UNREAD","+4799991111",,"26/09/21,16:00:00+08"\r\n'
                b"(1/3) Kun forste del av tre deler mottatt\r\n"
                b"OK\r\n"
            )
        if cmd.startswith("AT+CMGD="):
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    # 0 second timeout so partial messages expire immediately
    driver = ModemDriver(uart=uart, config={"sms_multipart_timeout_sec": 0})

    messages = driver.read_inbound_sms(delete_after_read=True)
    # Part 1 was partial and timed out, so it was released rather than lost
    assert len(messages) == 1
    assert messages[0]["sender"] == "+4799991111"
    assert messages[0]["body"] == "Kun forste del av tre deler mottatt"
    assert messages[0].get("partial") is True


def test_read_inbound_sms_pdu_multipart_reassembly(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    deleted_indices: list[int] = []

    pdu1 = (
        "06917429000100440A917409860813000062904281057480A005000346020190F63068BE5697E520"
        "B43D3D07A9CB67D0BCEC2697E5A0B21B345FA7D7EB323B7D06B1C3EE3368DE9E83E6EF3628BD5E97"
        "41E6871C046787E773501A640FBBD9E93328668381E8E5B39B056A97DD207499CD2ECB41F43C3C3D"
        "5F83C4F2FABA2C07B9DF65D0FCE1A683E6EF36880683C16030180C442F9FDD207A9A0D7A80E66B79"
        "DA5E0695DD"
    )
    pdu2 = (
        "06917429000100440A9174098608130000629042810584809705000346020240E8329B0E4A93D36F"
        "7A7ABE06B5CB6C72DA7DFE8196EF76BB2C0791CB6E10B9EC0691C32C5099CD2ECB41E2B0BC0C5ACB"
        "C37375590E2297DD2074994D079DE5617A7A0E7A9F4162765A0E62A7CFE7B29B5C06A541EC343B7F"
        "7E83DE67D0F94D3EAB1972D0BC7CFE81AC6910BD3CA797E5A034DA5E96D3CD6136DBE572B900"
    )

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd == "AT+CMGF=0":
            return b"OK\r\n"
        if cmd == "AT+CMGL=4":
            return (f"+CMGL: 1,1,,158\r\n{pdu1}\r\n+CMGL: 2,1,,151\r\n{pdu2}\r\nOK\r\n").encode()
        if cmd.startswith("AT+CMGD="):
            idx = int(cmd.split("=")[1].strip())
            deleted_indices.append(idx)
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    messages = driver.read_inbound_sms(delete_after_read=True)

    assert len(messages) == 1
    assert messages[0]["sender"] == "+4790688031"
    assert messages[0]["parts_count"] == 2
    assert "til å skrive en helt idiotisk melding" in messages[0]["body"]
    assert "godgjør seg" in messages[0]["body"]
    assert 1 in deleted_indices
    assert 2 in deleted_indices


def test_read_inbound_sms_text_mode_chunks_merged_and_at_stripped(
    mpy_env: MicroPythonEnvironment,
) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    deleted_indices: list[int] = []

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        # Simulate PDU mode being rejected, forcing text mode fallback
        if cmd == "AT+CMGF=0":
            return b"ERROR\r\n"
        if cmd == "AT+CMGF=1" or cmd == 'AT+CSCS="GSM"':
            return b"OK\r\n"
        if cmd == 'AT+CMGL="ALL"':
            # 153 chars part 1, and part 2 ending with @
            part1 = "Hva skjer hvis jeg sender en skikkelig lang sms som ikke fr plass i vanlig 160 tegn, men heller typisk bruker noe snt som 40000000 tegn til  skrive en"
            part2 = "helt idiotisk melding? Kommer den den da, eller bare krasjer den helt gratis og blir liggende i lilygo og godgjr seg? Vi tester ihvertfall....@"
            return (
                f'+CMGL: 1,"REC READ","+4790688031",,"26/09/24,18:50:47+08"\r\n'
                f"{part1}\r\n"
                f'+CMGL: 2,"REC READ","+4790688031",,"26/09/24,18:50:48+08"\r\n'
                f"{part2}\r\n"
                f"OK\r\n"
            ).encode()
        if cmd.startswith("AT+CMGD="):
            idx = int(cmd.split("=")[1].strip())
            deleted_indices.append(idx)
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    messages = driver.read_inbound_sms(delete_after_read=True)

    # Should be merged into exactly 1 message and trailing @ stripped
    assert len(messages) == 1
    assert messages[0]["sender"] == "+4790688031"
    assert not messages[0]["body"].endswith("@")
    assert "helt idiotisk melding?" in messages[0]["body"]
    assert 1 in deleted_indices
    assert 2 in deleted_indices


def test_configure_call_forwarding_success(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    commands_sent: list[str] = []

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        commands_sent.append(cmd)
        if cmd == 'AT+CCFC=0,3,"+4792830575",145':
            return b"OK\r\n"
        return b"ERROR\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    assert driver.configure_call_forwarding("+4792830575") is True
    assert 'AT+CCFC=0,3,"+4792830575",145' in commands_sent


def test_configure_call_forwarding_normalization(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    commands_sent: list[str] = []

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        commands_sent.append(cmd)
        if cmd == 'AT+CCFC=0,3,"+4792830575",145':
            return b"OK\r\n"
        return b"ERROR\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    # 8-digit Norwegian number shorthand should normalize to +4792830575
    assert driver.configure_call_forwarding("92 83 05 75") is True
    assert 'AT+CCFC=0,3,"+4792830575",145' in commands_sent


def test_configure_call_forwarding_disable(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    commands_sent: list[str] = []

    def responder(data: bytes) -> bytes | None:
        cmd = data.decode("utf-8", errors="ignore").strip()
        commands_sent.append(cmd)
        if cmd == "AT+CCFC=0,0":
            return b"OK\r\n"
        return b"ERROR\r\n"

    uart.responder = responder
    driver = ModemDriver(uart=uart)
    assert driver.configure_call_forwarding(enable=False) is True
    assert "AT+CCFC=0,0" in commands_sent


def test_configure_call_forwarding_invalid_or_empty(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    driver = ModemDriver(uart=uart)
    assert driver.configure_call_forwarding(number="") is False
    assert driver.configure_call_forwarding(number="   ") is False


def test_configure_call_forwarding_error_response(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        'AT+CCFC=0,3,"+4792830575",145': b"+CME ERROR: 30\r\n",
    }
    driver = ModemDriver(uart=uart)
    assert driver.configure_call_forwarding("+4792830575") is False


def test_query_call_forwarding(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    uart.auto_responses = {
        "AT+CCFC=0,2": (b'+CCFC: 1,1,"+4792830575",145\r\n+CCFC: 0,2,"",129\r\nOK\r\n'),
    }
    driver = ModemDriver(uart=uart)
    res = driver.query_call_forwarding(reason=0)
    assert res is not None
    assert len(res) == 2
    assert res[0]["active"] is True
    assert res[0]["status"] == 1
    assert res[0]["class"] == 1
    assert res[0]["number"] == "+4792830575"
    assert res[0]["type"] == 145
    assert res[1]["active"] is False


def test_init_modem_with_call_forwarding(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    ccfc_called = False

    def responder(data: bytes) -> bytes | None:
        nonlocal ccfc_called
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd in ("AT", "ATE0", "AT+CMGF=1", 'AT+CSCS="GSM"'):
            return b"OK\r\n"
        if cmd == "AT+CPIN?":
            return b"+CPIN: READY\r\n\r\nOK\r\n"
        if cmd == 'AT+CCFC=0,3,"+4792830575",145':
            ccfc_called = True
            return b"OK\r\n"
        return b"OK\r\n"

    uart.responder = responder
    cfg = {
        "call_forwarding_enabled": True,
        "call_forwarding_number": "+4792830575",
    }
    driver = ModemDriver(uart=uart, config=cfg)
    assert driver.init_modem() is True
    assert ccfc_called is True


def test_init_modem_call_forwarding_failure_graceful(mpy_env: MicroPythonEnvironment) -> None:
    from modem import ModemDriver

    uart = MockUART(1)
    ccfc_called = False

    def responder(data: bytes) -> bytes | None:
        nonlocal ccfc_called
        cmd = data.decode("utf-8", errors="ignore").strip()
        if cmd in ("AT", "ATE0", "AT+CMGF=1", 'AT+CSCS="GSM"'):
            return b"OK\r\n"
        if cmd == "AT+CPIN?":
            return b"+CPIN: READY\r\n\r\nOK\r\n"
        if cmd == 'AT+CCFC=0,3,"+4792830575",145':
            ccfc_called = True
            return b"+CME ERROR: 30\r\n"
        return b"OK\r\n"

    uart.responder = responder
    cfg = {
        "call_forwarding_enabled": True,
        "call_forwarding_number": "+4792830575",
    }
    driver = ModemDriver(uart=uart, config=cfg)
    # Even if network call forwarding fails, modem init should still succeed for SMS gateway operations
    assert driver.init_modem() is True
    assert ccfc_called is True
