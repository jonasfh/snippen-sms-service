"""Unit tests for src/snippen_sms/limiter.py (Issue #31)."""

from __future__ import annotations

import time

from snippen_sms.limiter import RateLimiter


def test_rate_limiter_allows_under_limits() -> None:
    """Verify that messages within limits are permitted."""
    limiter = RateLimiter(
        enabled=True,
        max_burst=3,
        burst_window_seconds=10.0,
        max_hourly=5,
        hourly_window_seconds=60.0,
    )

    t0 = time.time()
    can_send, reason = limiter.can_send(t0)
    assert can_send is True
    assert reason == ""

    limiter.record_send(t0)
    limiter.record_send(t0 + 1.0)

    can_send, _ = limiter.can_send(t0 + 2.0)
    assert can_send is True


def test_rate_limiter_burst_limit_trips() -> None:
    """Verify that exceeding burst threshold trips the circuit breaker."""
    limiter = RateLimiter(
        enabled=True,
        max_burst=2,
        burst_window_seconds=10.0,
        cooloff_seconds=30.0,
    )

    t0 = time.time()
    limiter.record_send(t0)
    limiter.record_send(t0 + 2.0)

    can_send, reason = limiter.can_send(t0 + 3.0)
    assert can_send is False
    assert "Burst rate limit reached" in reason
    assert limiter.is_circuit_open is True


def test_rate_limiter_hourly_limit_trips() -> None:
    """Verify that exceeding hourly threshold trips the circuit breaker."""
    limiter = RateLimiter(
        enabled=True,
        max_burst=10,
        burst_window_seconds=10.0,
        max_hourly=3,
        hourly_window_seconds=3600.0,
        cooloff_seconds=60.0,
    )

    t0 = time.time()
    limiter.record_send(t0)
    limiter.record_send(t0 + 50.0)
    limiter.record_send(t0 + 100.0)

    can_send, reason = limiter.can_send(t0 + 150.0)
    assert can_send is False
    assert "Hourly rate limit reached" in reason
    assert limiter.is_circuit_open is True


def test_rate_limiter_cooloff_recovery() -> None:
    """Verify circuit breaker automatically resets after cooloff."""
    limiter = RateLimiter(
        enabled=True,
        max_burst=1,
        burst_window_seconds=10.0,
        cooloff_seconds=5.0,
    )

    t0 = time.time()
    limiter.record_send(t0)

    can_send, _ = limiter.can_send(t0 + 1.0)
    assert can_send is False
    assert limiter.is_circuit_open is True

    # Advance time past cooloff and burst window
    t1 = t0 + 15.0
    can_send, reason = limiter.can_send(t1)
    assert can_send is True
    assert reason == ""
    assert limiter.is_circuit_open is False


def test_rate_limiter_manual_reset() -> None:
    """Verify deliberate manual reset restores sending immediately."""
    limiter = RateLimiter(
        enabled=True,
        max_burst=1,
        burst_window_seconds=100.0,
        cooloff_seconds=500.0,
    )

    t0 = time.time()
    limiter.record_send(t0)
    can_send, _ = limiter.can_send(t0 + 1.0)
    assert can_send is False
    assert limiter.is_circuit_open is True

    limiter.reset()

    assert limiter.is_circuit_open is False
    can_send, reason = limiter.can_send(t0 + 2.0)
    assert can_send is True
    assert reason == ""


def test_rate_limiter_disabled() -> None:
    """Verify disabled rate limiter allows all sends."""
    limiter = RateLimiter(enabled=False, max_burst=1)

    t0 = time.time()
    for i in range(50):
        limiter.record_send(t0 + float(i))

    can_send, _ = limiter.can_send(t0 + 60.0)
    assert can_send is True
    assert limiter.is_circuit_open is False
