"""Booking context resolution and conversation session management."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from snippen_sms.client import SnippenClient
from snippen_sms.models import (
    Booking,
    ConversationContext,
    ConversationState,
    Message,
)
from snippen_sms.storage import MessageStorage

logger = logging.getLogger("snippen_sms.context")

SELECTION_PATTERN = re.compile(
    r"^\s*(?:nr\.?|nummer|valg|booking|alternativ|#)?\s*(\d+)\.?\s*$",
    re.IGNORECASE,
)

ORDINAL_MAP = {
    "første": 1,
    "den første": 1,
    "1ste": 1,
    "andre": 2,
    "den andre": 2,
    "2dre": 2,
    "tredje": 3,
    "den tredje": 3,
    "3dje": 3,
    "fjerde": 4,
    "den fjerde": 4,
    "femte": 5,
    "den femte": 5,
}


class ResolutionStatus(str, Enum):
    """Outcome of resolving booking context for an SMS."""

    RESOLVED = "resolved"
    PROMPT_SENT = "prompt_sent"
    UNRESOLVED = "unresolved"
    INVALID_SELECTION = "invalid_selection"


@dataclass
class ContextResolutionResult:
    """Result returned by BookingContextResolver."""

    status: ResolutionStatus
    message: Message
    booking_id: str | None = None
    context: ConversationContext | None = None
    prompt_text: str | None = None
    candidate_bookings: list[Booking] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to dictionary representation."""
        return {
            "status": self.status.value,
            "message_id": self.message.id,
            "booking_id": self.booking_id,
            "prompt_text": self.prompt_text,
            "candidate_count": len(self.candidate_bookings),
        }


