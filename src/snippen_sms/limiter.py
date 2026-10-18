"""Rate limiting and circuit breaker protection for outgoing SMS (Issue #31)."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger("snippen_sms.limiter")


class RateLimiter:
    """Sliding-window rate limiter and circuit breaker for SMS dispatch.

    Protects service from accidental loops or excessive outbound messaging floods.
    Configurable burst limits, hourly limits, and circuit breaker cooloff periods.
    """

    def __init__(
        self,
        enabled: bool = True,
        max_burst: int = 10,
        burst_window_seconds: float = 300.0,
        max_hourly: int = 30,
        hourly_window_seconds: float = 3600.0,
        cooloff_seconds: float = 600.0,
    ) -> None:
        self.enabled = enabled
        self.max_burst = max_burst
        self.burst_window_seconds = burst_window_seconds
        self.max_hourly = max_hourly
        self.hourly_window_seconds = hourly_window_seconds
        self.cooloff_seconds = cooloff_seconds

        self.history: list[float] = []
        self.circuit_open_until: float = 0.0
        self.last_trip_reason: str = ""

    @property
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is currently open."""
        if not self.enabled:
            return False
        return self.circuit_open_until > time.time()

    def can_send(self, current_time: float | None = None) -> tuple[bool, str]:
        """Check if message dispatch is allowed under current rate limits.

        Returns:
            Tuple of (allowed: bool, reason: str).
        """
        if not self.enabled:
            return True, ""

        now = current_time if current_time is not None else time.time()

        # 1. Check circuit breaker status
        if self.circuit_open_until > now:
            remaining = int(self.circuit_open_until - now)
            return (
                False,
                f"Circuit breaker active ({self.last_trip_reason}). Cooling off for {remaining}s.",
            )

        if self.circuit_open_until > 0.0:
            # Cooloff period has expired; reset circuit breaker
            self.circuit_open_until = 0.0
            self.last_trip_reason = ""

        # 2. Prune old history
        cutoff = now - self.hourly_window_seconds
        self.history = [t for t in self.history if t >= cutoff]

        # 3. Check burst window
        burst_cutoff = now - self.burst_window_seconds
        burst_count = sum(1 for t in self.history if t >= burst_cutoff)
        if burst_count >= self.max_burst:
            self._trip(
                now,
                f"Burst limit exceeded ({burst_count}/{self.max_burst} in {self.burst_window_seconds}s)",
            )
            return (
                False,
                f"Burst rate limit reached ({burst_count} SMS in {self.burst_window_seconds}s). Circuit tripped for {self.cooloff_seconds}s.",
            )

        # 4. Check hourly window
        hourly_count = len(self.history)
        if hourly_count >= self.max_hourly:
            self._trip(
                now,
                f"Hourly limit exceeded ({hourly_count}/{self.max_hourly} in {self.hourly_window_seconds}s)",
            )
            return (
                False,
                f"Hourly rate limit reached ({hourly_count} SMS in {self.hourly_window_seconds}s). Circuit tripped for {self.cooloff_seconds}s.",
            )

        return True, ""

    def record_send(self, timestamp: float | None = None) -> None:
        """Record successful SMS dispatch timestamp."""
        ts = timestamp if timestamp is not None else time.time()
        self.history.append(ts)
        if len(self.history) > (self.max_hourly * 2):
            self.history = self.history[-self.max_hourly :]

    def reset(self) -> None:
        """Manually reset the circuit breaker and history to restore normal operation."""
        self.history.clear()
        self.circuit_open_until = 0.0
        self.last_trip_reason = ""
        logger.info("Rate limiter circuit breaker manually reset to normal operation.")

    def _trip(self, now: float, reason: str) -> None:
        self.circuit_open_until = now + self.cooloff_seconds
        self.last_trip_reason = reason
        logger.warning(
            "Rate limit circuit breaker TRIPPED: %s. Outbound SMS suspended for %ss.",
            reason,
            self.cooloff_seconds,
        )
