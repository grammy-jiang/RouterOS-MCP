"""Rate limiting for MCP tool execution with Redis backend.

Implements token bucket rate limiting per user/role with configurable limits.
Supports both in-memory (for lab/testing) and Redis-backed (for production)
storage to enable horizontal scaling across multiple service instances.

Rate limits by role:
- read_only: 10 requests/minute (configurable)
- ops_rw: 5 requests/minute (configurable)
- admin: unlimited (configurable, 0 = unlimited)
- approver: 5 requests/minute (configurable)

Example:
    # Redis-backed rate limiter (production)
    limiter = RateLimitStore(
        redis_url="redis://localhost:6379/0",
        pool_size=10,
        timeout_seconds=5.0,
        window_seconds=60,
    )
    await limiter.init()

    # Check and record
    await limiter.check_and_record(
        user_id="user-123",
        role="ops_rw",
        limit=5,
    )

See issue grammy-jiang/RouterOS-MCP#13 (Phase 5).
"""

import asyncio
import logging
import time
from collections import defaultdict

from prometheus_client import Counter, Histogram
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from routeros_mcp.infra.observability.metrics import _registry
from routeros_mcp.mcp.errors import RateLimitExceededError

logger = logging.getLogger(__name__)

# Constants
UNLIMITED_RATE_LIMIT = 999999  # Value representing unlimited rate limit quota

# Metrics for rate limiting operations
rate_limit_operations_total = Counter(
    "routeros_mcp_rate_limit_operations_total",
    "Total number of rate limit check operations",
    ["operation", "status", "role"],
    registry=_registry,
)

