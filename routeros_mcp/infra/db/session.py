"""Database session management with connection pooling.

Manages SQLAlchemy async engine and session creation with support
for both SQLite and PostgreSQL databases.

Key features:
- Async session management with context managers
- Connection pooling (PostgreSQL) and appropriate defaults (SQLite)
- Automatic session commit/rollback
- Global session manager singleton pattern
- FastAPI dependency injection support

See docs/18-database-schema-and-orm-specification.md for usage patterns.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from routeros_mcp.config import Settings


class DatabaseSessionManager:
    """Database session manager with connection pooling.

    Manages SQLAlchemy async engine and session creation
    with support for both SQLite and PostgreSQL.

    Example:
        manager = DatabaseSessionManager(settings)
        await manager.init()

        async with manager.session() as session:
            result = await session.execute(select(Device))
            devices = result.scalars().all()

        await manager.close()
    """

    def __init__(self, settings: Settings) -> None:
        """Initialize session manager.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def init(self) -> None:
        """Initialize database engine and session factory.

        Creates async engine with appropriate configuration for SQLite or PostgreSQL.
        Must be called before using session() method.
        """
        # SQLite-specific configuration
        if self.settings.is_sqlite:
            connect_args = {
                "check_same_thread": False,  # Required for async
                "timeout": 30.0,  # Lock timeout
            }
            pool_config = {}  # SQLite uses NullPool by default
        else:
            # PostgreSQL configuration
            connect_args = {}
            pool_config = {
                "pool_size": self.settings.database_pool_size,
                "max_overflow": self.settings.database_max_overflow,
                "pool_pre_ping": True,  # Verify connections
                "pool_recycle": 3600,  # Recycle after 1 hour
            }

        self._engine = create_async_engine(
            self.settings.database_url,
            echo=self.settings.database_echo,
            connect_args=connect_args,
            **pool_config,
        )

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def close(self) -> None:
        """Close database engine and cleanup connections."""
        if self._engine:
            await self._engine.dispose()
            self._engine = None
            self._session_factory = None

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session context manager.

        Automatically commits on success or rolls back on error.

        Yields:
            AsyncSession instance

        Raises:
            RuntimeError: If session manager not initialized

        Example:
            async with manager.session() as session:
                result = await session.execute(select(Device))
                # Session automatically commits on exit
        """
        if self._session_factory is None:
            raise RuntimeError("SessionManager not initialized. Call init() first.")

        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @property
    def engine(self) -> AsyncEngine:
        """Get database engine.

        Returns:
            AsyncEngine instance

        Raises:
            RuntimeError: If not initialized
        """
        if self._engine is None:
            raise RuntimeError("SessionManager not initialized. Call init() first.")
        return self._engine


# Global session manager instance
_session_manager: DatabaseSessionManager | None = None


def get_session_manager(settings: Settings | None = None) -> DatabaseSessionManager:
    """Get global session manager instance (singleton).

    Args:
        settings: Application settings (required on first call)

    Returns:
        DatabaseSessionManager instance

    Raises:
        RuntimeError: If not initialized and settings not provided

    Example:
        # Initialize on app startup
        settings = get_settings()
        manager = get_session_manager(settings)
        await manager.init()

        # Use elsewhere
        manager = get_session_manager()
        async with manager.session() as session:
            ...
    """
    global _session_manager

    if _session_manager is None:
        if settings is None:
            from routeros_mcp.config import get_settings

            settings = get_settings()
        _session_manager = DatabaseSessionManager(settings)

    return _session_manager


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session for FastAPI dependency injection.

    Yields:
        AsyncSession instance

    Example:
        from fastapi import Depends

        @app.get("/devices")
        async def list_devices(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Device))
            return result.scalars().all()
    """
    manager = get_session_manager()
    async with manager.session() as session:
        yield session


def get_session_factory(settings: Settings | None = None) -> DatabaseSessionManager:
    """Get session factory for creating sessions outside FastAPI context.

    Args:
        settings: Application settings (optional, uses global if not provided)

    Returns:
        Database session manager with session() method

    Example:
        factory = get_session_factory(settings)
        async with factory.session() as session:
            result = await session.execute(select(Device))
    """
    manager = get_session_manager(settings)
    if manager._session_factory is None:
        # Initialize if not already done
        import asyncio
        asyncio.create_task(manager.init())

    # Return the manager itself, not the session factory
    return manager


def reset_session_manager() -> None:
    """Reset global session manager (mainly for testing).

    This should only be used in test fixtures to ensure clean state.
    """
    global _session_manager
    _session_manager = None
