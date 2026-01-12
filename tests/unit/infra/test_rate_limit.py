"""Tests for Redis-backed rate limiting infrastructure."""

import time

import pytest

from routeros_mcp.infra.rate_limit import (
    InMemoryRateLimitStore,
    RateLimitStore,
    close_rate_limit_store,
    get_rate_limit_store,
    initialize_rate_limit_store,
)
from routeros_mcp.mcp.errors import RateLimitExceededError


@pytest.fixture
async def memory_store():
    """Create in-memory rate limit store for testing."""
    store = InMemoryRateLimitStore(window_seconds=60)
    await store.init()
    yield store
    await store.close()


@pytest.fixture
async def redis_store():
    """Create Redis-backed rate limit store for testing.

    Uses test Redis database (db=15) to avoid interfering with dev data.
    """
    store = RateLimitStore(
        redis_url="redis://localhost:6379/15",
        pool_size=5,
        timeout_seconds=2.0,
        window_seconds=60,
    )
    try:
        await store.init()
        # Clean up test database before test
        await store.reset()
        yield store
    except Exception:
        # Skip Redis tests if Redis not available
        pytest.skip("Redis not available for testing")
    finally:
        if store._initialized:
            await store.reset()
            await store.close()


# ========================================
# In-Memory Store Tests
# ========================================


@pytest.mark.asyncio
async def test_memory_store_allows_within_limit(memory_store):
    """Test in-memory store allows requests within limit."""
    # Should allow 10 requests
    for i in range(10):
        await memory_store.check_and_record("user-123", "read_only", limit=10)

    # All 10 used
    remaining = await memory_store.get_remaining("user-123", "read_only", limit=10)
    assert remaining == 0


@pytest.mark.asyncio
async def test_memory_store_blocks_over_limit(memory_store):
    """Test in-memory store blocks requests over limit."""
    # Fill up to limit
    for i in range(10):
        await memory_store.check_and_record("user-123", "read_only", limit=10)

    # 11th request should raise error
    with pytest.raises(RateLimitExceededError) as exc_info:
        await memory_store.check_and_record("user-123", "read_only", limit=10)

    error = exc_info.value
    assert "Rate limit exceeded" in str(error)
    assert error.data["user_id"] == "user-123"
    assert error.data["role"] == "read_only"
    assert error.data["limit"] == 10
    assert error.data["current_count"] == 10
    assert error.data["retry_after_seconds"] > 0


@pytest.mark.asyncio
async def test_memory_store_unlimited_access(memory_store):
    """Test in-memory store allows unlimited access with limit=0."""
    # Should allow unlimited requests
    for i in range(100):
        await memory_store.check_and_record("user-admin", "admin", limit=0)

    # Should still be unlimited
    remaining = await memory_store.get_remaining("user-admin", "admin", limit=0)
    assert remaining == 999999


@pytest.mark.asyncio
async def test_memory_store_sliding_window(memory_store):
    """Test in-memory store uses sliding window."""
    # Use short window for test
    store = InMemoryRateLimitStore(window_seconds=1)
    await store.init()

    # Fill up to limit
    for i in range(5):
        await store.check_and_record("user-123", "ops_rw", limit=5)

    # Should be blocked
    with pytest.raises(RateLimitExceededError):
        await store.check_and_record("user-123", "ops_rw", limit=5)

    # Wait for window to expire
    time.sleep(1.1)

    # Should allow requests again
    await store.check_and_record("user-123", "ops_rw", limit=5)
    remaining = await store.get_remaining("user-123", "ops_rw", limit=5)
    assert remaining == 4

    await store.close()


@pytest.mark.asyncio
async def test_memory_store_per_user_isolation(memory_store):
    """Test in-memory store tracks users independently."""
    # Fill limit for user-1
    for i in range(10):
        await memory_store.check_and_record("user-1", "read_only", limit=10)

    # user-2 should still be allowed
    await memory_store.check_and_record("user-2", "read_only", limit=10)
    remaining = await memory_store.get_remaining("user-2", "read_only", limit=10)
    assert remaining == 9


@pytest.mark.asyncio
async def test_memory_store_per_role_isolation(memory_store):
    """Test in-memory store tracks roles independently."""
    # Fill limit for read_only
    for i in range(10):
        await memory_store.check_and_record("user-123", "read_only", limit=10)

    # Same user with different role should still be allowed
    await memory_store.check_and_record("user-123", "ops_rw", limit=5)
    remaining = await memory_store.get_remaining("user-123", "ops_rw", limit=5)
    assert remaining == 4


@pytest.mark.asyncio
async def test_memory_store_reset_all(memory_store):
    """Test resetting all rate limit records."""
    await memory_store.check_and_record("user-1", "read_only", limit=10)
    await memory_store.check_and_record("user-2", "ops_rw", limit=5)

    # Reset all
    await memory_store.reset()

    # Should have full quota again
    remaining1 = await memory_store.get_remaining("user-1", "read_only", limit=10)
    remaining2 = await memory_store.get_remaining("user-2", "ops_rw", limit=5)
    assert remaining1 == 10
    assert remaining2 == 5


