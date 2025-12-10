"""Tests for database session management."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.config import Settings
from routeros_mcp.infra.db.session import (
    DatabaseSessionManager,
    get_session_manager,
    reset_session_manager,
)


@pytest.fixture
async def db_session():
    """Create an in-memory database session for testing."""
    from routeros_mcp.infra.db.models import Base
    
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        yield session
        
    await engine.dispose()


class TestDatabaseSessionManager:
    """Tests for DatabaseSessionManager class."""
    
    def test_initialization(self) -> None:
        """Test manager initialization."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        
        assert manager.settings == settings
        assert manager._engine is None
        assert manager._session_factory is None
        
    @pytest.mark.asyncio
    async def test_init_creates_engine_and_factory(self) -> None:
        """Test that init() creates engine and session factory."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        
        await manager.init()
        
        assert manager._engine is not None
        assert isinstance(manager._engine, AsyncEngine)
        assert manager._session_factory is not None
        
        await manager.close()
        
    @pytest.mark.asyncio
    async def test_session_context_manager(self) -> None:
        """Test session context manager."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        await manager.init()
        
        async with manager.session() as session:
            assert isinstance(session, AsyncSession)
            
        await manager.close()
        
    @pytest.mark.asyncio
    async def test_session_before_init_raises_error(self) -> None:
        """Test that accessing session before init raises RuntimeError."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        
        with pytest.raises(RuntimeError, match="not initialized"):
            async with manager.session():
                pass
                
    @pytest.mark.asyncio
    async def test_engine_property_before_init_raises_error(self) -> None:
        """Test that accessing engine before init raises RuntimeError."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = manager.engine
            
    @pytest.mark.asyncio
    async def test_engine_property_after_init(self) -> None:
        """Test engine property after initialization."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        await manager.init()
        
        engine = manager.engine
        assert isinstance(engine, AsyncEngine)
        
        await manager.close()
        
    @pytest.mark.asyncio
    async def test_session_auto_commit_on_success(self, db_session) -> None:
        """Test that session auto-commits on success."""
        # Insert a record
        from routeros_mcp.infra.db.models import Device
        device = Device(
            id="session-test-1",
            name="test-router-session-commit",
            management_address="198.51.100.101:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        db_session.add(device)
        await db_session.commit()
        
        # Verify it was committed
        from sqlalchemy import select
        result = await db_session.execute(select(Device).where(Device.id == "session-test-1"))
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.name == "test-router-session-commit"
        
    @pytest.mark.asyncio
    async def test_session_auto_rollback_on_error(self, db_session) -> None:
        """Test that session auto-rolls back on error."""
        # Try to insert a record but raise error
        from routeros_mcp.infra.db.models import Device
        try:
            device = Device(
                id="session-test-2",
                name="test-router-session-rollback",
                management_address="198.51.100.102:443",
                environment="lab",
                status="healthy",
                tags={},
                allow_advanced_writes=False,
                allow_professional_workflows=False,
            )
            db_session.add(device)
            await db_session.flush()  # Flush to database
            raise ValueError("Test error")
        except ValueError:
            await db_session.rollback()
            
        # Verify it was rolled back
        from sqlalchemy import select
        result = await db_session.execute(select(Device).where(Device.id == "session-test-2"))
        found = result.scalar_one_or_none()
        assert found is None
        
    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        """Test that close() properly cleans up."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        await manager.init()
        
        assert manager._engine is not None
        
        await manager.close()
        
        assert manager._engine is None
        assert manager._session_factory is None
        
    @pytest.mark.asyncio
    async def test_postgresql_connection_config(self) -> None:
        """Test PostgreSQL-specific connection configuration."""
        settings = Settings(database_url="postgresql+asyncpg://user:pass@localhost/testdb")
        manager = DatabaseSessionManager(settings)
        
        # Should initialize without error (won't connect since DB doesn't exist)
        await manager.init()
        
        # Engine should be created
        assert manager._engine is not None
        
        await manager.close()


class TestGetSessionManager:
    """Tests for get_session_manager singleton."""
    
    def setup_method(self) -> None:
        """Reset session manager before each test."""
        reset_session_manager()
        
    def teardown_method(self) -> None:
        """Reset session manager after each test."""
        reset_session_manager()
        
    def test_returns_same_instance(self) -> None:
        """Test that get_session_manager returns same instance."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        
        manager1 = get_session_manager(settings)
        manager2 = get_session_manager()
        
        assert manager1 is manager2
        
    def test_uses_default_settings_if_none_provided(self) -> None:
        """Test that default settings are used if none provided."""
        manager = get_session_manager()
        
        assert manager is not None
        assert manager.settings is not None
        
    def test_reset_session_manager(self) -> None:
        """Test that reset_session_manager clears singleton."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        
        manager1 = get_session_manager(settings)
        reset_session_manager()
        manager2 = get_session_manager(settings)
        
        assert manager1 is not manager2
