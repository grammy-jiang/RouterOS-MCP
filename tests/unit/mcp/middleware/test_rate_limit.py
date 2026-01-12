"""Tests for rate limiting middleware."""

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.mcp.errors import RateLimitExceededError
from routeros_mcp.mcp.middleware.rate_limit import (
    RateLimitMiddleware,
    create_rate_limit_middleware,
)
from routeros_mcp.security.auth import User


@pytest.fixture
def settings():
    """Create settings for testing."""
    return Settings(
        environment="lab",
        rate_limit_enabled=True,
        rate_limit_use_redis=False,  # Use in-memory for tests
        rate_limit_read_only_per_minute=10,
        rate_limit_ops_rw_per_minute=5,
        rate_limit_admin_per_minute=0,  # Unlimited
        rate_limit_approver_per_minute=5,
        rate_limit_window_seconds=60,
    )


@pytest.fixture
async def middleware(settings):
    """Create rate limit middleware for testing."""
    mw = RateLimitMiddleware(settings)
    await mw.init()
    yield mw
    await mw.close()


@pytest.fixture
def read_only_user():
    """Create read-only user for testing."""
    return User(
        sub="user-readonly",
        email="readonly@example.com",
        name="Read Only User",
        role="read_only",
        device_scope=None,
    )


@pytest.fixture
def ops_rw_user():
    """Create ops_rw user for testing."""
    return User(
        sub="user-opsrw",
        email="opsrw@example.com",
        name="Ops RW User",
        role="ops_rw",
        device_scope=None,
    )


@pytest.fixture
def admin_user():
    """Create admin user for testing."""
    return User(
        sub="user-admin",
        email="admin@example.com",
        name="Admin User",
        role="admin",
        device_scope=None,
    )


@pytest.fixture
def approver_user():
    """Create approver user for testing."""
    return User(
        sub="user-approver",
        email="approver@example.com",
        name="Approver User",
        role="approver",
        device_scope=None,
    )


# ========================================
# Middleware Initialization Tests
# ========================================


@pytest.mark.asyncio
async def test_middleware_init_with_redis(settings):
    """Test middleware initialization with Redis backend."""
    settings.rate_limit_use_redis = False  # Use memory for test

    mw = RateLimitMiddleware(settings)
    await mw.init()

    assert mw._initialized

    await mw.close()


@pytest.mark.asyncio
async def test_middleware_init_disabled(settings):
    """Test middleware initialization when disabled."""
    settings.rate_limit_enabled = False

    mw = RateLimitMiddleware(settings)
    await mw.init()

    assert mw._initialized

    await mw.close()


@pytest.mark.asyncio
async def test_middleware_init_multiple_times(settings):
    """Test middleware can be initialized multiple times safely."""
    mw = RateLimitMiddleware(settings)
    await mw.init()
    await mw.init()  # Should not crash

    assert mw._initialized

    await mw.close()


# ========================================
# Rate Limit Check Tests
# ========================================


@pytest.mark.asyncio
async def test_check_rate_limit_allows_within_limit(middleware, read_only_user):
    """Test rate limit check allows requests within limit."""
    # Should allow 10 requests
    for _i in range(10):
        headers = await middleware.check_rate_limit(read_only_user, "device/list")
        assert headers["limit"] == 10
        assert headers["remaining"] >= 0
        assert headers["reset"] > 0


@pytest.mark.asyncio
async def test_check_rate_limit_blocks_over_limit(middleware, ops_rw_user):
    """Test rate limit check blocks requests over limit."""
    # Fill up to limit (5 for ops_rw)
    for _i in range(5):
        await middleware.check_rate_limit(ops_rw_user, "dns/update-servers")

    # 6th request should raise error
    with pytest.raises(RateLimitExceededError) as exc_info:
        await middleware.check_rate_limit(ops_rw_user, "dns/update-servers")

    error = exc_info.value
    assert "Rate limit exceeded" in str(error)
    assert error.code == -32009  # MCP_RATE_LIMIT_EXCEEDED
    assert error.data["role"] == "ops_rw"
    assert error.data["limit"] == 5


@pytest.mark.asyncio
async def test_check_rate_limit_admin_unlimited(middleware, admin_user):
    """Test admin users have unlimited access."""
    # Should allow many requests
    for _i in range(50):
        headers = await middleware.check_rate_limit(admin_user, "system/reboot")
        assert headers["limit"] == 0
        assert headers["remaining"] == 999999


