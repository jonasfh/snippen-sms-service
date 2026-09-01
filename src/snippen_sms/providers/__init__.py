"""SMS Provider abstraction interfaces and implementations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from snippen_sms.providers.base import IncomingMessage, SendResult, SmsProvider
from snippen_sms.providers.http import HttpSmsProvider
from snippen_sms.providers.memory import InMemorySmsProvider
from snippen_sms.providers.mock import AutoReplyRule, MockSMSProvider, MockSmsProvider, SentRecord

PROVIDER_REGISTRY: dict[str, type[SmsProvider] | Callable[..., SmsProvider]] = {
    "mock": MockSmsProvider,
    "memory": InMemorySmsProvider,
    "in_memory": InMemorySmsProvider,
    "inmemory": InMemorySmsProvider,
    "http": HttpSmsProvider,
    "fake": HttpSmsProvider,
    "snippen-testing": HttpSmsProvider,
}


def get_provider(name: str = "mock", **kwargs: Any) -> SmsProvider:
    """Retrieve and instantiate an SMS provider by name.

    Args:
        name: Name of the provider ('mock', 'memory', 'http', 'fake', etc.).
        **kwargs: Optional configuration arguments passed to the provider constructor.

    Returns:
        An instantiated SmsProvider instance.

    Raises:
        ValueError: If provider name is not found in registry.
    """
    normalized_name = name.strip().lower()
    provider_cls = PROVIDER_REGISTRY.get(normalized_name)
    if provider_cls is None:
        valid_providers = ", ".join(sorted(PROVIDER_REGISTRY.keys()))
        raise ValueError(f"Unknown SMS provider '{name}'. Valid providers are: {valid_providers}")

    # Pass kwargs if provided and accepted, otherwise instantiate without arguments
    if kwargs:
        try:
            return provider_cls(**kwargs)
        except TypeError:
            pass
    return provider_cls()


def register_provider(
    name: str,
    provider_cls: type[SmsProvider] | Callable[..., SmsProvider],
) -> None:
    """Register a custom SMS provider class or factory in the provider registry.

    Args:
        name: Unique identifier for the provider.
        provider_cls: SmsProvider subclass or factory function.
    """
    PROVIDER_REGISTRY[name.strip().lower()] = provider_cls


__all__ = [
    "AutoReplyRule",
    "HttpSmsProvider",
    "InMemorySmsProvider",
    "IncomingMessage",
    "MockSMSProvider",
    "MockSmsProvider",
    "SendResult",
    "SentRecord",
    "SmsProvider",
    "get_provider",
    "register_provider",
]