class BookingContextResolver:
    """Resolves incoming SMS messages to appropriate Snippen bookings."""

    def __init__(
        self,
        storage: MessageStorage,
        client: SnippenClient | None = None,
        conversation_ttl_seconds: float = 7200.0,
        service_name: str = "snippen-sms-service",
    ) -> None:
        self.storage = storage
        self.client = client
        self.conversation_ttl_seconds = conversation_ttl_seconds
        self.service_name = service_name

    @staticmethod
    def parse_selection(text: str, max_options: int) -> int | None:
        """Parse user reply text to identify selected option index (1-based).

        Supports numeric strings ('1', '2', 'Nr 1', '#2', 'valg 1') and Norwegian ordinals.
        """
        clean = text.strip().lower()
        if not clean:
            return None

        # Check numeric regex match
        match = SELECTION_PATTERN.match(clean)
        if match:
            try:
                choice = int(match.group(1))
                if 1 <= choice <= max_options:
                    return choice
            except ValueError:
                pass

        # Check ordinal mappings
        if clean in ORDINAL_MAP:
            choice = ORDINAL_MAP[clean]
            if 1 <= choice <= max_options:
                return choice

        return None

    @staticmethod
    def format_selection_prompt(bookings: list[Booking]) -> str:
        """Format friendly Norwegian prompt asking user to select booking."""
        lines = [
            "Du har flere reservasjoner registrert hos oss:",
        ]
        for idx, b in enumerate(bookings, start=1):
            lines.append(f"{idx}. {b.format_summary()}")
        lines.append(
            "Vennligst svar med tallet (f.eks. 1 eller 2) for reservasjonen henvendelsen gjelder."
        )
        return "\n".join(lines)

    def _is_session_expired(self, context: ConversationContext, current_time: datetime) -> bool:
        """Check if active conversation session has exceeded TTL."""
        elapsed = (current_time - context.last_activity_at).total_seconds()
        return elapsed > self.conversation_ttl_seconds

    def resolve_incoming_message(
        self,
        message: Message,
        available_bookings: list[Booking] | None = None,
    ) -> ContextResolutionResult:
        """Resolve booking context for an incoming SMS message.

        Handles:
        1. Ongoing selection prompt (user replying with option number).
        2. Active conversation context continuation (within TTL).
        3. Unambiguous single booking (automatic association).
        4. Multiple candidate bookings (initiating selection prompt).
        5. Zero bookings (graceful handling without error).
        """
        sender = message.sender.strip()
        now = message.created_at or datetime.now(UTC)

        # Retrieve or initialize conversation context
        context = self.storage.get_conversation_context(sender)
        if context is None:
            context = ConversationContext(
                phone_number=sender,
                state=ConversationState.IDLE,
                last_activity_at=now,
            )
            context = self.storage.save_conversation_context(context)

        # Handle expired context
        if self._is_session_expired(context, now):
            logger.debug("Conversation session for %s expired; resetting state to idle", sender)
            context.state = ConversationState.IDLE
            context.pending_booking_ids = []
            context.pending_message_id = None
            context.active_booking_id = None
            context.last_activity_at = now
            context = self.storage.save_conversation_context(context)

        # 1. Check if user is replying to an active selection prompt
        if context.state == ConversationState.AWAITING_SELECTION and context.pending_booking_ids:
            choice = self.parse_selection(message.body, len(context.pending_booking_ids))
            if choice is not None:
                resolved_id = context.pending_booking_ids[choice - 1]
                logger.info(
                    "User %s selected booking %s (option %d)",
                    sender,
                    resolved_id,
                    choice,
                )

                # Associate current message
                message.booking_id = resolved_id
                message.conversation_id = context.id
                self.storage.save_message(message)

                # Associate pending original message if recorded
                if context.pending_message_id is not None:
                    self.storage.update_message_booking_context(
                        message_id=context.pending_message_id,
                        booking_id=resolved_id,
                        conversation_id=context.id,
                    )
                    logger.debug(
                        "Associated pending message ID %s with booking %s",
                        context.pending_message_id,
                        resolved_id,
                    )

                # Transition context to resolved active state
                context.state = ConversationState.RESOLVED
                context.active_booking_id = resolved_id
                context.pending_booking_ids = []
                context.pending_message_id = None
                context.last_activity_at = now
                self.storage.save_conversation_context(context)

                return ContextResolutionResult(
                    status=ResolutionStatus.RESOLVED,
                    message=message,
                    booking_id=resolved_id,
                    context=context,
                )

            logger.debug(
                "Inbound message from %s during selection was not a valid option choice: '%s'",
                sender,
                message.body,
            )

        # 2. Check if user has an active resolved booking context within TTL
        if context.state == ConversationState.RESOLVED and context.active_booking_id:
            message.booking_id = context.active_booking_id
            message.conversation_id = context.id
            self.storage.save_message(message)

            context.last_activity_at = now
            self.storage.save_conversation_context(context)

            logger.info(
                "Associated message ID %s from %s with active booking %s",
                message.id,
                sender,
                context.active_booking_id,
            )
            return ContextResolutionResult(
                status=ResolutionStatus.RESOLVED,
                message=message,
                booking_id=context.active_booking_id,
                context=context,
            )

        # 3. Fetch candidate bookings for sender
        candidate_bookings: list[Booking] = []
        if available_bookings is not None:
            candidate_bookings = available_bookings
        elif self.client is not None:
            try:
                candidate_bookings = self.client.fetch_bookings_for_phone(sender)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Failed to fetch bookings for %s from Snippen client: %s", sender, exc
                )
                candidate_bookings = []

        # Sort candidate bookings by start_time
        candidate_bookings.sort(key=lambda b: b.start_time)

        # Case A: 0 Bookings found
        if not candidate_bookings:
            logger.info("No active bookings found for sender %s", sender)
            message.booking_id = None
            message.conversation_id = context.id
            self.storage.save_message(message)

            context.state = ConversationState.IDLE
            context.last_activity_at = now
            self.storage.save_conversation_context(context)

            return ContextResolutionResult(
                status=ResolutionStatus.UNRESOLVED,
                message=message,
                booking_id=None,
                context=context,
            )

        # Case B: Exactly 1 Booking found (unambiguous context)
        if len(candidate_bookings) == 1:
            single_booking = candidate_bookings[0]
            resolved_id = single_booking.id
            logger.info(
                "Unambiguous single booking %s matched for sender %s",
                resolved_id,
                sender,
            )

            message.booking_id = resolved_id
            message.conversation_id = context.id
            self.storage.save_message(message)

            context.state = ConversationState.RESOLVED
            context.active_booking_id = resolved_id
            context.pending_booking_ids = []
            context.pending_message_id = None
            context.last_activity_at = now
            self.storage.save_conversation_context(context)

            return ContextResolutionResult(
                status=ResolutionStatus.RESOLVED,
                message=message,
                booking_id=resolved_id,
                context=context,
                candidate_bookings=candidate_bookings,
            )

        # Case C: Multiple (> 1) Bookings found (ambiguous context)
        logger.info(
            "Found %d candidate bookings for sender %s; initiating selection prompt",
            len(candidate_bookings),
            sender,
        )
        prompt_text = self.format_selection_prompt(candidate_bookings)

        # Save incoming message
        message.booking_id = None
        message.conversation_id = context.id
        saved_msg = self.storage.save_message(message)

        # Update context to awaiting selection
        context.state = ConversationState.AWAITING_SELECTION
        context.pending_booking_ids = [b.id for b in candidate_bookings]
        context.pending_message_id = saved_msg.id
        context.last_activity_at = now
        self.storage.save_conversation_context(context)

        # Enqueue clarification prompt outbound SMS
        self.storage.enqueue_outbox(
            recipient=sender,
            body=prompt_text,
            sender=self.service_name,
            conversation_id=context.id,
        )
        logger.info("Enqueued selection prompt to %s", sender)

        return ContextResolutionResult(
            status=ResolutionStatus.PROMPT_SENT,
            message=saved_msg,
            booking_id=None,
            prompt_text=prompt_text,
            candidate_bookings=candidate_bookings,
            context=context,
        )
