"""Inbound multipart SMS reassembly for Snippen SMS Service."""

from __future__ import annotations

import logging
import time

from snippen_sms.models import Message
from snippen_sms.providers.base import IncomingMessage

logger = logging.getLogger(__name__)


def parse_udh(text: str) -> tuple[int, int, int, str] | None:
    """Detect and parse GSM User Data Header (UDH) for concatenated SMS.

    Supports:
    - 8-bit reference binary (\\x05\\x00\\x03<ref><total><part>)
    - 16-bit reference binary (\\x06\\x08\\x04<ref_hi><ref_lo><total><part>)
    - 8-bit reference hex string (e.g. 050003...)
    - 16-bit reference hex string (e.g. 060804...)

    Returns (ref_id, total_parts, part_num, clean_body) or None.
    """
    if not text:
        return None

    # Binary 8-bit UDH: \x05\x00\x03
    if len(text) >= 6 and ord(text[0]) == 5 and ord(text[1]) == 0 and ord(text[2]) == 3:
        ref_id = ord(text[3])
        total = ord(text[4])
        part = ord(text[5])
        if total > 1 and 1 <= part <= total:
            return ref_id, total, part, text[6:]

    # Binary 16-bit UDH: \x06\x08\x04
    if len(text) >= 7 and ord(text[0]) == 6 and ord(text[1]) == 8 and ord(text[2]) == 4:
        ref_id = (ord(text[3]) << 8) | ord(text[4])
        total = ord(text[5])
        part = ord(text[6])
        if total > 1 and 1 <= part <= total:
            return ref_id, total, part, text[7:]

    # Hex 8-bit UDH: 050003...
    if len(text) >= 12 and text.startswith("050003"):
        try:
            ref_id = int(text[6:8], 16)
            total = int(text[8:10], 16)
            part = int(text[10:12], 16)
            if total > 1 and 1 <= part <= total:
                return ref_id, total, part, text[12:]
        except ValueError:
            pass

    # Hex 16-bit UDH: 060804...
    if len(text) >= 14 and text.startswith("060804"):
        try:
            ref_id = int(text[6:10], 16)
            total = int(text[10:12], 16)
            part = int(text[12:14], 16)
            if total > 1 and 1 <= part <= total:
                return ref_id, total, part, text[14:]
        except ValueError:
            pass

    return None


def parse_text_indicator(text: str) -> tuple[str, int, int, str] | None:
    """Parse text-mode multipart indicators like (1/2), [1/2], 1/2:, etc.

    Returns (ref_id, total_parts, part_num, clean_body) or None.
    """
    if not text:
        return None

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
                            rem = s[close_idx + 1 :].removeprefix(" ")
                            ref_id = f"txt_{total}"
                            return ref_id, total, part, rem

    # Prefix with colon or space: 1/2: or 1/2
    first_space = s.find(" ")
    first_token = s[:first_space] if first_space != -1 else s
    token_check = first_token.removesuffix(":")
    if "/" in token_check:
        parts = token_check.split("/", 1)
        if parts[0].isdigit() and parts[1].isdigit():
            part = int(parts[0])
            total = int(parts[1])
            if total > 1 and 1 <= part <= total:
                rem = s[len(first_token) :].removeprefix(" ")
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
                            rem = s_strip[:open_idx].removesuffix(" ")
                            ref_id = f"txt_{total}"
                            return ref_id, total, part, rem

    return None


def parse_multipart_info(text: str) -> tuple[str | int, int, int, str] | None:
    """Detect multipart SMS information via UDH or text indicators."""
    udh = parse_udh(text)
    if udh is not None:
        return udh
    return parse_text_indicator(text)


class InboundReassembler:
    """Buffers and reassembles incoming multipart SMS segments."""

    def __init__(self, timeout_sec: float = 30.0) -> None:
        self.timeout_sec = timeout_sec
        self._buffers: dict[tuple[str, str | int], dict] = {}

    def add_message(self, item: IncomingMessage) -> IncomingMessage | None:
        """Process an IncomingMessage instance.

        If standalone, returns item immediately.
        If part of multipart:
          - If all parts arrived, returns reassembled IncomingMessage.
          - If parts still pending, returns None.
        """
        info = parse_multipart_info(item.body)
        if info is None:
            return item

        ref_id, total, part_num, clean_body = info
        sender = item.sender
        key = (sender, ref_id)
        now = time.monotonic()

        if key not in self._buffers:
            self._buffers[key] = {
                "sender": sender,
                "first_item": item,
                "total": total,
                "parts": {},
                "first_seen": now,
            }

        buf = self._buffers[key]
        buf["parts"][part_num] = clean_body

        if len(buf["parts"]) >= total:
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

            first_msg = buf["first_item"]
            reassembled = IncomingMessage(
                sender=first_msg.sender,
                body=assembled_body,
                received_at=first_msg.received_at,
                provider_message_id=first_msg.provider_message_id,
            )
            del self._buffers[key]
            logger.info(
                "Successfully reassembled multipart SMS (%d parts) from %s",
                total,
                sender,
            )
            return reassembled

        return None

    def check_timeouts(self, timeout_sec: float | None = None) -> list[IncomingMessage]:
        """Release expired partial multipart messages."""
        if timeout_sec is None:
            timeout_sec = self.timeout_sec

        now = time.monotonic()
        expired_keys = []
        released: list[IncomingMessage] = []

        for key, buf in self._buffers.items():
            if now - buf["first_seen"] >= timeout_sec:
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
                first_msg = buf["first_item"]
                released.append(
                    IncomingMessage(
                        sender=first_msg.sender,
                        body=partial_body,
                        received_at=first_msg.received_at,
                        provider_message_id=first_msg.provider_message_id,
                    )
                )
                logger.warning(
                    "Timed out waiting for multipart SMS segments from %s (%d/%d parts arrived); releasing partial body",
                    buf["sender"],
                    len(buf["parts"]),
                    buf["total"],
                )

        for key in expired_keys:
            del self._buffers[key]

        return released


