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


def get_status(config: GatewayConfig | None = None) -> dict[str, Any]:
    """Return status of the SMS service (convenience helper)."""
    service = GatewayService(config=config)
    return service.get_status()


def handle_status(
    database_path: str = "data/sms_gateway.db",
    json_output: bool = False,
) -> int:
    """Print diagnostic health and status report of the SMS gateway service."""
    import json

    env_config = GatewayConfig.from_env()
    config = GatewayConfig(
        service_name=env_config.service_name,
        database_path=database_path,
        provider=env_config.provider,
        provider_url=env_config.provider_url,
        sync_enabled=False,
        check_updates_on_startup=False,
    )
    try:
        status = get_status(config)
        if json_output:
            print(json.dumps(status, indent=2))
        else:
            print(f"Service:            {status.get('service', 'snippen-sms-service')}")
            print(f"Status:             {status.get('status', 'unknown')}")
            print(f"Version:            v{status.get('version', __version__)}")
            print(f"Provider:           {status.get('provider', 'unknown')}")
            print(f"Database:           {status.get('database_path', database_path)}")
            print(
                f"Messages:           {status.get('total_messages', 0)} total "
                f"({status.get('outbox_pending', 0)} outbox pending, "
                f"{status.get('inbox_unprocessed', 0)} inbox unprocessed)"
            )
            print(f"API Sync:           {'Enabled' if status.get('sync_enabled') else 'Disabled'}")
            print(
                f"Context Resolver:   "
                f"{'Enabled' if status.get('booking_resolution_enabled') else 'Disabled'}"
            )
        return 0
    except Exception as exc:  # noqa: BLE001
        if json_output:
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            print(f"❌ Error checking service status: {exc}")
        return 1


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


def handle_check_update(
    repo: str = "jonasfh/snippen-sms-service",
    token: str | None = None,
) -> int:
    """Check GitHub Releases for available updates and display result."""
    from snippen_sms.updater import SoftwareUpdater

    updater = SoftwareUpdater(github_repo=repo, github_token=token)
    print(f"Checking for updates from GitHub repository: {repo}...")
    result = updater.check_for_update()

    print(f"\nCurrent Version:  v{result.current_version}")
    if result.error:
        print(f"Update Check:     Error ({result.error})")
        return 1

    if result.latest_version:
        print(f"Latest Release:   v{result.latest_version}")
    else:
        print("Latest Release:   (No published releases found yet)")

    if result.update_available:
        print("Status:           🚀 Update Available!")
        if result.release_info and result.release_info.wheel_url:
            print(f"Package Asset:    {result.release_info.wheel_url}")
        print("\nTo upgrade, run:  snippen-sms update")
    else:
        print("Status:           ✅ Up to date")
    return 0


def handle_update(
    repo: str = "jonasfh/snippen-sms-service",
    token: str | None = None,
    force: bool = False,
    database_path: str = "data/sms_gateway.db",
) -> int:
    """Download latest release artifact and perform upgrade."""
    from snippen_sms.updater import SoftwareUpdater

    updater = SoftwareUpdater(github_repo=repo, github_token=token)
    print(f"Fetching latest release from {repo}...")
    success, message = updater.perform_upgrade(force=force, database_path=database_path)

    if success:
        print(f"✅ {message}")
        print("\nIf running as a systemd service, restart the service to apply changes:")
        print("  sudo systemctl restart snippen-sms")
        return 0
    else:
        print(f"❌ Upgrade failed: {message}")
        return 1


def handle_sync(
    api_url: str | None,
    api_token: str | None,
    database_path: str = "data/sms_gateway.db",
) -> int:
    """Execute a single one-shot sync with Snippen and display results."""
    from snippen_sms.client import SnippenClient
    from snippen_sms.storage import MessageStorage
    from snippen_sms.sync import SyncService

    if not api_url:
        print("Error: No Snippen API URL provided. Set --api-url or SNIPPEN_SMS_API_URL.")
        return 1

    storage = MessageStorage(database_path)
    client = SnippenClient(api_url=api_url, api_token=api_token)
    sync_service = SyncService(storage=storage, client=client)

    print(f"Connecting to Snippen API at {api_url}...")
    res = sync_service.sync_all()

    print("\nSynchronization Results:")
    print(f"  - Inbound messages reported: {res['inbox_synced']}")
    print(f"  - Outbound messages fetched:  {res['outbox_enqueued']}")
    print(f"  - Statuses reported:         {res['statuses_reported']}")

    if res.get("error"):
        print(f"\n⚠️ Notice: Sync finished with error: {res['error']}")
        return 1

    print("\n✅ Synchronization completed successfully.")
    return 0


