"""Core Gateway Service application."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from snippen_sms.config import GatewayConfig
from snippen_sms.models import Message, MessageDirection, MessageStatus
from snippen_sms.providers import get_provider
from snippen_sms.providers.base import SmsProvider
from snippen_sms.storage import MessageStorage
from snippen_sms.updater import SoftwareUpdater, UpdateCheckResult

logger = logging.getLogger("snippen_sms.gateway")


class GatewayService:
    """Long-running gateway service managing SMS dispatch and ingestion."""

    def __init__(
        self,
        config: GatewayConfig | None = None,
        storage: MessageStorage | None = None,
        provider: SmsProvider | None = None,
        updater: SoftwareUpdater | None = None,
    ) -> None:
        self.config = config or GatewayConfig()
        self.storage = storage or MessageStorage(self.config.database_path)
        self.provider = provider or get_provider(self.config.provider)
        self.updater = updater or SoftwareUpdater(
            github_repo=self.config.github_repo,
            github_token=self.config.github_token,
        )
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._start_time: float | None = None
        self._latest_version_check: UpdateCheckResult | None = None
        self._last_update_check_time: float = 0.0

    @property
    def is_running(self) -> bool:
        """Return whether the gateway service is actively running."""
        return self._is_running

    @property
    def uptime_seconds(self) -> float:
        """Return service uptime in seconds."""
        if self._start_time is None:
            return 0.0
        return max(0.0, time.time() - self._start_time)

    def get_status(self) -> dict[str, Any]:
        """Return diagnostic health and status report."""
        from snippen_sms import __version__

        pending_outbox = self.storage.count_outbox(
            status=MessageStatus.PENDING
        ) + self.storage.count_outbox(status=MessageStatus.QUEUED)
        return {
            "status": "running" if self._is_running else "stopped",
            "service": self.config.service_name,
            "version": __version__,
            "provider": self.provider.__class__.__name__,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "database_path": self.config.database_path,
            "outbox_pending": pending_outbox,
            "outbox_total": self.storage.count_outbox(),
            "inbox_total": self.storage.count_inbox(),
            "total_messages": self.storage.count_messages(),
            "github_repo": self.config.github_repo,
            "update_available": (
                self._latest_version_check.update_available
                if self._latest_version_check is not None
                else False
            ),
            "latest_version": (
                self._latest_version_check.latest_version
                if self._latest_version_check is not None
                else None
            ),
        }

    def check_for_updates(self) -> UpdateCheckResult:
        """Check GitHub for new releases and log notices if available."""
        self._last_update_check_time = time.time()
        try:
            result = self.updater.check_for_update()
            self._latest_version_check = result
            if result.update_available:
                logger.info(
                    "A new release (%s) is available on GitHub (current: v%s). "
                    "Run 'snippen-sms update' to upgrade.",
                    result.latest_version,
                    result.current_version,
                )
            elif result.error:
                logger.debug("Update check completed with notice: %s", result.error)
            return result
        except Exception as exc:  # noqa: BLE001
            logger.debug("Exception during update check: %s", exc)
            err_result = UpdateCheckResult(
                update_available=False,
                current_version=self.config.service_name,
                latest_version=None,
                error=str(exc),
            )
            self._latest_version_check = err_result
            return err_result

    def enqueue_outbox(
        self,
        recipient: str,
        body: str,
        sender: str | None = None,
    ) -> Message:
        """Enqueue an outbound SMS into the persistent local outbox.

        Args:
            recipient: Destination phone number.
            body: Text content of the SMS.
            sender: Optional originating sender ID (defaults to service name).

        Returns:
            The saved pending Message instance.
        """
        sender_id = sender or self.config.service_name
        message = self.storage.enqueue_outbox(
            recipient=recipient,
            body=body,
            sender=sender_id,
            status=MessageStatus.PENDING,
        )
        logger.info("Enqueued message ID %s for %s to outbox", message.id, recipient)
        return message

    async def process_outbox(self, limit: int = 50) -> list[Message]:
        """Process pending and queued messages from the outbox via the SMS provider.

        Args:
            limit: Maximum number of pending messages to dispatch in this batch.

        Returns:
            List of processed Message instances with updated statuses.
        """
        pending_messages = self.storage.get_pending_outbox(limit=limit)
        if not pending_messages:
            return []

        logger.debug("Processing %d pending outbox messages...", len(pending_messages))
        processed: list[Message] = []

        for msg in pending_messages:
            if msg.id is None:
                continue

            try:
                result = await self.provider.send_sms(recipient=msg.recipient, body=msg.body)
                if result.success:
                    updated = self.storage.update_message_status(
                        msg.id,
                        status=MessageStatus.SENT,
                        modem_message_id=result.message_id,
                    )
                    logger.info("Dispatched outbox SMS ID %s to %s", msg.id, msg.recipient)
                    processed.append(updated or msg)
                else:
                    updated = self.storage.update_message_status(
                        msg.id,
                        status=MessageStatus.FAILED,
                        error_message=result.error_message,
                    )
                    logger.warning(
                        "Failed to dispatch outbox SMS ID %s to %s: %s",
                        msg.id,
                        msg.recipient,
                        result.error_message,
                    )
                    processed.append(updated or msg)
            except Exception as exc:
                logger.exception("Unexpected exception while dispatching outbox SMS ID %s", msg.id)
                updated = self.storage.update_message_status(
                    msg.id,
                    status=MessageStatus.FAILED,
                    error_message=str(exc),
                )
                processed.append(updated or msg)

        return processed

    async def send_sms(
        self,
        recipient: str,
        body: str,
        sender: str | None = None,
    ) -> Message:
        """Enqueue an outbound message to the outbox and immediately attempt delivery.

        Args:
            recipient: Destination phone number.
            body: Text content of the SMS.
            sender: Originating sender ID or service name.

        Returns:
            The persisted Message record with updated delivery status.
        """
        saved_msg = self.enqueue_outbox(recipient=recipient, body=body, sender=sender)
        assert saved_msg.id is not None

        try:
            result = await self.provider.send_sms(recipient=recipient, body=body)
            if result.success:
                updated = self.storage.update_message_status(
                    saved_msg.id,
                    status=MessageStatus.SENT,
                    modem_message_id=result.message_id,
                )
                logger.info("Dispatched SMS ID %s to %s", saved_msg.id, recipient)
                return updated or saved_msg
            else:
                updated = self.storage.update_message_status(
                    saved_msg.id,
                    status=MessageStatus.FAILED,
                    error_message=result.error_message,
                )
                logger.warning(
                    "Failed to dispatch SMS ID %s to %s: %s",
                    saved_msg.id,
                    recipient,
                    result.error_message,
                )
                return updated or saved_msg
        except Exception as exc:
            logger.exception("Unexpected exception while dispatching SMS ID %s", saved_msg.id)
            updated = self.storage.update_message_status(
                saved_msg.id,
                status=MessageStatus.FAILED,
                error_message=str(exc),
            )
            return updated or saved_msg

    async def poll_incoming_messages(self) -> list[Message]:
        """Poll incoming SMS messages from the provider and persist them to storage."""
        try:
            inbound_items = await self.provider.receive_sms()
        except Exception:
            logger.exception("Unexpected exception while polling incoming SMS from provider.")
            return []

        persisted_messages: list[Message] = []
        for item in inbound_items:
            msg = Message(
                direction=MessageDirection.INBOUND,
                sender=item.sender,
                recipient=self.config.service_name,
                body=item.body,
                status=MessageStatus.RECEIVED,
                modem_message_id=item.provider_message_id,
                created_at=item.received_at,
            )
            saved = self.storage.save_message(msg)
            persisted_messages.append(saved)
            logger.info("Ingested inbound SMS ID %s from %s", saved.id, saved.sender)

        return persisted_messages

    async def process_inbox(self) -> list[Message]:
        """Alias for poll_incoming_messages to ingest incoming provider messages."""
        return await self.poll_incoming_messages()

    async def start(self) -> None:
        """Initialize and start the gateway service."""
        if self._is_running:
            logger.warning("GatewayService is already running.")
            return

        await self.provider.open()
        self._is_running = True
        self._stop_event.clear()
        self._start_time = time.time()
        logger.info(
            "Starting %s using provider %s (poll interval: %ss)...",
            self.config.service_name,
            self.provider.__class__.__name__,
            self.config.poll_interval_seconds,
        )

        if self.config.check_updates_on_startup:
            try:
                self.check_for_updates()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Startup update check skipped or encountered error: %s", exc)

    async def stop(self) -> None:
        """Signal the gateway service to stop gracefully."""
        if not self._is_running:
            return

        logger.info("Stopping %s...", self.config.service_name)
        self._is_running = False
        self._stop_event.set()
        await self.provider.close()
        self.storage.close()

    async def run(self) -> None:
        """Main service execution loop."""
        await self.start()
        try:
            while not self._stop_event.is_set():
                # Service tick - process pending outbox and poll incoming messages
                logger.debug("Gateway heartbeat tick.")
                try:
                    await self.process_outbox()
                except Exception:
                    logger.exception("Error during outbox processing tick.")

                try:
                    await self.poll_incoming_messages()
                except Exception:
                    logger.exception("Error during incoming message polling tick.")

                # Periodic update check
                if (
                    self.config.auto_update_check
                    and (time.time() - self._last_update_check_time)
                    >= self.config.update_check_interval_seconds
                ):
                    try:
                        self.check_for_updates()
                    except Exception:
                        logger.exception("Error during periodic update check tick.")

                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=self.config.poll_interval_seconds,
                    )
                except TimeoutError:
                    # Timeout reached without stop event, continue loop
                    continue
        except asyncio.CancelledError:
            logger.info("Gateway service loop task cancelled.")
        finally:
            await self.stop()
            logger.info("Gateway service stopped cleanly.")
