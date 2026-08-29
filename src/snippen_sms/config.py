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

    @classmethod
    def from_env(cls) -> GatewayConfig:
        """Create configuration from environment variables."""
        return cls(
            service_name=os.getenv("SNIPPEN_SMS_SERVICE_NAME", "snippen-sms-service"),
            log_level=os.getenv("SNIPPEN_SMS_LOG_LEVEL", "INFO").upper(),
            poll_interval_seconds=float(os.getenv("SNIPPEN_SMS_POLL_INTERVAL", "2.0")),
            database_path=os.getenv("SNIPPEN_SMS_DATABASE_PATH", "data/sms_gateway.db"),
        )
