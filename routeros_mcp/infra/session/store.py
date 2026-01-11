"""Session storage backends for multi-instance deployments.

Provides pluggable session storage with Redis backend for horizontal scaling.
Sessions use 8-hour TTL with sliding window (TTL refreshed on access).

Example:
    # Redis backend
    store = RedisSessionStore(
        redis_url="redis://localhost:6379/0",
        pool_size=10,
        timeout_seconds=5.0,
    )
    await store.init()

    # Store session
    session_data = {"user_id": "123", "email": "user@example.com"}
    await store.set("session-abc", session_data)

    # Retrieve session (TTL refreshed on access)
    data = await store.get("session-abc")

    # Delete session
    await store.delete("session-abc")

See issue grammy-jiang/RouterOS-MCP#3 (Phase 5).
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)

# Session TTL: 8 hours (sliding window)
SESSION_TTL_SECONDS = 8 * 60 * 60  # 28800 seconds


class SessionStoreError(Exception):
    """Base exception for session store errors."""

    pass


class SessionStore(ABC):
    """Abstract base class for session storage backends.

    Defines the interface for pluggable session storage implementations.
    All implementations must support:
    - Async CRUD operations
    - TTL management with sliding window
    - Connection lifecycle management
    """

    @abstractmethod
    async def init(self) -> None:
        """Initialize the session store connection.

        Must be called before using any other methods.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the session store connection and cleanup resources."""
        pass

    @abstractmethod
    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve session data by ID.

        Args:
            session_id: Unique session identifier

        Returns:
            Session data as dict, or None if not found or expired

        Raises:
            SessionStoreError: If retrieval fails
        """
        pass

    @abstractmethod
    async def set(
        self, session_id: str, data: dict[str, Any], ttl_seconds: int | None = None
    ) -> None:
        """Store or update session data.

        Args:
            session_id: Unique session identifier
            data: Session data to store
            ttl_seconds: Optional TTL override (defaults to SESSION_TTL_SECONDS)

        Raises:
            SessionStoreError: If storage fails
        """
        pass

    @abstractmethod
    async def delete(self, session_id: str) -> bool:
        """Delete session by ID.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session was deleted, False if not found

        Raises:
            SessionStoreError: If deletion fails
        """
        pass

    @abstractmethod
    async def exists(self, session_id: str) -> bool:
        """Check if session exists and is not expired.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session exists and is valid

        Raises:
            SessionStoreError: If check fails
        """
        pass

    @abstractmethod
    async def refresh_ttl(self, session_id: str, ttl_seconds: int | None = None) -> bool:
        """Refresh session TTL (sliding window).

        Args:
            session_id: Unique session identifier
            ttl_seconds: Optional TTL override (defaults to SESSION_TTL_SECONDS)

        Returns:
            True if TTL was refreshed, False if session not found

        Raises:
            SessionStoreError: If refresh fails
        """
        pass


