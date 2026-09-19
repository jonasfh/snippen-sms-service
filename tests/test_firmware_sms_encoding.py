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
    decode_inbound_text,
    decode_ucs2_hex,
    encode_ucs2_hex,
    is_gsm7,
    is_ucs2_hex,
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
