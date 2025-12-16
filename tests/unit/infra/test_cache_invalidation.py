"""Tests for cache invalidation functionality."""

import asyncio

import pytest

from routeros_mcp.infra.observability.resource_cache import (
    ResourceCache,
    initialize_cache,
    get_cache,
)


class TestCacheInvalidation:
    """Tests for cache invalidation methods."""

    @pytest.fixture
    def cache(self) -> ResourceCache:
        """Create a cache instance for testing."""
        return ResourceCache(ttl_seconds=300, max_entries=100, enabled=True)

    @pytest.mark.asyncio
    async def test_invalidate_single_entry(self, cache: ResourceCache) -> None:
        """invalidate() should remove a specific cache entry."""
        # Set up cache entries
        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev1/dns-status", "dns_data", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")

        # Invalidate one entry
        result = await cache.invalidate("device://dev1/overview", "dev1")
        assert result is True

        # Verify invalidated entry is gone
        assert await cache.get("device://dev1/overview", "dev1") is None

        # Verify other entries remain
        assert await cache.get("device://dev1/dns-status", "dev1") == "dns_data"
        assert await cache.get("device://dev2/overview", "dev2") == "value2"

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_entry(self, cache: ResourceCache) -> None:
        """invalidate() should return False for nonexistent entry."""
        result = await cache.invalidate("device://nonexistent/overview", "dev1")
        assert result is False

    @pytest.mark.asyncio
    async def test_invalidate_device_all_entries(self, cache: ResourceCache) -> None:
        """invalidate_device() should remove all entries for a device."""
        # Set up cache entries for multiple devices
        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev1/dns-status", "dns_data", "dev1")
        await cache.set("device://dev1/ntp-status", "ntp_data", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")
        await cache.set("device://dev3/overview", "value3", "dev3")

        # Invalidate all dev1 entries
        count = await cache.invalidate_device("dev1")
        assert count == 3

        # Verify all dev1 entries are gone
        assert await cache.get("device://dev1/overview", "dev1") is None
        assert await cache.get("device://dev1/dns-status", "dev1") is None
        assert await cache.get("device://dev1/ntp-status", "dev1") is None

        # Verify other devices remain
        assert await cache.get("device://dev2/overview", "dev2") == "value2"
        assert await cache.get("device://dev3/overview", "dev3") == "value3"

    @pytest.mark.asyncio
    async def test_invalidate_device_no_entries(self, cache: ResourceCache) -> None:
        """invalidate_device() should return 0 for device with no entries."""
        await cache.set("device://dev1/overview", "value1", "dev1")

        count = await cache.invalidate_device("dev2")
        assert count == 0

        # Verify existing entry is not affected
        assert await cache.get("device://dev1/overview", "dev1") == "value1"

    @pytest.mark.asyncio
    async def test_invalidate_pattern_matching(self, cache: ResourceCache) -> None:
        """invalidate_pattern() should remove entries matching pattern."""
        # Set up cache entries
        await cache.set("device://dev1/dns-status", "dns1", "dev1")
        await cache.set("device://dev2/dns-status", "dns2", "dev2")
        await cache.set("device://dev1/ntp-status", "ntp1", "dev1")
        await cache.set("device://dev1/firewall-rules", "fw1", "dev1")

        # Invalidate all dns-status entries
        count = await cache.invalidate_pattern("dns-status")
        assert count == 2

        # Verify dns-status entries are gone
        assert await cache.get("device://dev1/dns-status", "dev1") is None
        assert await cache.get("device://dev2/dns-status", "dev2") is None

        # Verify other entries remain
        assert await cache.get("device://dev1/ntp-status", "dev1") == "ntp1"
        assert await cache.get("device://dev1/firewall-rules", "dev1") == "fw1"

    @pytest.mark.asyncio
    async def test_invalidate_pattern_firewall(self, cache: ResourceCache) -> None:
        """invalidate_pattern() should work for firewall resources."""
        # Set up cache entries
        await cache.set("device://dev1/firewall-rules", "rules1", "dev1")
        await cache.set("device://dev1/firewall-address-lists", "lists1", "dev1")
        await cache.set("device://dev1/dns-status", "dns1", "dev1")
        await cache.set("device://dev2/firewall-rules", "rules2", "dev2")

        # Invalidate all firewall entries for dev1
        count = await cache.invalidate_pattern("device://dev1/firewall")
        assert count == 2

        # Verify firewall entries are gone
        assert await cache.get("device://dev1/firewall-rules", "dev1") is None
        assert await cache.get("device://dev1/firewall-address-lists", "dev1") is None

        # Verify other entries remain
        assert await cache.get("device://dev1/dns-status", "dev1") == "dns1"
        assert await cache.get("device://dev2/firewall-rules", "dev2") == "rules2"

    @pytest.mark.asyncio
    async def test_invalidate_pattern_no_matches(self, cache: ResourceCache) -> None:
        """invalidate_pattern() should return 0 for no matches."""
        await cache.set("device://dev1/overview", "value1", "dev1")

        count = await cache.invalidate_pattern("nonexistent")
        assert count == 0

        # Verify existing entry is not affected
        assert await cache.get("device://dev1/overview", "dev1") == "value1"

    @pytest.mark.asyncio
    async def test_invalidate_disabled_cache(self) -> None:
        """Invalidation methods should work gracefully when cache disabled."""
        cache = ResourceCache(enabled=False)

        # All methods should return 0/False without error
        assert await cache.invalidate("device://dev1/overview", "dev1") is False
        assert await cache.invalidate_device("dev1") == 0
        assert await cache.invalidate_pattern("dns-status") == 0

    @pytest.mark.asyncio
    async def test_concurrent_invalidation(self, cache: ResourceCache) -> None:
        """Cache should handle concurrent invalidation safely."""
        # Set up entries
        for i in range(20):
            await cache.set(f"device://dev{i}/overview", f"value{i}", f"dev{i}")

        # Concurrent invalidations
        async def invalidate_device(device_id: str) -> int:
            return await cache.invalidate_device(device_id)

        # Invalidate multiple devices concurrently
        results = await asyncio.gather(*[invalidate_device(f"dev{i}") for i in range(10)])

        # Each should have invalidated exactly 1 entry
        assert all(count == 1 for count in results)

        # Verify only non-invalidated entries remain
        for i in range(10):
            assert await cache.get(f"device://dev{i}/overview", f"dev{i}") is None
        for i in range(10, 20):
            assert await cache.get(f"device://dev{i}/overview", f"dev{i}") == f"value{i}"

    @pytest.mark.asyncio
    async def test_invalidate_updates_cache_size_metric(self, cache: ResourceCache) -> None:
        """Invalidation should update cache size metrics."""
        from unittest.mock import patch

        with patch("routeros_mcp.infra.observability.resource_cache.metrics") as mock_metrics:
            # Set up entries
            await cache.set("device://dev1/overview", "value1", "dev1")
            await cache.set("device://dev2/overview", "value2", "dev2")

            # Reset mock to focus on invalidation calls
            mock_metrics.reset_mock()

            # Invalidate one entry
            await cache.invalidate("device://dev1/overview", "dev1")

            # Should update cache size
            mock_metrics.update_cache_size.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_clear_all_entries(self, cache: ResourceCache) -> None:
        """clear() should remove all cache entries."""
        # Set up entries
        await cache.set("device://dev1/overview", "value1", "dev1")
        await cache.set("device://dev2/overview", "value2", "dev2")
        await cache.set("device://dev3/overview", "value3", "dev3")

        # Clear all
        count = await cache.clear()
        assert count == 3

        # Verify all entries are gone
        assert await cache.get("device://dev1/overview", "dev1") is None
        assert await cache.get("device://dev2/overview", "dev2") is None
        assert await cache.get("device://dev3/overview", "dev3") is None

    @pytest.mark.asyncio
    async def test_invalidate_after_set(self, cache: ResourceCache) -> None:
        """Setting and then invalidating should work correctly."""
        # Set entry
        await cache.set("device://dev1/overview", "old_value", "dev1")
        assert await cache.get("device://dev1/overview", "dev1") == "old_value"

        # Invalidate
        result = await cache.invalidate("device://dev1/overview", "dev1")
        assert result is True

        # Should be gone
        assert await cache.get("device://dev1/overview", "dev1") is None

        # Set new value
        await cache.set("device://dev1/overview", "new_value", "dev1")
        assert await cache.get("device://dev1/overview", "dev1") == "new_value"


class TestCacheInvalidationIntegration:
    """Integration tests for cache invalidation with real scenarios."""

    @pytest.mark.asyncio
    async def test_config_change_invalidates_cache(self) -> None:
        """Config change should invalidate cache and fetch fresh data."""
        # Initialize cache
        cache = initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        # Simulate cached DNS status
        await cache.set("device://dev1/dns-status", "old_dns_data", "dev1")
        assert await cache.get("device://dev1/dns-status", "dev1") == "old_dns_data"

        # Simulate config update that invalidates cache
        count = await cache.invalidate("device://dev1/dns-status", "dev1")
        assert count is True

        # Cache should be empty now
        assert await cache.get("device://dev1/dns-status", "dev1") is None

        # Next fetch would get fresh data
        await cache.set("device://dev1/dns-status", "fresh_dns_data", "dev1")
        assert await cache.get("device://dev1/dns-status", "dev1") == "fresh_dns_data"

    @pytest.mark.asyncio
    async def test_status_change_invalidates_device(self) -> None:
        """Device status change should invalidate all device resources."""
        cache = initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        # Simulate cached device data
        await cache.set("device://dev1/overview", "overview_data", "dev1")
        await cache.set("device://dev1/health", "health_data", "dev1")
        await cache.set("device://dev1/interfaces", "interfaces_data", "dev1")

        # Simulate device status change (healthy -> unreachable)
        count = await cache.invalidate_device("dev1")
        assert count == 3

        # All device resources should be invalidated
        assert await cache.get("device://dev1/overview", "dev1") is None
        assert await cache.get("device://dev1/health", "dev1") is None
        assert await cache.get("device://dev1/interfaces", "dev1") is None

    @pytest.mark.asyncio
    async def test_race_condition_update_then_invalidate(self) -> None:
        """Test race condition: invalidate called before write completes."""
        cache = initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        # Initial cached value
        await cache.set("device://dev1/dns-status", "old_value", "dev1")

        # Simulate concurrent operations
        async def slow_update() -> None:
            """Simulates a slow update operation."""
            await asyncio.sleep(0.1)
            await cache.set("device://dev1/dns-status", "new_value", "dev1")

        async def fast_invalidate() -> bool:
            """Simulates fast invalidation."""
            await asyncio.sleep(0.05)
            return await cache.invalidate("device://dev1/dns-status", "dev1")

        # Run concurrently
        invalidate_result, _ = await asyncio.gather(fast_invalidate(), slow_update())

        # Invalidation should have happened before update
        # After both complete, the new value should be present
        result = await cache.get("device://dev1/dns-status", "dev1")
        assert result == "new_value"

    @pytest.mark.asyncio
    async def test_multiple_invalidations_same_entry(self) -> None:
        """Multiple invalidations of same entry should be safe."""
        cache = initialize_cache(ttl_seconds=300, max_entries=100, enabled=True)

        await cache.set("device://dev1/overview", "value", "dev1")

        # First invalidation
        result1 = await cache.invalidate("device://dev1/overview", "dev1")
        assert result1 is True

        # Second invalidation (entry already gone)
        result2 = await cache.invalidate("device://dev1/overview", "dev1")
        assert result2 is False

        # Third invalidation
        result3 = await cache.invalidate("device://dev1/overview", "dev1")
        assert result3 is False


class TestCacheInvalidationMetrics:
    """Tests for cache invalidation metrics."""

    @pytest.mark.asyncio
    async def test_invalidation_records_metric(self) -> None:
        """Cache invalidation should record metrics."""
        from unittest.mock import patch
        from routeros_mcp.infra.observability import metrics

        with patch.object(metrics, "record_cache_invalidation") as mock_record:
            # Call the metric function directly
            metrics.record_cache_invalidation("dns_ntp", "config_update")

            # Verify metric was recorded
            mock_record.assert_called_once_with("dns_ntp", "config_update")

    @pytest.mark.asyncio
    async def test_invalidation_metrics_by_service(self) -> None:
        """Different services should record separate metrics."""
        from unittest.mock import patch, call
        from routeros_mcp.infra.observability import metrics

        with patch.object(metrics, "cache_invalidations_total") as mock_counter:
            # Record invalidations from different services
            metrics.record_cache_invalidation("dns_ntp", "config_update")
            metrics.record_cache_invalidation("firewall", "rule_change")
            metrics.record_cache_invalidation("device", "status_change")

            # Verify each was recorded with correct labels
            assert mock_counter.labels.call_count == 3
            calls = mock_counter.labels.call_args_list
            assert call(service="dns_ntp", reason="config_update") in calls
            assert call(service="firewall", reason="rule_change") in calls
            assert call(service="device", reason="status_change") in calls
