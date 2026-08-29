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
from snippen_sms.migrations import MigrationRunner

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


def handle_migrate(db_path: str, target_version: int | None = None) -> int:
    """Execute database migrations up to target version (or latest)."""
    with MigrationRunner(db_path) as runner:
        applied = runner.run_migrations(target_version=target_version)
        current_version = runner.get_current_version()
        if applied:
            print(f"Applied {len(applied)} migration(s):")
            for m in applied:
                print(f"  - [{m.version:04d}] {m.name}")
            print(f"Database successfully updated to schema version {current_version}.")
        else:
            print(f"Database is already up to date at schema version {current_version}.")
    return 0


def handle_migrate_status(db_path: str) -> int:
    """Print current database migration status."""
    with MigrationRunner(db_path) as runner:
        current_version = runner.get_current_version()
        applied = runner.get_applied_migrations()
        pending = runner.get_pending_migrations()

        print(f"Database: {db_path}")
        print(f"Current Schema Version: {current_version}")
        print(f"\nApplied Migrations ({len(applied)}):")
        if applied:
            for m in applied:
                print(f"  - [{m['version']:04d}] {m['name']} (applied: {m['applied_at']})")
        else:
            print("  (None)")

        print(f"\nPending Migrations ({len(pending)}):")
        if pending:
            for m in pending:
                print(f"  - [{m.version:04d}] {m.name}")
        else:
            print("  (None - up to date)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
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
    parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path (default: data/sms_gateway.db)",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="SMS provider implementation to use (default: mock)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Run subcommand
    run_parser = subparsers.add_parser("run", help="Run the gateway service (default)")
    run_parser.add_argument(
        "--poll-interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0)",
    )
    run_parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )
    run_parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path (default: data/sms_gateway.db)",
    )
    run_parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="SMS provider implementation to use (default: mock)",
    )

    # Migrate subcommand
    migrate_parser = subparsers.add_parser("migrate", help="Run pending database migrations")
    migrate_parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path (default: data/sms_gateway.db)",
    )
    migrate_parser.add_argument(
        "--target-version",
        type=int,
        default=None,
        help="Target migration version to migrate up to",
    )

    # Migrate status subcommand
    status_parser = subparsers.add_parser("migrate-status", help="Show database migration status")
    status_parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path (default: data/sms_gateway.db)",
    )

    return parser


def main_cli() -> None:
    """Command-line entry point."""
    parser = build_parser()
    args = parser.parse_args()

    log_level = getattr(args, "log_level", "INFO") or "INFO"
    setup_logging(log_level)

    if args.command == "migrate":
        sys.exit(handle_migrate(args.database_path, getattr(args, "target_version", None)))
    elif args.command == "migrate-status":
        sys.exit(handle_migrate_status(args.database_path))
    else:
        # Default action: run gateway service
        db_path = getattr(args, "database_path", "data/sms_gateway.db")
        poll_interval = getattr(args, "poll_interval", 2.0)
        provider_arg = getattr(args, "provider", None)

        env_config = GatewayConfig.from_env()
        config = GatewayConfig(
            service_name=env_config.service_name,
            log_level=log_level,
            poll_interval_seconds=poll_interval,
            database_path=db_path,
            provider=provider_arg or env_config.provider,
        )

        try:
            asyncio.run(run_gateway(config))
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Exiting cleanly.")
            sys.exit(0)


if __name__ == "__main__":
    main_cli()
