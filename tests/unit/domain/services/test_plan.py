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
    async def test_update_plan_status_accepts_legacy_applied(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Ensure legacy 'applied' status maps to COMPLETED for compatibility."""
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

        # Move through required transitions
        await service.update_plan_status(plan_id, PlanStatus.APPROVED.value, "test-user")
        await service.update_plan_status(plan_id, PlanStatus.EXECUTING.value, "test-user")

        # Use legacy status value
        await service.update_plan_status(plan_id, "applied", "test-user")
        updated = await service.get_plan(plan_id)
        assert updated["status"] == PlanStatus.COMPLETED.value

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


class TestMultiDevicePlanService:
    """Tests for Phase 4 multi-device plan creation."""

    @pytest.mark.asyncio
    async def test_multi_device_plan(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test creating a multi-device plan with multiple devices."""
        service = PlanService(db_session)

        # Only use lab devices
        device_ids = [test_devices[0], test_devices[1]]

        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=device_ids,
            summary="Update DNS/NTP on lab devices",
            changes={"dns_servers": ["8.8.8.8", "8.8.4.4"]},
            change_type="dns_ntp",
            batch_size=2,
        )

        # Verify basic plan structure
        assert plan["plan_id"].startswith("plan-")
        assert plan["approval_token"].startswith("approve-")
        assert plan["device_count"] == 2
        assert plan["batch_size"] == 2
        assert plan["batch_count"] == 1
        assert plan["rollback_on_failure"] is True

        # Verify batches were calculated correctly
        assert len(plan["batches"]) == 1
        assert plan["batches"][0]["device_count"] == 2

    @pytest.mark.asyncio
    async def test_multi_device_plan_batch_calculation(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test batch calculation with different batch sizes."""
        service = PlanService(db_session)

        # Create 4 lab devices for testing
        # Use only lab devices from test_devices

        # Add 2 more lab devices
        for i in range(3, 5):
            device = Device(
                id=f"dev-lab-0{i}",
                name=f"router-lab-0{i}",
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

        device_ids = ["dev-lab-01", "dev-lab-02", "dev-lab-03", "dev-lab-04"]

        # Test with batch_size=2 (should create 2 batches)
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=device_ids,
            summary="Update DNS/NTP",
            changes={"dns_servers": ["8.8.8.8"]},
            change_type="dns_ntp",
            batch_size=2,
        )

        assert plan["batch_count"] == 2
        assert len(plan["batches"]) == 2
        assert plan["batches"][0]["device_count"] == 2
        assert plan["batches"][1]["device_count"] == 2

    @pytest.mark.asyncio
    async def test_multi_device_plan_requires_minimum_devices(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that multi-device plan requires at least 2 devices."""
        service = PlanService(db_session)

        # Try with only 1 device - should fail
        with pytest.raises(ValueError, match="at least 2 devices"):
            await service.create_multi_device_plan(
                tool_name="dns_ntp/plan-update",
                created_by="test-user",
                device_ids=[test_devices[0]],
                summary="Update DNS/NTP",
                changes={"dns_servers": ["8.8.8.8"]},
                change_type="dns_ntp",
            )

    @pytest.mark.asyncio
    async def test_multi_device_plan_maximum_devices(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that multi-device plan enforces maximum 50 devices."""
        service = PlanService(db_session)

        # Try with 51 devices - should fail
        device_ids = [f"dev-{i:03d}" for i in range(51)]

        with pytest.raises(ValueError, match="maximum 50 devices"):
            await service.create_multi_device_plan(
                tool_name="dns_ntp/plan-update",
                created_by="test-user",
                device_ids=device_ids,
                summary="Update DNS/NTP",
                changes={"dns_servers": ["8.8.8.8"]},
                change_type="dns_ntp",
            )

    @pytest.mark.asyncio
    async def test_multi_device_plan_same_environment_required(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that all devices must be in same environment."""
        service = PlanService(db_session)

        # Try mixing lab and staging devices - should fail
        device_ids = ["dev-lab-01", "dev-staging-01"]

        with pytest.raises(ValueError, match="same environment"):
            await service.create_multi_device_plan(
                tool_name="dns_ntp/plan-update",
                created_by="test-user",
                device_ids=device_ids,
                summary="Update DNS/NTP",
                changes={"dns_servers": ["8.8.8.8"]},
                change_type="dns_ntp",
                batch_size=2,  # Set batch_size to avoid exceeding device count
            )

    @pytest.mark.asyncio
    async def test_multi_device_plan_reachable_devices_required(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that unreachable devices fail plan creation."""
        service = PlanService(db_session)

        # Try with an unreachable device - should fail
        device_ids = ["dev-lab-01", "dev-unreachable"]

        with pytest.raises(ValueError, match="Pre-checks failed"):
            await service.create_multi_device_plan(
                tool_name="dns_ntp/plan-update",
                created_by="test-user",
                device_ids=device_ids,
                summary="Update DNS/NTP",
                changes={"dns_servers": ["8.8.8.8"]},
                change_type="dns_ntp",
                batch_size=2,  # Set batch_size to avoid exceeding device count
            )

    @pytest.mark.asyncio
    async def test_multi_device_plan_approval_token_generated(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that approval token is generated for multi-device plans."""
        service = PlanService(db_session)

        device_ids = ["dev-lab-01", "dev-lab-02"]

        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=device_ids,
            summary="Update DNS/NTP",
            changes={"dns_servers": ["8.8.8.8"]},
            change_type="dns_ntp",
            batch_size=2,  # Set batch_size to match device count
        )

        # Verify token format
        assert plan["approval_token"].startswith("approve-")
        parts = plan["approval_token"].split("-", 2)
        assert len(parts) >= 3
        assert parts[0] == "approve"

        # Verify expiration
        expires_at = datetime.fromisoformat(plan["approval_expires_at"])
        now = datetime.now(UTC)
        delta = expires_at - now
        assert timedelta(minutes=14) < delta < timedelta(minutes=16)

    @pytest.mark.asyncio
    async def test_multi_device_plan_metadata_structure(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that plan metadata includes batch configuration."""
        service = PlanService(db_session)

        device_ids = ["dev-lab-01", "dev-lab-02"]

        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=device_ids,
            summary="Update DNS/NTP",
            changes={"dns_servers": ["8.8.8.8"]},
            change_type="dns_ntp",
            batch_size=2,
            pause_seconds_between_batches=30,
            rollback_on_failure=False,
        )

        # Verify all fields are present
        assert plan["batch_size"] == 2
        assert plan["pause_seconds_between_batches"] == 30
        assert plan["rollback_on_failure"] is False
        assert "batches" in plan
        assert plan["batch_count"] == 1

    @pytest.mark.asyncio
    async def test_multi_device_plan_audit_logging(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that multi-device plan creation is audited."""
        service = PlanService(db_session)

        device_ids = ["dev-lab-01", "dev-lab-02"]

        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=device_ids,
            summary="Update DNS/NTP",
            changes={"dns_servers": ["8.8.8.8"]},
            change_type="dns_ntp",
            batch_size=2,  # Set batch_size to match device count
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
        assert audit_event.result == "SUCCESS"
        assert audit_event.meta["multi_device"] is True
        assert audit_event.meta["batch_count"] == 1
        assert audit_event.meta["change_type"] == "dns_ntp"

    @pytest.mark.asyncio
    async def test_multi_device_plan_batch_size_validation(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that invalid batch_size values are rejected."""
        service = PlanService(db_session)

        device_ids = ["dev-lab-01", "dev-lab-02"]

        # Test batch_size = 0 (should fail)
        with pytest.raises(ValueError, match="batch_size must be at least 1"):
            await service.create_multi_device_plan(
                tool_name="dns_ntp/plan-update",
                created_by="test-user",
                device_ids=device_ids,
                summary="Update DNS/NTP",
                changes={"dns_servers": ["8.8.8.8"]},
                change_type="dns_ntp",
                batch_size=0,
            )

        # Test negative batch_size (should fail)
        with pytest.raises(ValueError, match="batch_size must be at least 1"):
            await service.create_multi_device_plan(
                tool_name="dns_ntp/plan-update",
                created_by="test-user",
                device_ids=device_ids,
                summary="Update DNS/NTP",
                changes={"dns_servers": ["8.8.8.8"]},
                change_type="dns_ntp",
                batch_size=-1,
            )

        # Test batch_size > device count (should fail)
        with pytest.raises(ValueError, match="batch_size must not exceed"):
            await service.create_multi_device_plan(
                tool_name="dns_ntp/plan-update",
                created_by="test-user",
                device_ids=device_ids,
                summary="Update DNS/NTP",
                changes={"dns_servers": ["8.8.8.8"]},
                change_type="dns_ntp",
                batch_size=100,
            )

    @pytest.mark.asyncio
    async def test_multi_device_plan_pause_seconds_validation(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that negative pause_seconds_between_batches is rejected."""
        service = PlanService(db_session)

        device_ids = ["dev-lab-01", "dev-lab-02"]

        # Test negative pause_seconds (should fail)
        with pytest.raises(ValueError, match="pause_seconds_between_batches cannot be negative"):
            await service.create_multi_device_plan(
                tool_name="dns_ntp/plan-update",
                created_by="test-user",
                device_ids=device_ids,
                summary="Update DNS/NTP",
                changes={"dns_servers": ["8.8.8.8"]},
                change_type="dns_ntp",
                batch_size=2,  # Set batch_size to match device count
                pause_seconds_between_batches=-10,
            )


class TestPlanRollback:
    """Tests for Phase 4 automatic rollback on health check failure."""

    @pytest.mark.asyncio
    async def test_rollback_requires_rollback_on_failure_enabled(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that rollback only triggers if rollback_on_failure=True."""
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create plan with rollback disabled
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={"dns_servers": ["8.8.8.8"]},
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=False,
        )

        # Simulate plan execution
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        await db_session.commit()

        # Attempt rollback - should raise ValueError since rollback not enabled
        with pytest.raises(ValueError, match="Rollback not enabled"):
            await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
            )

    @pytest.mark.asyncio
    async def test_rollback_only_applies_to_completed_batches(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that rollback only applies to devices with status='applied'."""
        from unittest.mock import AsyncMock, patch
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create multi-device plan
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={
                "dns_servers": ["8.8.8.8"],
                "previous_state": {
                    "dev-lab-01": {"dns_servers": ["1.1.1.1"]},
                    "dev-lab-02": {"dns_servers": ["1.0.0.1"]},
                },
            },
            change_type="dns_ntp",
            batch_size=1,
            rollback_on_failure=True,
        )

        # Simulate partial execution: dev-lab-01 applied, dev-lab-02 pending
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        plan_model.device_statuses = {
            "dev-lab-01": "applied",
            "dev-lab-02": "pending",
        }
        await db_session.commit()

        # Mock DNS/NTP service to avoid actual device connections
        with patch("routeros_mcp.domain.services.dns_ntp.DNSNTPService") as mock_dns_ntp_class:
            mock_dns_ntp = AsyncMock()
            mock_dns_ntp_class.return_value = mock_dns_ntp
            mock_dns_ntp.update_dns_servers = AsyncMock()

            # Trigger rollback
            rollback_result = await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
            )

        # Verify only dev-lab-01 was rolled back (not dev-lab-02)
        assert rollback_result["summary"]["total"] == 1
        assert "dev-lab-01" in rollback_result["devices"]
        assert "dev-lab-02" not in rollback_result["devices"]
        assert rollback_result["devices"]["dev-lab-01"]["status"] == "rolled_back"

    @pytest.mark.asyncio
    async def test_rollback_per_device_status_tracking(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that per-device rollback status is tracked: applied → rolling_back → rolled_back."""
        from unittest.mock import AsyncMock, patch
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create plan with 2 devices
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={
                "dns_servers": ["8.8.8.8"],
                "previous_state": {
                    "dev-lab-01": {"dns_servers": ["1.1.1.1"]},
                    "dev-lab-02": {"dns_servers": ["1.0.0.1"]},
                },
            },
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=True,
        )

        # Set device status to applied
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        plan_model.device_statuses = {"dev-lab-01": "applied", "dev-lab-02": "applied"}
        await db_session.commit()

        # Mock DNS/NTP service
        with patch("routeros_mcp.domain.services.dns_ntp.DNSNTPService") as mock_dns_ntp_class:
            mock_dns_ntp = AsyncMock()
            mock_dns_ntp_class.return_value = mock_dns_ntp
            mock_dns_ntp.update_dns_servers = AsyncMock()

            # Trigger rollback
            rollback_result = await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
            )

        # Verify status progression for both devices
        assert rollback_result["devices"]["dev-lab-01"]["status"] == "rolled_back"
        assert rollback_result["devices"]["dev-lab-02"]["status"] == "rolled_back"

        # Check final plan state
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        final_plan = result.scalar_one()
        assert final_plan.status == PlanStatus.ROLLED_BACK.value
        assert final_plan.device_statuses["dev-lab-01"] == "rolled_back"
        assert final_plan.device_statuses["dev-lab-02"] == "rolled_back"

    @pytest.mark.asyncio
    async def test_rollback_plan_state_transitions(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test plan state transitions: executing → rolling_back → rolled_back."""
        from unittest.mock import AsyncMock, patch
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create plan with 2 devices
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={
                "dns_servers": ["8.8.8.8"],
                "previous_state": {
                    "dev-lab-01": {"dns_servers": ["1.1.1.1"]},
                    "dev-lab-02": {"dns_servers": ["1.0.0.1"]},
                },
            },
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=True,
        )

        # Set plan to executing with applied device
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        plan_model.device_statuses = {"dev-lab-01": "applied", "dev-lab-02": "applied"}
        await db_session.commit()

        # Mock DNS/NTP service
        with patch("routeros_mcp.domain.services.dns_ntp.DNSNTPService") as mock_dns_ntp_class:
            mock_dns_ntp = AsyncMock()
            mock_dns_ntp_class.return_value = mock_dns_ntp
            mock_dns_ntp.update_dns_servers = AsyncMock()

            # Trigger rollback
            await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
            )

        # Verify plan transitioned to rolled_back
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        final_plan = result.scalar_one()
        assert final_plan.status == PlanStatus.ROLLED_BACK.value

    @pytest.mark.asyncio
    async def test_rollback_restores_dns_ntp_from_previous_state(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that rollback restores previous DNS/NTP settings from plan metadata."""
        from unittest.mock import AsyncMock, patch
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create plan with previous state (2 devices required)
        previous_dns = ["1.1.1.1", "1.0.0.1"]
        previous_ntp = ["time.cloudflare.com"]
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={
                "dns_servers": ["8.8.8.8", "8.8.4.4"],
                "ntp_servers": ["pool.ntp.org"],
                "previous_state": {
                    "dev-lab-01": {
                        "dns_servers": previous_dns,
                        "ntp_servers": previous_ntp,
                        "ntp_enabled": True,
                    },
                    "dev-lab-02": {
                        "dns_servers": ["8.8.8.8"],
                        "ntp_servers": ["pool.ntp.org"],
                        "ntp_enabled": False,
                    },
                },
            },
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=True,
        )

        # Set device to applied
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        plan_model.device_statuses = {"dev-lab-01": "applied", "dev-lab-02": "pending"}
        await db_session.commit()

        # Mock DNS/NTP service and capture calls
        with patch("routeros_mcp.domain.services.dns_ntp.DNSNTPService") as mock_dns_ntp_class:
            mock_dns_ntp = AsyncMock()
            mock_dns_ntp_class.return_value = mock_dns_ntp
            mock_dns_ntp.update_dns_servers = AsyncMock()
            mock_dns_ntp.update_ntp_servers = AsyncMock()

            # Trigger rollback
            await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
            )

            # Verify DNS servers were restored for dev-lab-01 only
            mock_dns_ntp.update_dns_servers.assert_called_once_with(
                device_id="dev-lab-01",
                dns_servers=previous_dns,
                dry_run=False,
            )

            # Verify NTP servers were restored for dev-lab-01 only
            mock_dns_ntp.update_ntp_servers.assert_called_once_with(
                device_id="dev-lab-01",
                ntp_servers=previous_ntp,
                enabled=True,
                dry_run=False,
            )

    @pytest.mark.asyncio
    async def test_rollback_with_max_retries(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that rollback retries up to max_retries times on failure."""
        from unittest.mock import AsyncMock, patch
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create plan with 2 devices
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={
                "dns_servers": ["8.8.8.8"],
                "previous_state": {
                    "dev-lab-01": {"dns_servers": ["1.1.1.1"]},
                    "dev-lab-02": {"dns_servers": ["1.0.0.1"]},
                },
            },
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=True,
        )

        # Set device to applied
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        plan_model.device_statuses = {"dev-lab-01": "applied", "dev-lab-02": "pending"}
        await db_session.commit()

        # Mock DNS/NTP service to fail twice, succeed on third attempt
        with patch("routeros_mcp.domain.services.dns_ntp.DNSNTPService") as mock_dns_ntp_class:
            mock_dns_ntp = AsyncMock()
            mock_dns_ntp_class.return_value = mock_dns_ntp
            call_count = [0]

            def update_dns_side_effect(*args, **kwargs):
                call_count[0] += 1
                if call_count[0] < 3:
                    raise RuntimeError("Connection failed")
                # Third attempt succeeds
                return AsyncMock()

            mock_dns_ntp.update_dns_servers = AsyncMock(side_effect=update_dns_side_effect)

            # Trigger rollback with max_retries=3
            rollback_result = await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
                max_retries=3,
            )

        # Verify device rolled back successfully after retries
        assert rollback_result["devices"]["dev-lab-01"]["status"] == "rolled_back"
        assert rollback_result["devices"]["dev-lab-01"]["attempts"] == 3
        assert rollback_result["summary"]["success"] == 1
        assert rollback_result["summary"]["failed"] == 0

    @pytest.mark.asyncio
    async def test_rollback_failure_after_max_retries(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that rollback fails gracefully after exceeding max_retries."""
        from unittest.mock import AsyncMock, patch
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create plan with 2 devices
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={
                "dns_servers": ["8.8.8.8"],
                "previous_state": {
                    "dev-lab-01": {"dns_servers": ["1.1.1.1"]},
                    "dev-lab-02": {"dns_servers": ["1.0.0.1"]},
                },
            },
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=True,
        )

        # Set device to applied
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        plan_model.device_statuses = {"dev-lab-01": "applied", "dev-lab-02": "pending"}
        await db_session.commit()

        # Mock DNS/NTP service to always fail
        with patch("routeros_mcp.domain.services.dns_ntp.DNSNTPService") as mock_dns_ntp_class:
            mock_dns_ntp = AsyncMock()
            mock_dns_ntp_class.return_value = mock_dns_ntp
            mock_dns_ntp.update_dns_servers = AsyncMock(side_effect=RuntimeError("Device unreachable"))

            # Trigger rollback with max_retries=3
            rollback_result = await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
                max_retries=3,
            )

        # Verify rollback failed after max attempts
        assert rollback_result["devices"]["dev-lab-01"]["status"] == "rollback_failed"
        assert rollback_result["devices"]["dev-lab-01"]["attempts"] == 3
        assert len(rollback_result["devices"]["dev-lab-01"]["errors"]) == 3
        assert rollback_result["summary"]["success"] == 0
        assert rollback_result["summary"]["failed"] == 1

        # Verify device status is rollback_failed
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        final_plan = result.scalar_one()
        assert final_plan.device_statuses["dev-lab-01"] == "rollback_failed"

    @pytest.mark.asyncio
    async def test_rollback_logs_audit_events(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that rollback creates proper audit events."""
        from unittest.mock import AsyncMock, patch
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create plan with 2 devices
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={
                "dns_servers": ["8.8.8.8"],
                "previous_state": {
                    "dev-lab-01": {"dns_servers": ["1.1.1.1"]},
                    "dev-lab-02": {"dns_servers": ["1.0.0.1"]},
                },
            },
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=True,
        )

        # Set device to applied
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        plan_model.device_statuses = {"dev-lab-01": "applied", "dev-lab-02": "pending"}
        await db_session.commit()

        # Mock DNS/NTP service
        with patch("routeros_mcp.domain.services.dns_ntp.DNSNTPService") as mock_dns_ntp_class:
            mock_dns_ntp = AsyncMock()
            mock_dns_ntp_class.return_value = mock_dns_ntp
            mock_dns_ntp.update_dns_servers = AsyncMock()

            # Trigger rollback
            await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="test-user",
            )

        # Check rollback initiation audit event
        stmt = select(AuditEvent).where(
            AuditEvent.action == "PLAN_ROLLBACK_INITIATED",
            AuditEvent.plan_id == plan["plan_id"]
        )
        result = await db_session.execute(stmt)
        init_event = result.scalar_one_or_none()

        assert init_event is not None
        assert init_event.user_sub == "test-user"
        assert init_event.result == "SUCCESS"
        assert init_event.meta["reason"] == "health_check_failed"

        # Check rollback completion audit event
        stmt = select(AuditEvent).where(
            AuditEvent.action == "PLAN_ROLLBACK_COMPLETED",
            AuditEvent.plan_id == plan["plan_id"]
        )
        result = await db_session.execute(stmt)
        complete_event = result.scalar_one_or_none()

        assert complete_event is not None
        assert complete_event.result == "SUCCESS"
        assert complete_event.meta["success"] == 1
        assert complete_event.meta["failed"] == 0

    @pytest.mark.asyncio
    async def test_rollback_requires_previous_state(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that rollback fails if no previous state is available."""
        from routeros_mcp.infra.db.models import Plan as PlanModel

        service = PlanService(db_session)

        # Create plan without previous_state (2 devices required)
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={"dns_servers": ["8.8.8.8"]},  # No previous_state
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=True,
        )

        # Set device to applied
        stmt = select(PlanModel).where(PlanModel.id == plan["plan_id"])
        result = await db_session.execute(stmt)
        plan_model = result.scalar_one()
        plan_model.status = PlanStatus.EXECUTING.value
        plan_model.device_statuses = {"dev-lab-01": "applied", "dev-lab-02": "pending"}
        await db_session.commit()

        # Trigger rollback should fail
        with pytest.raises(ValueError, match="No previous state available"):
            await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
            )

    @pytest.mark.asyncio
    async def test_rollback_invalid_state_transition(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test that rollback fails if plan is not in EXECUTING state."""
        service = PlanService(db_session)

        # Create plan in PENDING state (2 devices required)
        plan = await service.create_multi_device_plan(
            tool_name="dns_ntp/plan-update",
            created_by="test-user",
            device_ids=["dev-lab-01", "dev-lab-02"],
            summary="Update DNS/NTP",
            changes={
                "dns_servers": ["8.8.8.8"],
                "previous_state": {
                    "dev-lab-01": {"dns_servers": ["1.1.1.1"]},
                    "dev-lab-02": {"dns_servers": ["1.0.0.1"]},
                },
            },
            change_type="dns_ntp",
            batch_size=2,
            rollback_on_failure=True,
        )

        # Try to rollback from PENDING state (should fail)
        with pytest.raises(ValueError, match="cannot be rolled back from status"):
            await service.rollback_plan(
                plan_id=plan["plan_id"],
                reason="health_check_failed",
                triggered_by="system",
            )