@pytest.mark.asyncio
async def test_memory_store_reset_user(memory_store):
    """Test resetting rate limits for specific user."""
    await memory_store.check_and_record("user-1", "read_only", limit=10)
    await memory_store.check_and_record("user-2", "read_only", limit=10)

    # Reset only user-1
    await memory_store.reset(user_id="user-1")

    # user-1 should have full quota, user-2 still has 1 used
    remaining1 = await memory_store.get_remaining("user-1", "read_only", limit=10)
    remaining2 = await memory_store.get_remaining("user-2", "read_only", limit=10)
    assert remaining1 == 10
    assert remaining2 == 9


@pytest.mark.asyncio
async def test_memory_store_reset_role(memory_store):
    """Test resetting rate limits for specific role."""
    await memory_store.check_and_record("user-123", "read_only", limit=10)
    await memory_store.check_and_record("user-123", "ops_rw", limit=5)

    # Reset only read_only
    await memory_store.reset(role="read_only")

    # read_only should have full quota, ops_rw still has 1 used
    remaining1 = await memory_store.get_remaining("user-123", "read_only", limit=10)
    remaining2 = await memory_store.get_remaining("user-123", "ops_rw", limit=5)
    assert remaining1 == 10
    assert remaining2 == 4


@pytest.mark.asyncio
async def test_memory_store_reset_user_and_role(memory_store):
    """Test resetting rate limits for specific user and role."""
    await memory_store.check_and_record("user-123", "read_only", limit=10)
    await memory_store.check_and_record("user-123", "ops_rw", limit=5)
    await memory_store.check_and_record("user-456", "read_only", limit=10)

    # Reset only user-123 read_only
    await memory_store.reset(user_id="user-123", role="read_only")

    # Only user-123 read_only should be reset
    remaining1 = await memory_store.get_remaining("user-123", "read_only", limit=10)
    remaining2 = await memory_store.get_remaining("user-123", "ops_rw", limit=5)
    remaining3 = await memory_store.get_remaining("user-456", "read_only", limit=10)
    assert remaining1 == 10
    assert remaining2 == 4
    assert remaining3 == 9


# ========================================
# Redis Store Tests
# ========================================


@pytest.mark.asyncio
async def test_redis_store_allows_within_limit(redis_store):
    """Test Redis store allows requests within limit."""
    # Should allow 10 requests
    for i in range(10):
        await redis_store.check_and_record("user-123", "read_only", limit=10)

    # All 10 used
    remaining = await redis_store.get_remaining("user-123", "read_only", limit=10)
    assert remaining == 0


@pytest.mark.asyncio
async def test_redis_store_blocks_over_limit(redis_store):
    """Test Redis store blocks requests over limit."""
    # Fill up to limit
    for i in range(5):
        await redis_store.check_and_record("user-456", "ops_rw", limit=5)

    # 6th request should raise error
    with pytest.raises(RateLimitExceededError) as exc_info:
        await redis_store.check_and_record("user-456", "ops_rw", limit=5)

    error = exc_info.value
    assert "Rate limit exceeded" in str(error)
    assert error.data["user_id"] == "user-456"
    assert error.data["role"] == "ops_rw"
    assert error.data["limit"] == 5
    assert error.data["retry_after_seconds"] > 0


@pytest.mark.asyncio
async def test_redis_store_unlimited_access(redis_store):
    """Test Redis store allows unlimited access with limit=0."""
    # Should allow many requests
    for i in range(50):
        await redis_store.check_and_record("user-admin", "admin", limit=0)

    # Should still be unlimited
    remaining = await redis_store.get_remaining("user-admin", "admin", limit=0)
    assert remaining == 999999


@pytest.mark.asyncio
async def test_redis_store_sliding_window(redis_store):
    """Test Redis store uses sliding window."""
    # Create store with short window
    store = RateLimitStore(
        redis_url="redis://localhost:6379/15",
        pool_size=5,
        timeout_seconds=2.0,
        window_seconds=1,
    )
    await store.init()
    await store.reset()

    try:
        # Fill up to limit
        for i in range(5):
            await store.check_and_record("user-789", "ops_rw", limit=5)

        # Should be blocked
        with pytest.raises(RateLimitExceededError):
            await store.check_and_record("user-789", "ops_rw", limit=5)

        # Wait for window to expire
        time.sleep(1.2)

        # Should allow requests again
        await store.check_and_record("user-789", "ops_rw", limit=5)
        remaining = await store.get_remaining("user-789", "ops_rw", limit=5)
        assert remaining == 4

    finally:
        await store.reset()
        await store.close()


@pytest.mark.asyncio
async def test_redis_store_per_user_isolation(redis_store):
    """Test Redis store tracks users independently."""
    # Fill limit for user-1
    for i in range(10):
        await redis_store.check_and_record("user-a", "read_only", limit=10)

    # user-b should still be allowed
    await redis_store.check_and_record("user-b", "read_only", limit=10)
    remaining = await redis_store.get_remaining("user-b", "read_only", limit=10)
    assert remaining == 9


