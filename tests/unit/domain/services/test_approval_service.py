"""Tests for ApprovalService.

Tests cover:
- Approval request creation
- List requests with filtering
- Approve requests
- Reject requests
- Self-approval prevention
- Status validation
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.services.approval import ApprovalService
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
async def test_plan(db_session: AsyncSession) -> str:
    """Create a test plan."""
    # Create test device first
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

    # Create test plan
    plan = Plan(
        id="plan-test-01",
        created_by="user-creator",
        tool_name="test_tool",
        status="pending",
        device_ids=["dev-test-01"],
        summary="Test plan",
        changes={"action": "test"},
    )
    db_session.add(plan)
    await db_session.commit()

    return plan.id


@pytest.fixture
async def approval_service(db_session: AsyncSession) -> ApprovalService:
    """Create ApprovalService instance."""
    return ApprovalService(db_session)


# ==================== Test: Create Approval Request ====================


@pytest.mark.asyncio
async def test_create_request_success(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test successful approval request creation."""
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
        notes="Please approve this plan",
    )

    assert request.id.startswith("approval-")
    assert request.plan_id == test_plan
    assert request.requested_by == "user-requester"
    assert request.status == "pending"
    assert request.notes == "Please approve this plan"
    assert request.requested_at is not None
    assert request.approved_by is None
    assert request.approved_at is None
    assert request.rejected_by is None
    assert request.rejected_at is None


@pytest.mark.asyncio
async def test_create_request_plan_not_found(
    approval_service: ApprovalService,
) -> None:
    """Test creation fails when plan does not exist."""
    with pytest.raises(ValueError, match="Plan not found"):
        await approval_service.create_request(
            plan_id="nonexistent-plan",
            requested_by="user-requester",
        )


@pytest.mark.asyncio
async def test_create_request_duplicate_pending(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test creation fails when plan already has pending request."""
    # Create first request
    await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )

    # Try to create second request for same plan
    with pytest.raises(ValueError, match="already has a pending approval request"):
        await approval_service.create_request(
            plan_id=test_plan,
            requested_by="user-requester-2",
        )


# ==================== Test: List Approval Requests ====================


@pytest.mark.asyncio
async def test_list_requests_all(
    approval_service: ApprovalService,
    test_plan: str,
    db_session: AsyncSession,
) -> None:
    """Test listing all approval requests."""
    # Create multiple requests with different statuses
    request1 = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-1",
    )

    # Manually create additional plans and requests for testing
    plan2 = Plan(
        id="plan-test-02",
        created_by="user-creator",
        tool_name="test_tool",
        status="pending",
        device_ids=["dev-test-01"],
        summary="Test plan 2",
        changes={"action": "test"},
    )
    db_session.add(plan2)
    await db_session.commit()

    request2 = await approval_service.create_request(
        plan_id="plan-test-02",
        requested_by="user-2",
    )

    # List all requests
    requests = await approval_service.list_requests()

    assert len(requests) == 2
    assert {r.id for r in requests} == {request1.id, request2.id}


@pytest.mark.asyncio
async def test_list_requests_filter_by_status(
    approval_service: ApprovalService,
    test_plan: str,
    db_session: AsyncSession,
) -> None:
    """Test filtering requests by status."""
    # Create request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )

    # Approve it
    await approval_service.approve_request(
        approval_request_id=request.id,
        approved_by="user-approver",
    )

    # Create another plan and pending request
    plan2 = Plan(
        id="plan-test-03",
        created_by="user-creator",
        tool_name="test_tool",
        status="pending",
        device_ids=["dev-test-01"],
        summary="Test plan 3",
        changes={"action": "test"},
    )
    db_session.add(plan2)
    await db_session.commit()

    request2 = await approval_service.create_request(
        plan_id="plan-test-03",
        requested_by="user-requester-2",
    )

    # Filter by pending status
    pending_requests = await approval_service.list_requests(status="pending")
    assert len(pending_requests) == 1
    assert pending_requests[0].id == request2.id

    # Filter by approved status
    approved_requests = await approval_service.list_requests(status="approved")
    assert len(approved_requests) == 1
    assert approved_requests[0].id == request.id


@pytest.mark.asyncio
async def test_list_requests_filter_by_plan_id(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test filtering requests by plan ID."""
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )

    # Filter by plan ID
    requests = await approval_service.list_requests(plan_id=test_plan)
    assert len(requests) == 1
    assert requests[0].id == request.id


