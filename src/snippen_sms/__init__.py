"""Snippen SMS Service package."""

from __future__ import annotations

__version__ = "0.12.0"

from snippen_sms.client import (
    SnippenApiError,
    SnippenAuthError,
    SnippenClient,
    SnippenClientError,
    SnippenNetworkError,
)
from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService
from snippen_sms.migrations import Migration, MigrationError, MigrationRunner
from snippen_sms.models import Message, MessageDirection, MessageStatus
from snippen_sms.providers import (
    IncomingMessage,
    InMemorySmsProvider,
    MockSMSProvider,
    MockSmsProvider,
    SendResult,
    SmsProvider,
    get_provider,
    register_provider,
)
from snippen_sms.storage import MessageStorage
from snippen_sms.sync import SyncService
from snippen_sms.updater import (
    ReleaseInfo,
    SoftwareUpdater,
    UpdateCheckResult,
    calculate_sha256,
    parse_checksums_file,
)

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
    "MockSMSProvider",
    "MockSmsProvider",
    "ReleaseInfo",
    "SendResult",
    "SmsProvider",
    "SnippenApiError",
    "SnippenAuthError",
    "SnippenClient",
    "SnippenClientError",
    "SnippenNetworkError",
    "SoftwareUpdater",
    "SyncService",
    "UpdateCheckResult",
    "__version__",
    "calculate_sha256",
    "get_provider",
    "parse_checksums_file",
    "register_provider",
]
