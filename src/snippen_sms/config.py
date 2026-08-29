"""Configuration settings for Snippen SMS Service."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class GatewayConfig:
    """Gateway service configuration settings."""

    service_name: str = "snippen-sms-service"
    log_level: str = "INFO"
    poll_interval_seconds: float = 2.0
    database_path: str = "data/sms_gateway.db"
    provider: str = "mock"
    github_repo: str = "jonasfh/snippen-sms-service"
    check_updates_on_startup: bool = True
    auto_update_check: bool = True
    update_check_interval_seconds: float = 86400.0
    github_token: str | None = None

    @classmethod
    def from_env(cls) -> GatewayConfig:
        """Create configuration from environment variables."""
        check_startup_env = (
            os.getenv("SNIPPEN_SMS_CHECK_UPDATES_ON_STARTUP", "true").strip().lower()
        )
        auto_check_env = os.getenv("SNIPPEN_SMS_AUTO_UPDATE_CHECK", "true").strip().lower()

        return cls(
            service_name=os.getenv("SNIPPEN_SMS_SERVICE_NAME", "snippen-sms-service"),
            log_level=os.getenv("SNIPPEN_SMS_LOG_LEVEL", "INFO").upper(),
            poll_interval_seconds=float(os.getenv("SNIPPEN_SMS_POLL_INTERVAL", "2.0")),
            database_path=os.getenv("SNIPPEN_SMS_DATABASE_PATH", "data/sms_gateway.db"),
            provider=os.getenv("SNIPPEN_SMS_PROVIDER", "mock"),
            github_repo=os.getenv("SNIPPEN_SMS_GITHUB_REPO", "jonasfh/snippen-sms-service"),
            check_updates_on_startup=check_startup_env in ("true", "1", "yes"),
            auto_update_check=auto_check_env in ("true", "1", "yes"),
            update_check_interval_seconds=float(
                os.getenv("SNIPPEN_SMS_UPDATE_CHECK_INTERVAL", "86400.0")
            ),
            github_token=os.getenv("SNIPPEN_SMS_GITHUB_TOKEN"),
        )
