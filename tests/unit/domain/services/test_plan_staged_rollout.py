"""Tests for Phase 4 staged rollout with health checks."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.models import PlanStatus
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.models import Base, Device


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
    """Create test devices for staged rollout tests."""
    devices_data = [
        {
            "id": "dev-lab-01",
            "name": "router-lab-01",
            "environment": "lab",
            "status": "healthy",
        },
        {
            "id": "dev-lab-02",
            "name": "router-lab-02",
            "environment": "lab",
            "status": "healthy",
        },
        {
            "id": "dev-lab-03",
            "name": "router-lab-03",
            "environment": "lab",
            "status": "healthy",
        },
        {
            "id": "dev-lab-04",
            "name": "router-lab-04",
            "environment": "lab",
            "status": "healthy",
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
            allow_professional_workflows=True,
        )
        db_session.add(device)
        device_ids.append(data["id"])

    await db_session.commit()
    return device_ids


@pytest.mark.asyncio
async def test_staged_rollout_healthy(
    db_session: AsyncSession, test_devices: list[str]
) -> None:
    """Test staged rollout completes successfully when all devices are healthy."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from routeros_mcp.domain.models import HealthCheckResult

    service = PlanService(db_session)

    # Create multi-device plan with 3 devices, batch_size=2
    device_ids = [test_devices[0], test_devices[1], test_devices[2]]
    plan = await service.create_multi_device_plan(
        tool_name="dns_ntp/plan-update",
        created_by="test-user",
        device_ids=device_ids,
        summary="Update DNS servers",
        changes={
            "dns_servers": ["8.8.8.8", "8.8.4.4"],
        },
        change_type="dns_ntp",
        risk_level="medium",
        batch_size=2,
        pause_seconds_between_batches=1,
        rollback_on_failure=True,
    )

    # Approve plan
    await service.approve_plan(plan["plan_id"], plan["approval_token"], "approver-user")

    # Mock DNS/NTP service
    mock_dns_ntp_service = AsyncMock()
    mock_dns_ntp_service.get_dns_servers = AsyncMock(
        return_value={"servers": ["1.1.1.1"]}
    )
    mock_dns_ntp_service.get_ntp_status = AsyncMock(
        return_value={"servers": ["time.google.com"], "enabled": True}
    )
    mock_dns_ntp_service.update_dns_servers = AsyncMock()
    mock_dns_ntp_service.update_ntp_servers = AsyncMock()

    # Mock health service to return healthy results
    with patch("routeros_mcp.domain.services.health.HealthService") as MockHealthService:
        mock_health_service = MagicMock()

        async def mock_run_batch_health_checks(device_ids, cpu_threshold, memory_threshold):
            # Return healthy results for all devices
            return {
                device_id: HealthCheckResult(
                    device_id=device_id,
                    status="healthy",
                    timestamp=datetime.now(UTC),
                    cpu_usage_percent=50.0,
                    memory_usage_percent=60.0,
                    uptime_seconds=3600,
                    issues=[],
                    warnings=[],
                )
                for device_id in device_ids
            }

        mock_health_service.run_batch_health_checks = mock_run_batch_health_checks
        MockHealthService.return_value = mock_health_service

        # Apply plan
        result = await service.apply_multi_device_plan(
            plan_id=plan["plan_id"],
            approval_token=plan["approval_token"],
            applied_by="test-user",
            dns_ntp_service=mock_dns_ntp_service,
        )

    # Verify results
    assert result["status"] == "completed"
    assert result["batches_completed"] == 2  # 3 devices / batch_size=2 = 2 batches
    assert result["summary"]["applied"] == 3
    assert result["summary"]["failed"] == 0
    assert result["halt_reason"] is None

    # Verify all devices have "applied" status
    for device_id in device_ids:
        assert result["devices"][device_id]["status"] == "applied"

    # Verify plan status is COMPLETED
    updated_plan = await service.get_plan(plan["plan_id"])
    assert updated_plan["status"] == PlanStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_staged_rollout_degraded_halt(
    db_session: AsyncSession, test_devices: list[str]
) -> None:
    """Test staged rollout halts when health checks fail."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from routeros_mcp.domain.models import HealthCheckResult

    service = PlanService(db_session)

    # Create multi-device plan
    device_ids = [test_devices[0], test_devices[1], test_devices[2]]
    plan = await service.create_multi_device_plan(
        tool_name="dns_ntp/plan-update",
        created_by="test-user",
        device_ids=device_ids,
        summary="Update DNS servers",
        changes={
            "dns_servers": ["8.8.8.8", "8.8.4.4"],
        },
        change_type="dns_ntp",
        risk_level="medium",
        batch_size=2,
        pause_seconds_between_batches=0,
        rollback_on_failure=False,  # Disable rollback for this test
    )

    # Approve plan
    await service.approve_plan(plan["plan_id"], plan["approval_token"], "approver-user")

    # Mock DNS/NTP service
    mock_dns_ntp_service = AsyncMock()
    mock_dns_ntp_service.get_dns_servers = AsyncMock(
        return_value={"servers": ["1.1.1.1"]}
    )
    mock_dns_ntp_service.get_ntp_status = AsyncMock(
        return_value={"servers": ["time.google.com"], "enabled": True}
    )
    mock_dns_ntp_service.update_dns_servers = AsyncMock()

    # Mock health service to return degraded result for second device in first batch
    with patch("routeros_mcp.domain.services.health.HealthService") as MockHealthService:
        mock_health_service = MagicMock()

        async def mock_run_batch_health_checks(device_ids, cpu_threshold, memory_threshold):
            # First device healthy, second device degraded (high CPU)
            results = {}
            for idx, device_id in enumerate(device_ids):
                if idx == 1:
                    # Second device in batch is degraded
                    results[device_id] = HealthCheckResult(
                        device_id=device_id,
                        status="degraded",
                        timestamp=datetime.now(UTC),
                        cpu_usage_percent=95.0,
                        memory_usage_percent=60.0,
                        uptime_seconds=3600,
                        issues=["CPU usage above threshold: 95.0% >= 80.0%"],
                        warnings=[],
                    )
                else:
                    results[device_id] = HealthCheckResult(
                        device_id=device_id,
                        status="healthy",
                        timestamp=datetime.now(UTC),
                        cpu_usage_percent=50.0,
                        memory_usage_percent=60.0,
                        uptime_seconds=3600,
                        issues=[],
                        warnings=[],
                    )
            return results

        mock_health_service.run_batch_health_checks = mock_run_batch_health_checks
        MockHealthService.return_value = mock_health_service

        # Apply plan
        result = await service.apply_multi_device_plan(
            plan_id=plan["plan_id"],
            approval_token=plan["approval_token"],
            applied_by="test-user",
            dns_ntp_service=mock_dns_ntp_service,
        )

    # Verify rollout halted
    assert result["status"] == "halted"
    assert result["batches_completed"] == 1  # Only first batch completed
    assert result["halt_reason"] is not None
    assert "health checks failed" in result["halt_reason"].lower()

    # Verify plan status is FAILED
    updated_plan = await service.get_plan(plan["plan_id"])
    assert updated_plan["status"] == PlanStatus.FAILED.value


@pytest.mark.asyncio
async def test_staged_rollout_with_rollback(
    db_session: AsyncSession, test_devices: list[str]
) -> None:
    """Test staged rollout triggers rollback when health checks fail."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from routeros_mcp.domain.models import HealthCheckResult

    service = PlanService(db_session)

    # Create multi-device plan with rollback enabled
    device_ids = [test_devices[0], test_devices[1]]
    plan = await service.create_multi_device_plan(
        tool_name="dns_ntp/plan-update",
        created_by="test-user",
        device_ids=device_ids,
        summary="Update DNS servers",
        changes={
            "dns_servers": ["8.8.8.8", "8.8.4.4"],
        },
        change_type="dns_ntp",
        risk_level="medium",
        batch_size=2,
        pause_seconds_between_batches=0,
        rollback_on_failure=True,  # Enable rollback
    )

    # Approve plan
    await service.approve_plan(plan["plan_id"], plan["approval_token"], "approver-user")

    # Mock DNS/NTP service
    mock_dns_ntp_service = AsyncMock()
    mock_dns_ntp_service.get_dns_servers = AsyncMock(
        return_value={"servers": ["1.1.1.1"]}
    )
    mock_dns_ntp_service.get_ntp_status = AsyncMock(
        return_value={"servers": ["time.google.com"], "enabled": True}
    )
    mock_dns_ntp_service.update_dns_servers = AsyncMock()

    # Mock health service to return degraded result
    with patch("routeros_mcp.domain.services.health.HealthService") as MockHealthService:
        mock_health_service = MagicMock()

        async def mock_run_batch_health_checks(device_ids, cpu_threshold, memory_threshold):
            # Return degraded for all devices (high memory)
            return {
                device_id: HealthCheckResult(
                    device_id=device_id,
                    status="degraded",
                    timestamp=datetime.now(UTC),
                    cpu_usage_percent=50.0,
                    memory_usage_percent=90.0,
                    uptime_seconds=3600,
                    issues=["Memory usage above threshold: 90.0% >= 85.0%"],
                    warnings=[],
                )
                for device_id in device_ids
            }

        mock_health_service.run_batch_health_checks = mock_run_batch_health_checks
        MockHealthService.return_value = mock_health_service

        # Apply plan
        result = await service.apply_multi_device_plan(
            plan_id=plan["plan_id"],
            approval_token=plan["approval_token"],
            applied_by="test-user",
            dns_ntp_service=mock_dns_ntp_service,
        )

    # Verify rollout halted and rollback triggered
    assert result["status"] == "halted"
    assert "rollback" in result
    assert result["rollback"]["rollback_enabled"] is True
    assert result["summary"]["rolled_back"] >= 0

    # Verify plan status is ROLLED_BACK
    updated_plan = await service.get_plan(plan["plan_id"])
    assert updated_plan["status"] == PlanStatus.ROLLED_BACK.value
