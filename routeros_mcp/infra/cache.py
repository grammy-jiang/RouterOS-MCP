"""Redis-backed cache for device resource data.

Provides distributed caching for device resources (interfaces, IPs, routes)
with configurable TTL per resource type. Supports cache invalidation on
device updates and plan execution.

Example:
    cache = RedisResourceCache(
        redis_url=settings.redis_url,
        ttl_interfaces=300,
        ttl_ips=300,
        ttl_routes=300,
    )
    await cache.init()
    
    # Cache interface data
    await cache.set_interfaces("dev-lab-01", interfaces_data)
    
    # Retrieve cached data
    cached = await cache.get_interfaces("dev-lab-01")
    
    # Invalidate device cache
    await cache.invalidate_device("dev-lab-01")
"""

import json
import logging
from typing import Any

from prometheus_client import Counter, Histogram
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from routeros_mcp.infra.observability.metrics import _registry

logger = logging.getLogger(__name__)

# Metrics for cache operations
redis_cache_operations_total = Counter(
    "routeros_mcp_redis_cache_operations_total",
    "Total number of Redis cache operations",
    ["operation", "resource_type", "status"],
    registry=_registry,
)

redis_cache_operation_duration_seconds = Histogram(
    "routeros_mcp_redis_cache_operation_duration_seconds",
    "Duration of Redis cache operations in seconds",
    ["operation", "resource_type"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=_registry,
)


class RedisCacheError(Exception):
    """Base exception for Redis cache errors."""
    pass


class RedisResourceCache:
    """Redis-backed cache for device resource data.
    
    Provides distributed caching with per-resource-type TTL configuration.
    Supports automatic cache invalidation on device updates.
    
    Resource types:
    - interfaces: Network interface data
    - ips: IP address assignments
    - routes: Routing table entries
    """

    def __init__(
        self,
        redis_url: str,
        ttl_interfaces: int = 300,
        ttl_ips: int = 300,
        ttl_routes: int = 300,
        pool_size: int = 10,
        timeout_seconds: float = 5.0,
        key_prefix: str = "resource:",
        enabled: bool = True,
    ) -> None:
        """Initialize Redis resource cache.
        
        Args:
            redis_url: Redis connection URL
            ttl_interfaces: TTL for interface data (seconds)
            ttl_ips: TTL for IP address data (seconds)
            ttl_routes: TTL for routing data (seconds)
            pool_size: Connection pool size
            timeout_seconds: Operation timeout
            key_prefix: Redis key prefix for cache entries
            enabled: Whether caching is enabled
        """
        self.redis_url = redis_url
        self.ttl_interfaces = ttl_interfaces
        self.ttl_ips = ttl_ips
        self.ttl_routes = ttl_routes
        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds
        self.key_prefix = key_prefix
        self.enabled = enabled

        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

        logger.info(
            "RedisResourceCache initialized",
            extra={
                "enabled": enabled,
                "ttl_interfaces": ttl_interfaces,
                "ttl_ips": ttl_ips,
                "ttl_routes": ttl_routes,
            },
        )

    async def init(self) -> None:
        """Initialize Redis connection pool and client.
        
        Raises:
            RedisCacheError: If connection fails
        """
        if not self.enabled:
            logger.info("Redis cache disabled, skipping initialization")
            return

        try:
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.pool_size,
                socket_timeout=self.timeout_seconds,
                socket_connect_timeout=self.timeout_seconds,
                decode_responses=True,
            )

            self._client = Redis(connection_pool=self._pool)

            # Test connection
            await self._client.ping()

            logger.info("Redis cache connection established")

        except RedisError as e:
            logger.error(f"Failed to initialize Redis cache: {e}")
            raise RedisCacheError(f"Failed to initialize Redis cache: {e}") from e

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self._client:
            await self._client.aclose()
            self._client = None

        if self._pool:
            await self._pool.aclose()
            self._pool = None

        logger.info("Redis cache connection closed")

    def _make_key(self, device_id: str, resource_type: str) -> str:
        """Create cache key for device resource.
        
        Args:
            device_id: Device identifier
            resource_type: Resource type (interfaces, ips, routes)
        
        Returns:
            Redis key in format "resource:{device_id}:{resource_type}"
        """
        return f"{self.key_prefix}{device_id}:{resource_type}"

    async def get_interfaces(self, device_id: str) -> list[dict[str, Any]] | None:
        """Get cached interface data for device.
        
        Args:
            device_id: Device identifier
        
        Returns:
            Cached interface data or None if not found
        """
        return await self._get(device_id, "interfaces")

    async def set_interfaces(
        self, device_id: str, data: list[dict[str, Any]]
    ) -> None:
        """Cache interface data for device.
        
        Args:
            device_id: Device identifier
            data: Interface data to cache
        """
        await self._set(device_id, "interfaces", data, self.ttl_interfaces)

    async def get_ips(self, device_id: str) -> list[dict[str, Any]] | None:
        """Get cached IP address data for device.
        
        Args:
            device_id: Device identifier
        
        Returns:
            Cached IP address data or None if not found
        """
        return await self._get(device_id, "ips")

    async def set_ips(
        self, device_id: str, data: list[dict[str, Any]]
    ) -> None:
        """Cache IP address data for device.
        
        Args:
            device_id: Device identifier
            data: IP address data to cache
        """
        await self._set(device_id, "ips", data, self.ttl_ips)

    async def get_routes(self, device_id: str) -> dict[str, Any] | None:
        """Get cached routing data for device.
        
        Args:
            device_id: Device identifier
        
        Returns:
            Cached routing data or None if not found
        """
        return await self._get(device_id, "routes")

    async def set_routes(
        self, device_id: str, data: dict[str, Any]
    ) -> None:
        """Cache routing data for device.
        
        Args:
            device_id: Device identifier
            data: Routing data to cache
        """
        await self._set(device_id, "routes", data, self.ttl_routes)

    async def _get(
        self, device_id: str, resource_type: str
    ) -> Any | None:
        """Get cached data for device resource.
        
        Args:
            device_id: Device identifier
            resource_type: Resource type (interfaces, ips, routes)
        
        Returns:
            Cached data or None if not found or expired
        """
        if not self.enabled or not self._client:
            return None

        key = self._make_key(device_id, resource_type)

        try:
            import time
            start_time = time.time()

            value = await self._client.get(key)

            duration = time.time() - start_time
            redis_cache_operation_duration_seconds.labels(
                operation="get",
                resource_type=resource_type,
            ).observe(duration)

            if value is None:
                redis_cache_operations_total.labels(
                    operation="get",
                    resource_type=resource_type,
                    status="miss",
                ).inc()
                logger.debug(f"Cache miss: {key}")
                return None

            redis_cache_operations_total.labels(
                operation="get",
                resource_type=resource_type,
                status="hit",
            ).inc()

            logger.debug(f"Cache hit: {key}")
            return json.loads(value)

        except (RedisError, json.JSONDecodeError) as e:
            redis_cache_operations_total.labels(
                operation="get",
                resource_type=resource_type,
                status="error",
            ).inc()
            logger.warning(f"Cache get error for {key}: {e}")
            return None

    async def _set(
        self,
        device_id: str,
        resource_type: str,
        data: Any,
        ttl_seconds: int,
    ) -> None:
        """Cache data for device resource.
        
        Args:
            device_id: Device identifier
            resource_type: Resource type (interfaces, ips, routes)
            data: Data to cache
            ttl_seconds: Time-to-live in seconds
        """
        if not self.enabled or not self._client:
            return

        key = self._make_key(device_id, resource_type)

        try:
            import time
            start_time = time.time()

            value = json.dumps(data)
            await self._client.setex(key, ttl_seconds, value)

            duration = time.time() - start_time
            redis_cache_operation_duration_seconds.labels(
                operation="set",
                resource_type=resource_type,
            ).observe(duration)

            redis_cache_operations_total.labels(
                operation="set",
                resource_type=resource_type,
                status="success",
            ).inc()

            logger.debug(f"Cache set: {key} (ttl={ttl_seconds}s)")

        except (RedisError, TypeError) as e:
            redis_cache_operations_total.labels(
                operation="set",
                resource_type=resource_type,
                status="error",
            ).inc()
            logger.warning(f"Cache set error for {key}: {e}")

    async def invalidate_device(self, device_id: str) -> int:
        """Invalidate all cached data for a device.
        
        Args:
            device_id: Device identifier
        
        Returns:
            Number of keys deleted
        """
        if not self.enabled or not self._client:
            return 0

        try:
            import time
            start_time = time.time()

            # Delete all resource types for this device
            keys = [
                self._make_key(device_id, "interfaces"),
                self._make_key(device_id, "ips"),
                self._make_key(device_id, "routes"),
            ]

            deleted = await self._client.delete(*keys)

            duration = time.time() - start_time
            redis_cache_operation_duration_seconds.labels(
                operation="invalidate",
                resource_type="all",
            ).observe(duration)

            redis_cache_operations_total.labels(
                operation="invalidate",
                resource_type="all",
                status="success",
            ).inc()

            logger.info(
                f"Invalidated cache for device: {device_id} ({deleted} keys)",
                extra={"device_id": device_id, "deleted_keys": deleted},
            )

            return deleted

        except RedisError as e:
            redis_cache_operations_total.labels(
                operation="invalidate",
                resource_type="all",
                status="error",
            ).inc()
            logger.warning(f"Cache invalidation error for {device_id}: {e}")
            return 0

    async def invalidate_resource(
        self, device_id: str, resource_type: str
    ) -> bool:
        """Invalidate cached data for a specific device resource.
        
        Args:
            device_id: Device identifier
            resource_type: Resource type (interfaces, ips, routes)
        
        Returns:
            True if key was deleted, False otherwise
        """
        if not self.enabled or not self._client:
            return False

        key = self._make_key(device_id, resource_type)

        try:
            deleted = await self._client.delete(key)

            redis_cache_operations_total.labels(
                operation="invalidate",
                resource_type=resource_type,
                status="success" if deleted > 0 else "not_found",
            ).inc()

            if deleted > 0:
                logger.info(f"Invalidated cache: {key}")

            return deleted > 0

        except RedisError as e:
            redis_cache_operations_total.labels(
                operation="invalidate",
                resource_type=resource_type,
                status="error",
            ).inc()
            logger.warning(f"Cache invalidation error for {key}: {e}")
            return False