rate_limit_operation_duration_seconds = Histogram(
    "routeros_mcp_rate_limit_operation_duration_seconds",
    "Duration of rate limit operations in seconds",
    ["operation", "backend"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=_registry,
)

rate_limit_exceeded_total = Counter(
    "routeros_mcp_rate_limit_exceeded_total",
    "Total number of rate limit exceeded events",
    ["role"],
    registry=_registry,
)


class RateLimitStore:
    """Rate limit storage with Redis backend for distributed rate limiting.

    Implements token bucket algorithm with sliding window for accurate
    rate limiting across multiple service instances.

    Attributes:
        redis_url: Redis connection URL
        pool_size: Connection pool size
        timeout_seconds: Operation timeout
        window_seconds: Rate limit time window
    """

    def __init__(
        self,
        redis_url: str,
        pool_size: int = 10,
        timeout_seconds: float = 5.0,
        window_seconds: int = 60,
    ) -> None:
        """Initialize rate limit store with Redis backend.

        Args:
            redis_url: Redis connection URL
            pool_size: Connection pool size
            timeout_seconds: Redis operation timeout
            window_seconds: Rate limit time window in seconds
        """
        self.redis_url = redis_url
        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds
        self.window_seconds = window_seconds
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None
        self._initialized = False

    async def init(self) -> None:
        """Initialize Redis connection pool.

        Must be called before using the store.

        Raises:
            RedisError: If connection fails
        """
        if self._initialized:
            logger.warning("RateLimitStore already initialized, skipping")
            return

        try:
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.pool_size,
                socket_timeout=self.timeout_seconds,
                socket_connect_timeout=self.timeout_seconds,
                decode_responses=True,
            )
            self._redis = Redis(connection_pool=self._pool)

            # Test connection
            await self._redis.ping()

            self._initialized = True
            logger.info(
                "Rate limit store initialized with Redis backend",
                extra={
                    "redis_url": self.redis_url,
                    "pool_size": self.pool_size,
                    "window_seconds": self.window_seconds,
                },
            )
        except RedisError as e:
            logger.error(f"Failed to initialize Redis rate limit store: {e}")
            raise

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None
        self._initialized = False
        logger.info("Rate limit store closed")

    def _get_key(self, user_id: str, role: str) -> str:
        """Generate Redis key for user rate limit.

        Args:
            user_id: User identifier
            role: User role

        Returns:
            Redis key string
        """
        return f"rate_limit:{role}:{user_id}"

    async def check_and_record(
        self,
        user_id: str,
        role: str,
        limit: int,
    ) -> None:
        """Check rate limit and record request if allowed.

        Uses Redis sorted sets with timestamps for sliding window.

        Args:
            user_id: User identifier
            role: User role (read_only, ops_rw, admin, approver)
            limit: Maximum requests allowed in window (0 = unlimited)

        Raises:
            RateLimitExceededError: If rate limit exceeded
            RedisError: If Redis operation fails
        """
        if not self._initialized or not self._redis:
            raise RuntimeError("RateLimitStore not initialized. Call init() first.")

        # Admin with 0 limit = unlimited
        if limit == 0:
            rate_limit_operations_total.labels(operation="check", status="allowed", role=role).inc()
            logger.debug(f"Rate limit bypassed for {role} (unlimited)")
            return

        start_time = time.time()
        key = self._get_key(user_id, role)
        now = time.time()
        cutoff = now - self.window_seconds

        try:
            # Use Redis Lua script for atomic check-and-increment
            # This prevents race conditions where concurrent requests could exceed the limit
            lua_script = """
            local key = KEYS[1]
            local now = tonumber(ARGV[1])
            local cutoff = tonumber(ARGV[2])
            local limit = tonumber(ARGV[3])
            local window = tonumber(ARGV[4])

            -- Remove old entries outside window
            redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)

            -- Count current requests in window
            local current = redis.call('ZCARD', key)

            -- Check if limit exceeded
            if current >= limit then
                -- Get oldest timestamp for retry-after calculation
                local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
                local retry_after = 0
                if #oldest > 0 then
                    retry_after = math.floor(oldest[2] + window - now)
                end
                return {0, current, retry_after}  -- exceeded
            end

            -- Record this request with current timestamp
            redis.call('ZADD', key, now, tostring(now))

            -- Set expiry on key (cleanup after window + buffer)
            redis.call('EXPIRE', key, window + 60)

            return {1, current + 1, 0}  -- allowed
            """

            # Execute atomic Lua script
            result = await self._redis.eval(
                lua_script,
                1,  # number of keys
                key,  # KEYS[1]
                now,  # ARGV[1]
                cutoff,  # ARGV[2]
                limit,  # ARGV[3]
                self.window_seconds,  # ARGV[4]
            )

            allowed, current_count, retry_after = result

            # Check if limit exceeded
            if allowed == 0:
                rate_limit_exceeded_total.labels(role=role).inc()
                rate_limit_operations_total.labels(
                    operation="check", status="exceeded", role=role
                ).inc()

                raise RateLimitExceededError(
                    f"Rate limit exceeded for role '{role}': "
                    f"{limit} requests per {self.window_seconds} seconds",
                    data={
                        "user_id": user_id,
                        "role": role,
                        "limit": limit,
                        "window_seconds": self.window_seconds,
                        "current_count": int(current_count),
                        "retry_after_seconds": max(1, int(retry_after)),
                    },
                )

            rate_limit_operations_total.labels(operation="check", status="allowed", role=role).inc()

            duration = time.time() - start_time
            rate_limit_operation_duration_seconds.labels(
                operation="check", backend="redis"
            ).observe(duration)

            logger.debug(
                f"Rate limit check passed: {role} user {user_id} "
                f"({int(current_count)}/{limit} in {self.window_seconds}s window)"
            )

        except RateLimitExceededError:
            raise
        except RedisError as e:
            logger.error(
                f"Redis error during rate limit check: {e}",
                extra={"user_id": user_id, "role": role},
            )
            # Fail-closed: block requests when Redis is unavailable to maintain rate limiting
            # This prevents bypassing rate limits during Redis outages but may cause service
            # disruption if Redis is down. For fail-open behavior, return success here instead.
            rate_limit_operations_total.labels(operation="check", status="error", role=role).inc()
            raise

    async def get_remaining(
        self,
        user_id: str,
        role: str,
        limit: int,
    ) -> int:
        """Get remaining requests allowed in current window.

        Args:
            user_id: User identifier
            role: User role
            limit: Maximum requests allowed

        Returns:
            Number of requests remaining (0 = no quota left)
        """
        if not self._initialized or not self._redis:
            raise RuntimeError("RateLimitStore not initialized. Call init() first.")

        # Unlimited access
        if limit == 0:
            return UNLIMITED_RATE_LIMIT

        key = self._get_key(user_id, role)
        now = time.time()
        cutoff = now - self.window_seconds

        try:
            # Remove expired entries and count current
            pipe = self._redis.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            results = await pipe.execute()
            current_count = int(results[1])

            return max(0, limit - current_count)

        except RedisError as e:
            logger.error(
                f"Redis error getting remaining quota: {e}",
                extra={"user_id": user_id, "role": role},
            )
            # On error, return 0 to be safe
            return 0

    async def reset(
        self,
        user_id: str | None = None,
        role: str | None = None,
    ) -> None:
        """Reset rate limit records.

        Args:
            user_id: If provided, reset only this user
            role: If provided, reset only this role
        """
        if not self._initialized or not self._redis:
            raise RuntimeError("RateLimitStore not initialized. Call init() first.")

        try:
            if user_id and role:
                # Reset specific user+role
                key = self._get_key(user_id, role)
                await self._redis.delete(key)
                logger.info(f"Reset rate limit for user {user_id} role {role}")
            elif role:
                # Reset all users with this role
                pattern = f"rate_limit:{role}:*"
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
                logger.info(f"Reset rate limit for all users with role {role}")
            elif user_id:
                # Reset all roles for this user
                pattern = f"rate_limit:*:{user_id}"
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
                logger.info(f"Reset rate limit for user {user_id} all roles")
            else:
                # Reset all rate limits
                pattern = "rate_limit:*"
                cursor = 0
                while True:
                    cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                    if keys:
                        await self._redis.delete(*keys)
                    if cursor == 0:
                        break
                logger.info("Reset all rate limits")

        except RedisError as e:
            logger.error(f"Redis error during reset: {e}")
            raise


