"""Tests for TTL-based resource caching layer."""

import asyncio
import time
from unittest.mock import patch

import pytest

from routeros_mcp.infra.observability.resource_cache import (
    CacheEntry,
    ResourceCache,
    get_cache,
    initialize_cache,
    with_cache,
)


class TestCacheEntry:
    """Tests for CacheEntry dataclass."""

    def test_cache_entry_creation(self) -> None:
        """CacheEntry should store value and timestamps."""
        now = time.time()
        entry = CacheEntry(
            value="test_value",
            expires_at=now + 300,
            created_at=now,
            last_accessed=now,
        )

        assert entry.value == "test_value"
        assert entry.expires_at == now + 300
        assert entry.created_at == now
        assert entry.last_accessed == now


class TestResourceCache:
    """Tests for ResourceCache class."""

    @pytest.fixture
    def cache(self) -> ResourceCache:
        """Create a cache instance for testing."""
        return ResourceCache(ttl_seconds=300, max_entries=10, enabled=True)

    @pytest.mark.asyncio
    async def test_cache_initialization(self) -> None:
        """Cache should initialize with correct settings."""
        cache = ResourceCache(ttl_seconds=60, max_entries=100, enabled=True)

        assert cache._enabled is True
        assert cache._ttl_seconds == 60
        assert cache._max_entries == 100
        assert len(cache._cache) == 0

    @pytest.mark.asyncio
    async def test_cache_disabled(self) -> None:
        """Disabled cache should not store or return values."""
        cache = ResourceCache(enabled=False)

        await cache.set("device://dev1/overview", "test_value", "dev1")
        result = await cache.get("device://dev1/overview", "dev1")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_and_get(self, cache: ResourceCache) -> None:
        """Cache should store and retrieve values."""
        await cache.set("device://dev1/overview", "test_value", "dev1")
        result = await cache.get("device://dev1/overview", "dev1")

        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache: ResourceCache) -> None:
        """Cache get should return None for missing keys."""
        result = await cache.get("device://nonexistent/overview", "dev1")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_key_with_device_id(self, cache: ResourceCache) -> None:
        """Cache should use device_id in key."""
        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")

        result1 = await cache.get("device://dev1/overview", "dev1")
        result2 = await cache.get("device://dev2/overview", "dev2")

        assert result1 == "value1"
        assert result2 == "value2"

    @pytest.mark.asyncio
    async def test_cache_key_without_device_id(self, cache: ResourceCache) -> None:
        """Cache should work without device_id."""
        await cache.set("fleet://health-summary", "fleet_data", None)
        result = await cache.get("fleet://health-summary", None)

        assert result == "fleet_data"

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self) -> None:
        """Cache entries should expire after TTL."""
        cache = ResourceCache(ttl_seconds=1, max_entries=10, enabled=True)

        await cache.set("device://dev1/overview", "test_value", "dev1")

        # Should be cached immediately
        result = await cache.get("device://dev1/overview", "dev1")
        assert result == "test_value"

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should be expired
        result = await cache.get("device://dev1/overview", "dev1")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self) -> None:
        """Cache should evict oldest entry when max_entries exceeded."""
        cache = ResourceCache(ttl_seconds=300, max_entries=3, enabled=True)

        # Fill cache to max
        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")
        await cache.set("device://dev3/overview", "value3", "dev3")

        # All should be cached
        assert await cache.get("device://dev1/overview", "dev1") == "value1"
        assert await cache.get("device://dev2/overview", "dev2") == "value2"
        assert await cache.get("device://dev3/overview", "dev3") == "value3"

        # Add one more - should evict dev1 (oldest)
        await cache.set("device://dev4/overview", "value4", "dev4")

        # dev1 should be evicted
        assert await cache.get("device://dev1/overview", "dev1") is None
        # Others should still be cached
        assert await cache.get("device://dev2/overview", "dev2") == "value2"
        assert await cache.get("device://dev3/overview", "dev3") == "value3"
        assert await cache.get("device://dev4/overview", "dev4") == "value4"

    @pytest.mark.asyncio
    async def test_cache_lru_access_updates_order(self) -> None:
        """Accessing a cache entry should move it to end (most recent)."""
        cache = ResourceCache(ttl_seconds=300, max_entries=3, enabled=True)

        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")
        await cache.set("device://dev3/overview", "value3", "dev3")

        # Access dev1 to make it most recent
        await cache.get("device://dev1/overview", "dev1")

        # Add dev4 - should evict dev2 (now oldest)
        await cache.set("device://dev4/overview", "value4", "dev4")

        # dev1 should still be cached (was accessed recently)
        assert await cache.get("device://dev1/overview", "dev1") == "value1"
        # dev2 should be evicted
        assert await cache.get("device://dev2/overview", "dev2") is None
        # dev3 and dev4 should be cached
        assert await cache.get("device://dev3/overview", "dev3") == "value3"
        assert await cache.get("device://dev4/overview", "dev4") == "value4"

    @pytest.mark.asyncio
    async def test_cache_invalidate(self, cache: ResourceCache) -> None:
        """Cache should support manual invalidation."""
        await cache.set("device://dev1/overview", "test_value", "dev1")

        # Should be cached
        assert await cache.get("device://dev1/overview", "dev1") == "test_value"

        # Invalidate
        result = await cache.invalidate("device://dev1/overview", "dev1")
        assert result is True

        # Should be gone
        assert await cache.get("device://dev1/overview", "dev1") is None

    @pytest.mark.asyncio
    async def test_cache_invalidate_nonexistent(self, cache: ResourceCache) -> None:
        """Invalidating nonexistent entry should return False."""
        result = await cache.invalidate("device://nonexistent/overview", "dev1")
        assert result is False

    @pytest.mark.asyncio
    async def test_cache_clear(self, cache: ResourceCache) -> None:
        """Cache clear should remove all entries."""
        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")
        await cache.set("device://dev3/overview", "value3", "dev3")

        count = await cache.clear()
        assert count == 3

        # All should be gone
        assert await cache.get("device://dev1/overview", "dev1") is None
        assert await cache.get("device://dev2/overview", "dev2") is None
        assert await cache.get("device://dev3/overview", "dev3") is None

    @pytest.mark.asyncio
    async def test_cache_get_stats(self, cache: ResourceCache) -> None:
        """Cache should provide statistics."""
        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")

        stats = await cache.get_stats()

        assert stats["enabled"] is True
        assert stats["total_entries"] == 2
        assert stats["max_entries"] == 10
        assert stats["ttl_seconds"] == 300
        assert stats["expired_entries"] == 0

    @pytest.mark.asyncio
    async def test_cache_cleanup_expired(self) -> None:
        """Cache cleanup should remove expired entries."""
        cache = ResourceCache(ttl_seconds=1, max_entries=10, enabled=True)

        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Cleanup
        count = await cache.cleanup_expired()
        assert count == 2

        # Should be empty
        stats = await cache.get_stats()
        assert stats["total_entries"] == 0

    @pytest.mark.asyncio
    async def test_cache_concurrent_access(self, cache: ResourceCache) -> None:
        """Cache should be thread-safe with concurrent access."""

        async def reader(n: int) -> str | None:
            return await cache.get(f"device://dev{n}/overview", f"dev{n}")

        async def writer(n: int) -> None:
            await cache.set(f"device://dev{n}/overview", f"value{n}", f"dev{n}")

        # Concurrent writes
        await asyncio.gather(*[writer(i) for i in range(20)])

        # Concurrent reads
        results = await asyncio.gather(*[reader(i) for i in range(20)])

        # All values should be present (some may have been evicted due to max_entries=10)
        non_none_results = [r for r in results if r is not None]
        assert len(non_none_results) == 10  # max_entries

    @pytest.mark.asyncio
    async def test_cache_set_updates_existing(self, cache: ResourceCache) -> None:
        """Setting an existing key should update value and timestamp."""
        await cache.set("device://dev1/overview", "old_value", "dev1")
        await asyncio.sleep(0.1)
        await cache.set("device://dev1/overview", "new_value", "dev1")

        result = await cache.get("device://dev1/overview", "dev1")
        assert result == "new_value"