@pytest.mark.asyncio
async def test_list_requests_pagination(
    approval_service: ApprovalService,
    db_session: AsyncSession,
) -> None:
    """Test pagination when listing requests."""
    # Create multiple plans and requests
    for i in range(5):
        plan = Plan(
            id=f"plan-test-{i}",
            created_by="user-creator",
            tool_name="test_tool",
            status="pending",
            device_ids=["dev-test-01"],
            summary=f"Test plan {i}",
            changes={"action": "test"},
        )
        db_session.add(plan)
        await db_session.commit()

        await approval_service.create_request(
            plan_id=f"plan-test-{i}",
            requested_by="user-requester",
        )

    # Test limit
    requests = await approval_service.list_requests(limit=2)
    assert len(requests) == 2

    # Test offset
    requests = await approval_service.list_requests(limit=2, offset=2)
    assert len(requests) == 2


# ==================== Test: Approve Request ====================


@pytest.mark.asyncio
async def test_approve_request_success(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test successful approval of request."""
    # Create request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )

    # Approve it
    approved = await approval_service.approve_request(
        approval_request_id=request.id,
        approved_by="user-approver",
        notes="Looks good",
    )

    assert approved.id == request.id
    assert approved.status == "approved"
    assert approved.approved_by == "user-approver"
    assert approved.approved_at is not None
    assert approved.notes == "Looks good"
    assert approved.rejected_by is None
    assert approved.rejected_at is None


@pytest.mark.asyncio
async def test_approve_request_not_found(
    approval_service: ApprovalService,
) -> None:
    """Test approval fails when request does not exist."""
    with pytest.raises(ValueError, match="Approval request not found"):
        await approval_service.approve_request(
            approval_request_id="nonexistent-request",
            approved_by="user-approver",
        )


@pytest.mark.asyncio
async def test_approve_request_already_approved(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test approval fails when request is already approved."""
    # Create and approve request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )
    await approval_service.approve_request(
        approval_request_id=request.id,
        approved_by="user-approver",
    )

    # Try to approve again
    with pytest.raises(ValueError, match="already approved"):
        await approval_service.approve_request(
            approval_request_id=request.id,
            approved_by="user-approver-2",
        )


@pytest.mark.asyncio
async def test_approve_request_self_approval_prevention(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test that users cannot approve their own requests."""
    # Create request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )

    # Try to self-approve
    with pytest.raises(ValueError, match="cannot approve their own requests"):
        await approval_service.approve_request(
            approval_request_id=request.id,
            approved_by="user-requester",  # Same as requested_by
        )


# ==================== Test: Reject Request ====================


@pytest.mark.asyncio
async def test_reject_request_success(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test successful rejection of request."""
    # Create request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )

    # Reject it
    rejected = await approval_service.reject_request(
        approval_request_id=request.id,
        rejected_by="user-approver",
        notes="Not ready yet",
    )

    assert rejected.id == request.id
    assert rejected.status == "rejected"
    assert rejected.rejected_by == "user-approver"
    assert rejected.rejected_at is not None
    assert rejected.notes == "Not ready yet"
    assert rejected.approved_by is None
    assert rejected.approved_at is None


@pytest.mark.asyncio
async def test_reject_request_not_found(
    approval_service: ApprovalService,
) -> None:
    """Test rejection fails when request does not exist."""
    with pytest.raises(ValueError, match="Approval request not found"):
        await approval_service.reject_request(
            approval_request_id="nonexistent-request",
            rejected_by="user-approver",
        )


@pytest.mark.asyncio
async def test_reject_request_already_rejected(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test rejection fails when request is already rejected."""
    # Create and reject request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )
    await approval_service.reject_request(
        approval_request_id=request.id,
        rejected_by="user-approver",
    )

    # Try to reject again
    with pytest.raises(ValueError, match="already rejected"):
        await approval_service.reject_request(
            approval_request_id=request.id,
            rejected_by="user-approver-2",
        )


@pytest.mark.asyncio
async def test_reject_request_already_approved(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test rejection fails when request is already approved."""
    # Create and approve request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )
    await approval_service.approve_request(
        approval_request_id=request.id,
        approved_by="user-approver",
    )

    # Try to reject
    with pytest.raises(ValueError, match="already approved"):
        await approval_service.reject_request(
            approval_request_id=request.id,
            rejected_by="user-approver-2",
        )


# ==================== Test: Get Request ====================


@pytest.mark.asyncio
async def test_get_request_success(
    approval_service: ApprovalService,
    test_plan: str,
) -> None:
    """Test getting a single request by ID."""
    # Create request
    request = await approval_service.create_request(
        plan_id=test_plan,
        requested_by="user-requester",
    )

    # Get it
    retrieved = await approval_service.get_request(request.id)
    assert retrieved is not None
    assert retrieved.id == request.id
    assert retrieved.plan_id == test_plan


@pytest.mark.asyncio
async def test_get_request_not_found(
    approval_service: ApprovalService,
) -> None:
    """Test getting a non-existent request returns None."""
    retrieved = await approval_service.get_request("nonexistent-request")
    assert retrieved is None