class InMemoryRateLimitStore:
    """In-memory rate limit store for lab/testing environments.

    Uses local dictionary for rate limit tracking. Not suitable for
    multi-instance deployments as state is not shared.
    """

    def __init__(self, window_seconds: int = 60) -> None:
        """Initialize in-memory rate limit store.

        Args:
            window_seconds: Rate limit time window in seconds
        """
        self.window_seconds = window_seconds
        self._records: dict[tuple[str, str], list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._initialized = True

    async def init(self) -> None:
        """Initialize store (no-op for in-memory)."""
        logger.info("In-memory rate limit store initialized")

    async def close(self) -> None:
        """Close store (no-op for in-memory)."""
        self._records.clear()
        logger.info("In-memory rate limit store closed")

    async def check_and_record(
        self,
        user_id: str,
        role: str,
        limit: int,
    ) -> None:
        """Check rate limit and record request if allowed.

        Args:
            user_id: User identifier
            role: User role
            limit: Maximum requests allowed (0 = unlimited)

        Raises:
            RateLimitExceededError: If rate limit exceeded
        """
        # Admin with 0 limit = unlimited
        if limit == 0:
            rate_limit_operations_total.labels(operation="check", status="allowed", role=role).inc()
            return

        start_time = time.time()

        async with self._lock:
            key = (user_id, role)
            now = time.time()
            cutoff = now - self.window_seconds

            # Remove old records
            self._records[key] = [ts for ts in self._records[key] if ts > cutoff]

            # Check limit
            if len(self._records[key]) >= limit:
                rate_limit_exceeded_total.labels(role=role).inc()
                rate_limit_operations_total.labels(
                    operation="check", status="exceeded", role=role
                ).inc()

                # Calculate retry-after from oldest timestamp
                retry_after = 0
                if self._records[key]:
                    oldest_ts = min(self._records[key])
                    retry_after = int(oldest_ts + self.window_seconds - now)

                raise RateLimitExceededError(
                    f"Rate limit exceeded for role '{role}': "
                    f"{limit} requests per {self.window_seconds} seconds",
                    data={
                        "user_id": user_id,
                        "role": role,
                        "limit": limit,
                        "window_seconds": self.window_seconds,
                        "current_count": len(self._records[key]),
                        "retry_after_seconds": max(1, retry_after),
                    },
                )

            # Record this request
            self._records[key].append(now)

            rate_limit_operations_total.labels(operation="check", status="allowed", role=role).inc()

            duration = time.time() - start_time
            rate_limit_operation_duration_seconds.labels(
                operation="check", backend="memory"
            ).observe(duration)

    async def get_remaining(
        self,
        user_id: str,
        role: str,
        limit: int,
    ) -> int:
        """Get remaining requests allowed in current window.

        Args:
            user_id: User identifier
            role: User role
            limit: Maximum requests allowed

        Returns:
            Number of requests remaining
        """
        if limit == 0:
            return UNLIMITED_RATE_LIMIT

        async with self._lock:
            key = (user_id, role)
            now = time.time()
            cutoff = now - self.window_seconds

            # Remove old records
            self._records[key] = [ts for ts in self._records[key] if ts > cutoff]

            return max(0, limit - len(self._records[key]))

    async def reset(
        self,
        user_id: str | None = None,
        role: str | None = None,
    ) -> None:
        """Reset rate limit records.

        Args:
            user_id: If provided, reset only this user
            role: If provided, reset only this role
        """
        if user_id is None and role is None:
            self._records.clear()
        elif user_id and role:
            key = (user_id, role)
            if key in self._records:
                del self._records[key]
        elif user_id:
            keys_to_delete = [k for k in self._records if k[0] == user_id]
            for key in keys_to_delete:
                del self._records[key]
        elif role:
            keys_to_delete = [k for k in self._records if k[1] == role]
            for key in keys_to_delete:
                del self._records[key]


# Global rate limit store instance
_global_rate_limit_store: RateLimitStore | InMemoryRateLimitStore | None = None


async def get_rate_limit_store() -> RateLimitStore | InMemoryRateLimitStore:
    """Get global rate limit store instance.

    Returns:
        Global rate limit store (singleton)

    Raises:
        RuntimeError: If store not initialized
    """
    global _global_rate_limit_store
    if _global_rate_limit_store is None:
        raise RuntimeError(
            "Rate limit store not initialized. " "Call initialize_rate_limit_store() first."
        )
    return _global_rate_limit_store


async def initialize_rate_limit_store(
    use_redis: bool = True,
    redis_url: str = "redis://localhost:6379/0",
    pool_size: int = 10,
    timeout_seconds: float = 5.0,
    window_seconds: int = 60,
) -> None:
    """Initialize global rate limit store.

    Args:
        use_redis: Use Redis backend (True) or in-memory (False)
        redis_url: Redis connection URL
        pool_size: Connection pool size
        timeout_seconds: Operation timeout
        window_seconds: Rate limit time window
    """
    global _global_rate_limit_store

    if _global_rate_limit_store is not None:
        logger.warning("Rate limit store already initialized")
        return

    if use_redis:
        _global_rate_limit_store = RateLimitStore(
            redis_url=redis_url,
            pool_size=pool_size,
            timeout_seconds=timeout_seconds,
            window_seconds=window_seconds,
        )
    else:
        _global_rate_limit_store = InMemoryRateLimitStore(window_seconds=window_seconds)

    await _global_rate_limit_store.init()
    logger.info(
        f"Rate limit store initialized: " f"{'Redis' if use_redis else 'in-memory'} backend"
    )


async def close_rate_limit_store() -> None:
    """Close global rate limit store."""
    global _global_rate_limit_store
    if _global_rate_limit_store is not None:
        await _global_rate_limit_store.close()
        _global_rate_limit_store = None