# Global cache instance
_cache_instance: RedisResourceCache | None = None


def get_redis_cache() -> RedisResourceCache:
    """Get global Redis cache instance.
    
    Returns:
        Global RedisResourceCache instance
    
    Raises:
        RuntimeError: If cache not initialized
    """
    if _cache_instance is None:
        raise RuntimeError("RedisResourceCache not initialized. Call initialize_redis_cache() first.")
    return _cache_instance


def initialize_redis_cache(
    redis_url: str,
    ttl_interfaces: int = 300,
    ttl_ips: int = 300,
    ttl_routes: int = 300,
    pool_size: int = 10,
    timeout_seconds: float = 5.0,
    enabled: bool = True,
) -> RedisResourceCache:
    """Initialize global Redis cache instance.
    
    Args:
        redis_url: Redis connection URL
        ttl_interfaces: TTL for interface data
        ttl_ips: TTL for IP address data
        ttl_routes: TTL for routing data
        pool_size: Connection pool size
        timeout_seconds: Operation timeout
        enabled: Whether caching is enabled
    
    Returns:
        Initialized RedisResourceCache instance
    """
    global _cache_instance
    _cache_instance = RedisResourceCache(
        redis_url=redis_url,
        ttl_interfaces=ttl_interfaces,
        ttl_ips=ttl_ips,
        ttl_routes=ttl_routes,
        pool_size=pool_size,
        timeout_seconds=timeout_seconds,
        enabled=enabled,
    )
    logger.info("Global RedisResourceCache initialized")
    return _cache_instance


def reset_redis_cache() -> None:
    """Reset the global Redis cache instance (primarily for testing)."""
    global _cache_instance
    _cache_instance = None


__all__ = [
    "RedisResourceCache",
    "RedisCacheError",
    "get_redis_cache",
    "initialize_redis_cache",
    "reset_redis_cache",
]
