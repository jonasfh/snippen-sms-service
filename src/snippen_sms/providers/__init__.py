"""SMS Provider abstraction interfaces and implementations."""

from __future__ import annotations

from snippen_sms.providers.base import IncomingMessage, SendResult, SmsProvider
from snippen_sms.providers.memory import InMemorySmsProvider, SentRecord

__all__ = [
    "InMemorySmsProvider",
    "IncomingMessage",
    "SendResult",
    "SentRecord",
    "SmsProvider",
]
