"""Tests for ComplianceService.

Tests cover:
- Audit event export (JSON/CSV formats)
- Approval decision summaries with filtering
- Policy violation detection and reporting
- Role assignment audit trails
- Date range filtering
- Statistics generation
"""

import csv
import io
import pytest
from datetime import UTC, datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.services.compliance import ComplianceService
from routeros_mcp.infra.db.models import (
    ApprovalRequest as ApprovalRequestModel,
    AuditEvent as AuditEventORM,
    Base,
    Plan,
)


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


@pytest.fixture
async def compliance_service(db_session: AsyncSession) -> ComplianceService:
    """Create ComplianceService instance."""
    return ComplianceService(db_session)


@pytest.fixture
async def sample_audit_events(db_session: AsyncSession) -> list[AuditEventORM]:
    """Create sample audit events for testing."""
    now = datetime.now(UTC)

    events = [
        AuditEventORM(
            id="evt-001",
            timestamp=now - timedelta(hours=5),
            user_sub="user-1",
            user_email="user1@example.com",
            user_role="admin",
            user_id="uid-001",
            device_id="dev-001",
            environment="lab",
            action="WRITE",
            tool_name="device_create",
            tool_tier="fundamental",
            result="SUCCESS",
            meta={},
        ),
        AuditEventORM(
            id="evt-002",
            timestamp=now - timedelta(hours=4),
            user_sub="user-2",
            user_email="user2@example.com",
            user_role="operator",
            user_id="uid-002",
            device_id="dev-002",
            environment="staging",
            action="AUTHZ_DENIED",
            tool_name="firewall_write",
            tool_tier="professional",
            result="FAILURE",
            error_message="Insufficient permissions",
            meta={},
        ),
        AuditEventORM(
            id="evt-003",
            timestamp=now - timedelta(hours=3),
            user_sub="user-3",
            user_email="user3@example.com",
            user_role="read_only",
            user_id="uid-003",
            device_id="dev-001",
            environment="lab",
            action="AUTHZ_DENIED",
            tool_name="device_delete",
            tool_tier="advanced",
            result="FAILURE",
            error_message="Read-only user cannot delete",
            meta={},
        ),
        AuditEventORM(
            id="evt-004",
            timestamp=now - timedelta(hours=2),
            user_sub="user-1",
            user_email="user1@example.com",
            user_role="admin",
            user_id="uid-001",
            approver_id="uid-004",
            approval_request_id="appr-001",
            device_id="dev-003",
            environment="prod",
            action="APPROVAL_GRANTED",
            tool_name="firewall_plan",
            tool_tier="professional",
            result="SUCCESS",
            meta={},
        ),
        AuditEventORM(
            id="evt-005",
            timestamp=now - timedelta(hours=1),
            user_sub="user-2",
            user_email="user2@example.com",
            user_role="operator",
            user_id="uid-002",
            device_id="dev-002",
            environment="staging",
            action="READ_SENSITIVE",
            tool_name="device_credentials",
            tool_tier="advanced",
            result="SUCCESS",
            meta={},
        ),
    ]

    for event in events:
        db_session.add(event)
    await db_session.commit()

    return events


@pytest.fixture
async def sample_approval_requests(db_session: AsyncSession) -> list[ApprovalRequestModel]:
    """Create sample approval requests for testing."""
    now = datetime.now(UTC)

    # Create test plans first
    plans = [
        Plan(
            id="plan-001",
            created_by="user-1",
            tool_name="firewall_plan",
            status="approved",
            device_ids=["dev-001"],
            summary="Firewall changes",
            changes={},
        ),
        Plan(
            id="plan-002",
            created_by="user-2",
            tool_name="routing_plan",
            status="rejected",
            device_ids=["dev-002"],
            summary="Routing changes",
            changes={},
        ),
        Plan(
            id="plan-003",
            created_by="user-3",
            tool_name="wireless_plan",
            status="pending",
            device_ids=["dev-003"],
            summary="Wireless changes",
            changes={},
        ),
    ]

    for plan in plans:
        db_session.add(plan)

    # Create approval requests
    requests = [
        ApprovalRequestModel(
            id="appr-001",
            plan_id="plan-001",
            requested_by="user-1",
            requested_at=now - timedelta(days=3),
            status="approved",
            approved_by="user-admin",
            approved_at=now - timedelta(days=2),
            notes="Looks good",
        ),
        ApprovalRequestModel(
            id="appr-002",
            plan_id="plan-002",
            requested_by="user-2",
            requested_at=now - timedelta(days=2),
            status="rejected",
            rejected_by="user-admin",
            rejected_at=now - timedelta(days=1),
            notes="Security concerns",
        ),
        ApprovalRequestModel(
            id="appr-003",
            plan_id="plan-003",
            requested_by="user-3",
            requested_at=now - timedelta(days=1),
            status="pending",
            notes="Urgent request",
        ),
    ]

    for request in requests:
        db_session.add(request)
    await db_session.commit()

    return requests


