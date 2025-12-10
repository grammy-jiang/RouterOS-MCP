"""Tests for database session management."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.infra.db.session import (
    DatabaseSessionManager,
    get_session_manager,
    reset_session_manager,
)


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
    async def test_session_auto_commit_on_success(self) -> None:
        """Test that session auto-commits on success."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        await manager.init()
        
        # Create tables
        from routeros_mcp.infra.db.models import Base
        async with manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        # Insert a record
        from routeros_mcp.infra.db.models import Device
        async with manager.session() as session:
            device = Device(
                id="test-1",
                name="test-router",
                management_address="192.168.1.1:443",
                environment="lab",
                status="healthy",
                tags={},
                allow_advanced_writes=False,
                allow_professional_workflows=False,
            )
            session.add(device)
            # Auto-commits on exit
            
        # Verify it was committed
        async with manager.session() as session:
            from sqlalchemy import select
            result = await session.execute(select(Device).where(Device.id == "test-1"))
            found = result.scalar_one_or_none()
            assert found is not None
            assert found.name == "test-router"
            
        await manager.close()
        
    @pytest.mark.asyncio
    async def test_session_auto_rollback_on_error(self) -> None:
        """Test that session auto-rolls back on error."""
        settings = Settings(database_url="sqlite+aiosqlite:///./test.db")
        manager = DatabaseSessionManager(settings)
        await manager.init()
        
        # Create tables
        from routeros_mcp.infra.db.models import Base
        async with manager.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        # Try to insert a record but raise error
        from routeros_mcp.infra.db.models import Device
        try:
            async with manager.session() as session:
                device = Device(
                    id="test-2",
                    name="test-router-2",
                    management_address="192.168.1.2:443",
                    environment="lab",
                    status="healthy",
                    tags={},
                    allow_advanced_writes=False,
                    allow_professional_workflows=False,
                )
                session.add(device)
                raise ValueError("Test error")
        except ValueError:
            pass
            
        # Verify it was rolled back
        async with manager.session() as session:
            from sqlalchemy import select
            result = await session.execute(select(Device).where(Device.id == "test-2"))
            found = result.scalar_one_or_none()
            assert found is None
            
        await manager.close()
        
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