def handle_send(
    recipient: str,
    body: str,
    provider_name: str | None = None,
    provider_url: str | None = None,
    database_path: str = "data/sms_gateway.db",
) -> int:
    """Send an SMS directly using the configured provider."""
    env_config = GatewayConfig.from_env()
    config = GatewayConfig(
        service_name=env_config.service_name,
        database_path=database_path,
        provider=provider_name or env_config.provider,
        provider_url=provider_url or env_config.provider_url,
        sync_enabled=False,
    )
    service = GatewayService(config=config)
    print(f"Sending SMS to {recipient} via provider '{config.provider}'...")
    try:
        msg = asyncio.run(service.send_sms(recipient=recipient, body=body))
        if msg.status.value == "sent":
            print(f"✅ SMS sent successfully! (ID: {msg.id}, Provider ID: {msg.modem_message_id})")
            return 0
        else:
            print(
                f"❌ SMS delivery failed (status: {msg.status.value}). Error: {msg.error_message}"
            )
            return 1
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Exception while sending SMS: {exc}")
        return 1


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
    parser.add_argument(
        "--provider-url",
        type=str,
        default=None,
        help="SMS HTTP provider base URL (default: SNIPPEN_SMS_PROVIDER_URL)",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="Snippen API endpoint base URL (default: SNIPPEN_SMS_API_URL)",
    )
    parser.add_argument(
        "--api-token",
        type=str,
        default=None,
        help="Snippen API Bearer/Auth token (default: SNIPPEN_SMS_API_TOKEN)",
    )
    parser.add_argument(
        "--sync-interval",
        type=float,
        default=None,
        help="Snippen synchronization interval in seconds (default: 5.0)",
    )
    parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Disable automatic synchronization with Snippen",
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
    run_parser.add_argument(
        "--provider-url",
        type=str,
        default=None,
        help="SMS HTTP provider base URL",
    )
    run_parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="Snippen API endpoint base URL",
    )
    run_parser.add_argument(
        "--api-token",
        type=str,
        default=None,
        help="Snippen API Bearer/Auth token",
    )
    run_parser.add_argument(
        "--sync-interval",
        type=float,
        default=None,
        help="Snippen synchronization interval in seconds",
    )
    run_parser.add_argument(
        "--no-sync",
        action="store_true",
        help="Disable automatic synchronization with Snippen",
    )

    # Send subcommand
    send_parser = subparsers.add_parser(
        "send",
        help="Directly send an SMS message via configured provider",
    )
    send_parser.add_argument(
        "--to",
        type=str,
        required=True,
        help="Destination phone number",
    )
    send_parser.add_argument(
        "--message",
        "--text",
        dest="message",
        type=str,
        required=True,
        help="Text content of the SMS message",
    )
    send_parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="SMS provider implementation to use",
    )
    send_parser.add_argument(
        "--provider-url",
        type=str,
        default=None,
        help="SMS provider base URL",
    )
    send_parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path (default: data/sms_gateway.db)",
    )

    # Sync subcommand
    sync_parser = subparsers.add_parser(
        "sync",
        help="Execute a one-time synchronization cycle with Snippen",
    )
    sync_parser.add_argument(
        "--api-url",
        type=str,
        default=None,
        help="Snippen API endpoint base URL (default: SNIPPEN_SMS_API_URL)",
    )
    sync_parser.add_argument(
        "--api-token",
        type=str,
        default=None,
        help="Snippen API Bearer/Auth token (default: SNIPPEN_SMS_API_TOKEN)",
    )
    sync_parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path (default: data/sms_gateway.db)",
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

    # Check update subcommand
    check_update_parser = subparsers.add_parser(
        "check-update",
        help="Check GitHub Releases for available software updates",
    )
    check_update_parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="GitHub repository (default: jonasfh/snippen-sms-service)",
    )

    # Update subcommand
    update_parser = subparsers.add_parser(
        "update",
        help="Download latest GitHub release artifact and upgrade software",
    )
    update_parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="GitHub repository (default: jonasfh/snippen-sms-service)",
    )
    update_parser.add_argument(
        "--force",
        action="store_true",
        help="Force reinstallation even if already at latest version",
    )
    update_parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path to apply migrations to post-upgrade",
    )

    # Status subcommand
    status_parser = subparsers.add_parser(
        "status",
        help="Show gateway service status and database health",
    )
    status_parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path (default: data/sms_gateway.db)",
    )
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output status report in JSON format",
    )

    # Health subcommand (alias for status)
    health_parser = subparsers.add_parser(
        "health",
        help="Check gateway service health (alias for status)",
    )
    health_parser.add_argument(
        "--database-path",
        type=str,
        default="data/sms_gateway.db",
        help="Database file path (default: data/sms_gateway.db)",
    )
    health_parser.add_argument(
        "--json",
        action="store_true",
        help="Output health report in JSON format",
    )

    return parser


