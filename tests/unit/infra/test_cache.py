"""Unit tests for Redis resource cache."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from routeros_mcp.infra.cache import (
    RedisResourceCache,
    RedisCacheError,
    get_redis_cache,
    initialize_redis_cache,
    reset_redis_cache,
)


class TestRedisResourceCache:
    """Tests for RedisResourceCache implementation."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client."""
        client = AsyncMock(spec=Redis)
        client.ping = AsyncMock()
        client.get = AsyncMock()
        client.setex = AsyncMock()
        client.delete = AsyncMock()
        client.aclose = AsyncMock()
        return client

    @pytest.fixture
    def cache(self) -> RedisResourceCache:
        """Create RedisResourceCache instance."""
        return RedisResourceCache(
            redis_url="redis://localhost:6379/0",
            ttl_interfaces=300,
            ttl_ips=300,
            ttl_routes=300,
            pool_size=5,
            timeout_seconds=3.0,
            key_prefix="test:",
            enabled=True,
        )

    @pytest.fixture
    def disabled_cache(self) -> RedisResourceCache:
        """Create disabled RedisResourceCache instance."""
        return RedisResourceCache(
            redis_url="redis://localhost:6379/0",
            enabled=False,
        )

    @pytest.mark.asyncio
    async def test_init_creates_connection(self, cache: RedisResourceCache) -> None:
        """init() should create Redis connection pool and client."""
        with (
            patch("routeros_mcp.infra.cache.ConnectionPool") as mock_pool_class,
            patch("routeros_mcp.infra.cache.Redis") as mock_redis_class,
        ):
            mock_pool = MagicMock()
            mock_pool_class.from_url.return_value = mock_pool

            mock_client = AsyncMock(spec=Redis)
            mock_client.ping = AsyncMock()
            mock_redis_class.return_value = mock_client

            await cache.init()

            # Verify pool creation
            mock_pool_class.from_url.assert_called_once_with(
                "redis://localhost:6379/0",
                max_connections=5,
                socket_timeout=3.0,
                socket_connect_timeout=3.0,
                decode_responses=True,
            )

            # Verify client creation and ping
            mock_redis_class.assert_called_once_with(connection_pool=mock_pool)
            mock_client.ping.assert_called_once()

    @pytest.mark.asyncio
    async def test_init_disabled_cache_skips_connection(
        self, disabled_cache: RedisResourceCache
    ) -> None:
        """init() should skip connection when cache is disabled."""
        with (
            patch("routeros_mcp.infra.cache.ConnectionPool") as mock_pool_class,
            patch("routeros_mcp.infra.cache.Redis") as mock_redis_class,
        ):
            await disabled_cache.init()

            # Verify no connection was created
            mock_pool_class.from_url.assert_not_called()
            mock_redis_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_init_failure_raises_error(self, cache: RedisResourceCache) -> None:
        """init() should raise RedisCacheError on connection failure."""
        with (
            patch("routeros_mcp.infra.cache.ConnectionPool"),
            patch("routeros_mcp.infra.cache.Redis") as mock_redis_class,
        ):
            mock_client = AsyncMock(spec=Redis)
            mock_client.ping = AsyncMock(side_effect=RedisError("Connection failed"))
            mock_redis_class.return_value = mock_client

            with pytest.raises(RedisCacheError, match="Failed to initialize Redis cache"):
                await cache.init()

    @pytest.mark.asyncio
    async def test_close_cleanup_resources(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """close() should cleanup Redis client and pool."""
        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()

        cache._client = mock_redis_client
        cache._pool = mock_pool

        await cache.close()

        mock_redis_client.aclose.assert_called_once()
        mock_pool.aclose.assert_called_once()
        assert cache._client is None
        assert cache._pool is None

    @pytest.mark.asyncio
    async def test_get_interfaces_cache_hit(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """get_interfaces() should return cached data on hit."""
        cache._client = mock_redis_client
        cache.enabled = True

        test_data = [
            {"name": "ether1", "type": "ether", "running": True},
            {"name": "ether2", "type": "ether", "running": False},
        ]
        mock_redis_client.get.return_value = json.dumps(test_data)

        result = await cache.get_interfaces("dev-lab-01")

        assert result == test_data
        mock_redis_client.get.assert_called_once_with("test:dev-lab-01:interfaces")

    @pytest.mark.asyncio
    async def test_get_interfaces_cache_miss(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """get_interfaces() should return None on cache miss."""
        cache._client = mock_redis_client
        cache.enabled = True

        mock_redis_client.get.return_value = None

        result = await cache.get_interfaces("dev-lab-01")

        assert result is None
        mock_redis_client.get.assert_called_once_with("test:dev-lab-01:interfaces")

    @pytest.mark.asyncio
    async def test_get_interfaces_disabled_cache(
        self, disabled_cache: RedisResourceCache
    ) -> None:
        """get_interfaces() should return None when cache is disabled."""
        result = await disabled_cache.get_interfaces("dev-lab-01")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_interfaces_redis_error(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """get_interfaces() should return None on Redis error."""
        cache._client = mock_redis_client
        cache.enabled = True

        mock_redis_client.get.side_effect = RedisError("Connection lost")

        result = await cache.get_interfaces("dev-lab-01")

        assert result is None

    @pytest.mark.asyncio
    async def test_set_interfaces(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """set_interfaces() should cache interface data with TTL."""
        cache._client = mock_redis_client
        cache.enabled = True

        test_data = [
            {"name": "ether1", "type": "ether", "running": True},
        ]

        await cache.set_interfaces("dev-lab-01", test_data)

        mock_redis_client.setex.assert_called_once_with(
            "test:dev-lab-01:interfaces",
            300,  # TTL
            json.dumps(test_data),
        )

    @pytest.mark.asyncio
    async def test_set_interfaces_disabled_cache(
        self, disabled_cache: RedisResourceCache
    ) -> None:
        """set_interfaces() should do nothing when cache is disabled."""
        # Should not raise any errors
        await disabled_cache.set_interfaces("dev-lab-01", [])

    @pytest.mark.asyncio
    async def test_get_ips_cache_hit(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """get_ips() should return cached IP data on hit."""
        cache._client = mock_redis_client
        cache.enabled = True

        test_data = [
            {"address": "192.168.1.1/24", "interface": "ether1"},
        ]
        mock_redis_client.get.return_value = json.dumps(test_data)

        result = await cache.get_ips("dev-lab-01")

        assert result == test_data
        mock_redis_client.get.assert_called_once_with("test:dev-lab-01:ips")

    @pytest.mark.asyncio
    async def test_set_ips(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """set_ips() should cache IP data with TTL."""
        cache._client = mock_redis_client
        cache.enabled = True

        test_data = [
            {"address": "192.168.1.1/24", "interface": "ether1"},
        ]

        await cache.set_ips("dev-lab-01", test_data)

        mock_redis_client.setex.assert_called_once_with(
            "test:dev-lab-01:ips",
            300,  # TTL
            json.dumps(test_data),
        )

    @pytest.mark.asyncio
    async def test_get_routes_cache_hit(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """get_routes() should return cached routing data on hit."""
        cache._client = mock_redis_client
        cache.enabled = True

        test_data = {"total_routes": 10, "static_routes": 5}
        mock_redis_client.get.return_value = json.dumps(test_data)

        result = await cache.get_routes("dev-lab-01")

        assert result == test_data
        mock_redis_client.get.assert_called_once_with("test:dev-lab-01:routes")

    @pytest.mark.asyncio
    async def test_set_routes(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """set_routes() should cache routing data with TTL."""
        cache._client = mock_redis_client
        cache.enabled = True

        test_data = {"total_routes": 10, "static_routes": 5}

        await cache.set_routes("dev-lab-01", test_data)

        mock_redis_client.setex.assert_called_once_with(
            "test:dev-lab-01:routes",
            300,  # TTL
            json.dumps(test_data),
        )

    @pytest.mark.asyncio
    async def test_invalidate_device(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """invalidate_device() should delete all resource keys for device."""
        cache._client = mock_redis_client
        cache.enabled = True

        mock_redis_client.delete.return_value = 3

        deleted = await cache.invalidate_device("dev-lab-01")

        assert deleted == 3
        mock_redis_client.delete.assert_called_once_with(
            "test:dev-lab-01:interfaces",
            "test:dev-lab-01:ips",
            "test:dev-lab-01:routes",
        )

    @pytest.mark.asyncio
    async def test_invalidate_device_disabled_cache(
        self, disabled_cache: RedisResourceCache
    ) -> None:
        """invalidate_device() should return 0 when cache is disabled."""
        deleted = await disabled_cache.invalidate_device("dev-lab-01")
        assert deleted == 0

    @pytest.mark.asyncio
    async def test_invalidate_device_redis_error(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """invalidate_device() should return 0 on Redis error."""
        cache._client = mock_redis_client
        cache.enabled = True

        mock_redis_client.delete.side_effect = RedisError("Connection lost")

        deleted = await cache.invalidate_device("dev-lab-01")

        assert deleted == 0

    @pytest.mark.asyncio
    async def test_invalidate_resource(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """invalidate_resource() should delete specific resource key."""
        cache._client = mock_redis_client
        cache.enabled = True

        mock_redis_client.delete.return_value = 1

        result = await cache.invalidate_resource("dev-lab-01", "interfaces")

        assert result is True
        mock_redis_client.delete.assert_called_once_with("test:dev-lab-01:interfaces")

    @pytest.mark.asyncio
    async def test_invalidate_resource_not_found(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """invalidate_resource() should return False when key not found."""
        cache._client = mock_redis_client
        cache.enabled = True

        mock_redis_client.delete.return_value = 0

        result = await cache.invalidate_resource("dev-lab-01", "interfaces")

        assert result is False


class TestRedisResourceCacheGlobal:
    """Tests for global cache instance management."""

    @pytest.fixture(autouse=True)
    def reset_cache(self) -> None:
        """Reset global cache before and after each test."""
        reset_redis_cache()
        yield
        reset_redis_cache()

    def test_get_redis_cache_not_initialized(self) -> None:
        """get_redis_cache() should raise error when not initialized."""
        with pytest.raises(RuntimeError, match="RedisResourceCache not initialized"):
            get_redis_cache()

    def test_initialize_redis_cache(self) -> None:
        """initialize_redis_cache() should create global instance."""
        cache = initialize_redis_cache(
            redis_url="redis://localhost:6379/0",
            ttl_interfaces=300,
            ttl_ips=300,
            ttl_routes=300,
        )

        assert cache is not None
        assert cache.ttl_interfaces == 300
        assert cache.ttl_ips == 300
        assert cache.ttl_routes == 300

        # Should be able to get the same instance
        assert get_redis_cache() is cache

    def test_reset_redis_cache(self) -> None:
        """reset_redis_cache() should clear global instance."""
        initialize_redis_cache(redis_url="redis://localhost:6379/0")

        reset_redis_cache()

        with pytest.raises(RuntimeError, match="RedisResourceCache not initialized"):
            get_redis_cache()


class TestRedisResourceCacheIntegration:
    """Integration tests for cache with multiple operations."""

    @pytest.fixture
    def cache(self) -> RedisResourceCache:
        """Create RedisResourceCache instance."""
        return RedisResourceCache(
            redis_url="redis://localhost:6379/0",
            ttl_interfaces=300,
            ttl_ips=300,
            ttl_routes=300,
            enabled=True,
        )

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client."""
        client = AsyncMock(spec=Redis)
        client.ping = AsyncMock()
        client.get = AsyncMock()
        client.setex = AsyncMock()
        client.delete = AsyncMock()
        return client

    @pytest.mark.asyncio
    async def test_cache_workflow(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """Test complete cache workflow: set, get, invalidate."""
        cache._client = mock_redis_client
        cache.enabled = True

        # Set interface data
        interfaces = [{"name": "ether1", "type": "ether"}]
        await cache.set_interfaces("dev-lab-01", interfaces)
        mock_redis_client.setex.assert_called_once()

        # Get interface data (cache hit)
        mock_redis_client.get.return_value = json.dumps(interfaces)
        result = await cache.get_interfaces("dev-lab-01")
        assert result == interfaces

        # Set IP data
        ips = [{"address": "192.168.1.1/24"}]
        await cache.set_ips("dev-lab-01", ips)

        # Invalidate device cache
        mock_redis_client.delete.return_value = 2
        deleted = await cache.invalidate_device("dev-lab-01")
        assert deleted == 2

        # Get should return None after invalidation (cache miss)
        mock_redis_client.get.return_value = None
        result = await cache.get_interfaces("dev-lab-01")
        assert result is None

    @pytest.mark.asyncio
    async def test_multiple_devices(
        self, cache: RedisResourceCache, mock_redis_client: AsyncMock
    ) -> None:
        """Test caching data for multiple devices."""
        cache._client = mock_redis_client
        cache.enabled = True

        # Cache data for device 1
        interfaces1 = [{"name": "ether1"}]
        await cache.set_interfaces("dev-lab-01", interfaces1)

        # Cache data for device 2
        interfaces2 = [{"name": "ether2"}]
        await cache.set_interfaces("dev-lab-02", interfaces2)

        # Both should be cached with different keys
        assert mock_redis_client.setex.call_count == 2

        # Invalidate device 1
        mock_redis_client.delete.return_value = 3
        deleted = await cache.invalidate_device("dev-lab-01")
        assert deleted == 3

        # Device 2 cache should still be intact
        mock_redis_client.get.return_value = json.dumps(interfaces2)
        result = await cache.get_interfaces("dev-lab-02")
        assert result == interfaces2
