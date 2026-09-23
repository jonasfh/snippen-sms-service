"""Unit tests for firmware/sms_encoding.py (GSM-7 and UCS-2 / UTF-16BE hex encoding)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

from sms_encoding import (
    InboundReassembler,
    decode_inbound_text,
    decode_ucs2_hex,
    encode_ucs2_hex,
    gsm7_length,
    is_gsm7,
    is_ucs2_hex,
    parse_multipart_info,
    parse_text_indicator,
    parse_udh,
    split_sms_body,
    ucs2_length,
)


def test_is_gsm7_ascii_and_extended() -> None:
    assert is_gsm7("Hello World 123!") is True
    assert is_gsm7("Test with brackets [123] and {curly} | euro € ~ ^") is True
    assert is_gsm7("") is True


def test_is_gsm7_norwegian_characters() -> None:
    # Norwegian characters are part of the GSM 03.38 standard
    assert is_gsm7("God dag, her er æ, ø og å samt Æ, Ø, Å!") is True


def test_is_gsm7_emojis_and_unsupported() -> None:
    # Emojis are outside GSM 03.38
    assert is_gsm7("Hei 🤖") is False
    assert is_gsm7("🎉 Gratulerer!") is False
    assert is_gsm7("Tommel opp 👍") is False
    # Unicode typography like en-dash, smart quotes
    assert is_gsm7("En–dash") is False
    assert is_gsm7("“Smart quotes”") is False


def test_encode_ucs2_hex_basic() -> None:
    assert encode_ucs2_hex("Hei") == "004800650069"
    # +47 (3 chars) + 99999999 (8 chars) = 11 characters
    assert encode_ucs2_hex("+4799999999") == "002B00340037" + "0039" * 8


def test_encode_ucs2_hex_norwegian() -> None:
    assert encode_ucs2_hex("æøåÆØÅ") == "00E600F800E500C600D800C5"


def test_encode_ucs2_hex_emojis() -> None:
    # 🤖 is U+1F916 -> UTF-16 surrogate pair 0xD83E 0xDD16
    assert encode_ucs2_hex("🤖") == "D83EDD16"
    assert encode_ucs2_hex("Hei 🤖!") == "0048006500690020D83EDD160021"


def test_decode_ucs2_hex_basic() -> None:
    assert decode_ucs2_hex("004800650069") == "Hei"
    assert decode_ucs2_hex("002b00340037") == "+47"


def test_decode_ucs2_hex_norwegian_and_emojis() -> None:
    hex_str = encode_ucs2_hex("Hei på deg 🤖! Velkommen til Snippen 🎉")
    decoded = decode_ucs2_hex(hex_str)
    assert decoded == "Hei på deg 🤖! Velkommen til Snippen 🎉"


def test_decode_ucs2_hex_invalid_inputs() -> None:
    # Not multiple of 4
    with pytest.raises(ValueError, match="multiple of 4"):
        decode_ucs2_hex("004")

    # Invalid hex characters
    with pytest.raises(ValueError, match="Invalid hex characters"):
        decode_ucs2_hex("00ZZ")

    # Incomplete surrogate pair
    with pytest.raises(ValueError, match="Incomplete UTF-16 surrogate pair"):
        decode_ucs2_hex("D83E")

    # Invalid low surrogate
    with pytest.raises(ValueError, match="Invalid UTF-16 low surrogate"):
        decode_ucs2_hex("D83E0041")


def test_is_ucs2_hex() -> None:
    valid_hex = encode_ucs2_hex("Din booking på Snippen er bekreftet 🤖")
    assert is_ucs2_hex(valid_hex) is True

    # Plain text should not match
    assert is_ucs2_hex("JA") is False
    assert is_ucs2_hex("NEI") is False
    assert is_ucs2_hex("+4799999999") is False
    assert is_ucs2_hex("Hei på deg!") is False
    assert (
        is_ucs2_hex("1234") is False
    )  # U+1234 is Ethiopic syllable, control check passes but heuristic filters
    assert is_ucs2_hex("") is False


def test_decode_inbound_text() -> None:
    # Plain text remains unchanged
    assert decode_inbound_text("JA") == "JA"
    assert decode_inbound_text("Hei Snippen!") == "Hei Snippen!"

    # UCS-2 hex encoded text is cleanly decoded
    msg = "Takk for koden! Vi er fremme 🤖 æøå"
    encoded = encode_ucs2_hex(msg)
    assert decode_inbound_text(encoded) == msg


def test_gsm7_length() -> None:
    assert gsm7_length("") == 0
    assert gsm7_length("Hello") == 5
    # Extended chars each count as 2 septets
    assert gsm7_length("€") == 2
    assert gsm7_length("[test]") == 8  # 4 normal + 2 brackets * 2 = 8
    # Norwegian letters are in basic table (1 septet each)
    assert gsm7_length("æøåÆØÅ") == 6


def test_ucs2_length() -> None:
    assert ucs2_length("") == 0
    assert ucs2_length("Hei") == 3
    assert ucs2_length("æøå") == 3
    # Emojis are surrogate pairs (2 UTF-16 code units)
    assert ucs2_length("🤖") == 2
    assert ucs2_length("Hei 🤖!") == 7  # 4 chars + 2 for emoji + 1 for !


def test_split_sms_body_short_gsm7() -> None:
    # 160 characters fits in a single message without indicator
    msg = "A" * 160
    chunks = split_sms_body(msg)
    assert len(chunks) == 1
    assert chunks[0] == msg


def test_split_sms_body_long_gsm7_word_boundaries() -> None:
    # 250 character typical booking confirmation message
    msg = (
        "Hei! Din booking på Snippen grendehus for 24. september er bekreftet. "
        "Vennligst betal leiebeløpet innen forfallsdato. "
        "Dørkoden din er 4589 og er gyldig fra kl. 12:00. "
        "Ved spørsmål, vennligst ta kontakt med styret. Velkommen til Snippen!"
    )
    assert len(msg) > 160
    chunks = split_sms_body(msg)

    assert len(chunks) == 2
    assert chunks[0].startswith("(1/2) ")
    assert chunks[1].startswith("(2/2) ")

    # Every chunk must be strictly <= 160 chars
    for chunk in chunks:
        assert gsm7_length(chunk) <= 160

    # Ensure text is not chopped mid-word where spaces were available
    assert not chunks[0].endswith("-")
    reconstructed = chunks[0][6:] + chunks[1][6:]
    assert reconstructed == msg


def test_split_sms_body_long_token_no_whitespace() -> None:
    # Message with an unbreakable 200-char continuous string
    long_url = (
        "https://vestreholmensameie.no/wp-json/snippen/v1/portal/booking/confirmation/token/"
        + ("X" * 120)
    )
    assert len(long_url) > 160
    chunks = split_sms_body(long_url)

    assert len(chunks) == 2
    assert chunks[0].startswith("(1/2) ")
    assert chunks[1].startswith("(2/2) ")
    for chunk in chunks:
        assert gsm7_length(chunk) <= 160

    # Reconstructed content matches original exactly
    assert chunks[0][6:] + chunks[1][6:] == long_url


def test_split_sms_body_short_ucs2() -> None:
    # UCS-2 message under 70 code units fits in single SMS without indicator
    msg = "Hei 🤖 fra Snippen!"
    assert ucs2_length(msg) <= 70
    chunks = split_sms_body(msg)
    assert len(chunks) == 1
    assert chunks[0] == msg


def test_split_sms_body_long_ucs2_with_emojis_surrogate_safety() -> None:
    # UCS-2 message exceeding 70 code units
    part1 = "Velkommen til Snippen grendehus! 🤖 "
    part2 = "Husk å vaske etter deg, og lukk alle vinduer før du forlater lokalet. 🎉 Vi ses!"
    msg = part1 + part2
    assert not is_gsm7(msg)
    assert ucs2_length(msg) > 70

    chunks = split_sms_body(msg)
    assert len(chunks) >= 2

    # Verify each chunk is strictly <= 70 code units (modem UCS-2 limit)
    for i, chunk in enumerate(chunks):
        assert chunk.startswith(f"({i + 1}/{len(chunks)}) ")
        assert ucs2_length(chunk) <= 70
        # Verify no broken surrogate pairs in hex encoding
        hex_encoded = encode_ucs2_hex(chunk)
        assert decode_ucs2_hex(hex_encoded) == chunk

    # Reconstructed text matches original
    reconstructed = "".join(c[6:] for c in chunks)
    assert reconstructed == msg


def test_split_sms_body_no_indicators() -> None:
    msg = "A" * 200
    chunks = split_sms_body(msg, add_indicators=False)
    assert len(chunks) == 2
    assert not chunks[0].startswith("(")
    assert "".join(chunks) == msg


def test_parse_udh() -> None:
    # 8-bit concatenated SMS UDH: \x05\x00\x03<ref><total><part>
    raw_8bit = "\x05\x00\x03\x2a\x02\x01Hei fra part 1"
    parsed_8bit = parse_udh(raw_8bit)
    assert parsed_8bit is not None
    ref_id, total, part, body = parsed_8bit
    assert ref_id == 42
    assert total == 2
    assert part == 1
    assert body == "Hei fra part 1"

    # 16-bit concatenated SMS UDH: \x06\x08\x04<ref_hi><ref_lo><total><part>
    raw_16bit = "\x06\x08\x04\x01\x20\x03\x02Hei fra part 2"
    parsed_16bit = parse_udh(raw_16bit)
    assert parsed_16bit is not None
    ref_id_16, total_16, part_16, body_16 = parsed_16bit
    assert ref_id_16 == 0x0120
    assert total_16 == 3
    assert part_16 == 2
    assert body_16 == "Hei fra part 2"

    # Plain text without UDH
    assert parse_udh("Hei Snippen!") is None
    assert parse_udh("") is None


def test_parse_text_indicator() -> None:
    # Prefix (1/2)
    res1 = parse_text_indicator("(1/2) Første del av melding")
    assert res1 is not None
    assert res1[1] == 2  # total
    assert res1[2] == 1  # part
    assert res1[3] == "Første del av melding"

    # Prefix [2/3]
    res2 = parse_text_indicator("[2/3] Andre del")
    assert res2 is not None
    assert res2[1] == 3
    assert res2[2] == 2
    assert res2[3] == "Andre del"

    # Prefix 1/2:
    res3 = parse_text_indicator("1/2: Tredje del")
    assert res3 is not None
    assert res3[1] == 2
    assert res3[2] == 1
    assert res3[3] == "Tredje del"

    # Suffix (2/2)
    res4 = parse_text_indicator("Siste del av melding (2/2)")
    assert res4 is not None
    assert res4[1] == 2
    assert res4[2] == 2
    assert res4[3] == "Siste del av melding"

    # Prefix 1/2 without colon
    res5 = parse_text_indicator("1/2 Fjerde del")
    assert res5 is not None
    assert res5[1] == 2
    assert res5[2] == 1
    assert res5[3] == "Fjerde del"

    # Plain text and edge cases
    assert parse_text_indicator("En vanlig melding") is None
    assert parse_text_indicator("hei") is None
    assert parse_text_indicator("Enkeltord") is None
    assert parse_text_indicator("") is None


def test_parse_multipart_info() -> None:
    # Tests both UDH and text indicators
    udh_msg = "\x05\x00\x03\x05\x02\x01UDH body"
    assert parse_multipart_info(udh_msg) == (5, 2, 1, "UDH body")

    text_msg = "(1/2) Text body"
    info = parse_multipart_info(text_msg)
    assert info is not None
    assert info[1] == 2
    assert info[2] == 1
    assert info[3] == "Text body"

    assert parse_multipart_info("Single message") is None


def test_inbound_reassembler_standalone_message() -> None:
    reassembler = InboundReassembler()
    msg = {"index": 1, "sender": "+4799999999", "body": "Enkel melding", "timestamp": "26/09/21"}
    res = reassembler.add_message(msg)
    assert res is not None
    assert res["body"] == "Enkel melding"
    assert res["sender"] == "+4799999999"


def test_inbound_reassembler_multipart_in_order() -> None:
    reassembler = InboundReassembler()
    part1 = {
        "index": 1,
        "sender": "+4799999999",
        "body": "(1/2) Første halvdel ",
        "timestamp": "26/09/21,12:00",
    }
    part2 = {
        "index": 2,
        "sender": "+4799999999",
        "body": "(2/2)andre halvdel",
        "timestamp": "26/09/21,12:01",
    }

    res1 = reassembler.add_message(part1)
    assert res1 is None  # Pending part 2

    res2 = reassembler.add_message(part2)
    assert res2 is not None
    assert res2["sender"] == "+4799999999"
    assert res2["body"] == "Første halvdel andre halvdel"
    assert res2["parts_count"] == 2


def test_inbound_reassembler_multipart_out_of_order() -> None:
    reassembler = InboundReassembler()
    # Part 2 arrives before Part 1
    part1 = {
        "index": 1,
        "sender": "+4788888888",
        "body": "(1/2)Start på melding ",
        "timestamp": "26/09/21,12:00",
    }
    part2 = {
        "index": 2,
        "sender": "+4788888888",
        "body": "(2/2)slutt på melding",
        "timestamp": "26/09/21,12:00",
    }

    assert reassembler.add_message(part2) is None
    res = reassembler.add_message(part1)
    assert res is not None
    assert res["body"] == "Start på melding slutt på melding"


def test_inbound_reassembler_timeout_partial() -> None:
    # Using 0 second timeout so it expires immediately
    reassembler = InboundReassembler(timeout_sec=0)
    part1 = {
        "index": 7,
        "sender": "+4777777777",
        "body": "(1/3) Del 1 av 3",
        "timestamp": "26/09/21,12:00",
    }

    assert reassembler.add_message(part1) is None

    # Check timeout
    timed_out = reassembler.check_timeouts(timeout_sec=0)
    assert len(timed_out) == 1
    assert timed_out[0]["sender"] == "+4777777777"
    assert timed_out[0]["body"] == "Del 1 av 3"
    assert timed_out[0]["partial"] is True
    assert timed_out[0]["parts_count"] == 1
    assert timed_out[0]["total_expected"] == 3

    # Subsequent timeout check returns empty (already released)
    assert reassembler.check_timeouts(timeout_sec=0) == []
