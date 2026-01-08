"""Tests for audit service."""

import pytest
from datetime import datetime, UTC
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from routeros_mcp.domain.services.audit import AuditService
from routeros_mcp.infra.db.models import AuditEvent, Base


@pytest.fixture
async def db_session() -> AsyncSession:
    """Create an in-memory database session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_list_events_empty(initialize_session_manager, db_session):
    """Test listing audit events when database is empty."""
    service = AuditService(db_session)
    result = await service.list_events()
    
    assert result["events"] == []
    assert result["total"] == 0
    assert result["page"] == 1
    assert result["total_pages"] == 0


@pytest.mark.asyncio
async def test_list_events_with_data(initialize_session_manager, db_session):
    """Test listing audit events with some data."""
    # Create test events
    event1 = AuditEvent(
        id="evt-001",
        timestamp=datetime.now(UTC),
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        device_id="dev-001",
        environment="lab",
        action="WRITE",
        tool_name="device_create",
        tool_tier="fundamental",
        result="SUCCESS",
        meta={"parameters": {"name": "test"}},
    )
    event2 = AuditEvent(
        id="evt-002",
        timestamp=datetime.now(UTC),
        user_sub="user-2",
        user_email="user2@example.com",
        user_role="operator",
        device_id="dev-002",
        environment="staging",
        action="READ_SENSITIVE",
        tool_name="device_test",
        tool_tier="fundamental",
        result="FAILURE",
        error_message="Connection timeout",
        meta={"parameters": {"device_id": "dev-002"}},
    )
    
    db_session.add(event1)
    db_session.add(event2)
    await db_session.commit()
    
    # List events
    service = AuditService(db_session)
    result = await service.list_events(page=1, page_size=10)
    
    assert len(result["events"]) == 2
    assert result["total"] == 2
    assert result["page"] == 1
    assert result["total_pages"] == 1
    
    # Verify event data
    events = result["events"]
    assert events[0]["id"] == "evt-002"  # Most recent first
    assert events[0]["success"] is False
    assert events[1]["id"] == "evt-001"
    assert events[1]["success"] is True


@pytest.mark.asyncio
async def test_list_events_with_filters(initialize_session_manager, db_session):
    """Test listing audit events with filters."""
    # Create test events
    event1 = AuditEvent(
        id="evt-001",
        timestamp=datetime.now(UTC),
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        device_id="dev-001",
        environment="lab",
        action="WRITE",
        tool_name="device_create",
        tool_tier="fundamental",
        result="SUCCESS",
        meta={},
    )
    event2 = AuditEvent(
        id="evt-002",
        timestamp=datetime.now(UTC),
        user_sub="user-2",
        user_email="user2@example.com",
        user_role="operator",
        device_id="dev-002",
        environment="staging",
        action="READ_SENSITIVE",
        tool_name="device_test",
        tool_tier="fundamental",
        result="FAILURE",
        error_message="Connection timeout",
        meta={},
    )
    
    db_session.add(event1)
    db_session.add(event2)
    await db_session.commit()
    
    service = AuditService(db_session)
    
    # Filter by device_id
    result = await service.list_events(device_id="dev-001")
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-001"
    
    # Filter by success
    result = await service.list_events(success=False)
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-002"
    
    # Filter by tool_name
    result = await service.list_events(tool_name="device_test")
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-002"


@pytest.mark.asyncio
async def test_list_events_pagination(initialize_session_manager, db_session):
    """Test pagination for audit events."""
    # Create multiple test events
    for i in range(25):
        event = AuditEvent(
            id=f"evt-{i:03d}",
            timestamp=datetime.now(UTC),
            user_sub=f"user-{i}",
            user_email=f"user{i}@example.com",
            user_role="admin",
            device_id=f"dev-{i:03d}",
            environment="lab",
            action="WRITE",
            tool_name="device_create",
            tool_tier="fundamental",
            result="SUCCESS",
            meta={},
        )
        db_session.add(event)
    
    await db_session.commit()
    
    service = AuditService(db_session)
    
    # First page
    result = await service.list_events(page=1, page_size=10)
    assert len(result["events"]) == 10
    assert result["total"] == 25
    assert result["page"] == 1
    assert result["total_pages"] == 3
    
    # Second page
    result = await service.list_events(page=2, page_size=10)
    assert len(result["events"]) == 10
    assert result["page"] == 2
    
    # Last page
    result = await service.list_events(page=3, page_size=10)
    assert len(result["events"]) == 5
    assert result["page"] == 3


@pytest.mark.asyncio
async def test_get_unique_devices(initialize_session_manager, db_session):
    """Test getting unique device IDs."""
    # Create test events with different devices
    for i, device_id in enumerate(["dev-001", "dev-002", "dev-001"]):
        event = AuditEvent(
            id=f"evt-{i:03d}",
            timestamp=datetime.now(UTC),
            user_sub=f"user-{i}",
            user_email=f"user{i}@example.com",
            user_role="admin",
            device_id=device_id,
            environment="lab",
            action="WRITE",
            tool_name="device_create",
            tool_tier="fundamental",
            result="SUCCESS",
            meta={},
        )
        db_session.add(event)
    
    await db_session.commit()
    
    service = AuditService(db_session)
    devices = await service.get_unique_devices()
    
    assert len(devices) == 2
    assert "dev-001" in devices
    assert "dev-002" in devices


@pytest.mark.asyncio
async def test_get_unique_tools(initialize_session_manager, db_session):
    """Test getting unique tool names."""
    # Create test events with different tools
    for i, tool_name in enumerate(["device_create", "device_test", "device_create"]):
        event = AuditEvent(
            id=f"evt-{i:03d}",
            timestamp=datetime.now(UTC),
            user_sub=f"user-{i}",
            user_email=f"user{i}@example.com",
            user_role="admin",
            device_id=f"dev-{i:03d}",
            environment="lab",
            action="WRITE",
            tool_name=tool_name,
            tool_tier="fundamental",
            result="SUCCESS",
            meta={},
        )
        db_session.add(event)
    
    await db_session.commit()
    
    service = AuditService(db_session)
    tools = await service.get_unique_tools()
    
    assert len(tools) == 2
    assert "device_create" in tools
    assert "device_test" in tools
