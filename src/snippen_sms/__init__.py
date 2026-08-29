"""Snippen SMS Service package."""

from __future__ import annotations

from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService
from snippen_sms.migrations import Migration, MigrationError, MigrationRunner
from snippen_sms.models import Message, MessageDirection, MessageStatus
from snippen_sms.storage import MessageStorage

__version__ = "0.4.0"

__all__ = [
    "GatewayConfig",
    "GatewayService",
    "Message",
    "MessageDirection",
    "MessageStatus",
    "MessageStorage",
    "Migration",
    "MigrationError",
    "MigrationRunner",
    "__version__",
]
