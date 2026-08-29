"""Main entry point and CLI for Snippen SMS Service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from typing import Any

from snippen_sms import __version__
from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService

logger = logging.getLogger("snippen_sms")


def setup_logging(level_name: str = "INFO") -> None:
    """Configure structured logging output."""
    numeric_level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_status() -> dict[str, Any]:
    """Return status of the SMS service (convenience helper)."""
    service = GatewayService()
    return service.get_status()


async def run_gateway(config: GatewayConfig) -> None:
    """Run the gateway service with OS signal handling."""
    service = GatewayService(config)
    loop = asyncio.get_running_loop()

    def handle_signal(sig: int) -> None:
        signame = signal.Signals(sig).name
        logger.info("Received exit signal %s. Initiating graceful shutdown...", signame)
        asyncio.create_task(service.stop())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: handle_signal(s))
        except NotImplementedError:
            # Signal handlers not implemented on some non-Unix platforms
            pass

    logger.info("Starting Snippen SMS Gateway v%s...", __version__)
    await service.run()


def main_cli() -> None:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(
        prog="snippen-sms",
        description="Snippen SMS Gateway Service",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"snippen-sms {__version__}",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    setup_logging(args.log_level)
    config = GatewayConfig(
        log_level=args.log_level,
        poll_interval_seconds=args.poll_interval,
    )

    try:
        asyncio.run(run_gateway(config))
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Exiting cleanly.")
        sys.exit(0)


if __name__ == "__main__":
    main_cli()