def reassemble_stored_messages(
    messages: list[Message],
) -> tuple[list[Message], dict[int, list[int]]]:
    """Inspect a list of unprocessed Message instances and merge any multipart segments

    belonging to the same sender and reference ID.

    Returns:
        (merged_messages, ack_map)
        where ack_map maps primary message ID -> list of all constituent message IDs.
    """
    if not messages:
        return [], {}

    # Group candidates by (sender, ref_id) if multipart info is found
    # Non-multipart messages remain standalone
    groups: dict[tuple[str, str | int], list[tuple[int, str, int, Message]]] = {}
    standalone: list[Message] = []
    ack_map: dict[int, list[int]] = {}

    for msg in messages:
        info = parse_multipart_info(msg.body)
        if info is not None:
            ref_id, total, part_num, clean_body = info
            key = (msg.sender, ref_id)
            if key not in groups:
                groups[key] = []
            groups[key].append((part_num, clean_body, total, msg))
        else:
            standalone.append(msg)
            if msg.id is not None:
                ack_map[msg.id] = [msg.id]
    # Merge any standalone messages that are unjoined text-mode chunks from same sender
    # (e.g. if modem stripped UDH in text mode, segment 1 is 153 chars or ends without terminal punctuation)
    if len(standalone) > 1:
        merged_standalone: list[Message] = []
        i = 0
        n = len(standalone)
        while i < n:
            curr = standalone[i]
            curr_body = (
                curr.body[:-1]
                if curr.body.endswith("@") and not curr.body.endswith("@@")
                else curr.body
            )
            absorbed_ids = [curr.id] if curr.id is not None else []
            while i + 1 < n:
                nxt = standalone[i + 1]
                if curr.sender and curr.sender == nxt.sender:
                    nxt_body = (
                        nxt.body[:-1]
                        if nxt.body.endswith("@") and not nxt.body.endswith("@@")
                        else nxt.body
                    )
                    is_concatenated_len = len(curr_body) in (153, 160, 67, 70)
                    is_sentence_continuation = (
                        curr_body
                        and not curr_body.endswith((".", "!", "?", "\n"))
                        and nxt_body
                        and nxt_body[0].islower()
                    )
                    if is_concatenated_len or is_sentence_continuation:
                        curr_body = curr_body + nxt_body
                        if nxt.id is not None:
                            absorbed_ids.append(nxt.id)
                        i += 1
                        continue
                break
            merged_msg = Message(
                id=curr.id,
                direction=curr.direction,
                sender=curr.sender,
                recipient=curr.recipient,
                body=curr_body,
                status=curr.status,
                external_id=curr.external_id,
                modem_message_id=curr.modem_message_id,
                booking_id=curr.booking_id,
                conversation_id=curr.conversation_id,
                error_message=curr.error_message,
                created_at=curr.created_at,
                modified_at=curr.modified_at,
            )
            merged_standalone.append(merged_msg)
            if curr.id is not None:
                ack_map[curr.id] = absorbed_ids
            i += 1
        standalone = merged_standalone
    elif len(standalone) == 1:
        curr = standalone[0]
        if curr.body.endswith("@") and not curr.body.endswith("@@"):
            curr.body = curr.body[:-1]

    merged_messages: list[Message] = list(standalone)

    for (sender, ref_id), parts in groups.items():
        total_expected = parts[0][2]
        part_dict = {p[0]: p[1] for p in parts}
        msg_dict = {p[0]: p[3] for p in parts}

        if len(part_dict) >= total_expected and all(
            i in part_dict for i in range(1, total_expected + 1)
        ):
            assembled_parts: list[str] = []
            for i in range(1, total_expected + 1):
                p_text = part_dict[i]
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

            primary_msg = msg_dict[1]
            all_ids = [m.id for m in msg_dict.values() if m.id is not None]

            merged_msg = Message(
                id=primary_msg.id,
                direction=primary_msg.direction,
                sender=primary_msg.sender,
                recipient=primary_msg.recipient,
                body=assembled_body,
                status=primary_msg.status,
                external_id=primary_msg.external_id,
                modem_message_id=primary_msg.modem_message_id,
                booking_id=primary_msg.booking_id,
                conversation_id=primary_msg.conversation_id,
                error_message=primary_msg.error_message,
                created_at=primary_msg.created_at,
                modified_at=primary_msg.modified_at,
            )
            merged_messages.append(merged_msg)
            if primary_msg.id is not None:
                ack_map[primary_msg.id] = all_ids
        else:
            for p in parts:
                msg = p[3]
                merged_messages.append(msg)
                if msg.id is not None:
                    ack_map[msg.id] = [msg.id]

    return merged_messages, ack_map
