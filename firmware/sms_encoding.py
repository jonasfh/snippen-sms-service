"""MicroPython SMS character encoding module for SimCom cellular modems.

Supports GSM 03.38 7-bit character detection, UCS-2 / UTF-16BE hexadecimal
encoding and decoding (supporting emojis, surrogate pairs, and international
characters such as Norwegian æ, ø, å).
"""

# GSM 03.38 basic 7-bit alphabet (128 characters)
GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
    "abcdefghijklmnopqrstuvwxyzäöñüà"
)

# GSM 03.38 extension characters
GSM7_EXTENDED = "^{}\\[~]|€\x0c"

_GSM7_ALL = set(GSM7_BASIC + GSM7_EXTENDED)

_HEX_DIGITS = set("0123456789abcdefABCDEF")


def is_gsm7(text: str) -> bool:
    """Return True if all characters in text belong to the GSM 03.38 character set."""
    if not text:
        return True
    for ch in text:
        if ch not in _GSM7_ALL:
            return False
    return True


def encode_ucs2_hex(text: str) -> str:
    """Encode a Python Unicode string into uppercase UCS-2 / UTF-16BE hex format.

    Characters with code points above 0xFFFF (such as emojis) are encoded
    as UTF-16 surrogate pairs.
    """
    hex_parts: list[str] = []
    for ch in text:
        cp = ord(ch)
        if cp <= 0xFFFF:
            hex_parts.append(f"{cp:04X}")
        else:
            # UTF-16 surrogate pair for code points > 0xFFFF
            cp_sub = cp - 0x10000
            high = 0xD800 + (cp_sub >> 10)
            low = 0xDC00 + (cp_sub & 0x3FF)
            hex_parts.append(f"{high:04X}{low:04X}")
    return "".join(hex_parts)


def decode_ucs2_hex(hex_str: str) -> str:
    """Decode an uppercase or lowercase UCS-2 / UTF-16BE hex string into a Python string.

    Properly handles UTF-16 surrogate pairs (e.g. emojis).
    Raises ValueError if input length is not a multiple of 4 or contains non-hex characters.
    """
    s = hex_str.strip()
    if not s:
        return ""

    if len(s) % 4 != 0:
        raise ValueError(f"UCS-2 hex string length must be a multiple of 4 (got {len(s)})")

    chars: list[str] = []
    idx = 0
    total = len(s)

    while idx < total:
        chunk = s[idx : idx + 4]
        try:
            val = int(chunk, 16)
        except ValueError as exc:
            raise ValueError(f"Invalid hex characters in chunk '{chunk}'") from exc

        # Check for UTF-16 high surrogate (0xD800 - 0xDBFF)
        if 0xD800 <= val <= 0xDBFF:
            if idx + 8 > total:
                raise ValueError("Incomplete UTF-16 surrogate pair at end of string")
            low_chunk = s[idx + 4 : idx + 8]
            try:
                low = int(low_chunk, 16)
            except ValueError as exc:
                raise ValueError(
                    f"Invalid hex characters in surrogate chunk '{low_chunk}'"
                ) from exc

            if not (0xDC00 <= low <= 0xDFFF):
                raise ValueError(f"Invalid UTF-16 low surrogate value: 0x{low:04X}")

            code_point = 0x10000 + ((val - 0xD800) << 10) + (low - 0xDC00)
            chars.append(chr(code_point))
            idx += 8
        else:
            chars.append(chr(val))
            idx += 4

    return "".join(chars)


def is_ucs2_hex(text: str) -> bool:
    """Heuristic check to determine if a string is a UCS-2 hex-encoded SMS body or field."""
    s = text.strip()
    if len(s) < 4 or len(s) % 4 != 0:
        return False

    for ch in s:
        if ch not in _HEX_DIGITS:
            return False

    try:
        decoded = decode_ucs2_hex(s)
        if not decoded:
            return False

        # If it's a single code point (4 hex chars), it must be an ASCII/Latin character (00xx)
        if len(s) == 4:
            return s.startswith("00")

        # For longer strings, verify that characters have valid UCS-2 high bytes.
        # Most international SMS contain Latin/ASCII (00xx), Norwegian (00xx),
        # or emojis (high surrogates D8xx-DBxx).
        has_expected_prefix = False
        for i in range(0, len(s), 4):
            high_byte = s[i : i + 2].upper()
            if high_byte == "00" or high_byte in ("D8", "D9", "DA", "DB", "DC", "DD", "DE", "DF"):
                has_expected_prefix = True
                break

        if not has_expected_prefix:
            return False

        # Ensure decoded string contains predominantly printable or whitespace characters
        control_count = sum(1 for ch in decoded if ord(ch) < 32 and ch not in "\r\n\t")
        return control_count == 0
    except (ValueError, OverflowError):
        return False


def decode_inbound_text(text: str) -> str:
    """Decode incoming SMS text or field, automatically unpacking UCS-2 hex if detected."""
    s = text.strip()
    if is_ucs2_hex(s):
        try:
            return decode_ucs2_hex(s)
        except Exception:  # noqa: BLE001
            return text
    return text
