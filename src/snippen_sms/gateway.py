"""Core Gateway Service application."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from snippen_sms.config import GatewayConfig

logger = logging.getLogger("snippen_sms.gateway")


class GatewayService:
    """Long-running gateway service managing SMS dispatch and ingestion."""

    def __init__(self, config: GatewayConfig | None = None) -> None:
        self.config = config or GatewayConfig()
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
            "uptime_seconds": round(self.uptime_seconds, 2),
            "poll_interval_seconds": self.config.poll_interval_seconds,
        }

    async def start(self) -> None:
        """Initialize and start the gateway service."""
        if self._is_running:
            logger.warning("GatewayService is already running.")
            return

        self._is_running = True
        self._stop_event.clear()
        self._start_time = time.time()
        logger.info(
            "Starting %s (poll interval: %ss)...",
            self.config.service_name,
            self.config.poll_interval_seconds,
        )

    async def stop(self) -> None:
        """Signal the gateway service to stop gracefully."""
        if not self._is_running:
            return

        logger.info("Stopping %s...", self.config.service_name)
        self._is_running = False
        self._stop_event.set()

    async def run(self) -> None:
        """Main service execution loop."""
        await self.start()
        try:
            while not self._stop_event.is_set():
                # Service tick - hooks for future polling/message queues
                logger.debug("Gateway heartbeat tick.")
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