# ==================== Test: Audit Event Export (JSON) ====================


@pytest.mark.asyncio
async def test_export_audit_events_json_no_filters(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test exporting audit events in JSON format without filters."""
    result = await compliance_service.export_audit_events(format="json")

    assert "events" in result
    assert "count" in result
    assert "filters" in result

    assert result["count"] == 5
    assert len(result["events"]) == 5

    # Check that events are ordered by timestamp (most recent first)
    timestamps = [e["timestamp"] for e in result["events"]]
    assert timestamps == sorted(timestamps, reverse=True)


@pytest.mark.asyncio
async def test_export_audit_events_json_with_date_range(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test exporting audit events with date range filter."""
    now = datetime.now(UTC)
    date_from = now - timedelta(hours=4, minutes=30)
    date_to = now - timedelta(hours=1, minutes=30)

    result = await compliance_service.export_audit_events(
        date_from=date_from,
        date_to=date_to,
        format="json",
    )

    # Should get events within the date range: evt-002, evt-003, evt-004
    assert result["count"] == 3
    assert result["filters"]["date_from"] == date_from.isoformat()
    assert result["filters"]["date_to"] == date_to.isoformat()


@pytest.mark.asyncio
async def test_export_audit_events_json_with_device_filter(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test exporting audit events filtered by device ID."""
    result = await compliance_service.export_audit_events(
        device_id="dev-001",
        format="json",
    )

    # Should get events for dev-001: evt-001, evt-003
    assert result["count"] == 2
    assert all(e["device_id"] == "dev-001" for e in result["events"])
    assert result["filters"]["device_id"] == "dev-001"


@pytest.mark.asyncio
async def test_export_audit_events_json_with_user_filter(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test exporting audit events filtered by user ID."""
    result = await compliance_service.export_audit_events(
        user_id="uid-001",
        format="json",
    )

    # Should get events for uid-001: evt-001, evt-004
    assert result["count"] == 2
    assert all(e["user_id"] == "uid-001" for e in result["events"])


@pytest.mark.asyncio
async def test_export_audit_events_json_with_tool_filter(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test exporting audit events filtered by tool name."""
    result = await compliance_service.export_audit_events(
        tool_name="device_create",
        format="json",
    )

    # Should get events for device_create tool: evt-001
    assert result["count"] == 1
    assert result["events"][0]["tool_name"] == "device_create"


# ==================== Test: Audit Event Export (CSV) ====================


@pytest.mark.asyncio
async def test_export_audit_events_csv_format(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test exporting audit events in CSV format."""
    result = await compliance_service.export_audit_events(format="csv")

    # Result should be a CSV string
    assert isinstance(result, str)
    assert "ID,Timestamp,User Sub" in result

    # Parse CSV to verify structure
    reader = csv.DictReader(io.StringIO(result))
    rows = list(reader)

    assert len(rows) == 5

    # Check first row has expected fields
    first_row = rows[0]
    assert "ID" in first_row
    assert "Timestamp" in first_row
    assert "User Sub" in first_row
    assert "Device ID" in first_row
    assert "Action" in first_row


# ==================== Test: Approval Decisions ====================


@pytest.mark.asyncio
async def test_get_approval_decisions_no_filters(
    compliance_service: ComplianceService,
    sample_approval_requests: list[ApprovalRequestModel],
) -> None:
    """Test getting approval decisions without filters."""
    result = await compliance_service.get_approval_decisions()

    assert "decisions" in result
    assert "total" in result
    assert "statistics" in result

    assert result["total"] == 3
    assert len(result["decisions"]) == 3

    # Check statistics
    stats = result["statistics"]
    assert stats["approved"] == 1
    assert stats["rejected"] == 1
    assert stats["pending"] == 1


@pytest.mark.asyncio
async def test_get_approval_decisions_approved_only(
    compliance_service: ComplianceService,
    sample_approval_requests: list[ApprovalRequestModel],
) -> None:
    """Test getting only approved decisions."""
    result = await compliance_service.get_approval_decisions(status="approved")

    assert result["total"] == 1
    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["status"] == "approved"
    assert result["decisions"][0]["approved_by"] == "user-admin"
    assert result["filters"]["status"] == "approved"


@pytest.mark.asyncio
async def test_get_approval_decisions_rejected_only(
    compliance_service: ComplianceService,
    sample_approval_requests: list[ApprovalRequestModel],
) -> None:
    """Test getting only rejected decisions."""
    result = await compliance_service.get_approval_decisions(status="rejected")

    assert result["total"] == 1
    assert len(result["decisions"]) == 1
    assert result["decisions"][0]["status"] == "rejected"
    assert result["decisions"][0]["rejected_by"] == "user-admin"
    assert result["filters"]["status"] == "rejected"


@pytest.mark.asyncio
async def test_get_approval_decisions_with_date_filter(
    compliance_service: ComplianceService,
    sample_approval_requests: list[ApprovalRequestModel],
) -> None:
    """Test getting approval decisions with date filter."""
    now = datetime.now(UTC)
    date_from = now - timedelta(days=2, hours=12)

    result = await compliance_service.get_approval_decisions(date_from=date_from)

    # Should get requests from last 2.5 days: appr-002, appr-003
    assert result["total"] == 2
    assert result["filters"]["date_from"] == date_from.isoformat()


@pytest.mark.asyncio
async def test_get_approval_decisions_pagination(
    compliance_service: ComplianceService,
    sample_approval_requests: list[ApprovalRequestModel],
) -> None:
    """Test approval decisions pagination."""
    result = await compliance_service.get_approval_decisions(limit=2, offset=0)

    assert len(result["decisions"]) == 2
    assert result["total"] == 3
    assert result["limit"] == 2
    assert result["offset"] == 0

    # Get next page
    result_page2 = await compliance_service.get_approval_decisions(limit=2, offset=2)
    assert len(result_page2["decisions"]) == 1


# ==================== Test: Policy Violations ====================


@pytest.mark.asyncio
async def test_get_policy_violations_all(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test getting all policy violations (AUTHZ_DENIED events)."""
    result = await compliance_service.get_policy_violations()

    assert "violations" in result
    assert "total" in result
    assert "statistics" in result

    # Should have 2 AUTHZ_DENIED events: evt-002, evt-003
    assert result["total"] == 2
    assert len(result["violations"]) == 2

    # Check all violations are AUTHZ_DENIED actions
    for violation in result["violations"]:
        assert violation["error_message"] is not None


@pytest.mark.asyncio
async def test_get_policy_violations_by_device(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test getting policy violations filtered by device."""
    result = await compliance_service.get_policy_violations(device_id="dev-001")

    # Should have 1 violation on dev-001: evt-003
    assert result["total"] == 1
    assert len(result["violations"]) == 1
    assert result["violations"][0]["device_id"] == "dev-001"
    assert result["filters"]["device_id"] == "dev-001"


@pytest.mark.asyncio
async def test_get_policy_violations_with_date_range(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test getting policy violations with date range."""
    now = datetime.now(UTC)
    date_from = now - timedelta(hours=3, minutes=30)
    date_to = now - timedelta(hours=2, minutes=30)

    result = await compliance_service.get_policy_violations(
        date_from=date_from,
        date_to=date_to,
    )

    # Should have 1 violation in range: evt-003
    assert result["total"] == 1
    assert result["filters"]["date_from"] == date_from.isoformat()
    assert result["filters"]["date_to"] == date_to.isoformat()


@pytest.mark.asyncio
async def test_get_policy_violations_statistics(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test policy violations statistics by device."""
    result = await compliance_service.get_policy_violations()

    stats = result["statistics"]
    assert stats["total_violations"] == 2

    # Check by_device breakdown
    by_device = stats["by_device"]
    assert by_device["dev-001"] == 1  # evt-003
    assert by_device["dev-002"] == 1  # evt-002


# ==================== Test: Role Audit ====================


@pytest.mark.asyncio
async def test_get_role_audit_all(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test getting role audit trail for all users."""
    result = await compliance_service.get_role_audit()

    assert "role_history" in result
    assert "total_events" in result
    assert "filters" in result

    # Should have events for 3 users: uid-001, uid-002, uid-003
    role_history = result["role_history"]
    assert "uid-001" in role_history
    assert "uid-002" in role_history
    assert "uid-003" in role_history


@pytest.mark.asyncio
async def test_get_role_audit_by_user(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test getting role audit trail for specific user."""
    result = await compliance_service.get_role_audit(user_id="uid-001")

    role_history = result["role_history"]
    assert "uid-001" in role_history
    assert len(role_history) == 1  # Only uid-001

    # Check uid-001 has 2 events: evt-001, evt-004
    assert len(role_history["uid-001"]) == 2
    assert result["filters"]["user_id"] == "uid-001"


@pytest.mark.asyncio
async def test_get_role_audit_with_date_range(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test getting role audit trail with date range."""
    now = datetime.now(UTC)
    date_from = now - timedelta(hours=3, minutes=30)
    date_to = now - timedelta(hours=0, minutes=30)

    result = await compliance_service.get_role_audit(
        date_from=date_from,
        date_to=date_to,
    )

    # Should have events in range: evt-003, evt-004, evt-005
    role_history = result["role_history"]
    assert len(role_history) >= 2  # At least uid-001, uid-002, uid-003

    assert result["filters"]["date_from"] == date_from.isoformat()
    assert result["filters"]["date_to"] == date_to.isoformat()


@pytest.mark.asyncio
async def test_get_role_audit_tracks_role_changes(
    compliance_service: ComplianceService,
    sample_audit_events: list[AuditEventORM],
) -> None:
    """Test that role audit tracks user role field in events."""
    result = await compliance_service.get_role_audit(user_id="uid-001")

    # Check that role history includes user_role field
    uid_001_history = result["role_history"]["uid-001"]
    assert all("user_role" in event for event in uid_001_history)

    # Check that role is captured correctly
    assert any(event["user_role"] == "admin" for event in uid_001_history)


# ==================== Test: Empty Results ====================


@pytest.mark.asyncio
async def test_export_audit_events_empty_database(
    compliance_service: ComplianceService,
) -> None:
    """Test exporting audit events from empty database."""
    result = await compliance_service.export_audit_events(format="json")

    assert result["count"] == 0
    assert len(result["events"]) == 0


@pytest.mark.asyncio
async def test_get_approval_decisions_empty_database(
    compliance_service: ComplianceService,
) -> None:
    """Test getting approval decisions from empty database."""
    result = await compliance_service.get_approval_decisions()

    assert result["total"] == 0
    assert len(result["decisions"]) == 0
    assert result["statistics"]["approved"] == 0
    assert result["statistics"]["rejected"] == 0
    assert result["statistics"]["pending"] == 0


@pytest.mark.asyncio
async def test_get_policy_violations_empty_database(
    compliance_service: ComplianceService,
) -> None:
    """Test getting policy violations from empty database."""
    result = await compliance_service.get_policy_violations()

    assert result["total"] == 0
    assert len(result["violations"]) == 0


@pytest.mark.asyncio
async def test_get_role_audit_empty_database(
    compliance_service: ComplianceService,
) -> None:
    """Test getting role audit from empty database."""
    result = await compliance_service.get_role_audit()

    assert result["total_events"] == 0
    assert len(result["role_history"]) == 0