@pytest.mark.asyncio
async def test_redis_store_per_role_isolation(redis_store):
    """Test Redis store tracks roles independently."""
    # Fill limit for read_only
    for i in range(10):
        await redis_store.check_and_record("user-c", "read_only", limit=10)

    # Same user with different role should still be allowed
    await redis_store.check_and_record("user-c", "ops_rw", limit=5)
    remaining = await redis_store.get_remaining("user-c", "ops_rw", limit=5)
    assert remaining == 4


@pytest.mark.asyncio
async def test_redis_store_reset_user(redis_store):
    """Test resetting Redis rate limits for specific user."""
    await redis_store.check_and_record("user-reset-1", "read_only", limit=10)
    await redis_store.check_and_record("user-reset-2", "read_only", limit=10)

    # Reset only user-reset-1
    await redis_store.reset(user_id="user-reset-1")

    # user-reset-1 should have full quota
    remaining1 = await redis_store.get_remaining("user-reset-1", "read_only", limit=10)
    remaining2 = await redis_store.get_remaining("user-reset-2", "read_only", limit=10)
    assert remaining1 == 10
    assert remaining2 == 9


@pytest.mark.asyncio
async def test_redis_store_reset_role(redis_store):
    """Test resetting Redis rate limits for specific role."""
    await redis_store.check_and_record("user-reset-3", "read_only", limit=10)
    await redis_store.check_and_record("user-reset-3", "ops_rw", limit=5)

    # Reset only read_only role
    await redis_store.reset(role="read_only")

    # read_only should have full quota, ops_rw still has 1 used
    remaining1 = await redis_store.get_remaining("user-reset-3", "read_only", limit=10)
    remaining2 = await redis_store.get_remaining("user-reset-3", "ops_rw", limit=5)
    assert remaining1 == 10
    assert remaining2 == 4


@pytest.mark.asyncio
async def test_redis_store_key_expiry(redis_store):
    """Test Redis keys have TTL set for automatic cleanup."""
    await redis_store.check_and_record("user-ttl", "read_only", limit=10)

    # Check that key has TTL set
    key = redis_store._get_key("user-ttl", "read_only")
    ttl = await redis_store._redis.ttl(key)

    # TTL should be window_seconds + 60 seconds buffer
    assert ttl > 0
    assert ttl <= redis_store.window_seconds + 60


# ========================================
# Global Store Tests
# ========================================


@pytest.mark.asyncio
async def test_initialize_and_get_global_store():
    """Test initializing and getting global rate limit store."""
    # Initialize with in-memory store
    await initialize_rate_limit_store(
        use_redis=False,
        window_seconds=60,
    )

    # Get store
    store = await get_rate_limit_store()
    assert isinstance(store, InMemoryRateLimitStore)

    # Use store
    await store.check_and_record("user-global", "read_only", limit=10)
    remaining = await store.get_remaining("user-global", "read_only", limit=10)
    assert remaining == 9

    # Cleanup
    await close_rate_limit_store()


@pytest.mark.asyncio
async def test_get_store_before_init_raises_error():
    """Test getting store before initialization raises error."""
    # Ensure store is closed
    await close_rate_limit_store()

    with pytest.raises(RuntimeError, match="not initialized"):
        await get_rate_limit_store()


@pytest.mark.asyncio
async def test_initialize_store_multiple_times():
    """Test initializing store multiple times doesn't crash."""
    await initialize_rate_limit_store(use_redis=False)

    # Second init should log warning but not crash
    await initialize_rate_limit_store(use_redis=False)

    # Cleanup
    await close_rate_limit_store()


# ========================================
# Metrics Tests
# ========================================


@pytest.mark.asyncio
async def test_memory_store_records_metrics(memory_store):
    """Test in-memory store records Prometheus metrics."""
    from routeros_mcp.infra.rate_limit import (
        rate_limit_exceeded_total,
        rate_limit_operations_total,
    )

    # Record allowed requests
    for i in range(3):
        await memory_store.check_and_record("user-metrics", "read_only", limit=5)

    # Check metrics were recorded
    allowed_count = rate_limit_operations_total.labels(
        operation="check", status="allowed", role="read_only"
    )._value._value
    assert allowed_count >= 3

    # Trigger rate limit exceeded
    for i in range(2):
        await memory_store.check_and_record("user-metrics", "read_only", limit=5)

    with pytest.raises(RateLimitExceededError):
        await memory_store.check_and_record("user-metrics", "read_only", limit=5)

    # Check exceeded metric
    exceeded_count = rate_limit_exceeded_total.labels(role="read_only")._value._value
    assert exceeded_count >= 1


@pytest.mark.asyncio
async def test_redis_store_records_metrics(redis_store):
    """Test Redis store records Prometheus metrics."""
    from routeros_mcp.infra.rate_limit import rate_limit_operations_total

    # Record some requests
    for i in range(3):
        await redis_store.check_and_record("user-redis-metrics", "ops_rw", limit=5)

    # Check metrics were recorded
    allowed_count = rate_limit_operations_total.labels(
        operation="check", status="allowed", role="ops_rw"
    )._value._value
    assert allowed_count >= 3
