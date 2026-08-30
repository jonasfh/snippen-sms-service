"""Tests for Booking Context Resolution and Conversation Management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from snippen_sms.client import SnippenClient
from snippen_sms.context import (
    BookingContextResolver,
    ResolutionStatus,
)
from snippen_sms.models import (
    Booking,
    ConversationContext,
    ConversationState,
    Message,
    MessageDirection,
    MessageStatus,
)
from snippen_sms.storage import MessageStorage


@pytest.fixture
def storage() -> MessageStorage:
    """Create in-memory message storage."""
    return MessageStorage(db_path=":memory:")


@pytest.fixture
def sample_bookings() -> list[Booking]:
    """Sample booking dataset."""
    now = datetime(2026, 12, 15, 16, 0, tzinfo=UTC)
    later = datetime(2027, 1, 5, 11, 0, tzinfo=UTC)
    return [
        Booking(
            id="book-101",
            customer_phone="+4791234567",
            customer_name="Ola Nordmann",
            start_time=now,
            resource_name="Badstue",
            status="confirmed",
        ),
        Booking(
            id="book-202",
            customer_phone="+4791234567",
            customer_name="Ola Nordmann",
            start_time=later,
            resource_name="Felleslokale",
            status="confirmed",
        ),
    ]


def test_parse_selection() -> None:
    """Verify parsing of selection replies in Norwegian and numeric formats."""
    # Direct numbers
    assert BookingContextResolver.parse_selection("1", 3) == 1
    assert BookingContextResolver.parse_selection(" 2 ", 3) == 2
    assert BookingContextResolver.parse_selection("3.", 3) == 3
    assert BookingContextResolver.parse_selection("#2", 3) == 2

    # Prefixes
    assert BookingContextResolver.parse_selection("nr 1", 3) == 1
    assert BookingContextResolver.parse_selection("nr. 2", 3) == 2
    assert BookingContextResolver.parse_selection("nummer 3", 3) == 3
    assert BookingContextResolver.parse_selection("valg 1", 3) == 1
    assert BookingContextResolver.parse_selection("booking 2", 3) == 2

    # Ordinals
    assert BookingContextResolver.parse_selection("første", 3) == 1
    assert BookingContextResolver.parse_selection("den første", 3) == 1
    assert BookingContextResolver.parse_selection("andre", 3) == 2
    assert BookingContextResolver.parse_selection("den andre", 3) == 2
    assert BookingContextResolver.parse_selection("tredje", 3) == 3

    # Out of bounds & invalid
    assert BookingContextResolver.parse_selection("4", 3) is None
    assert BookingContextResolver.parse_selection("0", 3) is None
    assert BookingContextResolver.parse_selection("hei på deg", 3) is None
    assert BookingContextResolver.parse_selection("", 3) is None


def test_format_selection_prompt(sample_bookings: list[Booking]) -> None:
    """Verify formatting of multi-booking selection prompt."""
    prompt = BookingContextResolver.format_selection_prompt(sample_bookings)
    assert "Du har flere reservasjoner registrert hos oss:" in prompt
    assert "1. 15.12.2026 kl. 16:00 (Badstue)" in prompt
    assert "2. 05.01.2027 kl. 11:00 (Felleslokale)" in prompt
    assert "Vennligst svar med tallet" in prompt


def test_resolve_unambiguous_single_booking(
    storage: MessageStorage,
    sample_bookings: list[Booking],
) -> None:
    """Verify automatic context association when a user has exactly one active booking."""
    resolver = BookingContextResolver(storage=storage)
    single_booking = [sample_bookings[0]]

    msg = Message(
        direction=MessageDirection.INBOUND,
        sender="+4791234567",
        recipient="snippen-sms-service",
        body="Hva er koden til døra?",
        status=MessageStatus.RECEIVED,
    )
    saved_msg = storage.save_message(msg)

    result = resolver.resolve_incoming_message(saved_msg, available_bookings=single_booking)

    assert result.status == ResolutionStatus.RESOLVED
    assert result.booking_id == "book-101"

    # Verify message is updated in database
    db_msg = storage.get_message(saved_msg.id)  # type: ignore[arg-type]
    assert db_msg is not None
    assert db_msg.booking_id == "book-101"

    # Verify conversation context
    context = storage.get_conversation_context("+4791234567")
    assert context is not None
    assert context.state == ConversationState.RESOLVED
    assert context.active_booking_id == "book-101"

    # No outbox prompt was queued
    assert storage.count_outbox() == 0


def test_resolve_zero_bookings(storage: MessageStorage) -> None:
    """Verify clean handling when user has no active bookings."""
    resolver = BookingContextResolver(storage=storage)

    msg = Message(
        direction=MessageDirection.INBOUND,
        sender="+4799999999",
        recipient="snippen-sms-service",
        body="Hei, jeg lurer på priser.",
        status=MessageStatus.RECEIVED,
    )
    saved_msg = storage.save_message(msg)

    result = resolver.resolve_incoming_message(saved_msg, available_bookings=[])

    assert result.status == ResolutionStatus.UNRESOLVED
    assert result.booking_id is None

    db_msg = storage.get_message(saved_msg.id)  # type: ignore[arg-type]
    assert db_msg is not None
    assert db_msg.booking_id is None

    context = storage.get_conversation_context("+4799999999")
    assert context is not None
    assert context.state == ConversationState.IDLE
    assert storage.count_outbox() == 0


def test_resolve_multiple_bookings_flow(
    storage: MessageStorage,
    sample_bookings: list[Booking],
) -> None:
    """Verify full interactive selection flow with prompt and numeric reply."""
    resolver = BookingContextResolver(storage=storage)

    # 1. User sends initial free-text message
    msg1 = Message(
        direction=MessageDirection.INBOUND,
        sender="+4791234567",
        recipient="snippen-sms-service",
        body="Ehh, jeg trenger noen bord. Er det mulig å få utvask etterpå?",
        status=MessageStatus.RECEIVED,
    )
    saved_msg1 = storage.save_message(msg1)

    result1 = resolver.resolve_incoming_message(saved_msg1, available_bookings=sample_bookings)

    assert result1.status == ResolutionStatus.PROMPT_SENT
    assert result1.booking_id is None
    assert result1.prompt_text is not None

    # Verify context state is awaiting selection
    context1 = storage.get_conversation_context("+4791234567")
    assert context1 is not None
    assert context1.state == ConversationState.AWAITING_SELECTION
    assert context1.pending_booking_ids == ["book-101", "book-202"]
    assert context1.pending_message_id == saved_msg1.id

    # Verify prompt SMS was queued to outbox
    outbox_msgs = storage.get_pending_outbox()
    assert len(outbox_msgs) == 1
    assert outbox_msgs[0].recipient == "+4791234567"
    assert "Du har flere reservasjoner" in outbox_msgs[0].body

    # 2. User replies with "1" to select the first booking
    msg2 = Message(
        direction=MessageDirection.INBOUND,
        sender="+4791234567",
        recipient="snippen-sms-service",
        body="1",
        status=MessageStatus.RECEIVED,
    )
    saved_msg2 = storage.save_message(msg2)

    result2 = resolver.resolve_incoming_message(saved_msg2)

    assert result2.status == ResolutionStatus.RESOLVED
    assert result2.booking_id == "book-101"

    # Both initial message and reply message now have booking_id set
    db_msg1 = storage.get_message(saved_msg1.id)  # type: ignore[arg-type]
    db_msg2 = storage.get_message(saved_msg2.id)  # type: ignore[arg-type]
    assert db_msg1 is not None and db_msg1.booking_id == "book-101"
    assert db_msg2 is not None and db_msg2.booking_id == "book-101"

    # Context is now resolved
    context2 = storage.get_conversation_context("+4791234567")
    assert context2 is not None
    assert context2.state == ConversationState.RESOLVED
    assert context2.active_booking_id == "book-101"
    assert context2.pending_booking_ids == []
    assert context2.pending_message_id is None

    # 3. Subsequent message from user within TTL automatically inherits active booking
    msg3 = Message(
        direction=MessageDirection.INBOUND,
        sender="+4791234567",
        recipient="snippen-sms-service",
        body="Flott, takk!",
        status=MessageStatus.RECEIVED,
    )
    saved_msg3 = storage.save_message(msg3)

    result3 = resolver.resolve_incoming_message(saved_msg3)
    assert result3.status == ResolutionStatus.RESOLVED
    assert result3.booking_id == "book-101"

    db_msg3 = storage.get_message(saved_msg3.id)  # type: ignore[arg-type]
    assert db_msg3 is not None and db_msg3.booking_id == "book-101"


def test_session_expiration(
    storage: MessageStorage,
    sample_bookings: list[Booking],
) -> None:
    """Verify that expired conversation context resets to idle."""
    resolver = BookingContextResolver(storage=storage, conversation_ttl_seconds=3600.0)

    # Setup context with old timestamp (3 hours ago)
    old_time = datetime.now(UTC) - timedelta(hours=3)
    context = ConversationContext(
        phone_number="+4791234567",
        active_booking_id="book-101",
        state=ConversationState.RESOLVED,
        last_activity_at=old_time,
    )
    storage.save_conversation_context(context)

    # Incoming message after TTL should refresh context with available bookings
    msg = Message(
        direction=MessageDirection.INBOUND,
        sender="+4791234567",
        recipient="snippen-sms-service",
        body="Ny melding etter lang tid",
        status=MessageStatus.RECEIVED,
    )
    saved_msg = storage.save_message(msg)

    # Since user now has 2 bookings, it should prompt again
    result = resolver.resolve_incoming_message(saved_msg, available_bookings=sample_bookings)
    assert result.status == ResolutionStatus.PROMPT_SENT


def test_resolver_with_snippen_client(storage: MessageStorage) -> None:
    """Verify integration between resolver and SnippenClient."""
    mock_client = MagicMock(spec=SnippenClient)
    now = datetime(2026, 12, 15, 16, 0, tzinfo=UTC)
    mock_client.fetch_bookings_for_phone.return_value = [
        Booking(
            id="book-999",
            customer_phone="+4791234567",
            customer_name="Test Bruker",
            start_time=now,
            resource_name="Badstue #2",
        )
    ]

    resolver = BookingContextResolver(storage=storage, client=mock_client)

    msg = Message(
        direction=MessageDirection.INBOUND,
        sender="+4791234567",
        recipient="snippen-sms-service",
        body="Trenger vi nøkkel?",
        status=MessageStatus.RECEIVED,
    )
    saved_msg = storage.save_message(msg)

    result = resolver.resolve_incoming_message(saved_msg)

    assert result.status == ResolutionStatus.RESOLVED
    assert result.booking_id == "book-999"
    mock_client.fetch_bookings_for_phone.assert_called_once_with("+4791234567")
