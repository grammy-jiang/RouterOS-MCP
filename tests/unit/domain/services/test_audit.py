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


@pytest.mark.asyncio
async def test_list_events_date_range_filter(initialize_session_manager, db_session):
    """Test filtering audit events by date range."""
    from datetime import timedelta

    base_time = datetime.now(UTC)

    # Create events at different times
    event1 = AuditEvent(
        id="evt-001",
        timestamp=base_time - timedelta(days=5),
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
        timestamp=base_time - timedelta(days=2),
        user_sub="user-2",
        user_email="user2@example.com",
        user_role="operator",
        device_id="dev-002",
        environment="staging",
        action="READ_SENSITIVE",
        tool_name="device_test",
        tool_tier="fundamental",
        result="SUCCESS",
        meta={},
    )
    event3 = AuditEvent(
        id="evt-003",
        timestamp=base_time,
        user_sub="user-3",
        user_email="user3@example.com",
        user_role="admin",
        device_id="dev-003",
        environment="lab",
        action="WRITE",
        tool_name="device_update",
        tool_tier="fundamental",
        result="SUCCESS",
        meta={},
    )

    db_session.add(event1)
    db_session.add(event2)
    db_session.add(event3)
    await db_session.commit()

    service = AuditService(db_session)

    # Filter events from last 3 days
    result = await service.list_events(
        date_from=base_time - timedelta(days=3),
    )
    assert len(result["events"]) == 2
    event_ids = [e["id"] for e in result["events"]]
    assert "evt-002" in event_ids
    assert "evt-003" in event_ids

    # Filter events up to 3 days ago
    result = await service.list_events(
        date_to=base_time - timedelta(days=3),
    )
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-001"

    # Filter events in specific range
    result = await service.list_events(
        date_from=base_time - timedelta(days=4),
        date_to=base_time - timedelta(days=1),
    )
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-002"


@pytest.mark.asyncio
async def test_list_events_search_filter(initialize_session_manager, db_session):
    """Test keyword search in audit events."""
    # Create events with different error messages and metadata
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
        meta={"parameters": {"name": "test-router"}},
    )
    event2 = AuditEvent(
        id="evt-002",
        timestamp=datetime.now(UTC),
        user_sub="user-2",
        user_email="user2@example.com",
        user_role="operator",
        device_id="dev-002",
        environment="staging",
        action="WRITE",
        tool_name="device_test",
        tool_tier="fundamental",
        result="FAILURE",
        error_message="Connection timeout to device",
        meta={},
    )
    event3 = AuditEvent(
        id="evt-003",
        timestamp=datetime.now(UTC),
        user_sub="user-3",
        user_email="user3@example.com",
        user_role="admin",
        device_id="dev-003",
        environment="lab",
        action="READ_SENSITIVE",
        tool_name="device_info",
        tool_tier="fundamental",
        result="SUCCESS",
        meta={"result_summary": "Retrieved firewall configuration"},
    )

    db_session.add(event1)
    db_session.add(event2)
    db_session.add(event3)
    await db_session.commit()

    service = AuditService(db_session)

    # Search for "timeout" in error message
    result = await service.list_events(search="timeout")
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-002"

    # Search for "test" in metadata (should match event1's parameters)
    result = await service.list_events(search="test-router")
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-001"

    # Search for "firewall" in metadata
    result = await service.list_events(search="firewall")
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-003"

    # Search with no matches
    result = await service.list_events(search="nonexistent")
    assert len(result["events"]) == 0


@pytest.mark.asyncio
async def test_list_events_filter_by_user_id(initialize_session_manager, db_session):
    """Test filtering audit events by user_id (Phase 5)."""
    # Create events with different user IDs
    event1 = AuditEvent(
        id="evt-001",
        timestamp=datetime.now(UTC),
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        user_id="user-1",
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
        user_id="user-2",
        device_id="dev-002",
        environment="staging",
        action="WRITE",
        tool_name="device_test",
        tool_tier="fundamental",
        result="SUCCESS",
        meta={},
    )
    event3 = AuditEvent(
        id="evt-003",
        timestamp=datetime.now(UTC),
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        user_id="user-1",
        device_id="dev-003",
        environment="lab",
        action="READ_SENSITIVE",
        tool_name="device_info",
        tool_tier="fundamental",
        result="SUCCESS",
        meta={},
    )

    db_session.add(event1)
    db_session.add(event2)
    db_session.add(event3)
    await db_session.commit()

    service = AuditService(db_session)

    # Filter by user_id="user-1"
    result = await service.list_events(user_id="user-1")
    assert len(result["events"]) == 2
    event_ids = [e["id"] for e in result["events"]]
    assert "evt-001" in event_ids
    assert "evt-003" in event_ids

    # Filter by user_id="user-2"
    result = await service.list_events(user_id="user-2")
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-002"