class RedisSessionStore(SessionStore):
    """Redis-backed session storage for multi-instance deployments.

    Stores session data in Redis with 8-hour TTL (sliding window).
    Connection pooling and automatic retries for resilience.

    Example:
        store = RedisSessionStore(
            redis_url="redis://localhost:6379/0",
            pool_size=10,
            timeout_seconds=5.0,
        )
        await store.init()

        await store.set("session-123", {"user": "alice"})
        data = await store.get("session-123")  # TTL refreshed
    """

    def __init__(
        self,
        redis_url: str,
        pool_size: int = 10,
        timeout_seconds: float = 5.0,
        key_prefix: str = "session:",
    ) -> None:
        """Initialize Redis session store.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0)
            pool_size: Connection pool size
            timeout_seconds: Operation timeout
            key_prefix: Redis key prefix for sessions
        """
        self.redis_url = redis_url
        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds
        self.key_prefix = key_prefix

        self._pool: ConnectionPool | None = None
        self._client: Redis | None = None

    async def init(self) -> None:
        """Initialize Redis connection pool and client."""
        try:
            self._pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.pool_size,
                socket_timeout=self.timeout_seconds,
                socket_connect_timeout=self.timeout_seconds,
                decode_responses=True,  # Auto-decode to strings
            )
            self._client = Redis(connection_pool=self._pool)

            # Test connection
            await self._client.ping()  # type: ignore[misc]
            logger.info(
                "Redis session store initialized",
                extra={"redis_url": self.redis_url, "pool_size": self.pool_size},
            )
        except RedisError as e:
            raise SessionStoreError(f"Failed to initialize Redis connection: {e}") from e

    async def close(self) -> None:
        """Close Redis connection and cleanup pool."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pool:
            await self._pool.aclose()
            self._pool = None
        logger.info("Redis session store closed")

    def _get_redis_key(self, session_id: str) -> str:
        """Generate Redis key for session ID."""
        return f"{self.key_prefix}{session_id}"

    async def get(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve session data and refresh TTL (sliding window).

        Args:
            session_id: Unique session identifier

        Returns:
            Session data as dict, or None if not found or expired

        Raises:
            SessionStoreError: If retrieval fails
        """
        if not self._client:
            raise SessionStoreError("Session store not initialized. Call init() first.")

        try:
            redis_key = self._get_redis_key(session_id)

            # Get session data
            data_str = await self._client.get(redis_key)
            if data_str is None:
                return None

            # Parse JSON
            data: dict[str, Any] = json.loads(data_str)

            # Refresh TTL (sliding window)
            await self._client.expire(redis_key, SESSION_TTL_SECONDS)

            logger.debug(
                "Session retrieved and TTL refreshed",
                extra={"session_id": session_id, "ttl_seconds": SESSION_TTL_SECONDS},
            )

            return data

        except (RedisError, json.JSONDecodeError) as e:
            raise SessionStoreError(f"Failed to retrieve session {session_id}: {e}") from e

    async def set(
        self, session_id: str, data: dict[str, Any], ttl_seconds: int | None = None
    ) -> None:
        """Store or update session data with TTL.

        Args:
            session_id: Unique session identifier
            data: Session data to store
            ttl_seconds: Optional TTL override (defaults to SESSION_TTL_SECONDS)

        Raises:
            SessionStoreError: If storage fails
        """
        if not self._client:
            raise SessionStoreError("Session store not initialized. Call init() first.")

        try:
            redis_key = self._get_redis_key(session_id)
            ttl = ttl_seconds if ttl_seconds is not None else SESSION_TTL_SECONDS

            # Serialize to JSON
            data_str = json.dumps(data)

            # Store with TTL
            await self._client.setex(redis_key, ttl, data_str)

            logger.debug(
                "Session stored",
                extra={"session_id": session_id, "ttl_seconds": ttl},
            )

        except (RedisError, TypeError) as e:
            raise SessionStoreError(f"Failed to store session {session_id}: {e}") from e

    async def delete(self, session_id: str) -> bool:
        """Delete session by ID.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session was deleted, False if not found

        Raises:
            SessionStoreError: If deletion fails
        """
        if not self._client:
            raise SessionStoreError("Session store not initialized. Call init() first.")

        try:
            redis_key = self._get_redis_key(session_id)
            deleted = await self._client.delete(redis_key)

            logger.debug(
                "Session deleted" if deleted else "Session not found for deletion",
                extra={"session_id": session_id, "deleted": bool(deleted)},
            )

            return bool(deleted)

        except RedisError as e:
            raise SessionStoreError(f"Failed to delete session {session_id}: {e}") from e

    async def exists(self, session_id: str) -> bool:
        """Check if session exists and is not expired.

        Args:
            session_id: Unique session identifier

        Returns:
            True if session exists and is valid

        Raises:
            SessionStoreError: If check fails
        """
        if not self._client:
            raise SessionStoreError("Session store not initialized. Call init() first.")

        try:
            redis_key = self._get_redis_key(session_id)
            exists = await self._client.exists(redis_key)
            return bool(exists)

        except RedisError as e:
            raise SessionStoreError(f"Failed to check session {session_id}: {e}") from e

    async def refresh_ttl(self, session_id: str, ttl_seconds: int | None = None) -> bool:
        """Refresh session TTL (sliding window).

        Args:
            session_id: Unique session identifier
            ttl_seconds: Optional TTL override (defaults to SESSION_TTL_SECONDS)

        Returns:
            True if TTL was refreshed, False if session not found

        Raises:
            SessionStoreError: If refresh fails
        """
        if not self._client:
            raise SessionStoreError("Session store not initialized. Call init() first.")

        try:
            redis_key = self._get_redis_key(session_id)
            ttl = ttl_seconds if ttl_seconds is not None else SESSION_TTL_SECONDS

            # EXPIRE returns 1 if key exists, 0 if not found
            refreshed = await self._client.expire(redis_key, ttl)

            logger.debug(
                "Session TTL refreshed" if refreshed else "Session not found for TTL refresh",
                extra={"session_id": session_id, "ttl_seconds": ttl, "refreshed": bool(refreshed)},
            )

            return bool(refreshed)

        except RedisError as e:
            raise SessionStoreError(f"Failed to refresh TTL for session {session_id}: {e}") from e
