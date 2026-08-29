"""Core Gateway Service application."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from snippen_sms.config import GatewayConfig
from snippen_sms.models import Message, MessageDirection, MessageStatus
from snippen_sms.providers.base import SmsProvider
from snippen_sms.providers.memory import InMemorySmsProvider
from snippen_sms.storage import MessageStorage

logger = logging.getLogger("snippen_sms.gateway")


class GatewayService:
    """Long-running gateway service managing SMS dispatch and ingestion."""

    def __init__(
        self,
        config: GatewayConfig | None = None,
        storage: MessageStorage | None = None,
        provider: SmsProvider | None = None,
    ) -> None:
        self.config = config or GatewayConfig()
        self.storage = storage or MessageStorage(self.config.database_path)
        self.provider = provider or InMemorySmsProvider()
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._start_time: float | None = None

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

        return {
            "status": "running" if self._is_running else "stopped",
            "service": self.config.service_name,
            "version": __version__,
            "provider": self.provider.__class__.__name__,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "poll_interval_seconds": self.config.poll_interval_seconds,
            "database_path": self.config.database_path,
            "total_messages": self.storage.count_messages(),
        }

    async def send_sms(
        self,
        recipient: str,
        body: str,
        sender: str | None = None,
    ) -> Message:
        """Dispatch an outbound SMS message through the provider and persist records.

        Args:
            recipient: Destination phone number.
            body: Text content of the SMS.
            sender: Originating sender ID or service name.

        Returns:
            The persisted Message record with updated delivery status.
        """
        sender_id = sender or self.config.service_name
        msg = Message(
            direction=MessageDirection.OUTBOUND,
            sender=sender_id,
            recipient=recipient,
            body=body,
            status=MessageStatus.PENDING,
        )
        saved_msg = self.storage.save_message(msg)
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
                # Service tick - poll incoming messages and process queue
                logger.debug("Gateway heartbeat tick.")
                try:
                    await self.poll_incoming_messages()
                except Exception:
                    logger.exception("Error during incoming message polling tick.")

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
