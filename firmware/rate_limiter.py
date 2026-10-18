"""Rate limiting and circuit breaker protection for outgoing SMS (Issue #31)."""

try:
    import utime as time
except ImportError:
    import time


class SmsRateLimiter:
    """Sliding-window rate limiter and circuit breaker for cellular SMS dispatch.

    Enforces:
    1. Short-term burst limit (e.g. max 10 messages within 300 seconds).
    2. Hourly limit (e.g. max 30 messages within 3600 seconds).
    3. Circuit breaker that suspends dispatch when thresholds are breached,
       recovering automatically after a cooloff period or via manual reset.
    """

    def __init__(
        self,
        enabled: bool = True,
        max_burst: int = 10,
        burst_window_sec: int = 300,
        max_hourly: int = 30,
        hourly_window_sec: int = 3600,
        cooloff_sec: int = 600,
    ) -> None:
        self.enabled = enabled
        self.max_burst = max_burst
        self.burst_window_sec = burst_window_sec
        self.max_hourly = max_hourly
        self.hourly_window_sec = hourly_window_sec
        self.cooloff_sec = cooloff_sec

        self.history: list[float] = []
        self.circuit_open_until: float = 0.0
        self.last_trip_reason: str = ""

    @property
    def is_circuit_open(self) -> bool:
        """Check if circuit breaker is currently open (blocking sends)."""
        if not self.enabled:
            return False
        return self.circuit_open_until > time.time()

    def can_send(self, current_time: float | None = None) -> tuple[bool, str]:
        """Evaluate if an SMS can be transmitted under current rate limits.

        Args:
            current_time: Optional current timestamp (defaults to time.time()).

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
            # Cooloff period has expired; automatically close circuit breaker
            self.circuit_open_until = 0.0
            self.last_trip_reason = ""

        # 2. Prune history older than the longest window
        cutoff = now - self.hourly_window_sec
        self.history = [t for t in self.history if t >= cutoff]

        # 3. Check short-term burst window
        burst_cutoff = now - self.burst_window_sec
        burst_count = sum(1 for t in self.history if t >= burst_cutoff)
        if burst_count >= self.max_burst:
            self._trip(
                now,
                f"Burst limit exceeded ({burst_count}/{self.max_burst} in {self.burst_window_sec}s)",
            )
            return (
                False,
                f"Burst rate limit reached ({burst_count} SMS in {self.burst_window_sec}s). Circuit tripped for {self.cooloff_sec}s.",
            )

        # 4. Check hourly window
        hourly_count = len(self.history)
        if hourly_count >= self.max_hourly:
            self._trip(
                now,
                f"Hourly limit exceeded ({hourly_count}/{self.max_hourly} in {self.hourly_window_sec}s)",
            )
            return (
                False,
                f"Hourly rate limit reached ({hourly_count} SMS in {self.hourly_window_sec}s). Circuit tripped for {self.cooloff_sec}s.",
            )

        return True, ""

    def record_send(self, timestamp: float | None = None) -> None:
        """Record successful transmission timestamp."""
        ts = timestamp if timestamp is not None else time.time()
        self.history.append(ts)
        # Bounded retention
        if len(self.history) > (self.max_hourly * 2):
            self.history = self.history[-self.max_hourly :]

    def reset(self) -> None:
        """Deliberately restore normal operation and reset circuit breaker and history."""
        self.history = []
        self.circuit_open_until = 0.0
        self.last_trip_reason = ""

    def _trip(self, now: float, reason: str) -> None:
        """Open the circuit breaker."""
        self.circuit_open_until = now + self.cooloff_sec
        self.last_trip_reason = reason