@pytest.mark.asyncio
async def test_list_events_filter_by_approver_id(initialize_session_manager, db_session):
    """Test filtering audit events by approver_id (Phase 5)."""
    # Create approval events with different approvers
    event1 = AuditEvent(
        id="evt-001",
        timestamp=datetime.now(UTC),
        user_sub="approver-1",
        user_email="approver1@example.com",
        user_role="approver",
        user_id="user-1",
        approver_id="approver-1",
        approval_request_id="req-001",
        device_id=None,
        environment=None,
        action="APPROVAL_GRANTED",
        tool_name="firewall/plan",
        tool_tier="professional",
        plan_id="plan-001",
        result="SUCCESS",
        meta={},
    )
    event2 = AuditEvent(
        id="evt-002",
        timestamp=datetime.now(UTC),
        user_sub="approver-2",
        user_email="approver2@example.com",
        user_role="approver",
        user_id="user-2",
        approver_id="approver-2",
        approval_request_id="req-002",
        device_id=None,
        environment=None,
        action="APPROVAL_REJECTED",
        tool_name="routing/plan",
        tool_tier="professional",
        plan_id="plan-002",
        result="SUCCESS",
        meta={},
    )

    db_session.add(event1)
    db_session.add(event2)
    await db_session.commit()

    service = AuditService(db_session)

    # Filter by approver_id="approver-1"
    result = await service.list_events(approver_id="approver-1")
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-001"
    assert result["events"][0]["approver_id"] == "approver-1"

    # Filter by approver_id="approver-2"
    result = await service.list_events(approver_id="approver-2")
    assert len(result["events"]) == 1
    assert result["events"][0]["id"] == "evt-002"
    assert result["events"][0]["approver_id"] == "approver-2"


@pytest.mark.asyncio
async def test_list_events_filter_by_approval_request_id(initialize_session_manager, db_session):
    """Test filtering audit events by approval_request_id (Phase 5)."""
    # Create events associated with approval requests
    event1 = AuditEvent(
        id="evt-001",
        timestamp=datetime.now(UTC),
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        user_id="user-1",
        approval_request_id="req-001",
        device_id=None,
        environment=None,
        action="APPROVAL_REQUEST_CREATED",
        tool_name="firewall/plan",
        tool_tier="professional",
        plan_id="plan-001",
        result="SUCCESS",
        meta={},
    )
    event2 = AuditEvent(
        id="evt-002",
        timestamp=datetime.now(UTC),
        user_sub="approver-1",
        user_email="approver1@example.com",
        user_role="approver",
        user_id="user-1",
        approver_id="approver-1",
        approval_request_id="req-001",
        device_id=None,
        environment=None,
        action="APPROVAL_GRANTED",
        tool_name="firewall/plan",
        tool_tier="professional",
        plan_id="plan-001",
        result="SUCCESS",
        meta={},
    )
    event3 = AuditEvent(
        id="evt-003",
        timestamp=datetime.now(UTC),
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        user_id="user-1",
        approver_id="approver-1",
        approval_request_id="req-001",
        device_id="dev-001",
        environment="lab",
        action="PLAN_EXECUTION_STARTED",
        tool_name="firewall/plan",
        tool_tier="professional",
        plan_id="plan-001",
        job_id="job-001",
        result="SUCCESS",
        meta={},
    )

    db_session.add(event1)
    db_session.add(event2)
    db_session.add(event3)
    await db_session.commit()

    service = AuditService(db_session)

    # Filter by approval_request_id="req-001"
    result = await service.list_events(approval_request_id="req-001")
    assert len(result["events"]) == 3
    for event in result["events"]:
        assert event["approval_request_id"] == "req-001"


