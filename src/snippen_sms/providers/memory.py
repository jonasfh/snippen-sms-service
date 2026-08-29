"""In-memory SMS provider implementation for testing and offline environments."""

from __future__ import annotations

from snippen_sms.providers.mock import MockSmsProvider, SentRecord


class InMemorySmsProvider(MockSmsProvider):
    """In-memory SMS provider for automated testing and hardware-agnostic simulation.

    Subclasses MockSmsProvider for backwards compatibility with tests and callers.
    """

    def __init__(self, id_prefix: str = "mem") -> None:
        super().__init__(id_prefix=id_prefix)


__all__ = [
    "InMemorySmsProvider",
    "SentRecord",
]
