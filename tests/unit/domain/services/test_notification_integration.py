"""Integration tests for notification service with approval and job services.

Tests cover:
- Approval service sends notifications on approve/reject
- Job service sends notifications on completion/failure
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.services.approval import ApprovalService
from routeros_mcp.domain.services.job import JobService
from routeros_mcp.domain.services.notification import (
    MockNotificationBackend,
    NotificationService,
)
from routeros_mcp.infra.db.models import Base, Device, Plan


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
async def test_device(db_session: AsyncSession) -> str:
    """Create a test device."""
    device = Device(
        id="dev-test-01",
        name="router-test-01",
        management_ip="192.168.1.1",
        management_port=443,
        environment="lab",
        status="healthy",
        tags={},
        allow_advanced_writes=True,
        allow_professional_workflows=True,
    )
    db_session.add(device)
    await db_session.commit()
    return device.id


@pytest.fixture
async def test_plan(db_session: AsyncSession, test_device: str) -> str:
    """Create a test plan."""
    plan = Plan(
        id="plan-test-01",
        created_by="user-creator",
        tool_name="test_tool",
        status="pending",
        device_ids=[test_device],
        summary="Test plan for notifications",
        changes={"action": "test"},
    )
    db_session.add(plan)
    await db_session.commit()
    return plan.id


@pytest.fixture
def notification_backend() -> MockNotificationBackend:
    """Create mock notification backend."""
    return MockNotificationBackend()


@pytest.fixture
def notification_service(notification_backend: MockNotificationBackend) -> NotificationService:
    """Create notification service with mock backend."""
    return NotificationService(
        backend=notification_backend,
        from_address="test@example.com",
        base_url="https://routeros-mcp.example.com",
    )


@pytest.fixture
async def approval_service(
    db_session: AsyncSession, notification_service: NotificationService
) -> ApprovalService:
    """Create approval service with notification service."""
    return ApprovalService(db_session, notification_service=notification_service)


@pytest.fixture
async def job_service(
    db_session: AsyncSession, notification_service: NotificationService
) -> JobService:
    """Create job service with notification service."""
    return JobService(db_session, notification_service=notification_service)


# ==================== Test: Approval Service Integration ====================


@pytest.mark.asyncio
async def test_approval_service_sends_notification_on_approve(
    approval_service: ApprovalService,
    notification_backend: MockNotificationBackend,
    test_plan: str,
) -> None:
    """Test that approval service sends notification when request is approved."""
    # Create approval request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
        notes="Please approve",
    )

    # Clear any notifications from request creation
    notification_backend.clear()

    # Approve the request
    await approval_service.approve_request(
        approval_request_id=request.id,
        approved_by="user-approver",
        notes="Looks good",
    )

    # Verify notification was sent
    assert len(notification_backend.sent_notifications) == 1
    notification = notification_backend.sent_notifications[0]
    assert notification.to_address == "user-requester@placeholder.invalid"
    assert test_plan in notification.subject
    assert "Approved" in notification.subject
    assert "user-approver" in notification.body_text
    assert "Looks good" in notification.body_text
    assert "https://routeros-mcp.example.com/plans/plan-test-01" in notification.body_text


@pytest.mark.asyncio
async def test_approval_service_sends_notification_on_reject(
    approval_service: ApprovalService,
    notification_backend: MockNotificationBackend,
    test_plan: str,
) -> None:
    """Test that approval service sends notification when request is rejected."""
    # Create approval request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
        notes="Please approve",
    )

    # Clear any notifications from request creation
    notification_backend.clear()

    # Reject the request
    await approval_service.reject_request(
        approval_request_id=request.id,
        rejected_by="user-approver",
        notes="Needs more work",
    )

    # Verify notification was sent
    assert len(notification_backend.sent_notifications) == 1
    notification = notification_backend.sent_notifications[0]
    assert notification.to_address == "user-requester@placeholder.invalid"
    assert test_plan in notification.subject
    assert "Rejected" in notification.subject
    assert "user-approver" in notification.body_text
    assert "Needs more work" in notification.body_text
    assert "https://routeros-mcp.example.com/plans/plan-test-01" in notification.body_text


@pytest.mark.asyncio
async def test_approval_service_no_notification_without_service(
    db_session: AsyncSession,
    test_plan: str,
) -> None:
    """Test that approval service works without notification service."""
    # Create approval service WITHOUT notification service
    approval_service = ApprovalService(db_session, notification_service=None)

    # Create and approve request - should not raise any errors
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )

    approved = await approval_service.approve_request(
        approval_request_id=request.id,
        approved_by="user-approver",
    )

    assert approved.status == "approved"
