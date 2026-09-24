"""MicroPython SMS character encoding module for SimCom cellular modems.

Supports GSM 03.38 7-bit character detection, UCS-2 / UTF-16BE hexadecimal
encoding and decoding (supporting emojis, surrogate pairs, and international
characters such as Norwegian æ, ø, å).
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


# GSM 03.38 basic 7-bit alphabet (128 characters)
GSM7_BASIC = (
    "@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./"
    "0123456789:;<=>?¡"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿"
    "abcdefghijklmnopqrstuvwxyzäöñüà"
)

# GSM 03.38 extension characters
GSM7_EXTENDED = "^{}\\[~]|€\x0c"
GSM7_EXT_MAP = {
    10: "\x0c",
    20: "^",
    40: "{",
    41: "}",
    47: "\\",
    60: "[",
    61: "~",
    62: "]",
    64: "|",
    101: "€",
}

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


def gsm7_length(text: str) -> int:
    """Return character count in GSM 03.38 septets (extended characters count as 2)."""
    if not text:
        return 0
    total = 0
    for ch in text:
        if ch in GSM7_EXTENDED:
            total += 2
        else:
            total += 1
    return total


def ucs2_length(text: str) -> int:
    """Return character count in UCS-2 / UTF-16 16-bit code units (surrogates count as 2)."""
    if not text:
        return 0
    total = 0
    for ch in text:
        if ord(ch) > 0xFFFF:
            total += 2
        else:
            total += 1
    return total


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


def split_sms_body(
    text: str,
    max_gsm_len: int = 160,
    max_ucs2_len: int = 70,
    multipart_gsm_limit: int = 153,
    multipart_ucs2_limit: int = 67,
    add_indicators: bool = True,
) -> list[str]:
    """Split an SMS message into ordered chunks if it exceeds single SMS capacity.

    Handles GSM-7 vs UCS-2 character sets, surrogate pair boundaries (never splitting
    an emoji code point across chunks), and whitespace/word boundaries.
    When add_indicators is True, prepends '(i/N) ' to chunks while strictly
    guaranteeing each segment length stays within single SMS limits.
    """
    if not text:
        return [""]

    use_gsm = is_gsm7(text)
    if use_gsm:
        single_limit = max_gsm_len
        char_len_fn = lambda c: 2 if c in GSM7_EXTENDED else 1
        total_len = gsm7_length(text)
        default_mp_limit = multipart_gsm_limit
    else:
        single_limit = max_ucs2_len
        char_len_fn = lambda c: 2 if ord(c) > 0xFFFF else 1
        total_len = ucs2_length(text)
        default_mp_limit = multipart_ucs2_limit

    if total_len <= single_limit:
        return [text]

    # Message exceeds single SMS limit -> chunking required
    est_parts = max(2, (total_len + default_mp_limit - 1) // default_mp_limit)
    total_parts = est_parts

    chunks: list[str] = []
    text_len = len(text)

    # Re-evaluate up to 3 times to stabilize part count formatting (e.g. 9 -> 10 parts)
    for _ in range(3):
        indicator_len = len(f"({total_parts}/{total_parts}) ") if add_indicators else 0
        max_payload = (default_mp_limit if not add_indicators else single_limit) - indicator_len

        chunks = []
        idx = 0

        while idx < text_len:
            cur_len = 0
            end = idx
            while end < text_len:
                c_len = char_len_fn(text[end])
                if cur_len + c_len > max_payload:
                    break
                cur_len += c_len
                end += 1

            if end >= text_len:
                chunks.append(text[idx:])
                break

            # Try splitting at whitespace boundary in text[idx:end]
            split_idx = -1
            for s in range(end - 1, idx, -1):
                if text[s] in (" ", "\n", "\t"):
                    split_idx = s + 1
                    break

            if split_idx > idx:
                chunks.append(text[idx:split_idx])
                idx = split_idx
            else:
                chunks.append(text[idx:end])
                idx = end

        if not add_indicators or len(chunks) == total_parts:
            break
        total_parts = len(chunks)

    if not add_indicators:
        return chunks

    actual_total = len(chunks)
    return [f"({i + 1}/{actual_total}) {c}" for i, c in enumerate(chunks)]


def decode_pdu(pdu_hex: str) -> dict | None:
    """Decode a GSM 03.40 / 3GPP TS 23.040 SMS-DELIVER PDU hex string.

    Returns a dict with:
      - sender: E.164 formatted phone number (e.g. +4790688031)
      - timestamp: Service center timestamp (YY/MM/DD,HH:MM:SS)
      - body: decoded text (GSM 7-bit or UCS-2)
      - udh_info: (ref_id, total_parts, part_num) if multipart UDH present, else None
      - dcs: Data coding scheme int
    or None if decoding fails.
    """
    if not pdu_hex:
        return None
    s = pdu_hex.strip()
    try:
        smsc_len = int(s[:2], 16)
        idx = 2 + smsc_len * 2
        fo = int(s[idx : idx + 2], 16)
        udhi = bool(fo & 0x40)
        idx += 2

        oa_digits = int(s[idx : idx + 2], 16)
        idx += 2
        toa = int(s[idx : idx + 2], 16)
        idx += 2
        oa_octets = (oa_digits + 1) // 2
        oa_hex = s[idx : idx + oa_octets * 2]
        idx += oa_octets * 2
        sender_digits = "".join(oa_hex[i + 1] + oa_hex[i] for i in range(0, len(oa_hex), 2))[
            :oa_digits
        ]
        sender = ("+" if (toa == 145 or toa == 0x91) else "") + sender_digits

        # Skip TP-PID
        idx += 2
        dcs = int(s[idx : idx + 2], 16)
        idx += 2
        scts_hex = s[idx : idx + 14]
        idx += 14
        scts = "".join(scts_hex[i + 1] + scts_hex[i] for i in range(0, 14, 2))
        timestamp = f"{scts[0:2]}/{scts[2:4]}/{scts[4:6]},{scts[6:8]}:{scts[8:10]}:{scts[10:12]}"

        udl = int(s[idx : idx + 2], 16)
        idx += 2
        ud_hex = s[idx:]
        ud_bytes = bytes(int(ud_hex[i : i + 2], 16) for i in range(0, len(ud_hex), 2))

        udh_info = None
        udh_septets = 0

        if udhi and len(ud_bytes) > 0:
            udhl = ud_bytes[0]
            udh = ud_bytes[1 : 1 + udhl]
            udh_septets = ((udhl + 1) * 8 + 6) // 7
            p = 0
            while p + 1 < len(udh):
                iei = udh[p]
                iel = udh[p + 1]
                if iei == 0x00 and iel >= 3:
                    udh_info = (udh[p + 2], udh[p + 3], udh[p + 4])
                    break
                if iei == 0x08 and iel >= 4:
                    udh_info = ((udh[p + 2] << 8) | udh[p + 3], udh[p + 4], udh[p + 5])
                    break
                p += 2 + iel

        is_ucs2 = (dcs & 0x0C) == 0x08
        if is_ucs2:
            payload = ud_bytes[1 + ud_bytes[0] :] if (udhi and len(ud_bytes) > 0) else ud_bytes
            chars: list[str] = []
            i = 0
            n = len(payload)
            while i + 1 < n:
                val = (payload[i] << 8) | payload[i + 1]
                i += 2
                if 0xD800 <= val <= 0xDBFF and i + 1 < n:
                    val2 = (payload[i] << 8) | payload[i + 1]
                    if 0xDC00 <= val2 <= 0xDFFF:
                        i += 2
                        cp = 0x10000 + ((val - 0xD800) << 10) + (val2 - 0xDC00)
                        chars.append(chr(cp))
                        continue
                chars.append(chr(val))
            body = "".join(chars)
        else:
            septets: list[int] = []
            buf = 0
            bits = 0
            for b in ud_bytes:
                buf |= b << bits
                bits += 8
                while bits >= 7:
                    septets.append(buf & 0x7F)
                    buf >>= 7
                    bits -= 7
            if bits > 0 and len(septets) < udl:
                septets.append(buf & 0x7F)

            payload_septets = septets[udh_septets:udl]
            chars = []
            is_esc = False
            for sept in payload_septets:
                if is_esc:
                    chars.append(GSM7_EXT_MAP.get(sept, "?"))
                    is_esc = False
                elif sept == 27:
                    is_esc = True
                elif sept < len(GSM7_BASIC):
                    chars.append(GSM7_BASIC[sept])
                else:
                    chars.append("?")
            body = "".join(chars)

        return {
            "sender": sender,
            "timestamp": timestamp,
            "body": body,
            "udh_info": udh_info,
            "dcs": dcs,
        }
    except Exception as exc:  # noqa: BLE001
        print(f"[sms_encoding] decode_pdu error: {exc}")
        return None


def parse_udh(text: str) -> tuple[int, int, int, str] | None:
    """Detect and parse GSM User Data Header (UDH) for concatenated SMS.

    Supports:
    - 8-bit reference (IEI 0x00, 5-byte UDH: \\x05\\x00\\x03<ref><total><part>)
    - 16-bit reference (IEI 0x08, 6-byte UDH: \\x06\\x08\\x04<ref_hi><ref_lo><total><part>)
    - 8-bit reference hex string (e.g. 050003...)
    - 16-bit reference hex string (e.g. 060804...)

    Returns (ref_id, total_parts, part_num, clean_body) or None if not UDH.
    """
    if not text:
        return None

    # Check for 8-bit concatenated SMS UDH: \x05\x00\x03
    if len(text) >= 6 and ord(text[0]) == 5 and ord(text[1]) == 0 and ord(text[2]) == 3:
        ref_id = ord(text[3])
        total = ord(text[4])
        part = ord(text[5])
        if total > 1 and 1 <= part <= total:
            return ref_id, total, part, text[6:]

    # Check for 16-bit concatenated SMS UDH: \x06\x08\x04
    if len(text) >= 7 and ord(text[0]) == 6 and ord(text[1]) == 8 and ord(text[2]) == 4:
        ref_id = (ord(text[3]) << 8) | ord(text[4])
        total = ord(text[5])
        part = ord(text[6])
        if total > 1 and 1 <= part <= total:
            return ref_id, total, part, text[7:]

    # Check for hex-encoded UDH
    if len(text) >= 12 and text.startswith("050003"):
        try:
            ref_id = int(text[6:8], 16)
            total = int(text[8:10], 16)
            part = int(text[10:12], 16)
            if total > 1 and 1 <= part <= total:
                clean_body = text[12:]
                if is_ucs2_hex(clean_body):
                    clean_body = decode_ucs2_hex(clean_body)
                return ref_id, total, part, clean_body
        except ValueError:
            pass

    if len(text) >= 14 and text.startswith("060804"):
        try:
            ref_id = int(text[6:10], 16)
            total = int(text[10:12], 16)
            part = int(text[12:14], 16)
            if total > 1 and 1 <= part <= total:
                clean_body = text[14:]
                if is_ucs2_hex(clean_body):
                    clean_body = decode_ucs2_hex(clean_body)
                return ref_id, total, part, clean_body
        except ValueError:
            pass

    return None


def parse_text_indicator(text: str) -> tuple[str, int, int, str] | None:
    """Parse text-mode multipart indicators like (1/2), [1/2], 1/2:, etc.

    Returns (ref_id, total_parts, part_num, clean_body) or None.
    """
    if not text:
        return None

    # Only strip leading spaces to detect prefix, preserving interior and trailing whitespace
    s = text.lstrip(" ")
    if not s:
        return None

    # Prefix with parentheses: (1/2) or [1/2]
    for open_ch, close_ch in (("(", ")"), ("[", "]")):
        if s.startswith(open_ch):
            close_idx = s.find(close_ch)
            if 0 < close_idx <= 12:
                inner = s[1:close_idx].strip()
                if "/" in inner:
                    parts = inner.split("/", 1)
                    if parts[0].isdigit() and parts[1].isdigit():
                        part = int(parts[0])
                        total = int(parts[1])
                        if total > 1 and 1 <= part <= total:
                            rem = s[close_idx + 1 :]
                            if rem.startswith(" "):
                                rem = rem[1:]
                            ref_id = f"txt_{total}"
                            return ref_id, total, part, rem

    # Prefix with colon or space: 1/2: or 1/2
    first_space = s.find(" ")
    first_token = s[:first_space] if first_space != -1 else s
    token_check = first_token[:-1] if first_token.endswith(":") else first_token
    if "/" in token_check:
        parts = token_check.split("/", 1)
        if parts[0].isdigit() and parts[1].isdigit():
            part = int(parts[0])
            total = int(parts[1])
            if total > 1 and 1 <= part <= total:
                rem = s[len(first_token) :]
                if rem.startswith(" "):
                    rem = rem[1:]
                ref_id = f"txt_{total}"
                return ref_id, total, part, rem

    # Suffix with parentheses: ... (1/2) or ... [1/2]
    s_strip = text.rstrip(" ")
    for open_ch, close_ch in (("(", ")"), ("[", "]")):
        if s_strip.endswith(close_ch):
            open_idx = s_strip.rfind(open_ch)
            if open_idx != -1 and len(s_strip) - open_idx <= 14:
                inner = s_strip[open_idx + 1 : -1].strip()
                if "/" in inner:
                    parts = inner.split("/", 1)
                    if parts[0].isdigit() and parts[1].isdigit():
                        part = int(parts[0])
                        total = int(parts[1])
                        if total > 1 and 1 <= part <= total:
                            rem = s_strip[:open_idx]
                            if rem.endswith(" "):
                                rem = rem[:-1]
                            ref_id = f"txt_{total}"
                            return ref_id, total, part, rem

    return None


def parse_multipart_info(text: str) -> tuple[str | int, int, int, str] | None:
    """Detect multipart SMS information via UDH or text indicators.

    Returns (ref_id, total_parts, part_num, clean_body) or None.
    """
    udh = parse_udh(text)
    if udh is not None:
        return udh
    return parse_text_indicator(text)


class InboundReassembler:
    """Buffers and reassembles incoming multipart SMS segments."""

    def __init__(self, timeout_sec: int = 30) -> None:
        self.timeout_sec = timeout_sec
        self._buffers: dict[tuple[str, str | int], dict] = {}

    def add_message(self, msg: dict) -> dict | None:
        """Process an inbound message dict.

        If the message is standalone (not multipart), returns it immediately.
        If it is a part of a multipart message:
          - If all parts have arrived, returns the fully reassembled message.
          - If parts are still pending, returns None.
        """
        body = msg.get("body", "")
        sender = msg.get("sender", "")

        udh_info = msg.get("udh_info")
        if udh_info is not None and isinstance(udh_info, (tuple, list)) and len(udh_info) == 3:
            ref_id, total, part_num = udh_info
            clean_body = body
            info = (ref_id, total, part_num, clean_body)
        else:
            info = parse_multipart_info(body)

        if info is None:
            return msg

        ref_id, total, part_num, clean_body = info
        key = (sender, ref_id)
        now = _ticks_ms()

        if key not in self._buffers:
            self._buffers[key] = {
                "sender": sender,
                "timestamp": msg.get("timestamp", ""),
                "status": msg.get("status", "REC UNREAD"),
                "total": total,
                "parts": {},
                "first_seen_ms": now,
                "indices": [],
            }

        buf = self._buffers[key]
        buf["parts"][part_num] = clean_body
        if "index" in msg and msg["index"] not in buf["indices"]:
            buf["indices"].append(msg["index"])

        if len(buf["parts"]) >= total:
            # All parts received! Assemble in order 1..total
            assembled_parts: list[str] = []
            for i in range(1, total + 1):
                p_text = buf["parts"].get(i, "")
                if assembled_parts:
                    prev = assembled_parts[-1]
                    if (
                        isinstance(ref_id, str)
                        and ref_id.startswith("txt_")
                        and prev
                        and not prev.endswith((" ", "\n", "\t"))
                        and p_text
                        and not p_text.startswith((" ", "\n", "\t"))
                    ):
                        assembled_parts.append(" ")
                assembled_parts.append(p_text)
            assembled_body = "".join(assembled_parts)
            complete_msg = {
                "index": buf["indices"][0] if buf["indices"] else msg.get("index"),
                "sender": buf["sender"],
                "timestamp": buf["timestamp"],
                "status": buf["status"],
                "body": assembled_body,
                "parts_count": total,
            }
            del self._buffers[key]
            return complete_msg

        return None

    def check_timeouts(self, timeout_sec: int | None = None) -> list[dict]:
        """Release any expired partial multipart messages so no messages are lost."""
        if timeout_sec is None:
            timeout_sec = self.timeout_sec

        timeout_ms = timeout_sec * 1000
        now = _ticks_ms()
        expired_keys: list[tuple[str, str | int]] = []
        released_messages: list[dict] = []

        for key, buf in self._buffers.items():
            if _ticks_diff(now, buf["first_seen_ms"]) >= timeout_ms:
                expired_keys.append(key)
                assembled_parts: list[str] = []
                for k in sorted(buf["parts"].keys()):
                    p_text = buf["parts"][k]
                    if assembled_parts:
                        prev = assembled_parts[-1]
                        if (
                            isinstance(key[1], str)
                            and str(key[1]).startswith("txt_")
                            and prev
                            and not prev.endswith((" ", "\n", "\t"))
                            and p_text
                            and not p_text.startswith((" ", "\n", "\t"))
                        ):
                            assembled_parts.append(" ")
                    assembled_parts.append(p_text)
                partial_body = "".join(assembled_parts)
                partial_msg = {
                    "index": buf["indices"][0] if buf["indices"] else 0,
                    "sender": buf["sender"],
                    "timestamp": buf["timestamp"],
                    "status": buf["status"],
                    "body": partial_body,
                    "parts_count": len(buf["parts"]),
                    "total_expected": buf["total"],
                    "partial": True,
                }
                released_messages.append(partial_msg)

        for key in expired_keys:
            del self._buffers[key]

        return released_messages