class TestGlobalCacheFunctions:
    """Tests for global cache instance management."""

    def test_initialize_cache(self) -> None:
        """initialize_cache should create global instance."""
        cache = initialize_cache(ttl_seconds=60, max_entries=100, enabled=True)

        assert cache is not None
        assert cache._ttl_seconds == 60
        assert cache._max_entries == 100
        assert cache._enabled is True

    def test_get_cache_before_init(self) -> None:
        """get_cache should raise if not initialized."""
        # Reset global cache
        from routeros_mcp.infra.observability import resource_cache as cache_module

        cache_module._cache_instance = None

        with pytest.raises(RuntimeError, match="not initialized"):
            get_cache()

    def test_get_cache_after_init(self) -> None:
        """get_cache should return initialized instance."""
        cache = initialize_cache(ttl_seconds=60, max_entries=100, enabled=True)
        retrieved = get_cache()

        assert retrieved is cache


class TestWithCacheDecorator:
    """Tests for @with_cache decorator."""

    @pytest.mark.asyncio
    async def test_decorator_caches_result(self) -> None:
        """Decorator should cache function results."""
        initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        call_count = 0

        @with_cache("device://{device_id}/overview")
        async def fetch_overview(device_id: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"overview_{device_id}"

        # First call - should hit function
        result1 = await fetch_overview("dev1")
        assert result1 == "overview_dev1"
        assert call_count == 1

        # Second call - should use cache
        result2 = await fetch_overview("dev1")
        assert result2 == "overview_dev1"
        assert call_count == 1  # Not incremented

    @pytest.mark.asyncio
    async def test_decorator_different_devices(self) -> None:
        """Decorator should cache separately for different devices."""
        initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        call_count = 0

        @with_cache("device://{device_id}/overview")
        async def fetch_overview(device_id: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"overview_{device_id}"

        result1 = await fetch_overview("dev1")
        result2 = await fetch_overview("dev2")

        assert result1 == "overview_dev1"
        assert result2 == "overview_dev2"
        assert call_count == 2

        # Cache hits for both
        await fetch_overview("dev1")
        await fetch_overview("dev2")
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_cache_disabled(self) -> None:
        """Decorator should skip caching when disabled."""
        initialize_cache(ttl_seconds=300, max_entries=100, enabled=False)

        call_count = 0

        @with_cache("device://{device_id}/overview")
        async def fetch_overview(device_id: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"overview_{device_id}"

        await fetch_overview("dev1")
        await fetch_overview("dev1")

        # Both calls should hit function
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_with_metrics(self) -> None:
        """Decorator should record metrics."""
        initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        with patch("routeros_mcp.infra.observability.resource_cache.metrics") as mock_metrics:

            @with_cache("device://{device_id}/overview")
            async def fetch_overview(device_id: str) -> str:
                return f"overview_{device_id}"

            # First call - cache miss
            await fetch_overview("dev1")
            # Should record miss and fetch
            assert mock_metrics.record_cache_miss.called
            assert mock_metrics.record_cache_fetch.called

            # Reset mocks
            mock_metrics.reset_mock()

            # Second call - cache hit
            await fetch_overview("dev1")
            # Should record hit and fetch
            assert mock_metrics.record_cache_hit.called
            assert mock_metrics.record_cache_fetch.called

    @pytest.mark.asyncio
    async def test_decorator_ttl_expiration(self) -> None:
        """Decorator should refetch after TTL expiration."""
        initialize_cache(ttl_seconds=1, max_entries=100, enabled=True)

        call_count = 0

        @with_cache("device://{device_id}/overview")
        async def fetch_overview(device_id: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"overview_{device_id}_{call_count}"

        # First call
        result1 = await fetch_overview("dev1")
        assert result1 == "overview_dev1_1"
        assert call_count == 1

        # Wait for expiration
        await asyncio.sleep(1.1)

        # Should refetch
        result2 = await fetch_overview("dev1")
        assert result2 == "overview_dev1_2"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_with_plan_id(self) -> None:
        """Decorator should work with plan_id parameter."""
        initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        call_count = 0

        @with_cache("plan://{plan_id}/summary")
        async def fetch_plan(plan_id: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"plan_{plan_id}"

        # First call - should hit function
        result1 = await fetch_plan("plan-123")
        assert result1 == "plan_plan-123"
        assert call_count == 1

        # Second call - should use cache
        result2 = await fetch_plan("plan-123")
        assert result2 == "plan_plan-123"
        assert call_count == 1  # Not incremented

        # Different plan_id - should hit function
        result3 = await fetch_plan("plan-456")
        assert result3 == "plan_plan-456"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_with_user_sub(self) -> None:
        """Decorator should work with user_sub parameter."""
        initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        call_count = 0

        @with_cache("audit://events/by-user/{user_sub}")
        async def fetch_audit(user_sub: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"audit_{user_sub}"

        # First call - should hit function
        result1 = await fetch_audit("user-abc")
        assert result1 == "audit_user-abc"
        assert call_count == 1

        # Second call - should use cache
        result2 = await fetch_audit("user-abc")
        assert result2 == "audit_user-abc"
        assert call_count == 1  # Not incremented

        # Different user_sub - should hit function
        result3 = await fetch_audit("user-xyz")
        assert result3 == "audit_user-xyz"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_missing_parameter_skips_cache(self) -> None:
        """Decorator should bypass cache when required parameter is missing."""
        initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        call_count = 0

        @with_cache("device://{device_id}/overview")
        async def fetch_overview(**kwargs: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"overview_{kwargs.get('device_id')}_{kwargs.get('wrong_id')}"

        # Missing device_id should not be cached
        result1 = await fetch_overview(wrong_id="first")
        result2 = await fetch_overview(wrong_id="second")

        assert result1 == "overview_None_first"
        assert result2 == "overview_None_second"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_with_no_parameter(self) -> None:
        """Decorator should work with URIs that have no parameters."""
        initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        call_count = 0

        @with_cache("fleet://health-summary")
        async def fetch_fleet() -> str:
            nonlocal call_count
            call_count += 1
            return "fleet_summary"

        # First call - should hit function
        result1 = await fetch_fleet()
        assert result1 == "fleet_summary"
        assert call_count == 1

        # Second call - should use cache
        result2 = await fetch_fleet()
        assert result2 == "fleet_summary"
        assert call_count == 1  # Not incremented

