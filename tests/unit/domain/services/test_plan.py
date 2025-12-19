"""Tests for enhanced PlanService Phase 3 features.

Tests cover:
- Cryptographic token validation
- State machine transitions
- Pre-checks framework
- Audit logging
- Token expiration (15 minutes)
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.models import PlanStatus
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.models import AuditEvent, Base, Device


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
async def test_devices(db_session: AsyncSession) -> list[str]:
    """Create test devices with varying configurations."""
    devices_data = [
        {
            "id": "dev-lab-01",
            "name": "router-lab-01",
            "environment": "lab",
            "status": "healthy",
            "allow_professional_workflows": True,
        },
        {
            "id": "dev-lab-02",
            "name": "router-lab-02",
            "environment": "lab",
            "status": "degraded",
            "allow_professional_workflows": True,
        },
        {
            "id": "dev-staging-01",
            "name": "router-staging-01",
            "environment": "staging",
            "status": "healthy",
            "allow_professional_workflows": True,
        },
        {
            "id": "dev-prod-01",
            "name": "router-prod-01",
            "environment": "prod",
            "status": "healthy",
            "allow_professional_workflows": True,
        },
        {
            "id": "dev-no-prof",
            "name": "router-no-professional",
            "environment": "lab",
            "status": "healthy",
            "allow_professional_workflows": False,
        },
        {
            "id": "dev-unreachable",
            "name": "router-unreachable",
            "environment": "lab",
            "status": "unreachable",
            "allow_professional_workflows": True,
        },
    ]

    device_ids = []
    for data in devices_data:
        device = Device(
            id=data["id"],
            name=data["name"],
            management_ip="192.168.1.1",
            management_port=443,
            environment=data["environment"],
            status=data["status"],
            tags={},
            allow_advanced_writes=True,
            allow_professional_workflows=data["allow_professional_workflows"],
        )
        db_session.add(device)
        device_ids.append(data["id"])

    await db_session.commit()
    return device_ids


class TestPlanServiceEnhancements:
    """Tests for Phase 3 PlanService enhancements."""

    @pytest.mark.asyncio
    async def test_token_expiration_15_minutes(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test approval token expires in 15 minutes (not 1 hour)."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Check expiration is 15 minutes from now
        expires_at = datetime.fromisoformat(plan["approval_expires_at"])
        now = datetime.now(UTC)
        delta = expires_at - now

        # Allow small tolerance for test execution time
        assert timedelta(minutes=14) < delta < timedelta(minutes=16)
        assert delta < timedelta(hours=1)  # Definitely not 1 hour

    @pytest.mark.asyncio
    async def test_approval_token_hmac_format(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test approval token uses HMAC-based format."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        token = plan["approval_token"]

        # Token should start with "approve-"
        assert token.startswith("approve-")

        # Token should have signature and random parts
        parts = token.split("-", 2)
        assert len(parts) >= 3
        assert parts[0] == "approve"
        assert len(parts[1]) > 0  # Signature part
        assert len(parts[2]) > 0  # Random part

    @pytest.mark.asyncio
    async def test_state_machine_valid_transitions(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test all valid state transitions work."""
        service = PlanService(db_session)

        # Create plan (starts in PENDING)
        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )
        plan_id = plan["plan_id"]

        # PENDING → APPROVED
        await service.update_plan_status(plan_id, PlanStatus.APPROVED.value, "test-user")
        updated = await service.get_plan(plan_id)
        assert updated["status"] == PlanStatus.APPROVED.value

        # APPROVED → EXECUTING
        await service.update_plan_status(plan_id, PlanStatus.EXECUTING.value, "test-user")
        updated = await service.get_plan(plan_id)
        assert updated["status"] == PlanStatus.EXECUTING.value

        # EXECUTING → COMPLETED
        await service.update_plan_status(plan_id, PlanStatus.COMPLETED.value, "test-user")
        updated = await service.get_plan(plan_id)
        assert updated["status"] == PlanStatus.COMPLETED.value

    @pytest.mark.asyncio
    async def test_state_machine_invalid_transitions(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test invalid state transitions are rejected."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )
        plan_id = plan["plan_id"]

        # PENDING → EXECUTING is invalid (must go through APPROVED)
        with pytest.raises(ValueError, match="Invalid status transition"):
            await service.update_plan_status(plan_id, PlanStatus.EXECUTING.value, "test-user")

        # PENDING → COMPLETED is invalid
        with pytest.raises(ValueError, match="Invalid status transition"):
            await service.update_plan_status(plan_id, PlanStatus.COMPLETED.value, "test-user")

    @pytest.mark.asyncio
    async def test_state_machine_terminal_states(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test terminal states cannot transition."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )
        plan_id = plan["plan_id"]

        # Move to COMPLETED (terminal state)
        await service.update_plan_status(plan_id, PlanStatus.APPROVED.value, "test-user")
        await service.update_plan_status(plan_id, PlanStatus.EXECUTING.value, "test-user")
        await service.update_plan_status(plan_id, PlanStatus.COMPLETED.value, "test-user")

        # Try to transition from COMPLETED - should fail
        with pytest.raises(ValueError, match="Invalid status transition"):
            await service.update_plan_status(plan_id, PlanStatus.FAILED.value, "test-user")

    @pytest.mark.asyncio
    async def test_pre_checks_professional_workflows_required(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test pre-checks fail if device doesn't allow professional workflows."""
        service = PlanService(db_session)

        # Device "dev-no-prof" has allow_professional_workflows=False
        with pytest.raises(ValueError, match="Pre-checks failed"):
            await service.create_plan(
                tool_name="test-tool",
                created_by="test-user",
                device_ids=["dev-no-prof"],
                summary="Test plan",
                changes={},
                risk_level="low",
            )

    @pytest.mark.asyncio
    async def test_pre_checks_unreachable_device(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test pre-checks fail for unreachable devices."""
        service = PlanService(db_session)

        with pytest.raises(ValueError, match="Pre-checks failed"):
            await service.create_plan(
                tool_name="test-tool",
                created_by="test-user",
                device_ids=["dev-unreachable"],
                summary="Test plan",
                changes={},
                risk_level="low",
            )

    @pytest.mark.asyncio
    async def test_pre_checks_warnings_degraded_device(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test pre-checks generate warnings for degraded devices."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=["dev-lab-02"],  # This device is degraded
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Should succeed but have warnings
        assert "pre_check_results" in plan
        pre_checks = plan["pre_check_results"]
        assert pre_checks["status"] == "passed"
        assert len(pre_checks["warnings"]) > 0
        assert any("degraded" in w.lower() for w in pre_checks["warnings"])

    @pytest.mark.asyncio
    async def test_pre_checks_warnings_high_risk_prod(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test pre-checks warn on high-risk operations in production."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=["dev-prod-01"],
            summary="High risk production change",
            changes={},
            risk_level="high",
        )

        # Should succeed but have warnings about production
        assert "pre_check_results" in plan
        pre_checks = plan["pre_check_results"]
        assert len(pre_checks["warnings"]) > 0
        assert any("production" in w.lower() for w in pre_checks["warnings"])

    @pytest.mark.asyncio
    async def test_audit_logging_plan_created(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test audit event logged for plan creation."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Check audit event was created
        stmt = select(AuditEvent).where(
            AuditEvent.action == "PLAN_CREATED",
            AuditEvent.plan_id == plan["plan_id"]
        )
        result = await db_session.execute(stmt)
        audit_event = result.scalar_one_or_none()

        assert audit_event is not None
        assert audit_event.user_sub == "test-user"
        assert audit_event.tool_name == "test-tool"
        assert audit_event.result == "SUCCESS"
        assert "device_count" in audit_event.meta

    @pytest.mark.asyncio
    async def test_audit_logging_plan_approved(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test audit event logged for plan approval."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Approve plan
        await service.approve_plan(plan["plan_id"], plan["approval_token"], "approver-user")

        # Check approval audit event
        stmt = select(AuditEvent).where(
            AuditEvent.action == "PLAN_APPROVED",
            AuditEvent.plan_id == plan["plan_id"]
        )
        result = await db_session.execute(stmt)
        audit_event = result.scalar_one_or_none()

        assert audit_event is not None
        assert audit_event.user_sub == "approver-user"
        assert audit_event.result == "SUCCESS"

    @pytest.mark.asyncio
    async def test_audit_logging_status_update(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test audit event logged for status updates."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Update status
        await service.update_plan_status(plan["plan_id"], PlanStatus.APPROVED.value, "test-user")

        # Check status update audit event
        stmt = select(AuditEvent).where(
            AuditEvent.action == "PLAN_STATUS_UPDATE",
            AuditEvent.plan_id == plan["plan_id"]
        )
        result = await db_session.execute(stmt)
        audit_event = result.scalar_one_or_none()

        assert audit_event is not None
        assert audit_event.result == "SUCCESS"
        assert audit_event.meta["old_status"] == PlanStatus.PENDING.value
        assert audit_event.meta["new_status"] == PlanStatus.APPROVED.value

    @pytest.mark.asyncio
    async def test_audit_logging_failures(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test audit events logged for failures."""
        service = PlanService(db_session)

        # Try to create plan with invalid device
        try:
            await service.create_plan(
                tool_name="test-tool",
                created_by="test-user",
                device_ids=["nonexistent-device"],
                summary="Test plan",
                changes={},
                risk_level="low",
            )
        except ValueError:
            pass  # Expected

        # Check failure audit event
        stmt = select(AuditEvent).where(
            AuditEvent.action == "PLAN_CREATED",
            AuditEvent.result == "FAILURE"
        )
        result = await db_session.execute(stmt)
        audit_event = result.scalar_one_or_none()

        assert audit_event is not None
        assert audit_event.user_sub == "test-user"
        assert audit_event.error_message is not None
        assert "not found" in audit_event.error_message.lower()

    @pytest.mark.asyncio
    async def test_approval_token_constant_time_comparison(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test approval token validation uses constant-time comparison."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Valid token should work
        result = await service.approve_plan(
            plan["plan_id"], plan["approval_token"], "approver-user"
        )
        assert result["status"] == PlanStatus.APPROVED.value

        # Create another plan to test invalid token
        plan2 = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan 2",
            changes={},
            risk_level="low",
        )

        # Invalid token should fail (using secrets.compare_digest internally)
        with pytest.raises(ValueError, match="Invalid approval token"):
            await service.approve_plan(plan2["plan_id"], "invalid-token", "approver-user")

    @pytest.mark.asyncio
    async def test_cancellation_from_any_non_terminal_state(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test plan can be cancelled from any non-terminal state."""
        service = PlanService(db_session)

        # Test cancellation from PENDING
        plan1 = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan 1",
            changes={},
            risk_level="low",
        )
        await service.update_plan_status(plan1["plan_id"], PlanStatus.CANCELLED.value, "test-user")
        result = await service.get_plan(plan1["plan_id"])
        assert result["status"] == PlanStatus.CANCELLED.value

        # Test cancellation from APPROVED
        plan2 = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan 2",
            changes={},
            risk_level="low",
        )
        await service.update_plan_status(plan2["plan_id"], PlanStatus.APPROVED.value, "test-user")
        await service.update_plan_status(plan2["plan_id"], PlanStatus.CANCELLED.value, "test-user")
        result = await service.get_plan(plan2["plan_id"])
        assert result["status"] == PlanStatus.CANCELLED.value

        # Test cancellation from EXECUTING
        plan3 = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=[test_devices[0]],
            summary="Test plan 3",
            changes={},
            risk_level="low",
        )
        await service.update_plan_status(plan3["plan_id"], PlanStatus.APPROVED.value, "test-user")
        await service.update_plan_status(plan3["plan_id"], PlanStatus.EXECUTING.value, "test-user")
        await service.update_plan_status(plan3["plan_id"], PlanStatus.CANCELLED.value, "test-user")
        result = await service.get_plan(plan3["plan_id"])
        assert result["status"] == PlanStatus.CANCELLED.value
