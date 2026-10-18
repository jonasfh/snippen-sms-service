"""Unit tests for firmware/rate_limiter.py (Issue #31)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = REPO_ROOT / "firmware"
if str(FIRMWARE_DIR) not in sys.path:
    sys.path.insert(0, str(FIRMWARE_DIR))

import rate_limiter


def test_rate_limiter_allow_under_limits() -> None:
    """Verify that messages within burst and hourly limits are allowed."""
    limiter = rate_limiter.SmsRateLimiter(
        enabled=True,
        max_burst=3,
        burst_window_sec=10,
        max_hourly=5,
        hourly_window_sec=60,
    )

    t0 = time.time()
    can_send, reason = limiter.can_send(t0)
    assert can_send is True
    assert reason == ""

    limiter.record_send(t0)
    limiter.record_send(t0 + 1.0)

    can_send, reason = limiter.can_send(t0 + 2.0)
    assert can_send is True


def test_rate_limiter_burst_limit_trips_circuit_breaker() -> None:
    """Verify that exceeding burst threshold trips the circuit breaker."""
    limiter = rate_limiter.SmsRateLimiter(
        enabled=True,
        max_burst=2,
        burst_window_sec=10,
        max_hourly=10,
        hourly_window_sec=60,
        cooloff_sec=30,
    )

    t0 = time.time()
    limiter.record_send(t0)
    limiter.record_send(t0 + 2.0)

    # 3rd message exceeds max_burst=2 within 10s
    can_send, reason = limiter.can_send(t0 + 3.0)
    assert can_send is False
    assert "Burst rate limit reached" in reason
    assert limiter.is_circuit_open is True


def test_rate_limiter_hourly_limit_trips_circuit_breaker() -> None:
    """Verify that exceeding hourly threshold trips the circuit breaker."""
    limiter = rate_limiter.SmsRateLimiter(
        enabled=True,
        max_burst=10,  # High burst limit
        burst_window_sec=10,
        max_hourly=3,
        hourly_window_sec=3600,
        cooloff_sec=60,
    )

    t0 = time.time()
    # Spread over time so burst is not exceeded
    limiter.record_send(t0)
    limiter.record_send(t0 + 50.0)
    limiter.record_send(t0 + 100.0)

    can_send, reason = limiter.can_send(t0 + 150.0)
    assert can_send is False
    assert "Hourly rate limit reached" in reason
    assert limiter.is_circuit_open is True


def test_rate_limiter_cooloff_recovery() -> None:
    """Verify that circuit breaker closes after cooloff period expires."""
    limiter = rate_limiter.SmsRateLimiter(
        enabled=True,
        max_burst=1,
        burst_window_sec=10,
        cooloff_sec=5,
    )

    t0 = time.time()
    limiter.record_send(t0)
    can_send, _ = limiter.can_send(t0 + 1.0)
    assert can_send is False
    assert limiter.is_circuit_open is True

    # Advance beyond cooloff and burst window
    t1 = t0 + 15.0
    can_send, reason = limiter.can_send(t1)
    assert can_send is True
    assert reason == ""
    assert limiter.is_circuit_open is False


def test_rate_limiter_manual_reset() -> None:
    """Verify that deliberate reset restores sending immediately."""
    limiter = rate_limiter.SmsRateLimiter(
        enabled=True,
        max_burst=1,
        burst_window_sec=100,
        cooloff_sec=500,
    )

    t0 = time.time()
    limiter.record_send(t0)
    can_send, _ = limiter.can_send(t0 + 1.0)
    assert can_send is False
    assert limiter.is_circuit_open is True

    # Manually reset
    limiter.reset()

    assert limiter.is_circuit_open is False
    assert len(limiter.history) == 0
    can_send, reason = limiter.can_send(t0 + 2.0)
    assert can_send is True
    assert reason == ""


def test_rate_limiter_disabled() -> None:
    """Verify that disabled rate limiter allows any amount of sends."""
    limiter = rate_limiter.SmsRateLimiter(
        enabled=False,
        max_burst=1,
        burst_window_sec=100,
    )

    t0 = time.time()
    for i in range(100):
        limiter.record_send(t0 + float(i))

    can_send, reason = limiter.can_send(t0 + 101.0)
    assert can_send is True
    assert reason == ""
    assert limiter.is_circuit_open is False
