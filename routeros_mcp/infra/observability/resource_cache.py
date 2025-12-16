"""TTL-based resource caching layer with LRU eviction.

Provides in-memory caching for MCP resource responses to reduce RouterOS load
and improve response time. Features include:
- Configurable TTL (time-to-live) for cache entries
- LRU (Least Recently Used) eviction when max entries exceeded
- Thread-safe async operations using asyncio locks
- Prometheus metrics for cache hits, misses, and evictions

See docs/08-observability-logging-metrics-and-diagnostics.md for metrics design.
"""

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Callable, Optional, TypeVar

from routeros_mcp.infra.observability import metrics

logger = logging.getLogger(__name__)

# Type variable for decorated function
F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class CacheEntry:
    """Cache entry with value, TTL, and access time."""

    value: str
    expires_at: float
    created_at: float
    last_accessed: float


class ResourceCache:
    """In-memory cache with TTL and LRU eviction.

    Thread-safe cache implementation using asyncio locks for concurrent access.
    Entries are keyed by resource URI and optional resource identifier
    (e.g., device_id, plan_id, user_sub).

    Example:
        cache = ResourceCache(ttl_seconds=300, max_entries=1000)
        await cache.set("device://dev1/overview", "value_data", "dev1")
        result = await cache.get("device://dev1/overview", "dev1")
    """

    def __init__(
        self,
        ttl_seconds: int = 300,
        max_entries: int = 1000,
        enabled: bool = True,
    ) -> None:
        """Initialize cache.

        Args:
            ttl_seconds: Time-to-live for cache entries in seconds
            max_entries: Maximum number of cache entries (LRU eviction)
            enabled: Whether caching is enabled
        """
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = asyncio.Lock()

        logger.info(
            f"ResourceCache initialized: enabled={enabled}, "
            f"ttl={ttl_seconds}s, max_entries={max_entries}"
        )

    def _make_key(self, resource_uri: str, resource_id: Optional[str] = None) -> str:
        """Create cache key from resource URI and optional resource identifier.

        Args:
            resource_uri: Resource URI (e.g., "device://dev1/overview")
            resource_id: Optional resource identifier (device_id, plan_id, user_sub, etc.)

        Returns:
            Cache key in format "{resource_uri}:{resource_id}" or "{resource_uri}"
        """
        if resource_id:
            return f"{resource_uri}:{resource_id}"
        return resource_uri

    async def get(
        self, resource_uri: str, resource_id: Optional[str] = None
    ) -> Optional[str]:
        """Get cached value if available and not expired.

        Args:
            resource_uri: Resource URI
            resource_id: Optional resource identifier (device_id, plan_id, user_sub, etc.)

        Returns:
            Cached value or None if not found or expired
        """
        if not self._enabled:
            return None

        key = self._make_key(resource_uri, resource_id)

        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                # Record cache miss metric
                metrics.record_cache_miss(resource_uri)
                return None

            # Check expiration
            now = time.time()
            if now >= entry.expires_at:
                # Entry expired, remove it
                del self._cache[key]
                metrics.update_cache_size(len(self._cache))
                logger.debug(f"Cache entry expired: {key}")
                # Record cache miss for expired entries
                metrics.record_cache_miss(resource_uri)
                return None

            # Update last accessed time and move to end (LRU)
            entry.last_accessed = now
            self._cache.move_to_end(key)

            # Record cache hit metric
            metrics.record_cache_hit(resource_uri)

            logger.debug(f"Cache hit: {key}")
            return entry.value

    async def set(
        self, resource_uri: str, value: str, resource_id: Optional[str] = None
    ) -> None:
        """Store value in cache with TTL.

        Args:
            resource_uri: Resource URI
            value: Value to cache
            resource_id: Optional resource identifier (device_id, plan_id, user_sub, etc.)
        """
        if not self._enabled:
            return

        key = self._make_key(resource_uri, resource_id)
        now = time.time()

        async with self._lock:
            # Check if we need to evict (LRU)
            if len(self._cache) >= self._max_entries and key not in self._cache:
                # Remove oldest entry (first item in OrderedDict)
                evicted_key = next(iter(self._cache))
                del self._cache[evicted_key]
                metrics.record_cache_eviction()
                logger.debug(f"Cache LRU eviction: {evicted_key}")

            # Store entry
            entry = CacheEntry(
                value=value,
                expires_at=now + self._ttl_seconds,
                created_at=now,
                last_accessed=now,
            )
            self._cache[key] = entry
            # Move to end (most recently used)
            self._cache.move_to_end(key)

            # Update cache size metric
            metrics.update_cache_size(len(self._cache))

            logger.debug(f"Cache set: {key} (ttl={self._ttl_seconds}s)")

    async def invalidate(
        self, resource_uri: str, resource_id: Optional[str] = None
    ) -> bool:
        """Invalidate (remove) a cache entry.

        Args:
            resource_uri: Resource URI
            resource_id: Optional resource identifier (device_id, plan_id, user_sub, etc.)

        Returns:
            True if entry was found and removed, False otherwise
        """
        if not self._enabled:
            return False

        key = self._make_key(resource_uri, resource_id)

        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Cache invalidated: {key}")
                return True
            return False

    async def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cache cleared: {count} entries removed")
            return count

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        async with self._lock:
            now = time.time()
            expired_count = sum(
                1 for entry in self._cache.values() if now >= entry.expires_at
            )

            return {
                "enabled": self._enabled,
                "total_entries": len(self._cache),
                "expired_entries": expired_count,
                "max_entries": self._max_entries,
                "ttl_seconds": self._ttl_seconds,
            }

    async def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of expired entries removed
        """
        async with self._lock:
            now = time.time()
            expired_keys = [
                key
                for key, entry in self._cache.items()
                if now >= entry.expires_at
            ]

            for key in expired_keys:
                del self._cache[key]

            if expired_keys:
                logger.debug(f"Cache cleanup: removed {len(expired_keys)} expired entries")

            return len(expired_keys)


# Global cache instance (initialized by application)
_cache_instance: Optional[ResourceCache] = None


def get_cache() -> ResourceCache:
    """Get global cache instance.

    Returns:
        Global ResourceCache instance

    Raises:
        RuntimeError: If cache not initialized
    """
    if _cache_instance is None:
        raise RuntimeError("ResourceCache not initialized. Call initialize_cache() first.")
    return _cache_instance


def initialize_cache(
    ttl_seconds: int = 300,
    max_entries: int = 1000,
    enabled: bool = True,
) -> ResourceCache:
    """Initialize global cache instance.

    Args:
        ttl_seconds: Time-to-live for cache entries
        max_entries: Maximum number of cache entries
        enabled: Whether caching is enabled

    Returns:
        Initialized ResourceCache instance
    """
    global _cache_instance
    _cache_instance = ResourceCache(
        ttl_seconds=ttl_seconds,
        max_entries=max_entries,
        enabled=enabled,
    )
    logger.info("Global ResourceCache initialized")
    return _cache_instance


def with_cache(resource_uri: str) -> Callable[[F], F]:
    """Decorator to add caching to resource providers.

    This decorator wraps resource provider functions to automatically cache
    their results. The cache key is built from the resource URI and the
    first parameter extracted from the URI template (e.g., device_id, plan_id, user_sub).

    If the cache is not initialized (e.g., in tests), the decorator will
    skip caching and call the function directly.

    Args:
        resource_uri: Resource URI template (e.g., "device://{device_id}/overview",
                     "plan://{plan_id}/summary", "audit://events/by-user/{user_sub}")

    Returns:
        Decorator function

    Example:
        @with_cache("device://{device_id}/overview")
        async def device_overview(device_id: str) -> str:
            # Expensive RouterOS call here
            return result
            
        @with_cache("plan://{plan_id}/summary")
        async def plan_summary(plan_id: str) -> str:
            # Cached by plan_id
            return result
    """
    from functools import wraps
    import time as time_module
    import re

    # Extract parameter name from URI template (e.g., "{device_id}" -> "device_id")
    param_match = re.search(r'\{(\w+)\}', resource_uri)
    param_name = param_match.group(1) if param_match else None

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Try to get cache, but gracefully handle if not initialized
            try:
                cache = get_cache()
            except RuntimeError:
                # Cache not initialized (e.g., in tests), skip caching
                return await func(*args, **kwargs)

            # Extract resource_id from arguments based on parameter name
            resource_id = None
            if param_name:
                # Try to get from kwargs first, then from first positional arg
                resource_id = kwargs.get(param_name) or (args[0] if args else None)

            # Build actual resource URI by replacing parameter placeholder
            actual_uri = resource_uri
            if resource_id and param_name:
                actual_uri = resource_uri.replace(f"{{{param_name}}}", str(resource_id))

            # Try to get from cache
            start_time = time_module.time()

            cached_value = await cache.get(actual_uri, resource_id)
            if cached_value is not None:
                duration = time_module.time() - start_time
                metrics.record_cache_fetch(actual_uri, duration, cache_hit=True)
                return cached_value

            # Cache miss - call the actual function
            result = await func(*args, **kwargs)

            # Store in cache
            await cache.set(actual_uri, result, resource_id)

            duration = time_module.time() - start_time
            metrics.record_cache_fetch(actual_uri, duration, cache_hit=False)

            return result

        return wrapper  # type: ignore[return-value]

    return decorator  # type: ignore[return-value]


__all__ = [
    "ResourceCache",
    "CacheEntry",
    "get_cache",
    "initialize_cache",
    "with_cache",
]
