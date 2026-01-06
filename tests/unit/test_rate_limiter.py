"""Tests for rate limiter."""

import time

import pytest

from routeros_mcp.infra.rate_limiter import RateLimiter, get_rate_limiter, reset_rate_limiter
from routeros_mcp.mcp.errors import RateLimitExceededError


@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit() -> None:
    """Test rate limiter allows operations within limit."""
    limiter = RateLimiter()

    # Should allow 10 operations
    for _i in range(10):
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)

    # 10 operations recorded
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=60) == 0


@pytest.mark.asyncio
async def test_rate_limiter_blocks_over_limit() -> None:
    """Test rate limiter blocks operations over limit."""
    limiter = RateLimiter()

    # Fill up to limit
    for _i in range(10):
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)

    # 11th operation should raise error
    with pytest.raises(RateLimitExceededError) as exc_info:
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)

    assert "Rate limit exceeded" in str(exc_info.value)
    assert "dev-001" in str(exc_info.value)
    assert exc_info.value.data["device_id"] == "dev-001"
    assert exc_info.value.data["operation"] == "ping"
    assert exc_info.value.data["limit"] == 10


@pytest.mark.asyncio
async def test_rate_limiter_sliding_window() -> None:
    """Test rate limiter uses sliding window (old records expire)."""
    limiter = RateLimiter()

    # Fill up to limit
    for _i in range(10):
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=1)

    # Should be blocked immediately
    with pytest.raises(RateLimitExceededError):
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=1)

    # Wait for window to expire
    time.sleep(1.1)

    # Should allow operations again
    await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=1)
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=1) == 9


@pytest.mark.asyncio
async def test_rate_limiter_per_device_isolation() -> None:
    """Test rate limiter tracks devices independently."""
    limiter = RateLimiter()

    # Fill limit for dev-001
    for _i in range(10):
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)

    # dev-002 should still be allowed
    await limiter.check_and_record("dev-002", "ping", limit=10, window_seconds=60)
    assert await limiter.get_remaining("dev-002", "ping", limit=10, window_seconds=60) == 9


@pytest.mark.asyncio
async def test_rate_limiter_per_operation_isolation() -> None:
    """Test rate limiter tracks operations independently."""
    limiter = RateLimiter()

    # Fill limit for ping
    for _i in range(10):
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)

    # traceroute should still be allowed
    await limiter.check_and_record("dev-001", "traceroute", limit=10, window_seconds=60)
    assert await limiter.get_remaining("dev-001", "traceroute", limit=10, window_seconds=60) == 9


@pytest.mark.asyncio
async def test_rate_limiter_reset_all() -> None:
    """Test resetting all rate limit records."""
    limiter = RateLimiter()

    # Record operations
    await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)
    await limiter.check_and_record("dev-002", "traceroute", limit=10, window_seconds=60)

    # Reset all
    limiter.reset()

    # Should have full quota again
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=60) == 10
    assert await limiter.get_remaining("dev-002", "traceroute", limit=10, window_seconds=60) == 10


@pytest.mark.asyncio
async def test_rate_limiter_reset_device() -> None:
    """Test resetting rate limits for specific device."""
    limiter = RateLimiter()

    # Record operations for multiple devices
    await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)
    await limiter.check_and_record("dev-002", "ping", limit=10, window_seconds=60)

    # Reset only dev-001
    limiter.reset(device_id="dev-001")

    # dev-001 should have full quota, dev-002 should still have 1 used
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=60) == 10
    assert await limiter.get_remaining("dev-002", "ping", limit=10, window_seconds=60) == 9


@pytest.mark.asyncio
async def test_rate_limiter_reset_operation() -> None:
    """Test resetting rate limits for specific operation."""
    limiter = RateLimiter()

    # Record operations
    await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)
    await limiter.check_and_record("dev-001", "traceroute", limit=10, window_seconds=60)

    # Reset only ping
    limiter.reset(operation="ping")

    # ping should have full quota, traceroute should still have 1 used
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=60) == 10
    assert await limiter.get_remaining("dev-001", "traceroute", limit=10, window_seconds=60) == 9


@pytest.mark.asyncio
async def test_rate_limiter_reset_device_and_operation() -> None:
    """Test resetting rate limits for specific device and operation."""
    limiter = RateLimiter()

    # Record operations
    await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)
    await limiter.check_and_record("dev-001", "traceroute", limit=10, window_seconds=60)
    await limiter.check_and_record("dev-002", "ping", limit=10, window_seconds=60)

    # Reset only dev-001 ping
    limiter.reset(device_id="dev-001", operation="ping")

    # Only dev-001 ping should be reset
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=60) == 10
    assert await limiter.get_remaining("dev-001", "traceroute", limit=10, window_seconds=60) == 9
    assert await limiter.get_remaining("dev-002", "ping", limit=10, window_seconds=60) == 9


def test_get_rate_limiter_singleton() -> None:
    """Test global rate limiter is singleton."""
    limiter1 = get_rate_limiter()
    limiter2 = get_rate_limiter()

    assert limiter1 is limiter2


@pytest.mark.asyncio
async def test_reset_rate_limiter_global() -> None:
    """Test resetting global rate limiter."""
    limiter = get_rate_limiter()
    await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)

    # Reset global
    reset_rate_limiter()

    # Should have full quota
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=60) == 10


@pytest.mark.asyncio
async def test_rate_limiter_get_remaining_accuracy() -> None:
    """Test get_remaining returns accurate count."""
    limiter = RateLimiter()

    # Start with full quota
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=60) == 10

    # Use 3 operations
    for _i in range(3):
        await limiter.check_and_record("dev-001", "ping", limit=10, window_seconds=60)

    # Should have 7 remaining
    assert await limiter.get_remaining("dev-001", "ping", limit=10, window_seconds=60) == 7
