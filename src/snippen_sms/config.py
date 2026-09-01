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
    provider_url: str | None = None
    provider_timeout_seconds: float = 10.0
    github_repo: str = "jonasfh/snippen-sms-service"
    check_updates_on_startup: bool = True
    auto_update_check: bool = True
    update_check_interval_seconds: float = 86400.0
    github_token: str | None = None
    snippen_api_url: str | None = None
    snippen_api_token: str | None = None
    sync_interval_seconds: float = 5.0
    sync_timeout_seconds: float = 10.0
    sync_enabled: bool = True
    booking_resolution_enabled: bool = True
    conversation_ttl_seconds: float = 7200.0

    @classmethod
    def from_env(cls) -> GatewayConfig:
        """Create configuration from environment variables."""
        check_startup_env = (
            os.getenv("SNIPPEN_SMS_CHECK_UPDATES_ON_STARTUP", "true").strip().lower()
        )
        auto_check_env = os.getenv("SNIPPEN_SMS_AUTO_UPDATE_CHECK", "true").strip().lower()
        sync_enabled_env = os.getenv("SNIPPEN_SMS_SYNC_ENABLED", "true").strip().lower()
        booking_res_env = (
            os.getenv("SNIPPEN_SMS_BOOKING_RESOLUTION_ENABLED", "true").strip().lower()
        )

        api_url = os.getenv("SNIPPEN_SMS_API_URL") or os.getenv("SNIPPEN_API_URL")
        api_token = os.getenv("SNIPPEN_SMS_API_TOKEN") or os.getenv("SNIPPEN_API_TOKEN")

        return cls(
            service_name=os.getenv("SNIPPEN_SMS_SERVICE_NAME", "snippen-sms-service"),
            log_level=os.getenv("SNIPPEN_SMS_LOG_LEVEL", "INFO").upper(),
            poll_interval_seconds=float(os.getenv("SNIPPEN_SMS_POLL_INTERVAL", "2.0")),
            database_path=os.getenv("SNIPPEN_SMS_DATABASE_PATH", "data/sms_gateway.db"),
            provider=os.getenv("SNIPPEN_SMS_PROVIDER", "mock"),
            provider_url=os.getenv("SNIPPEN_SMS_PROVIDER_URL"),
            provider_timeout_seconds=float(os.getenv("SNIPPEN_SMS_PROVIDER_TIMEOUT", "10.0")),
            github_repo=os.getenv("SNIPPEN_SMS_GITHUB_REPO", "jonasfh/snippen-sms-service"),
            check_updates_on_startup=check_startup_env in ("true", "1", "yes"),
            auto_update_check=auto_check_env in ("true", "1", "yes"),
            update_check_interval_seconds=float(
                os.getenv("SNIPPEN_SMS_UPDATE_CHECK_INTERVAL", "86400.0")
            ),
            github_token=os.getenv("SNIPPEN_SMS_GITHUB_TOKEN"),
            snippen_api_url=api_url,
            snippen_api_token=api_token,
            sync_interval_seconds=float(os.getenv("SNIPPEN_SMS_SYNC_INTERVAL", "5.0")),
            sync_timeout_seconds=float(os.getenv("SNIPPEN_SMS_SYNC_TIMEOUT", "10.0")),
            sync_enabled=sync_enabled_env in ("true", "1", "yes"),
            booking_resolution_enabled=booking_res_env in ("true", "1", "yes"),
            conversation_ttl_seconds=float(
                os.getenv("SNIPPEN_SMS_CONVERSATION_TTL_SECONDS", "7200.0")
            ),
        )
