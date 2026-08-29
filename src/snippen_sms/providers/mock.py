"""Mock SMS provider implementation for testing and offline development."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from snippen_sms.providers.base import IncomingMessage, SendResult, SmsProvider

logger = logging.getLogger("snippen_sms.providers.mock")


@dataclass
class SentRecord:
    """Record of a message sent through MockSmsProvider."""

    recipient: str
    body: str
    result: SendResult
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class AutoReplyRule:
    """Rule to automatically queue a simulated inbound reply when a matching SMS is sent."""

    trigger: str
    reply: str
    sender: str = "MOCK-SENDER"
    case_sensitive: bool = False


class MockSmsProvider(SmsProvider):
    """Mock SMS provider for automated testing and hardware-free simulation.

    Enables testing the entire SMS gateway without physical modems, SIM cards,
    or external cloud messaging APIs.
    """

    def __init__(self, id_prefix: str = "mock") -> None:
        self.id_prefix = id_prefix
        self.sent_messages: list[SentRecord] = []
        self._inbox: list[IncomingMessage] = []
        self.is_opened: bool = False
        self._fail_next_sends: bool = False
        self._send_error_message: str = "Simulated provider dispatch failure"
        self._fail_next_receives: bool = False
        self._receive_error_message: str = "Simulated provider receive failure"
        self._auto_replies: list[AutoReplyRule] = []

    async def open(self) -> None:
        """Mark the mock provider interface as opened."""
        self.is_opened = True
        logger.debug("MockSmsProvider opened.")

    async def close(self) -> None:
        """Mark the mock provider interface as closed."""
        self.is_opened = False
        logger.debug("MockSmsProvider closed.")

    def simulate_send_failure(
        self,
        should_fail: bool = True,
        error_message: str = "Simulated provider dispatch failure",
    ) -> None:
        """Configure the provider to simulate send errors for subsequent messages."""
        self._fail_next_sends = should_fail
        self._send_error_message = error_message

    def simulate_receive_failure(
        self,
        should_fail: bool = True,
        error_message: str = "Simulated provider receive failure",
    ) -> None:
        """Configure the provider to simulate receive errors on subsequent polling."""
        self._fail_next_receives = should_fail
        self._receive_error_message = error_message

    def add_auto_reply(
        self,
        trigger: str,
        reply: str,
        sender: str = "MOCK-SENDER",
        case_sensitive: bool = False,
    ) -> None:
        """Register an auto-reply rule that triggers an inbound SMS when matching outbound SMS is sent."""
        self._auto_replies.append(
            AutoReplyRule(
                trigger=trigger,
                reply=reply,
                sender=sender,
                case_sensitive=case_sensitive,
            )
        )

    def simulate_inbound(
        self,
        sender: str,
        body: str,
        received_at: datetime | None = None,
        provider_message_id: str | None = None,
    ) -> IncomingMessage:
        """Enqueue an incoming SMS into the mock provider's inbox for ingestion."""
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

    def simulate_incoming(
        self,
        sender: str,
        body: str,
        received_at: datetime | None = None,
        provider_message_id: str | None = None,
    ) -> IncomingMessage:
        """Convenience alias for simulate_inbound."""
        return self.simulate_inbound(
            sender=sender,
            body=body,
            received_at=received_at,
            provider_message_id=provider_message_id,
        )

    async def send_sms(self, recipient: str, body: str) -> SendResult:
        """Send an SMS via the mock provider or simulate failure."""
        if self._fail_next_sends:
            result = SendResult(
                success=False,
                error_message=self._send_error_message,
            )
        else:
            msg_id = f"{self.id_prefix}-{uuid.uuid4().hex[:8]}"
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

        # Process auto-replies if send was successful
        if result.success:
            for rule in self._auto_replies:
                matched = (
                    (rule.trigger in body)
                    if rule.case_sensitive
                    else (rule.trigger.lower() in body.lower())
                )
                if matched:
                    self.simulate_inbound(
                        sender=rule.sender if rule.sender != "MOCK-SENDER" else recipient,
                        body=rule.reply,
                    )

        return result

    async def receive_sms(self) -> list[IncomingMessage]:
        """Drain and return all pending incoming messages from the inbox."""
        if self._fail_next_receives:
            raise RuntimeError(self._receive_error_message)

        messages = list(self._inbox)
        self._inbox.clear()
        logger.debug("Drained %d incoming messages from mock inbox.", len(messages))
        return messages

    def clear(self) -> None:
        """Reset sent message history, inbox, error simulation state, and auto-replies."""
        self.sent_messages.clear()
        self._inbox.clear()
        self._fail_next_sends = False
        self._send_error_message = "Simulated provider dispatch failure"
        self._fail_next_receives = False
        self._receive_error_message = "Simulated provider receive failure"
        self._auto_replies.clear()


# Alias for capitalization conventions
MockSMSProvider = MockSmsProvider
