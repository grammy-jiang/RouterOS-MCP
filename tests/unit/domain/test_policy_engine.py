"""Tests for PolicyEngine.

Tests cover:
- Tier validation for all user roles
- Self-approval prevention
- Device scope enforcement
- Admin override with audit trail
- Tool tier access validation
- Policy violation error messages
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.services.policy import (
    DeviceScopePolicyViolation,
    PolicyEngine,
    SelfApprovalPolicyViolation,
    TierPolicyViolation,
)
from routeros_mcp.infra.db.models import AuditEvent, Base
from routeros_mcp.security.authz import ToolTier, UserRole


@pytest.fixture
async def db_session():  # type: ignore[misc]
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
async def policy_engine(db_session: AsyncSession) -> PolicyEngine:
    """Create PolicyEngine instance."""
    return PolicyEngine(db_session)


# ==================== Test: Tier Validation ====================


@pytest.mark.asyncio
async def test_validate_tier_access_read_only_cannot_plan(
    policy_engine: PolicyEngine,
) -> None:
    """Test that read_only users cannot create plans."""
    with pytest.raises(
        TierPolicyViolation, match="read_only.*cannot perform operation.*plan_create"
    ):
        await policy_engine.validate_tier_access(
            user_role=UserRole.READ_ONLY,
            operation="plan_create",
            user_sub="user-readonly",
        )


@pytest.mark.asyncio
async def test_validate_tier_access_read_only_cannot_execute(
    policy_engine: PolicyEngine,
) -> None:
    """Test that read_only users cannot execute plans."""
    with pytest.raises(
        TierPolicyViolation, match="read_only.*cannot perform operation.*plan_execute"
    ):
        await policy_engine.validate_tier_access(
            user_role=UserRole.READ_ONLY,
            operation="plan_execute",
            user_sub="user-readonly",
        )


@pytest.mark.asyncio
async def test_validate_tier_access_read_only_cannot_write(
    policy_engine: PolicyEngine,
) -> None:
    """Test that read_only users cannot perform device writes."""
    with pytest.raises(
        TierPolicyViolation, match="read_only.*cannot perform operation.*device_write"
    ):
        await policy_engine.validate_tier_access(
            user_role=UserRole.READ_ONLY,
            operation="device_write",
            user_sub="user-readonly",
        )


@pytest.mark.asyncio
async def test_validate_tier_access_ops_rw_can_plan(
    policy_engine: PolicyEngine,
) -> None:
    """Test that ops_rw users can create plans."""
    # Should not raise
    await policy_engine.validate_tier_access(
        user_role=UserRole.OPS_RW,
        operation="plan_create",
        user_sub="user-ops",
    )


@pytest.mark.asyncio
async def test_validate_tier_access_ops_rw_can_execute(
    policy_engine: PolicyEngine,
) -> None:
    """Test that ops_rw users can execute plans."""
    # Should not raise
    await policy_engine.validate_tier_access(
        user_role=UserRole.OPS_RW,
        operation="plan_execute",
        user_sub="user-ops",
    )


@pytest.mark.asyncio
async def test_validate_tier_access_ops_rw_cannot_multi_device(
    policy_engine: PolicyEngine,
) -> None:
    """Test that ops_rw users cannot perform multi-device operations."""
    with pytest.raises(
        TierPolicyViolation, match="ops_rw.*cannot perform operation.*multi_device_plan"
    ):
        await policy_engine.validate_tier_access(
            user_role=UserRole.OPS_RW,
            operation="multi_device_plan",
            user_sub="user-ops",
        )


@pytest.mark.asyncio
async def test_validate_tier_access_admin_can_do_anything(
    policy_engine: PolicyEngine,
) -> None:
    """Test that admin users have full access."""
    operations = [
        "plan_create",
        "plan_execute",
        "device_write",
        "config_change",
        "multi_device_plan",
        "professional_tier_operation",
    ]

    for operation in operations:
        # Should not raise for any operation
        await policy_engine.validate_tier_access(
            user_role=UserRole.ADMIN,
            operation=operation,
            user_sub="user-admin",
        )


@pytest.mark.asyncio
async def test_validate_tier_access_approver_cannot_execute(
    policy_engine: PolicyEngine,
) -> None:
    """Test that approver users cannot execute operations."""
    operations = ["plan_execute", "device_write", "config_change"]

    for operation in operations:
        with pytest.raises(TierPolicyViolation, match="approver.*cannot execute operations"):
            await policy_engine.validate_tier_access(
                user_role=UserRole.APPROVER,
                operation=operation,
                user_sub="user-approver",
            )


# ==================== Test: Self-Approval Prevention ====================


@pytest.mark.asyncio
async def test_validate_approval_same_user_raises(
    policy_engine: PolicyEngine,
) -> None:
    """Test that self-approval is prevented."""
    with pytest.raises(SelfApprovalPolicyViolation, match="cannot approve their own requests"):
        await policy_engine.validate_approval(
            requester_sub="user-123",
            approver_sub="user-123",  # Same user
            approval_request_id="approval-001",
        )


@pytest.mark.asyncio
async def test_validate_approval_different_users_passes(
    policy_engine: PolicyEngine,
) -> None:
    """Test that approval by different user is allowed."""
    # Should not raise
    await policy_engine.validate_approval(
        requester_sub="user-123",
        approver_sub="user-456",  # Different user
        approval_request_id="approval-001",
        plan_id="plan-001",
    )


# ==================== Test: Device Scope Enforcement ====================


@pytest.mark.asyncio
async def test_validate_device_scope_no_restrictions(
    policy_engine: PolicyEngine,
) -> None:
    """Test that None device_scopes grants full access."""
    # Should not raise
    await policy_engine.validate_device_scope(
        device_id="dev-prod-01",
        device_scopes=None,  # Full access
        user_sub="user-admin",
        user_role=UserRole.ADMIN,
    )


@pytest.mark.asyncio
async def test_validate_device_scope_empty_list_grants_full_access(
    policy_engine: PolicyEngine,
) -> None:
    """Test that empty device_scopes list grants full access."""
    # Should not raise
    await policy_engine.validate_device_scope(
        device_id="dev-prod-01",
        device_scopes=[],  # Full access
        user_sub="user-admin",
        user_role=UserRole.ADMIN,
    )


@pytest.mark.asyncio
async def test_validate_device_scope_device_in_scope(
    policy_engine: PolicyEngine,
) -> None:
    """Test that device in scope is allowed."""
    # Should not raise
    await policy_engine.validate_device_scope(
        device_id="dev-lab-01",
        device_scopes=["dev-lab-01", "dev-lab-02"],
        user_sub="user-ops",
        user_role=UserRole.OPS_RW,
    )


@pytest.mark.asyncio
async def test_validate_device_scope_device_not_in_scope_raises(
    policy_engine: PolicyEngine,
) -> None:
    """Test that device not in scope is denied."""
    with pytest.raises(DeviceScopePolicyViolation, match="not in allowed scope"):
        await policy_engine.validate_device_scope(
            device_id="dev-prod-01",
            device_scopes=["dev-lab-01", "dev-staging-01"],
            user_sub="user-ops",
            user_role=UserRole.OPS_RW,
        )


@pytest.mark.asyncio
async def test_validate_device_scope_shows_limited_device_list(
    policy_engine: PolicyEngine,
) -> None:
    """Test that error message shows limited device list for many devices."""
    many_devices = [f"dev-{i:03d}" for i in range(20)]

    with pytest.raises(DeviceScopePolicyViolation) as exc_info:
        await policy_engine.validate_device_scope(
            device_id="dev-prod-01",
            device_scopes=many_devices,
            user_sub="user-ops",
        )

    # Should show only first 5 devices with ellipsis
    error_msg = str(exc_info.value)
    assert "20 device(s)" in error_msg
    assert "..." in error_msg


# ==================== Test: Admin Override ====================


@pytest.mark.asyncio
async def test_admin_override_creates_audit_event(
    policy_engine: PolicyEngine,
    db_session: AsyncSession,
) -> None:
    """Test that admin override creates audit event."""
    audit_id = await policy_engine.admin_override(
        admin_sub="admin-001",
        policy_type="tier_restriction",
        reason="Emergency fix required",
        context={"device_id": "dev-prod-01"},
        admin_email="admin@example.com",
    )

    # Verify audit event was created
    result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == audit_id))
    audit_event = result.scalar_one_or_none()

    assert audit_event is not None
    assert audit_event.user_sub == "admin-001"
    assert audit_event.user_email == "admin@example.com"
    assert audit_event.user_role == "admin"
    assert audit_event.action == "POLICY_OVERRIDE"
    assert audit_event.result == "SUCCESS"
    assert audit_event.tool_name == "policy_engine"
    assert audit_event.tool_tier == "professional"
    assert audit_event.meta["policy_type"] == "tier_restriction"
    assert audit_event.meta["reason"] == "Emergency fix required"
    assert audit_event.meta["context"]["device_id"] == "dev-prod-01"


@pytest.mark.asyncio
async def test_admin_override_empty_reason_raises(
    policy_engine: PolicyEngine,
) -> None:
    """Test that admin override requires non-empty reason."""
    with pytest.raises(ValueError, match="requires a non-empty reason"):
        await policy_engine.admin_override(
            admin_sub="admin-001",
            policy_type="tier_restriction",
            reason="",  # Empty reason
        )


@pytest.mark.asyncio
async def test_admin_override_whitespace_reason_raises(
    policy_engine: PolicyEngine,
) -> None:
    """Test that admin override requires non-whitespace reason."""
    with pytest.raises(ValueError, match="requires a non-empty reason"):
        await policy_engine.admin_override(
            admin_sub="admin-001",
            policy_type="tier_restriction",
            reason="   ",  # Whitespace-only reason
        )


@pytest.mark.asyncio
async def test_admin_override_invalid_policy_type_raises(
    policy_engine: PolicyEngine,
) -> None:
    """Test that admin override validates policy_type."""
    with pytest.raises(ValueError, match="Invalid policy_type"):
        await policy_engine.admin_override(
            admin_sub="admin-001",
            policy_type="invalid_type",
            reason="Test reason",
        )


@pytest.mark.asyncio
async def test_admin_override_valid_policy_types(
    policy_engine: PolicyEngine,
    db_session: AsyncSession,
) -> None:
    """Test that all valid policy types are accepted."""
    valid_types = [
        "tier_restriction",
        "self_approval_prevention",
        "device_scope_restriction",
        "rate_limit",
        "time_window",
    ]

    for policy_type in valid_types:
        audit_id = await policy_engine.admin_override(
            admin_sub="admin-001",
            policy_type=policy_type,
            reason=f"Testing {policy_type}",
        )

        # Verify audit event was created
        result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == audit_id))
        audit_event = result.scalar_one_or_none()
        assert audit_event is not None
        assert audit_event.meta["policy_type"] == policy_type


# ==================== Test: Tool Tier Access Validation ====================


@pytest.mark.asyncio
async def test_validate_tool_tier_access_read_only_fundamental(
    policy_engine: PolicyEngine,
) -> None:
    """Test that read_only can access fundamental tier tools."""
    # Should not raise
    await policy_engine.validate_tool_tier_access(
        user_role=UserRole.READ_ONLY,
        tool_tier=ToolTier.FUNDAMENTAL,
        user_sub="user-readonly",
        tool_name="device/list",
    )


@pytest.mark.asyncio
async def test_validate_tool_tier_access_read_only_cannot_advanced(
    policy_engine: PolicyEngine,
) -> None:
    """Test that read_only cannot access advanced tier tools."""
    with pytest.raises(TierPolicyViolation, match="read_only.*cannot execute advanced tier tools"):
        await policy_engine.validate_tool_tier_access(
            user_role=UserRole.READ_ONLY,
            tool_tier=ToolTier.ADVANCED,
            user_sub="user-readonly",
            tool_name="dns/update-servers",
        )


@pytest.mark.asyncio
async def test_validate_tool_tier_access_read_only_cannot_professional(
    policy_engine: PolicyEngine,
) -> None:
    """Test that read_only cannot access professional tier tools."""
    with pytest.raises(
        TierPolicyViolation, match="read_only.*cannot execute professional tier tools"
    ):
        await policy_engine.validate_tool_tier_access(
            user_role=UserRole.READ_ONLY,
            tool_tier=ToolTier.PROFESSIONAL,
            user_sub="user-readonly",
            tool_name="firewall/plan",
        )


@pytest.mark.asyncio
async def test_validate_tool_tier_access_ops_rw_can_advanced(
    policy_engine: PolicyEngine,
) -> None:
    """Test that ops_rw can access advanced tier tools."""
    # Should not raise
    await policy_engine.validate_tool_tier_access(
        user_role=UserRole.OPS_RW,
        tool_tier=ToolTier.ADVANCED,
        user_sub="user-ops",
        tool_name="dns/update-servers",
    )


@pytest.mark.asyncio
async def test_validate_tool_tier_access_ops_rw_cannot_professional(
    policy_engine: PolicyEngine,
) -> None:
    """Test that ops_rw cannot access professional tier tools."""
    with pytest.raises(TierPolicyViolation, match="ops_rw.*cannot execute professional tier tools"):
        await policy_engine.validate_tool_tier_access(
            user_role=UserRole.OPS_RW,
            tool_tier=ToolTier.PROFESSIONAL,
            user_sub="user-ops",
            tool_name="firewall/plan",
        )


@pytest.mark.asyncio
async def test_validate_tool_tier_access_admin_can_professional(
    policy_engine: PolicyEngine,
) -> None:
    """Test that admin can access professional tier tools."""
    # Should not raise
    await policy_engine.validate_tool_tier_access(
        user_role=UserRole.ADMIN,
        tool_tier=ToolTier.PROFESSIONAL,
        user_sub="user-admin",
        tool_name="firewall/plan",
    )


@pytest.mark.asyncio
async def test_validate_tool_tier_access_approver_cannot_execute_any(
    policy_engine: PolicyEngine,
) -> None:
    """Test that approver cannot execute any tools."""
    tiers = [ToolTier.FUNDAMENTAL, ToolTier.ADVANCED, ToolTier.PROFESSIONAL]

    for tier in tiers:
        with pytest.raises(TierPolicyViolation, match="approver.*cannot execute tools"):
            await policy_engine.validate_tool_tier_access(
                user_role=UserRole.APPROVER,
                tool_tier=tier,
                user_sub="user-approver",
            )


# ==================== Test: Error Messages ====================


@pytest.mark.asyncio
async def test_tier_violation_includes_user_sub(
    policy_engine: PolicyEngine,
) -> None:
    """Test that tier violation error includes user subject."""
    with pytest.raises(TierPolicyViolation) as exc_info:
        await policy_engine.validate_tier_access(
            user_role=UserRole.READ_ONLY,
            operation="plan_create",
            user_sub="user-123",
        )

    error_msg = str(exc_info.value)
    assert "user: user-123" in error_msg


@pytest.mark.asyncio
async def test_self_approval_violation_includes_user_sub(
    policy_engine: PolicyEngine,
) -> None:
    """Test that self-approval violation error includes user subject."""
    with pytest.raises(SelfApprovalPolicyViolation) as exc_info:
        await policy_engine.validate_approval(
            requester_sub="user-123",
            approver_sub="user-123",
        )

    error_msg = str(exc_info.value)
    assert "user: user-123" in error_msg


@pytest.mark.asyncio
async def test_device_scope_violation_shows_device_count(
    policy_engine: PolicyEngine,
) -> None:
    """Test that device scope violation shows device count."""
    with pytest.raises(DeviceScopePolicyViolation) as exc_info:
        await policy_engine.validate_device_scope(
            device_id="dev-prod-01",
            device_scopes=["dev-lab-01", "dev-staging-01"],
            user_sub="user-ops",
        )

    error_msg = str(exc_info.value)
    assert "2 device(s)" in error_msg


@pytest.mark.asyncio
async def test_tier_violation_suggests_contact_admin(
    policy_engine: PolicyEngine,
) -> None:
    """Test that tier violation suggests contacting admin."""
    with pytest.raises(TierPolicyViolation) as exc_info:
        await policy_engine.validate_tier_access(
            user_role=UserRole.READ_ONLY,
            operation="plan_create",
        )

    error_msg = str(exc_info.value)
    assert "administrator" in error_msg.lower()