def main_cli() -> None:
    """Command-line entry point."""
    parser = build_parser()
    args = parser.parse_args()

    log_level = getattr(args, "log_level", "INFO") or "INFO"
    setup_logging(log_level)

    env_config = GatewayConfig.from_env()

    if args.command == "send":
        sys.exit(
            handle_send(
                recipient=args.to,
                body=args.message,
                provider_name=getattr(args, "provider", None),
                provider_url=getattr(args, "provider_url", None),
                database_path=getattr(args, "database_path", env_config.database_path),
            )
        )
    elif args.command == "sync":
        api_url = getattr(args, "api_url", None) or env_config.snippen_api_url
        api_token = getattr(args, "api_token", None) or env_config.snippen_api_token
        db_path = getattr(args, "database_path", env_config.database_path)
        sys.exit(handle_sync(api_url=api_url, api_token=api_token, database_path=db_path))
    elif args.command == "migrate":
        sys.exit(handle_migrate(args.database_path, getattr(args, "target_version", None)))
    elif args.command == "migrate-status":
        sys.exit(handle_migrate_status(args.database_path))
    elif args.command == "check-update":
        repo = getattr(args, "repo", None) or env_config.github_repo
        sys.exit(handle_check_update(repo=repo, token=env_config.github_token))
    elif args.command == "update":
        repo = getattr(args, "repo", None) or env_config.github_repo
        db_path = getattr(args, "database_path", env_config.database_path)
        sys.exit(
            handle_update(
                repo=repo,
                token=env_config.github_token,
                force=getattr(args, "force", False),
                database_path=db_path,
            )
        )
    elif args.command in ("status", "health"):
        db_path = getattr(args, "database_path", env_config.database_path)
        json_out = getattr(args, "json", False)
        sys.exit(handle_status(database_path=db_path, json_output=json_out))
    else:
        # Default action: run gateway service
        db_path = getattr(args, "database_path", "data/sms_gateway.db")
        poll_interval = getattr(args, "poll_interval", 2.0)
        provider_arg = getattr(args, "provider", None)
        provider_url_arg = getattr(args, "provider_url", None)
        api_url = getattr(args, "api_url", None) or env_config.snippen_api_url
        api_token = getattr(args, "api_token", None) or env_config.snippen_api_token
        sync_interval = getattr(args, "sync_interval", None)
        if sync_interval is None:
            sync_interval = env_config.sync_interval_seconds
        no_sync = getattr(args, "no_sync", False)
        sync_enabled = not no_sync and env_config.sync_enabled

        config = GatewayConfig(
            service_name=env_config.service_name,
            log_level=log_level,
            poll_interval_seconds=poll_interval,
            database_path=db_path,
            provider=provider_arg or env_config.provider,
            provider_url=provider_url_arg or env_config.provider_url,
            github_repo=env_config.github_repo,
            check_updates_on_startup=env_config.check_updates_on_startup,
            auto_update_check=env_config.auto_update_check,
            update_check_interval_seconds=env_config.update_check_interval_seconds,
            github_token=env_config.github_token,
            snippen_api_url=api_url,
            snippen_api_token=api_token,
            sync_interval_seconds=sync_interval,
            sync_timeout_seconds=env_config.sync_timeout_seconds,
            sync_enabled=sync_enabled,
        )

        try:
            asyncio.run(run_gateway(config))
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received. Exiting cleanly.")
            sys.exit(0)


if __name__ == "__main__":
    main_cli()
