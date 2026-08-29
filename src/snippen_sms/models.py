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
    FAILED = "failed"
    DELIVERED = "delivered"


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
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat(),
            "modified_at": self.modified_at.isoformat(),
        }
