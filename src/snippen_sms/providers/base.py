"""Base SMS provider abstraction interface and data structures."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class SendResult:
    """Result of an outbound SMS transmission attempt."""

    success: bool
    message_id: str | None = None
    error_message: str | None = None


@dataclass
class IncomingMessage:
    """Represents an inbound SMS message retrieved from a provider."""

    sender: str
    body: str
    received_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    provider_message_id: str | None = None

    def __post_init__(self) -> None:
        """Ensure received_at is timezone-aware UTC."""
        if self.received_at.tzinfo is None:
            self.received_at = self.received_at.replace(tzinfo=UTC)


class SmsProvider(abc.ABC):
    """Abstract base class for SMS hardware and cloud messaging providers."""

    async def open(self) -> None:
        """Initialize provider connections and hardware interfaces."""

    async def close(self) -> None:
        """Release provider resources and close hardware interfaces."""

    @abc.abstractmethod
    async def send_sms(self, recipient: str, body: str) -> SendResult:
        """Send an SMS message to a recipient.

        Args:
            recipient: The destination phone number in E.164 or local format.
            body: The text content of the SMS.

        Returns:
            SendResult containing status and provider reference or error detail.
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def receive_sms(self) -> list[IncomingMessage]:
        """Fetch and drain pending incoming SMS messages from the provider.

        Returns:
            List of IncomingMessage objects received by the provider.
        """
        raise NotImplementedError
