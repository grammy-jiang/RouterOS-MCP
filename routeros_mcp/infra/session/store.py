"""Session storage backends for multi-instance deployments.

Provides pluggable session storage with Redis backend for horizontal scaling.
Sessions use 8-hour TTL with sliding window (TTL refreshed on access).

Example:
    # Redis backend with encryption
    from routeros_mcp.security.crypto import CredentialEncryption

    crypto = CredentialEncryption(settings.encryption_key, settings.environment)
    store = RedisSessionStore(
        redis_url=settings.redis_url,
        pool_size=settings.redis_pool_size,
        timeout_seconds=settings.redis_timeout_seconds,
        encryption=crypto,
    )
    await store.init()

    # Store session
    session_data = SessionData(
        user_id="123",
        email="user@example.com",
        role="admin",
    )
    await store.set("session-abc", session_data)

    # Retrieve session (TTL refreshed on access)
    data = await store.get("session-abc")

    # Delete session
    await store.delete("session-abc")

See issue grammy-jiang/RouterOS-MCP#3 (Phase 5).
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, TypedDict

from prometheus_client import Counter, Histogram
from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from routeros_mcp.infra.observability.metrics import _registry
from routeros_mcp.security.crypto import CredentialEncryption, EncryptionError

logger = logging.getLogger(__name__)

# Session TTL: 8 hours (sliding window)
SESSION_TTL_SECONDS = 8 * 60 * 60  # 28800 seconds

# Session ID validation pattern (alphanumeric, hyphen, underscore only)
_SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")

# Metrics for session store operations
session_operations_total = Counter(
    "routeros_mcp_session_operations_total",
    "Total number of session store operations",
    ["operation", "status"],
    registry=_registry,
)

session_operation_duration_seconds = Histogram(
    "routeros_mcp_session_operation_duration_seconds",
    "Duration of session store operations in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
    registry=_registry,
)


class SessionData(TypedDict, total=False):
    """Type-safe structure for session data.

    Defines the expected structure of session data stored in Redis.
    Using TypedDict provides type checking while maintaining dict compatibility.

    Attributes:
        user_id: Unique user identifier (OIDC sub claim)
        email: User's email address
        display_name: User's display name
        role: User's role (read_only/ops_rw/admin)
        access_token: OAuth access token (encrypted at rest)
        refresh_token: OAuth refresh token (encrypted at rest)
        expires_at: Unix timestamp when access token expires
        id_token: OIDC ID token (JWT)
        device_scope: Optional list of allowed device IDs
        pkce_verifier: PKCE code verifier for OAuth flow
        state: OAuth state parameter
    """

    user_id: str
    email: str | None
    display_name: str | None
    role: str
    access_token: str | None
    refresh_token: str | None
    expires_at: float | None
    id_token: str | None
    device_scope: list[str] | None
    pkce_verifier: str | None
    state: str | None


class SessionStoreError(Exception):
    """Base exception for session store errors."""


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

    @abstractmethod
    async def close(self) -> None:
        """Close the session store connection and cleanup resources."""

    @abstractmethod
    async def get(self, session_id: str) -> SessionData | None:
        """Retrieve session data by ID.

        Args:
            session_id: Unique session identifier

        Returns:
            Session data, or None if not found or expired

        Raises:
            SessionStoreError: If retrieval fails
        """

    @abstractmethod
    async def set(self, session_id: str, data: SessionData, ttl_seconds: int | None = None) -> None:
        """Store or update session data.

        Args:
            session_id: Unique session identifier
            data: Session data to store
            ttl_seconds: Optional TTL override (defaults to SESSION_TTL_SECONDS)

        Raises:
            SessionStoreError: If storage fails
        """

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


class RedisSessionStore(SessionStore):
    """Redis-backed session storage for multi-instance deployments.

    Stores session data in Redis with 8-hour TTL (sliding window).
    Connection pooling and automatic retries for resilience.
    Optional encryption at rest for sensitive session data.

    Example:
        from routeros_mcp.security.crypto import CredentialEncryption

        crypto = CredentialEncryption(settings.encryption_key, settings.environment)
        store = RedisSessionStore(
            redis_url=settings.redis_url,
            pool_size=settings.redis_pool_size,
            timeout_seconds=settings.redis_timeout_seconds,
            encryption=crypto,
        )
        await store.init()

        session_data = SessionData(user_id="123", email="user@example.com")
        await store.set("session-123", session_data)
        data = await store.get("session-123")  # TTL refreshed atomically
    """

    def __init__(
        self,
        redis_url: str,
        pool_size: int = 10,
        timeout_seconds: float = 5.0,
        key_prefix: str = "session:",
        encryption: CredentialEncryption | None = None,
    ) -> None:
        """Initialize Redis session store.

        Args:
            redis_url: Redis connection URL (e.g., redis://localhost:6379/0 or
                      rediss://secure.redis.example.com:6380/0 for TLS)
            pool_size: Connection pool size
            timeout_seconds: Operation timeout
            key_prefix: Redis key prefix for sessions
            encryption: Optional encryption handler for session data at rest
        """
        self.redis_url = redis_url
        self.pool_size = pool_size
        self.timeout_seconds = timeout_seconds
        self.key_prefix = key_prefix
        self.encryption = encryption

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
        """Close Redis connection and cleanup pool.

        Best-effort cleanup: errors during close are logged but do not propagate.
        Internal references are cleared regardless to avoid inconsistent state.
        """
        # Take local copies and clear attributes first to avoid exposing half-closed resources
        client = self._client
        pool = self._pool
        self._client = None
        self._pool = None

        if client is not None:
            try:
                await client.aclose()
            except Exception as exc:
                logger.error(
                    "Error while closing Redis client during session store shutdown",
                    exc_info=exc,
                )

        if pool is not None:
            try:
                await pool.aclose()
            except Exception as exc:
                logger.error(
                    "Error while closing Redis connection pool during session store shutdown",
                    exc_info=exc,
                )

        logger.info("Redis session store closed")

    def _validate_session_id(self, session_id: str) -> None:
        """Validate that the session ID is safe to use as a Redis key suffix.

        Only allows alphanumeric characters plus hyphen and underscore to avoid
        unexpected behavior with Redis key patterns or collisions.

        Args:
            session_id: Session identifier to validate

        Raises:
            SessionStoreError: If session ID is invalid
        """
        if not session_id:
            raise SessionStoreError("Session ID must be non-empty")

        if not _SESSION_ID_PATTERN.match(session_id):
            raise SessionStoreError(
                f"Session ID '{session_id}' contains invalid characters; "
                "only alphanumeric characters, hyphen (-), and underscore (_) are allowed"
            )

    def _get_redis_key(self, session_id: str) -> str:
        """Generate Redis key for session ID.

        Args:
            session_id: Session identifier

        Returns:
            Full Redis key with prefix

        Raises:
            SessionStoreError: If session ID is invalid
        """
        self._validate_session_id(session_id)
        return f"{self.key_prefix}{session_id}"

    async def get(self, session_id: str) -> SessionData | None:
        """Retrieve session data and refresh TTL atomically (sliding window).

        Uses Redis GETEX command to atomically retrieve and refresh TTL in a single
        operation, avoiding race conditions between GET and EXPIRE.

        Args:
            session_id: Unique session identifier

        Returns:
            Session data, or None if not found or expired

        Raises:
            SessionStoreError: If retrieval fails
        """
        if not self._client:
            raise SessionStoreError("Session store not initialized. Call init() first.")

        operation = "get"
        try:
            with session_operation_duration_seconds.labels(operation=operation).time():
                redis_key = self._get_redis_key(session_id)

                # Use GETEX to atomically retrieve and refresh TTL (Redis 6.2+)
                # This avoids race condition between GET and EXPIRE
                data_str = await self._client.getex(
                    redis_key,
                    ex=SESSION_TTL_SECONDS,  # Refresh TTL to 8 hours
                )

                if data_str is None:
                    session_operations_total.labels(operation=operation, status="miss").inc()
                    return None

                # Decrypt if encryption is enabled
                if self.encryption:
                    try:
                        data_str = self.encryption.decrypt(data_str)
                    except EncryptionError as e:
                        raise SessionStoreError(
                            f"Failed to decrypt session {session_id}: {e}"
                        ) from e

                # Parse JSON
                data_dict: dict[str, Any] = json.loads(data_str)
                # Cast to SessionData (TypedDict doesn't enforce at runtime, just for type checking)
                data: SessionData = data_dict  # type: ignore[assignment]

                logger.debug(
                    "Session retrieved and TTL refreshed atomically",
                    extra={"session_id": session_id, "ttl_seconds": SESSION_TTL_SECONDS},
                )

                session_operations_total.labels(operation=operation, status="hit").inc()
                return data

        except (RedisError, json.JSONDecodeError) as e:
            session_operations_total.labels(operation=operation, status="error").inc()
            raise SessionStoreError(f"Failed to retrieve session {session_id}: {e}") from e

    async def set(self, session_id: str, data: SessionData, ttl_seconds: int | None = None) -> None:
        """Store or update session data with TTL.

        Encrypts session data at rest if encryption is enabled.

        Args:
            session_id: Unique session identifier
            data: Session data to store
            ttl_seconds: Optional TTL override (defaults to SESSION_TTL_SECONDS)

        Raises:
            SessionStoreError: If storage fails
        """
        if not self._client:
            raise SessionStoreError("Session store not initialized. Call init() first.")

        operation = "set"
        try:
            with session_operation_duration_seconds.labels(operation=operation).time():
                redis_key = self._get_redis_key(session_id)
                ttl = ttl_seconds if ttl_seconds is not None else SESSION_TTL_SECONDS

                # Serialize to JSON
                data_str = json.dumps(data)

                # Encrypt if encryption is enabled
                if self.encryption:
                    try:
                        data_str = self.encryption.encrypt(data_str)
                    except EncryptionError as e:
                        raise SessionStoreError(
                            f"Failed to encrypt session {session_id}: {e}"
                        ) from e

                # Store with TTL
                await self._client.setex(redis_key, ttl, data_str)

                logger.debug(
                    "Session stored",
                    extra={
                        "session_id": session_id,
                        "ttl_seconds": ttl,
                        "encrypted": self.encryption is not None,
                    },
                )

                session_operations_total.labels(operation=operation, status="success").inc()

        except (RedisError, TypeError) as e:
            session_operations_total.labels(operation=operation, status="error").inc()
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

        operation = "delete"
        try:
            with session_operation_duration_seconds.labels(operation=operation).time():
                redis_key = self._get_redis_key(session_id)
                deleted = await self._client.delete(redis_key)

                logger.debug(
                    "Session deleted" if deleted else "Session not found for deletion",
                    extra={"session_id": session_id, "deleted": bool(deleted)},
                )

                session_operations_total.labels(
                    operation=operation, status="success" if deleted else "not_found"
                ).inc()

                return bool(deleted)

        except RedisError as e:
            session_operations_total.labels(operation=operation, status="error").inc()
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

        operation = "exists"
        try:
            with session_operation_duration_seconds.labels(operation=operation).time():
                redis_key = self._get_redis_key(session_id)
                exists = await self._client.exists(redis_key)

                session_operations_total.labels(
                    operation=operation, status="found" if exists else "not_found"
                ).inc()

                return bool(exists)

        except RedisError as e:
            session_operations_total.labels(operation=operation, status="error").inc()
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

        operation = "refresh_ttl"
        try:
            with session_operation_duration_seconds.labels(operation=operation).time():
                redis_key = self._get_redis_key(session_id)
                ttl = ttl_seconds if ttl_seconds is not None else SESSION_TTL_SECONDS

                # EXPIRE returns 1 if key exists, 0 if not found
                refreshed = await self._client.expire(redis_key, ttl)

                logger.debug(
                    "Session TTL refreshed" if refreshed else "Session not found for TTL refresh",
                    extra={
                        "session_id": session_id,
                        "ttl_seconds": ttl,
                        "refreshed": bool(refreshed),
                    },
                )

                session_operations_total.labels(
                    operation=operation, status="success" if refreshed else "not_found"
                ).inc()

                return bool(refreshed)

        except RedisError as e:
            session_operations_total.labels(operation=operation, status="error").inc()
            raise SessionStoreError(f"Failed to refresh TTL for session {session_id}: {e}") from e
