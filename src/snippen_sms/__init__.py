"""Snippen SMS Service package."""

from __future__ import annotations

from snippen_sms.config import GatewayConfig
from snippen_sms.gateway import GatewayService

__version__ = "0.2.0"

__all__ = ["GatewayConfig", "GatewayService", "__version__"]
