"""Synchronization service coordinating between SMS storage and Snippen API."""

from __future__ import annotations

import logging
from typing import Any

from snippen_sms.client import (
    SnippenAuthError,
    SnippenClient,
    SnippenClientError,
    SnippenNetworkError,
)
from snippen_sms.models import Message, MessageDirection
from snippen_sms.storage import MessageStorage

logger = logging.getLogger("snippen_sms.sync")


class SyncService:
    """Manages two-way data synchronization between the gateway and Snippen backend."""

    def __init__(
        self,
        storage: MessageStorage,
        client: SnippenClient,
        service_name: str = "snippen-sms-service",
    ) -> None:
        self.storage = storage
        self.client = client
        self.service_name = service_name

    def sync_inbox(self, limit: int = 100) -> list[int]:
        """Report unhandled received inbound SMS messages to Snippen and mark them processed.

        Returns:
            List of message IDs successfully acknowledged and processed by Snippen.
        """
        unprocessed = self.storage.get_unprocessed_inbox(limit=limit)
        if not unprocessed:
            return []

        logger.debug("Reporting %d unprocessed inbound SMS to Snippen...", len(unprocessed))
        acknowledged_ids = self.client.report_inbound_messages(unprocessed)

        for msg_id in acknowledged_ids:
            self.storage.mark_inbox_processed(msg_id)
            logger.info("Marked inbound message ID %s as processed post-sync", msg_id)

        return acknowledged_ids

    def sync_outbox(self) -> list[Message]:
        """Fetch pending outgoing SMS messages from Snippen and enqueue them locally.

        Deduplicates against existing records via external_id to prevent double-sending.

        Returns:
            List of newly enqueued Message instances.
        """
        items = self.client.fetch_pending_outbox()
        if not items:
            return []

        logger.debug("Received %d pending outbox candidate(s) from Snippen", len(items))
        enqueued: list[Message] = []

        for item in items:
            raw_id = item.get("id") or item.get("external_id")
            external_id = str(raw_id).strip() if raw_id is not None else None
            recipient = str(item.get("recipient") or item.get("to") or "").strip()
            body = str(item.get("body") or item.get("message") or item.get("text") or "").strip()
            sender = str(item.get("sender") or item.get("from") or "").strip() or self.service_name

            if not recipient or not body:
                logger.warning(
                    "Skipping invalid outbox item from Snippen (missing recipient or body): %s",
                    item,
                )
                continue

            # Deduplicate by external_id if present
            if external_id:
                existing = self.storage.get_message_by_external_id(
                    external_id=external_id,
                    direction=MessageDirection.OUTBOUND,
                )
                if existing is not None:
                    logger.debug(
                        "Skipping duplicate outbox item with external ID '%s' (existing local ID %s)",
                        external_id,
                        existing.id,
                    )
                    continue

            msg = self.storage.enqueue_outbox(
                recipient=recipient,
                body=body,
                sender=sender,
                external_id=external_id,
            )
            enqueued.append(msg)
            logger.info(
                "Enqueued outbound SMS ID %s from Snippen (external ID: %s) for %s",
                msg.id,
                external_id,
                recipient,
            )

        return enqueued

    def sync_statuses(self, limit: int = 100) -> int:
        """Report delivery status updates (SENT / FAILED) of outbound messages to Snippen.

        Returns:
            Count of messages whose statuses were successfully reported.
        """
        unreported = self.storage.get_unreported_outbox_statuses(limit=limit)
        if not unreported:
            return 0

        status_payloads: list[dict[str, Any]] = []
        for msg in unreported:
            if msg.external_id:
                status_payloads.append(
                    {
                        "external_id": msg.external_id,
                        "gateway_id": msg.id,
                        "status": msg.status.value,
                        "error_message": msg.error_message,
                        "modem_message_id": msg.modem_message_id,
                    }
                )

        if not status_payloads:
            return 0

        logger.debug("Reporting %d delivery status update(s) to Snippen...", len(status_payloads))
        self.client.report_outbox_status(status_payloads)

        for msg in unreported:
            if msg.id is not None:
                self.storage.mark_outbox_status_reported(msg.id)

        logger.info(
            "Successfully reported %d delivery status update(s) to Snippen", len(unreported)
        )
        return len(unreported)

    def sync_all(self) -> dict[str, Any]:
        """Perform a complete sync cycle: report inbound, fetch outbox, and report statuses.

        Returns:
            Diagnostic dictionary summarizing the synchronization cycle.
        """
        result: dict[str, Any] = {
            "inbox_synced": 0,
            "outbox_enqueued": 0,
            "statuses_reported": 0,
            "error": None,
        }

        try:
            inbox_ids = self.sync_inbox()
            result["inbox_synced"] = len(inbox_ids)
        except (SnippenAuthError, SnippenNetworkError, SnippenClientError) as exc:
            logger.warning("Inbox synchronization failed: %s", exc)
            result["error"] = str(exc)

        try:
            outbox_msgs = self.sync_outbox()
            result["outbox_enqueued"] = len(outbox_msgs)
        except (SnippenAuthError, SnippenNetworkError, SnippenClientError) as exc:
            logger.warning("Outbox synchronization failed: %s", exc)
            result["error"] = str(exc)

        try:
            reported_count = self.sync_statuses()
            result["statuses_reported"] = reported_count
        except (SnippenAuthError, SnippenNetworkError, SnippenClientError) as exc:
            logger.warning("Status reporting synchronization failed: %s", exc)
            result["error"] = str(exc)

        return result