@pytest.mark.asyncio
async def test_log_approval_request_created(initialize_session_manager, db_session):
    """Test logging approval request creation event (Phase 5)."""
    service = AuditService(db_session)

    await service.log_approval_request_created(
        event_id="evt-001",
        user_id="user-1",
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        approval_request_id="req-001",
        plan_id="plan-001",
        tool_name="firewall/plan",
        meta={"plan_summary": "Add firewall rules"},
    )

    # Verify event was created
    result = await service.list_events(approval_request_id="req-001")
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["id"] == "evt-001"
    assert event["user_id"] == "user-1"
    assert event["action"] == "APPROVAL_REQUEST_CREATED"
    assert event["approval_request_id"] == "req-001"


@pytest.mark.asyncio
async def test_log_approval_granted(initialize_session_manager, db_session):
    """Test logging approval granted event (Phase 5)."""
    service = AuditService(db_session)

    await service.log_approval_granted(
        event_id="evt-002",
        user_id="user-1",
        approver_id="approver-1",
        user_sub="approver-1",
        user_email="approver1@example.com",
        user_role="approver",
        approval_request_id="req-001",
        plan_id="plan-001",
        tool_name="firewall/plan",
        meta={"approval_notes": "Looks good to me"},
    )

    # Verify event was created
    result = await service.list_events(approval_request_id="req-001")
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["id"] == "evt-002"
    assert event["user_id"] == "user-1"
    assert event["approver_id"] == "approver-1"
    assert event["action"] == "APPROVAL_GRANTED"


@pytest.mark.asyncio
async def test_log_approval_rejected(initialize_session_manager, db_session):
    """Test logging approval rejected event (Phase 5)."""
    service = AuditService(db_session)

    await service.log_approval_rejected(
        event_id="evt-003",
        user_id="user-1",
        approver_id="approver-1",
        user_sub="approver-1",
        user_email="approver1@example.com",
        user_role="approver",
        approval_request_id="req-002",
        plan_id="plan-002",
        tool_name="routing/plan",
        meta={"rejection_reason": "Needs more review"},
    )

    # Verify event was created
    result = await service.list_events(approval_request_id="req-002")
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["id"] == "evt-003"
    assert event["user_id"] == "user-1"
    assert event["approver_id"] == "approver-1"
    assert event["action"] == "APPROVAL_REJECTED"


@pytest.mark.asyncio
async def test_log_plan_execution_started(initialize_session_manager, db_session):
    """Test logging plan execution started event (Phase 5)."""
    service = AuditService(db_session)

    await service.log_plan_execution_started(
        event_id="evt-004",
        user_id="user-1",
        approver_id="approver-1",
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        approval_request_id="req-001",
        plan_id="plan-001",
        job_id="job-001",
        tool_name="firewall/plan",
        device_id="dev-001",
        environment="lab",
        meta={"execution_mode": "apply"},
    )

    # Verify event was created
    result = await service.list_events(approval_request_id="req-001")
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["id"] == "evt-004"
    assert event["user_id"] == "user-1"
    assert event["approver_id"] == "approver-1"
    assert event["action"] == "PLAN_EXECUTION_STARTED"
    assert event["approval_request_id"] == "req-001"


@pytest.mark.asyncio
async def test_phase5_event_fields_in_response(initialize_session_manager, db_session):
    """Test that Phase 5 fields are included in list_events response."""
    # Create event with all Phase 5 fields
    event = AuditEvent(
        id="evt-001",
        timestamp=datetime.now(UTC),
        user_sub="user-1",
        user_email="user1@example.com",
        user_role="admin",
        user_id="user-1",
        approver_id="approver-1",
        approval_request_id="req-001",
        device_id="dev-001",
        environment="lab",
        action="PLAN_EXECUTION_STARTED",
        tool_name="firewall/plan",
        tool_tier="professional",
        plan_id="plan-001",
        job_id="job-001",
        result="SUCCESS",
        meta={"test": "data"},
    )

    db_session.add(event)
    await db_session.commit()

    service = AuditService(db_session)
    result = await service.list_events()

    assert len(result["events"]) == 1
    event_data = result["events"][0]

    # Verify all Phase 5 fields are present
    assert "user_id" in event_data
    assert "approver_id" in event_data
    assert "approval_request_id" in event_data

    # Verify values
    assert event_data["user_id"] == "user-1"
    assert event_data["approver_id"] == "approver-1"
    assert event_data["approval_request_id"] == "req-001"
