"""Unit tests for session store implementations."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.asyncio import Redis
from redis.exceptions import RedisError

from routeros_mcp.infra.session.store import (
    RedisSessionStore,
    SESSION_TTL_SECONDS,
    SessionData,
    SessionStore,
    SessionStoreError,
)


class TestSessionStoreInterface:
    """Tests for SessionStore abstract interface."""

    def test_session_store_is_abstract(self) -> None:
        """SessionStore cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            SessionStore()  # type: ignore


class TestRedisSessionStore:
    """Tests for RedisSessionStore implementation."""

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Create mock Redis client."""
        client = AsyncMock(spec=Redis)
        client.ping = AsyncMock()
        client.getex = AsyncMock()  # Updated to use getex
        client.setex = AsyncMock()
        client.delete = AsyncMock()
        client.exists = AsyncMock()
        client.expire = AsyncMock()
        client.aclose = AsyncMock()
        return client

    @pytest.fixture
    def store(self) -> RedisSessionStore:
        """Create RedisSessionStore instance."""
        return RedisSessionStore(
            redis_url="redis://localhost:6379/0",
            pool_size=5,
            timeout_seconds=3.0,
            key_prefix="test:",
        )

    @pytest.mark.asyncio
    async def test_init_creates_connection(self, store: RedisSessionStore) -> None:
        """init() should create Redis connection pool and client."""
        with (
            patch("routeros_mcp.infra.session.store.ConnectionPool") as mock_pool_class,
            patch("routeros_mcp.infra.session.store.Redis") as mock_redis_class,
        ):
            mock_pool = MagicMock()
            mock_pool_class.from_url.return_value = mock_pool

            mock_client = AsyncMock(spec=Redis)
            mock_client.ping = AsyncMock()
            mock_redis_class.return_value = mock_client

            await store.init()

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
    async def test_init_failure_raises_error(self, store: RedisSessionStore) -> None:
        """init() should raise SessionStoreError on connection failure."""
        with (
            patch("routeros_mcp.infra.session.store.ConnectionPool"),
            patch("routeros_mcp.infra.session.store.Redis") as mock_redis_class,
        ):
            mock_client = AsyncMock(spec=Redis)
            mock_client.ping = AsyncMock(side_effect=RedisError("Connection failed"))
            mock_redis_class.return_value = mock_client

            with pytest.raises(SessionStoreError, match="Failed to initialize Redis connection"):
                await store.init()

    @pytest.mark.asyncio
    async def test_close_cleanup_resources(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """close() should cleanup Redis client and pool."""
        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()

        store._client = mock_redis_client
        store._pool = mock_pool

        await store.close()

        mock_redis_client.aclose.assert_called_once()
        mock_pool.aclose.assert_called_once()
        assert store._client is None
        # mypy: pool is set to None after the assert above is checked
        # so this line is marked as unreachable, but it's still valid
        assert store._pool is None  # type: ignore[unreachable]

    @pytest.mark.asyncio
    async def test_get_session_success(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """get() should retrieve session data and refresh TTL atomically using GETEX."""
        store._client = mock_redis_client

        session_data: SessionData = {
            "user_id": "123",
            "email": "user@example.com",
            "role": "admin",
        }
        mock_redis_client.getex.return_value = json.dumps(session_data)

        result = await store.get("session-abc")

        assert result == session_data
        # Verify GETEX was called with EX parameter for atomic TTL refresh
        mock_redis_client.getex.assert_called_once_with("test:session-abc", ex=SESSION_TTL_SECONDS)

    @pytest.mark.asyncio
    async def test_get_session_not_found(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """get() should return None if session not found."""
        store._client = mock_redis_client
        mock_redis_client.getex.return_value = None

        result = await store.get("nonexistent")

        assert result is None
        mock_redis_client.getex.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_redis_error(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """get() should raise SessionStoreError on Redis error."""
        store._client = mock_redis_client
        mock_redis_client.getex.side_effect = RedisError("Connection timeout")

        with pytest.raises(SessionStoreError, match="Failed to retrieve session"):
            await store.get("session-abc")

    @pytest.mark.asyncio
    async def test_get_session_not_initialized(self, store: RedisSessionStore) -> None:
        """get() should raise error if store not initialized."""
        with pytest.raises(SessionStoreError, match="not initialized"):
            await store.get("session-abc")

    @pytest.mark.asyncio
    async def test_set_session_success(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """set() should store session data with TTL."""
        store._client = mock_redis_client

        session_data: SessionData = {"user_id": "456", "role": "admin"}  # type: ignore[typeddict-item]
        await store.set("session-xyz", session_data)

        mock_redis_client.setex.assert_called_once_with(
            "test:session-xyz", SESSION_TTL_SECONDS, json.dumps(session_data)
        )

    @pytest.mark.asyncio
    async def test_set_session_custom_ttl(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """set() should support custom TTL override."""
        store._client = mock_redis_client

        session_data: SessionData = {"user_id": "temp"}  # type: ignore[typeddict-item]
        custom_ttl = 3600  # 1 hour

        await store.set("session-temp", session_data, ttl_seconds=custom_ttl)

        mock_redis_client.setex.assert_called_once_with(
            "test:session-temp", custom_ttl, json.dumps(session_data)
        )

    @pytest.mark.asyncio
    async def test_set_session_redis_error(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """set() should raise SessionStoreError on Redis error."""
        store._client = mock_redis_client
        mock_redis_client.setex.side_effect = RedisError("Write failed")

        with pytest.raises(SessionStoreError, match="Failed to store session"):
            await store.set("session-abc", {"user_id": "123"})  # type: ignore[typeddict-item]

    @pytest.mark.asyncio
    async def test_delete_session_success(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """delete() should remove session and return True."""
        store._client = mock_redis_client
        mock_redis_client.delete.return_value = 1  # Redis returns count of deleted keys

        result = await store.delete("session-abc")

        assert result is True
        mock_redis_client.delete.assert_called_once_with("test:session-abc")

    @pytest.mark.asyncio
    async def test_delete_session_not_found(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """delete() should return False if session not found."""
        store._client = mock_redis_client
        mock_redis_client.delete.return_value = 0

        result = await store.delete("nonexistent")

        assert result is False
        mock_redis_client.delete.assert_called_once_with("test:nonexistent")

    @pytest.mark.asyncio
    async def test_delete_session_redis_error(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """delete() should raise SessionStoreError on Redis error."""
        store._client = mock_redis_client
        mock_redis_client.delete.side_effect = RedisError("Delete failed")

        with pytest.raises(SessionStoreError, match="Failed to delete session"):
            await store.delete("session-abc")

    @pytest.mark.asyncio
    async def test_exists_session_found(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """exists() should return True if session exists."""
        store._client = mock_redis_client
        mock_redis_client.exists.return_value = 1

        result = await store.exists("session-abc")

        assert result is True
        mock_redis_client.exists.assert_called_once_with("test:session-abc")

    @pytest.mark.asyncio
    async def test_exists_session_not_found(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """exists() should return False if session not found."""
        store._client = mock_redis_client
        mock_redis_client.exists.return_value = 0

        result = await store.exists("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_ttl_success(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """refresh_ttl() should extend session TTL."""
        store._client = mock_redis_client
        mock_redis_client.expire.return_value = 1  # Key exists

        result = await store.refresh_ttl("session-abc")

        assert result is True
        mock_redis_client.expire.assert_called_once_with("test:session-abc", SESSION_TTL_SECONDS)

    @pytest.mark.asyncio
    async def test_refresh_ttl_custom_ttl(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """refresh_ttl() should support custom TTL override."""
        store._client = mock_redis_client
        mock_redis_client.expire.return_value = 1

        custom_ttl = 1800  # 30 minutes
        result = await store.refresh_ttl("session-abc", ttl_seconds=custom_ttl)

        assert result is True
        mock_redis_client.expire.assert_called_once_with("test:session-abc", custom_ttl)

    @pytest.mark.asyncio
    async def test_refresh_ttl_not_found(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """refresh_ttl() should return False if session not found."""
        store._client = mock_redis_client
        mock_redis_client.expire.return_value = 0  # Key not found

        result = await store.refresh_ttl("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_ttl_redis_error(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """refresh_ttl() should raise SessionStoreError on Redis error."""
        store._client = mock_redis_client
        mock_redis_client.expire.side_effect = RedisError("Expire failed")

        with pytest.raises(SessionStoreError, match="Failed to refresh TTL"):
            await store.refresh_ttl("session-abc")

    @pytest.mark.asyncio
    async def test_concurrent_access_simulation(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """Simulate concurrent access to same session (sliding window)."""
        store._client = mock_redis_client

        session_data: SessionData = {"user_id": "789", "email": "test@example.com", "role": "user"}
        mock_redis_client.getex.return_value = json.dumps(session_data)

        # Simulate 5 concurrent reads (each should refresh TTL atomically via GETEX)
        tasks = [store.get("session-concurrent") for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # All reads should succeed
        assert all(r == session_data for r in results)

        # getex() should be called 5 times (atomic get + TTL refresh)
        assert mock_redis_client.getex.call_count == 5

        # Verify all calls used atomic GETEX with TTL refresh
        for call in mock_redis_client.getex.call_args_list:
            assert call[1]["ex"] == SESSION_TTL_SECONDS

    @pytest.mark.asyncio
    async def test_ttl_expiration_behavior(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """Test session expiration after TTL."""
        store._client = mock_redis_client

        # First get: session exists
        session_data: SessionData = {"user_id": "expired", "role": "user"}
        mock_redis_client.getex.return_value = json.dumps(session_data)

        result1 = await store.get("session-expire")
        assert result1 == session_data

        # Simulate expiration: subsequent get returns None
        mock_redis_client.getex.return_value = None

        result2 = await store.get("session-expire")
        assert result2 is None

    @pytest.mark.asyncio
    async def test_key_prefix_isolation(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """Test that key prefix properly isolates sessions."""
        store._client = mock_redis_client

        session_data: SessionData = {"user_id": "test"}  # type: ignore[typeddict-item]
        await store.set("my-session", session_data)

        # Verify the Redis key includes the prefix
        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args
        assert call_args[0][0] == "test:my-session"

    @pytest.mark.asyncio
    async def test_session_data_serialization(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """Test complex session data serialization/deserialization."""
        store._client = mock_redis_client

        # Complex session data with various types
        complex_data: SessionData = {
            "user_id": "complex-123",
            "email": "user@example.com",
            "role": "admin",
            "device_scope": ["device1", "device2"],
        }  # type: ignore[typeddict-item]

        await store.set("session-complex", complex_data)

        # Verify serialization
        mock_redis_client.setex.assert_called_once()
        call_args = mock_redis_client.setex.call_args
        serialized = call_args[0][2]

        # Verify we can deserialize back
        deserialized = json.loads(serialized)
        assert deserialized == complex_data

    @pytest.mark.asyncio
    async def test_invalid_json_in_redis(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """Test handling of corrupted JSON data in Redis."""
        store._client = mock_redis_client
        mock_redis_client.getex.return_value = "{ invalid json"

        with pytest.raises(SessionStoreError, match="Failed to retrieve session"):
            await store.get("session-corrupt")

    @pytest.mark.asyncio
    async def test_session_id_validation_empty(self, store: RedisSessionStore) -> None:
        """Test that empty session IDs are rejected."""
        with pytest.raises(SessionStoreError, match="Session ID must be non-empty"):
            store._get_redis_key("")

    @pytest.mark.asyncio
    async def test_session_id_validation_invalid_chars(self, store: RedisSessionStore) -> None:
        """Test that session IDs with invalid characters are rejected."""
        invalid_ids = [
            "session with spaces",
            "session:with:colons",
            "session@with@at",
            "session/with/slash",
            "session\\with\\backslash",
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(SessionStoreError, match="contains invalid characters"):
                store._get_redis_key(invalid_id)

    @pytest.mark.asyncio
    async def test_session_id_validation_valid_chars(self, store: RedisSessionStore) -> None:
        """Test that session IDs with valid characters are accepted."""
        valid_ids = [
            "session-123",
            "session_456",
            "SESSION-ABC",
            "session123ABC",
            "a1-b2_c3",
        ]

        for valid_id in valid_ids:
            # Should not raise
            key = store._get_redis_key(valid_id)
            assert key == f"test:{valid_id}"

    @pytest.mark.asyncio
    async def test_set_not_initialized(self, store: RedisSessionStore) -> None:
        """Test that set() raises error if store not initialized."""
        with pytest.raises(SessionStoreError, match="not initialized"):
            await store.set("session-abc", {"user_id": "123"})

    @pytest.mark.asyncio
    async def test_delete_not_initialized(self, store: RedisSessionStore) -> None:
        """Test that delete() raises error if store not initialized."""
        with pytest.raises(SessionStoreError, match="not initialized"):
            await store.delete("session-abc")

    @pytest.mark.asyncio
    async def test_exists_not_initialized(self, store: RedisSessionStore) -> None:
        """Test that exists() raises error if store not initialized."""
        with pytest.raises(SessionStoreError, match="not initialized"):
            await store.exists("session-abc")

    @pytest.mark.asyncio
    async def test_refresh_ttl_not_initialized(self, store: RedisSessionStore) -> None:
        """Test that refresh_ttl() raises error if store not initialized."""
        with pytest.raises(SessionStoreError, match="not initialized"):
            await store.refresh_ttl("session-abc")

    @pytest.mark.asyncio
    async def test_concurrent_access_with_writes(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """Test concurrent set() and get() operations maintain data consistency."""
        store._client = mock_redis_client

        # Simulate concurrent writes and reads
        session_data_1: SessionData = {
            "user_id": "user1",
            "email": "user1@example.com",
            "role": "admin",
        }
        session_data_2: SessionData = {
            "user_id": "user2",
            "email": "user2@example.com",
            "role": "user",
        }

        mock_redis_client.setex = AsyncMock()
        mock_redis_client.getex = AsyncMock(
            side_effect=[
                json.dumps(session_data_1),
                json.dumps(session_data_2),
                json.dumps(session_data_1),
            ]
        )

        # Execute concurrent operations
        tasks = [
            store.set("session-1", session_data_1),
            store.set("session-2", session_data_2),
            store.get("session-1"),
            store.get("session-2"),
            store.get("session-1"),
        ]

        await asyncio.gather(*tasks)

        # Verify operations completed
        assert mock_redis_client.setex.call_count == 2
        assert mock_redis_client.getex.call_count == 3

    @pytest.mark.asyncio
    async def test_close_with_client_error(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """Test that close() handles client errors gracefully."""
        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock()

        # Make client close raise an error
        mock_redis_client.aclose = AsyncMock(side_effect=RedisError("Close failed"))

        store._client = mock_redis_client
        store._pool = mock_pool

        # Should not raise, but should log error
        await store.close()

        # Both should still be set to None
        assert store._client is None
        assert store._pool is None  # type: ignore[unreachable]

    @pytest.mark.asyncio
    async def test_close_with_pool_error(
        self, store: RedisSessionStore, mock_redis_client: AsyncMock
    ) -> None:
        """Test that close() handles pool errors gracefully."""
        mock_pool = MagicMock()
        mock_pool.aclose = AsyncMock(side_effect=RedisError("Pool close failed"))

        store._client = mock_redis_client
        store._pool = mock_pool

        # Should not raise, but should log error
        await store.close()

        # Both should still be set to None
        assert store._client is None
        assert store._pool is None  # type: ignore[unreachable]


class TestSessionStoreIntegration:
    """Integration-like tests for session store (mocked Redis)."""

    @pytest.mark.asyncio
    async def test_session_lifecycle(self) -> None:
        """Test complete session lifecycle: create, read, update, delete."""
        with (
            patch("routeros_mcp.infra.session.store.ConnectionPool") as mock_pool_class,
            patch("routeros_mcp.infra.session.store.Redis") as mock_redis_class,
        ):
            mock_pool = MagicMock()
            mock_pool.aclose = AsyncMock()
            mock_pool_class.from_url.return_value = mock_pool

            mock_client = AsyncMock(spec=Redis)
            mock_client.ping = AsyncMock()
            mock_redis_class.return_value = mock_client

            store = RedisSessionStore(redis_url="redis://localhost:6379/0")
            await store.init()

            # 1. Create session
            mock_client.setex = AsyncMock()
            initial_data: SessionData = {"user_id": "alice", "role": "user"}  # type: ignore[typeddict-item]
            await store.set("session-lifecycle", initial_data)
            assert mock_client.setex.called

            # 2. Read session
            mock_client.getex = AsyncMock(return_value=json.dumps(initial_data))
            data = await store.get("session-lifecycle")
            assert data == initial_data

            # 3. Update session
            updated_data: SessionData = {"user_id": "alice", "role": "admin"}  # type: ignore[typeddict-item]
            await store.set("session-lifecycle", updated_data)

            # 4. Delete session
            mock_client.delete = AsyncMock(return_value=1)
            deleted = await store.delete("session-lifecycle")
            assert deleted is True

            # 5. Verify deletion
            mock_client.getex = AsyncMock(return_value=None)
            data = await store.get("session-lifecycle")
            assert data is None

            await store.close()