@pytest.mark.asyncio
async def test_check_rate_limit_returns_correct_headers(middleware, read_only_user):
    """Test rate limit check returns correct header values."""
    headers = await middleware.check_rate_limit(read_only_user, "device/list")

    assert "limit" in headers
    assert "remaining" in headers
    assert "reset" in headers
    assert isinstance(headers["limit"], int)
    assert isinstance(headers["remaining"], int)
    assert isinstance(headers["reset"], int)
    assert headers["limit"] == 10
    assert headers["remaining"] == 9  # 1 request used


@pytest.mark.asyncio
async def test_check_rate_limit_per_user_isolation(middleware, read_only_user):
    """Test rate limits are isolated per user."""
    # Create second user
    user2 = User(
        sub="user-readonly-2",
        email="readonly2@example.com",
        name="Read Only User 2",
        role="read_only",
        device_scope=None,
    )

    # Fill limit for user1
    for _i in range(10):
        await middleware.check_rate_limit(read_only_user, "device/list")

    # user2 should still be allowed
    headers = await middleware.check_rate_limit(user2, "device/list")
    assert headers["remaining"] == 9


@pytest.mark.asyncio
async def test_check_rate_limit_per_role(middleware):
    """Test different roles have different limits."""
    # Create users with different roles
    readonly = User(
        sub="test-ro",
        email="ro@test.com",
        name="RO",
        role="read_only",
        device_scope=None,
    )
    opsrw = User(
        sub="test-ops",
        email="ops@test.com",
        name="Ops",
        role="ops_rw",
        device_scope=None,
    )

    # read_only gets 10/min
    headers_ro = await middleware.check_rate_limit(readonly, "device/list")
    assert headers_ro["limit"] == 10

    # ops_rw gets 5/min
    headers_ops = await middleware.check_rate_limit(opsrw, "dns/update")
    assert headers_ops["limit"] == 5


# ========================================
# Rate Limit Headers Tests
# ========================================


@pytest.mark.asyncio
async def test_get_rate_limit_headers(middleware, read_only_user):
    """Test getting rate limit headers for user."""
    headers = await middleware.get_rate_limit_headers(read_only_user)

    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    assert "X-RateLimit-Reset" in headers
    assert headers["X-RateLimit-Limit"] == "10"
    assert int(headers["X-RateLimit-Remaining"]) == 10


@pytest.mark.asyncio
async def test_get_rate_limit_headers_after_requests(middleware, ops_rw_user):
    """Test rate limit headers reflect current usage."""
    # Make 3 requests
    for _i in range(3):
        await middleware.check_rate_limit(ops_rw_user, "interface/list")

    headers = await middleware.get_rate_limit_headers(ops_rw_user)
    assert headers["X-RateLimit-Limit"] == "5"
    assert int(headers["X-RateLimit-Remaining"]) == 2


@pytest.mark.asyncio
async def test_get_rate_limit_headers_admin_unlimited(middleware, admin_user):
    """Test admin headers show unlimited."""
    headers = await middleware.get_rate_limit_headers(admin_user)

    assert headers["X-RateLimit-Limit"] == "unlimited"
    assert int(headers["X-RateLimit-Remaining"]) == 999999


@pytest.mark.asyncio
async def test_get_rate_limit_headers_when_disabled(settings, read_only_user):
    """Test headers are empty when rate limiting disabled."""
    settings.rate_limit_enabled = False
    mw = RateLimitMiddleware(settings)
    await mw.init()

    headers = await mw.get_rate_limit_headers(read_only_user)
    assert headers == {}

    await mw.close()


# ========================================
# Error Handling Tests
# ========================================


@pytest.mark.asyncio
async def test_check_rate_limit_before_init_raises_error(settings, read_only_user):
    """Test checking rate limit before init raises error."""
    mw = RateLimitMiddleware(settings)
    # Don't call init()

    with pytest.raises(RuntimeError, match="not initialized"):
        await mw.check_rate_limit(read_only_user, "device/list")


