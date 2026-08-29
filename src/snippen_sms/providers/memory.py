"""In-memory SMS provider implementation for testing and offline environments."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from snippen_sms.providers.base import IncomingMessage, SendResult, SmsProvider

logger = logging.getLogger("snippen_sms.providers.memory")


@dataclass
class SentRecord:
    """Record of a message sent through InMemorySmsProvider."""

    recipient: str
    body: str
    result: SendResult
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class InMemorySmsProvider(SmsProvider):
    """In-memory SMS provider for automated testing and hardware-agnostic simulation."""

    def __init__(self) -> None:
        self.sent_messages: list[SentRecord] = []
        self._inbox: list[IncomingMessage] = []
        self.is_opened: bool = False
        self._fail_next_sends: bool = False
        self._send_error_message: str = "Simulated provider dispatch failure"

    async def open(self) -> None:
        """Mark the provider interface as opened."""
        self.is_opened = True
        logger.debug("InMemorySmsProvider opened.")

    async def close(self) -> None:
        """Mark the provider interface as closed."""
        self.is_opened = False
        logger.debug("InMemorySmsProvider closed.")

    def simulate_send_failure(
        self,
        should_fail: bool = True,
        error_message: str = "Simulated provider dispatch failure",
    ) -> None:
        """Configure the provider to simulate send errors for subsequent messages."""
        self._fail_next_sends = should_fail
        self._send_error_message = error_message

    def simulate_inbound(
        self,
        sender: str,
        body: str,
        received_at: datetime | None = None,
        provider_message_id: str | None = None,
    ) -> IncomingMessage:
        """Enqueue an incoming SMS into the provider's inbox for ingestion."""
        msg_id = provider_message_id or f"inbound-{uuid.uuid4().hex[:8]}"
        msg = IncomingMessage(
            sender=sender,
            body=body,
            received_at=received_at or datetime.now(UTC),
            provider_message_id=msg_id,
        )
        self._inbox.append(msg)
        logger.debug("Simulated inbound SMS queued from %s: %s", sender, body)
        return msg

    async def send_sms(self, recipient: str, body: str) -> SendResult:
        """Send SMS or record failure if error simulation is active."""
        if self._fail_next_sends:
            result = SendResult(
                success=False,
                error_message=self._send_error_message,
            )
        else:
            msg_id = f"mem-{uuid.uuid4().hex[:8]}"
            result = SendResult(
                success=True,
                message_id=msg_id,
            )

        self.sent_messages.append(
            SentRecord(
                recipient=recipient,
                body=body,
                result=result,
            )
        )
        logger.debug("Sent SMS to %s, success=%s", recipient, result.success)
        return result

    async def receive_sms(self) -> list[IncomingMessage]:
        """Drain and return all pending incoming messages from the in-memory inbox."""
        messages = list(self._inbox)
        self._inbox.clear()
        logger.debug("Drained %d incoming messages from in-memory inbox.", len(messages))
        return messages

    def clear(self) -> None:
        """Reset sent message history, inbox, and failure simulation state."""
        self.sent_messages.clear()
        self._inbox.clear()
        self._fail_next_sends = False
        self._send_error_message = "Simulated provider dispatch failure"
