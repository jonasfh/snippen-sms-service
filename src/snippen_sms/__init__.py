"""Snippen SMS Service package."""

from __future__ import annotations

from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService
from snippen_sms.migrations import Migration, MigrationError, MigrationRunner
from snippen_sms.models import Message, MessageDirection, MessageStatus
from snippen_sms.providers import IncomingMessage, InMemorySmsProvider, SendResult, SmsProvider
from snippen_sms.storage import MessageStorage

__version__ = "0.5.0"

__all__ = [
    "GatewayConfig",
    "GatewayService",
    "InMemorySmsProvider",
    "IncomingMessage",
    "Message",
    "MessageDirection",
    "MessageStatus",
    "MessageStorage",
    "Migration",
    "MigrationError",
    "MigrationRunner",
    "SendResult",
    "SmsProvider",
    "__version__",
]