@pytest.mark.asyncio
async def test_check_rate_limit_when_disabled_allows_all(settings, read_only_user):
    """Test rate limit check allows all when disabled."""
    settings.rate_limit_enabled = False
    mw = RateLimitMiddleware(settings)
    await mw.init()

    # Should allow unlimited requests
    for _i in range(100):
        headers = await mw.check_rate_limit(read_only_user, "device/list")
        assert headers["limit"] == 999999
        assert headers["remaining"] == 999999

    await mw.close()


@pytest.mark.asyncio
async def test_rate_limit_exceeded_includes_retry_after(middleware, ops_rw_user):
    """Test rate limit exceeded error includes retry-after data."""
    # Fill up to limit
    for _i in range(5):
        await middleware.check_rate_limit(ops_rw_user, "tool/execute")

    # Next request should include retry-after
    with pytest.raises(RateLimitExceededError) as exc_info:
        await middleware.check_rate_limit(ops_rw_user, "tool/execute")

    error = exc_info.value
    assert "retry_after_seconds" in error.data
    assert error.data["retry_after_seconds"] > 0


# ========================================
# Factory Function Tests
# ========================================


@pytest.mark.asyncio
async def test_create_rate_limit_middleware(settings):
    """Test factory function creates middleware."""
    mw = create_rate_limit_middleware(settings)
    assert isinstance(mw, RateLimitMiddleware)
    assert mw.settings == settings

    await mw.init()
    await mw.close()


# ========================================
# Integration Tests
# ========================================


@pytest.mark.asyncio
async def test_full_rate_limit_flow(middleware):
    """Test complete rate limit flow with multiple users and roles."""
    # Create users
    ro_user = User(
        sub="integration-ro",
        email="ro@test.com",
        name="RO User",
        role="read_only",
        device_scope=None,
    )
    ops_user = User(
        sub="integration-ops",
        email="ops@test.com",
        name="Ops User",
        role="ops_rw",
        device_scope=None,
    )
    admin = User(
        sub="integration-admin",
        email="admin@test.com",
        name="Admin",
        role="admin",
        device_scope=None,
    )

    # read_only: can make 10 requests
    for i in range(10):
        headers = await middleware.check_rate_limit(ro_user, "device/list")
        assert headers["remaining"] == 10 - i - 1

    # 11th should fail
    with pytest.raises(RateLimitExceededError):
        await middleware.check_rate_limit(ro_user, "device/list")

    # ops_rw: can make 5 requests
    for _ in range(5):
        await middleware.check_rate_limit(ops_user, "interface/update")

    # 6th should fail
    with pytest.raises(RateLimitExceededError):
        await middleware.check_rate_limit(ops_user, "interface/update")

    # admin: unlimited
    for _ in range(100):
        await middleware.check_rate_limit(admin, "system/reboot")

    # Still works
    headers = await middleware.check_rate_limit(admin, "system/reboot")
    assert headers["remaining"] == 999999


@pytest.mark.asyncio
async def test_approver_role_rate_limit(middleware, approver_user):
    """Test approver role has correct rate limit."""
    # Approvers get 5/min
    for _i in range(5):
        headers = await middleware.check_rate_limit(approver_user, "plan/approve")
        assert headers["limit"] == 5

    # 6th should fail
    with pytest.raises(RateLimitExceededError):
        await middleware.check_rate_limit(approver_user, "plan/approve")


# ========================================
# Redis Error Handling Tests
# ========================================


@pytest.mark.asyncio
async def test_middleware_handles_redis_errors(settings, ops_rw_user):
    """Test middleware converts Redis errors to InternalError."""
    from unittest.mock import patch

    from redis.exceptions import ConnectionError as RedisConnectionError

    from routeros_mcp.mcp.errors import InternalError

    mw = RateLimitMiddleware(settings)
    await mw.init()

    # Mock the store's check_and_record to raise RedisError
    from routeros_mcp.infra.rate_limit import get_rate_limit_store

    store = await get_rate_limit_store()

    with patch.object(
        store, "check_and_record", side_effect=RedisConnectionError("Connection refused")
    ):
        # Should convert to InternalError
        with pytest.raises(InternalError) as exc_info:
            await mw.check_rate_limit(ops_rw_user, "test/tool")

        error = exc_info.value
        assert "Rate limiting service temporarily unavailable" in str(error)
        assert "original_error" in error.data

    await mw.close()
