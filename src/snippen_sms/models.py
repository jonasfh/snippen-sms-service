"""Domain models for Snippen SMS Service."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class MessageDirection(str, Enum):
    """Direction of the SMS message."""

    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageStatus(str, Enum):
    """Lifecycle status of an SMS message."""

    PENDING = "pending"
    QUEUED = "queued"
    SENT = "sent"
    RECEIVED = "received"
    PROCESSED = "processed"
    FAILED = "failed"
    DELIVERED = "delivered"


class ConversationState(str, Enum):
    """State of an ongoing conversational context."""

    IDLE = "idle"
    AWAITING_SELECTION = "awaiting_selection"
    RESOLVED = "resolved"


@dataclass
class Booking:
    """Represents a Snippen booking record associated with a user."""

    id: str
    customer_phone: str
    start_time: datetime
    customer_name: str | None = None
    end_time: datetime | None = None
    resource_name: str | None = None
    status: str = "confirmed"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    modified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Ensure datetimes have UTC timezone if naive."""
        if self.start_time.tzinfo is None:
            self.start_time = self.start_time.replace(tzinfo=UTC)
        if self.end_time is not None and self.end_time.tzinfo is None:
            self.end_time = self.end_time.replace(tzinfo=UTC)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.modified_at.tzinfo is None:
            self.modified_at = self.modified_at.replace(tzinfo=UTC)

    def format_summary(self) -> str:
        """Format a human-readable booking summary for SMS presentation.

        Example: '15.12.2026 kl. 16:00 (Badstue)' or '15.12.2026 kl. 16:00'.
        """
        # Format date as DD.MM.YYYY and time as HH:MM
        date_str = self.start_time.strftime("%d.%m.%Y kl. %H:%M")
        if self.resource_name:
            return f"{date_str} ({self.resource_name})"
        return date_str

    def to_dict(self) -> dict[str, Any]:
        """Convert booking to dictionary representation."""
        return {
            "id": self.id,
            "customer_phone": self.customer_phone,
            "customer_name": self.customer_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "resource_name": self.resource_name,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
        }


@dataclass
class ConversationContext:
    """Represents the active conversation session for a phone number."""

    phone_number: str
    id: int | None = None
    active_booking_id: str | None = None
    pending_booking_ids: list[str] = field(default_factory=list)
    pending_message_id: int | None = None
    state: ConversationState = ConversationState.IDLE
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    modified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate and normalize fields."""
        if isinstance(self.state, str) and not isinstance(self.state, ConversationState):
            self.state = ConversationState(self.state)
        if self.last_activity_at.tzinfo is None:
            self.last_activity_at = self.last_activity_at.replace(tzinfo=UTC)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.modified_at.tzinfo is None:
            self.modified_at = self.modified_at.replace(tzinfo=UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert conversation context to dictionary representation."""
        return {
            "id": self.id,
            "phone_number": self.phone_number,
            "active_booking_id": self.active_booking_id,
            "pending_booking_ids": self.pending_booking_ids,
            "pending_message_id": self.pending_message_id,
            "state": self.state.value,
            "last_activity_at": self.last_activity_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
        }


@dataclass
class Message:
    """Represents an SMS message handled by the gateway."""

    direction: MessageDirection
    sender: str
    recipient: str
    body: str
    id: int | None = None
    status: MessageStatus = MessageStatus.PENDING
    modem_message_id: str | None = None
    external_id: str | None = None
    booking_id: str | None = None
    conversation_id: int | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    modified_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Validate and normalize enum fields."""
        if isinstance(self.direction, str) and not isinstance(self.direction, MessageDirection):
            self.direction = MessageDirection(self.direction)
        if isinstance(self.status, str) and not isinstance(self.status, MessageStatus):
            self.status = MessageStatus(self.status)
        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(tzinfo=UTC)
        if self.modified_at.tzinfo is None:
            self.modified_at = self.modified_at.replace(tzinfo=UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert message to dictionary representation."""
        return {
            "id": self.id,
            "direction": self.direction.value,
            "sender": self.sender,
            "recipient": self.recipient,
            "body": self.body,
            "status": self.status.value,
            "modem_message_id": self.modem_message_id,
            "external_id": self.external_id,
            "booking_id": self.booking_id,
            "conversation_id": self.conversation_id,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
        }
