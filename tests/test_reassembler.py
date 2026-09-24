"""Unit tests for inbound multipart SMS reassembly."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from snippen_sms.models import Message, MessageDirection, MessageStatus
from snippen_sms.providers.base import IncomingMessage
from snippen_sms.reassembler import (
    InboundReassembler,
    parse_multipart_info,
    parse_text_indicator,
    parse_udh,
    reassemble_stored_messages,
)


def test_parse_udh_8bit_binary() -> None:
    # \x05\x00\x03<ref><total><part>
    raw = "\x05\x00\x03\x2a\x02\x01Hello Part 1"
    res = parse_udh(raw)
    assert res is not None
    ref_id, total, part, body = res
    assert ref_id == 0x2A
    assert total == 2
    assert part == 1
    assert body == "Hello Part 1"


def test_parse_udh_16bit_binary() -> None:
    # \x06\x08\x04<ref_hi><ref_lo><total><part>
    raw = "\x06\x08\x04\x01\x2c\x03\x02Middle part"
    res = parse_udh(raw)
    assert res is not None
    ref_id, total, part, body = res
    assert ref_id == 0x012C
    assert total == 3
    assert part == 2
    assert body == "Middle part"


def test_parse_udh_8bit_hex() -> None:
    raw = "0500032a0201Hello from hex UDH"
    res = parse_udh(raw)
    assert res is not None
    ref_id, total, part, body = res
    assert ref_id == 0x2A
    assert total == 2
    assert part == 1
    assert body == "Hello from hex UDH"


def test_parse_udh_16bit_hex() -> None:
    raw = "06080412340301First part of 3"
    res = parse_udh(raw)
    assert res is not None
    ref_id, total, part, body = res
    assert ref_id == 0x1234
    assert total == 3
    assert part == 1
    assert body == "First part of 3"


def test_parse_udh_invalid() -> None:
    assert parse_udh("") is None
    assert parse_udh("Hello world") is None
    # Total = 1 (not multipart)
    assert parse_udh("\x05\x00\x03\x2a\x01\x01Single") is None
    # Part > total
    assert parse_udh("\x05\x00\x03\x2a\x02\x03Invalid") is None
    # Hex corrupted
    assert parse_udh("050003ZZ0201Corrupt") is None


def test_parse_text_indicator_prefixes() -> None:
    # (1/2) prefix
    res = parse_text_indicator("(1/2) Hei, dette er del en.")
    assert res is not None
    ref_id, total, part, body = res
    assert total == 2
    assert part == 1
    assert body == "Hei, dette er del en."

    # [2/2] prefix
    res = parse_text_indicator("[2/2] og dette er del to.")
    assert res is not None
    ref_id, total, part, body = res
    assert ref_id == "txt_2"
    assert total == 2
    assert part == 2
    assert body == "og dette er del to."

    # 1/2: prefix
    res = parse_text_indicator("1/2: Første del")
    assert res is not None
    assert res[1] == 2
    assert res[2] == 1
    assert res[3] == "Første del"

    # 1/2 prefix
    res = parse_text_indicator("1/2 Første del")
    assert res is not None
    assert res[1] == 2
    assert res[2] == 1
    assert res[3] == "Første del"


def test_parse_text_indicator_suffixes() -> None:
    # Suffix with (1/2)
    res = parse_text_indicator("Dette er første del (1/2)")
    assert res is not None
    ref_id, total, part, body = res
    assert ref_id == "txt_2"
    assert total == 2
    assert part == 1
    assert body == "Dette er første del"

    # Suffix with [2/2]
    res = parse_text_indicator("Dette er andre del [2/2]")
    assert res is not None
    assert res[1] == 2
    assert res[2] == 2
    assert res[3] == "Dette er andre del"


def test_parse_text_indicator_invalid() -> None:
    assert parse_text_indicator("") is None
    assert parse_text_indicator("Just a normal text message") is None
    assert parse_text_indicator("No slash (abc)") is None
    assert parse_text_indicator("(1/1) Single message") is None


def test_parse_multipart_info() -> None:
    # Falls back from UDH to text indicators
    udh_raw = "\x05\x00\x03\x2a\x02\x01UDH message"
    assert parse_multipart_info(udh_raw) is not None
    assert parse_multipart_info(udh_raw)[0] == 0x2A

    txt_raw = "(1/2) Text indicator"
    assert parse_multipart_info(txt_raw) is not None
    assert parse_multipart_info(txt_raw)[0] == "txt_2"


def test_inbound_reassembler_standalone() -> None:
    reassembler = InboundReassembler(timeout_sec=30.0)
    msg = IncomingMessage(sender="+4790000001", body="Standard single SMS")
    result = reassembler.add_message(msg)
    assert result is msg


def test_inbound_reassembler_in_order_udh() -> None:
    reassembler = InboundReassembler(timeout_sec=30.0)
    part1 = IncomingMessage(
        sender="+4790000001",
        body="\x05\x00\x03\x10\x02\x01Første del av lang melding. ",
        provider_message_id="msg_p1",
    )
    part2 = IncomingMessage(
        sender="+4790000001",
        body="\x05\x00\x03\x10\x02\x02Andre del av lang melding.",
        provider_message_id="msg_p2",
    )

    res1 = reassembler.add_message(part1)
    assert res1 is None

    res2 = reassembler.add_message(part2)
    assert res2 is not None
    assert res2.sender == "+4790000001"
    assert res2.body == "Første del av lang melding. Andre del av lang melding."
    assert res2.provider_message_id == "msg_p1"


def test_inbound_reassembler_out_of_order() -> None:
    reassembler = InboundReassembler(timeout_sec=30.0)
    part1 = IncomingMessage(
        sender="+4790000001",
        body="\x05\x00\x03\x11\x02\x01Part 1: start. ",
        provider_message_id="msg_1",
    )
    part2 = IncomingMessage(
        sender="+4790000001",
        body="\x05\x00\x03\x11\x02\x02Part 2: end.",
        provider_message_id="msg_2",
    )

    # Deliver part 2 first
    res2 = reassembler.add_message(part2)
    assert res2 is None

    # Deliver part 1 second
    res1 = reassembler.add_message(part1)
    assert res1 is not None
    assert res1.body == "Part 1: start. Part 2: end."


def test_inbound_reassembler_text_indicators() -> None:
    reassembler = InboundReassembler(timeout_sec=30.0)
    part1 = IncomingMessage(sender="+4790000002", body="(1/2) Første halvdel")
    part2 = IncomingMessage(sender="+4790000002", body="(2/2) andre halvdel")

    assert reassembler.add_message(part1) is None
    merged = reassembler.add_message(part2)
    assert merged is not None
    # Text indicator parts automatically insert a space if not separated by whitespace
    assert merged.body == "Første halvdel andre halvdel"


def test_inbound_reassembler_multiple_senders_concurrent() -> None:
    reassembler = InboundReassembler(timeout_sec=30.0)
    alice_p1 = IncomingMessage(sender="+4790000001", body="\x05\x00\x03\x01\x02\x01Alice 1")
    bob_p1 = IncomingMessage(sender="+4790000002", body="\x05\x00\x03\x01\x02\x01Bob 1")
    alice_p2 = IncomingMessage(sender="+4790000001", body="\x05\x00\x03\x01\x02\x02Alice 2")
    bob_p2 = IncomingMessage(sender="+4790000002", body="\x05\x00\x03\x01\x02\x02Bob 2")

    assert reassembler.add_message(alice_p1) is None
    assert reassembler.add_message(bob_p1) is None

    alice_full = reassembler.add_message(alice_p2)
    assert alice_full is not None
    assert alice_full.sender == "+4790000001"
    assert alice_full.body == "Alice 1Alice 2"

    bob_full = reassembler.add_message(bob_p2)
    assert bob_full is not None
    assert bob_full.sender == "+4790000002"
    assert bob_full.body == "Bob 1Bob 2"


def test_inbound_reassembler_timeout() -> None:
    reassembler = InboundReassembler(timeout_sec=0.1)
    part1 = IncomingMessage(sender="+4790000001", body="\x05\x00\x03\x05\x02\x01Only part 1")
    assert reassembler.add_message(part1) is None

    # Immediate timeout check: should return empty
    assert reassembler.check_timeouts(timeout_sec=10.0) == []

    # Sleep slightly past timeout
    time.sleep(0.15)
    released = reassembler.check_timeouts(timeout_sec=0.1)
    assert len(released) == 1
    assert released[0].sender == "+4790000001"
    assert released[0].body == "Only part 1"

    # Subsequent check is empty because buffer was purged
    assert reassembler.check_timeouts(timeout_sec=0.1) == []


def test_reassemble_stored_messages() -> None:
    now = datetime.now(UTC)
    m1 = Message(
        id=10,
        direction=MessageDirection.INBOUND,
        sender="+4790000001",
        recipient="+4790000000",
        body="Normal standalone message",
        status=MessageStatus.RECEIVED,
        created_at=now,
        modified_at=now,
    )
    p1 = Message(
        id=11,
        direction=MessageDirection.INBOUND,
        sender="+4790000002",
        recipient="+4790000000",
        body="\x05\x00\x03\x20\x02\x01Første del av lang melding. ",
        status=MessageStatus.RECEIVED,
        created_at=now,
        modified_at=now,
    )
    p2 = Message(
        id=12,
        direction=MessageDirection.INBOUND,
        sender="+4790000002",
        recipient="+4790000000",
        body="\x05\x00\x03\x20\x02\x02Andre del av lang melding.",
        status=MessageStatus.RECEIVED,
        created_at=now,
        modified_at=now,
    )

    merged, ack_map = reassemble_stored_messages([m1, p1, p2])

    assert len(merged) == 2
    # m1 should be unchanged
    assert m1 in merged
    assert ack_map[10] == [10]

    # Find the merged message
    merged_p = next(m for m in merged if m.id == 11)
    assert merged_p.body == "Første del av lang melding. Andre del av lang melding."
    assert set(ack_map[11]) == {11, 12}


def test_reassemble_stored_messages_incomplete() -> None:
    now = datetime.now(UTC)
    p1 = Message(
        id=21,
        direction=MessageDirection.INBOUND,
        sender="+4790000002",
        recipient="+4790000000",
        body="\x05\x00\x03\x30\x02\x01Only part 1 received so far",
        status=MessageStatus.RECEIVED,
        created_at=now,
        modified_at=now,
    )
    merged, ack_map = reassemble_stored_messages([p1])
    assert len(merged) == 1
    assert merged[0].id == 21
    assert merged[0].body == "\x05\x00\x03\x30\x02\x01Only part 1 received so far"
    assert ack_map[21] == [21]


def test_reassemble_stored_messages_text_mode_chunks_and_trailing_at() -> None:
    now = datetime.now(UTC)
    chunk1 = Message(
        id=50,
        direction=MessageDirection.INBOUND,
        sender="+4790688031",
        recipient="+4790000000",
        body="Hva skjer hvis jeg sender en skikkelig lang sms som ikke fr plass i vanlig 160 tegn, men heller typisk bruker noe snt som 40000000 tegn til  skrive en",
        status=MessageStatus.RECEIVED,
        created_at=now,
        modified_at=now,
    )
    chunk2 = Message(
        id=51,
        direction=MessageDirection.INBOUND,
        sender="+4790688031",
        recipient="+4790000000",
        body="helt idiotisk melding? Kommer den den da, eller bare krasjer den helt gratis og blir liggende i lilygo og godgjr seg? Vi tester ihvertfall....@",
        status=MessageStatus.RECEIVED,
        created_at=now,
        modified_at=now,
    )
    merged, ack_map = reassemble_stored_messages([chunk1, chunk2])
    assert len(merged) == 1
    assert merged[0].id == 50
    assert not merged[0].body.endswith("@")
    assert "helt idiotisk melding?" in merged[0].body
    assert set(ack_map[50]) == {50, 51}
