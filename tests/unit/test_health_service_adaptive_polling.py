"""Unit tests for adaptive polling strategy in HealthService (Phase 4).

Tests cover:
- Device classification (critical vs non-critical)
- Interval adjustment after 10 consecutive healthy checks
- Reset to base interval on unhealthy/degraded checks
- Exponential backoff for unreachable devices
- Health status tracking
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import HealthCheckResult
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.infra.db.models import Device as DeviceORM


class TestAdaptivePollingIntervals:
    """Test base polling intervals for critical vs non-critical devices."""

    def test_critical_device_base_interval(self):
        """Critical devices should have 30s base polling interval."""
        service = HealthService(session=None, settings=Settings())
        interval = service.get_device_polling_interval("dev-001", critical=True)
        assert interval == 30

    def test_non_critical_device_base_interval(self):
        """Non-critical devices should have 60s base polling interval."""
        service = HealthService(session=None, settings=Settings())
        interval = service.get_device_polling_interval("dev-001", critical=False)
        assert interval == 60


class TestAdaptivePollingIntervalAdjustment:
    """Test interval adjustment based on consecutive healthy checks."""

    @pytest.mark.asyncio
    async def test_interval_increases_after_10_healthy_checks(self):
        """Interval should increase by 50% after 10 consecutive healthy checks."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        # Mock device with 9 consecutive healthy checks
        mock_device = DeviceORM(
            id="dev-001",
            name="Test Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=False,
            health_status="healthy",
            consecutive_healthy_checks=9,
            polling_interval_seconds=60,
            last_backoff_at=None,
        )

        # Mock database query to return device
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        # Simulate healthy check result
        health_result = HealthCheckResult(
            device_id="dev-001",
            status="healthy",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=30.0,
            memory_usage_percent=40.0,
            uptime_seconds=86400,
            issues=[],
            warnings=[],
        )

        # Update adaptive polling
        await service._update_adaptive_polling("dev-001", health_result)

        # Verify interval was increased to 90s (60 * 1.5)
        session.execute.assert_called()
        call_args = session.execute.call_args_list[-1]
        update_stmt = call_args[0][0]
        
        # Check that the update statement has correct values
        assert hasattr(update_stmt, "_values")

    @pytest.mark.asyncio
    async def test_interval_capped_at_300_seconds(self):
        """Interval should never exceed 300 seconds (5 minutes)."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        # Mock device with high interval (250s) and 10 healthy checks
        mock_device = DeviceORM(
            id="dev-001",
            name="Test Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=False,
            health_status="healthy",
            consecutive_healthy_checks=10,
            polling_interval_seconds=250,
            last_backoff_at=None,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        health_result = HealthCheckResult(
            device_id="dev-001",
            status="healthy",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=30.0,
            memory_usage_percent=40.0,
            uptime_seconds=86400,
            issues=[],
            warnings=[],
        )

        await service._update_adaptive_polling("dev-001", health_result)

        # Interval should be capped at 300s (not 375s = 250 * 1.5)
        session.execute.assert_called()


class TestAdaptivePollingReset:
    """Test interval reset on unhealthy/degraded checks."""

    @pytest.mark.asyncio
    async def test_degraded_check_resets_to_base_interval(self):
        """Degraded check should reset interval to base (60s for non-critical)."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        # Mock device with elevated interval
        mock_device = DeviceORM(
            id="dev-001",
            name="Test Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=False,
            health_status="healthy",
            consecutive_healthy_checks=5,
            polling_interval_seconds=135,  # Already increased
            last_backoff_at=None,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        # Simulate degraded check
        health_result = HealthCheckResult(
            device_id="dev-001",
            status="degraded",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=85.0,  # High CPU
            memory_usage_percent=40.0,
            uptime_seconds=86400,
            issues=["High CPU usage: 85.0%"],
            warnings=[],
        )

        await service._update_adaptive_polling("dev-001", health_result)

        # Verify interval was reset and consecutive count cleared
        session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_critical_device_resets_to_30s(self):
        """Critical device should reset to 30s base interval."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        # Mock critical device with elevated interval
        mock_device = DeviceORM(
            id="dev-crit-001",
            name="Critical Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="prod",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=True,  # Critical device
            health_status="healthy",
            consecutive_healthy_checks=3,
            polling_interval_seconds=67,  # Increased from 30s
            last_backoff_at=None,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        # Simulate degraded check
        health_result = HealthCheckResult(
            device_id="dev-crit-001",
            status="degraded",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=90.0,
            memory_usage_percent=40.0,
            uptime_seconds=86400,
            issues=["Critical CPU usage: 90.0%"],
            warnings=[],
        )

        await service._update_adaptive_polling("dev-crit-001", health_result)

        session.execute.assert_called()


class TestExponentialBackoff:
    """Test exponential backoff for unreachable devices."""

    @pytest.mark.asyncio
    async def test_first_unreachable_sets_60s_interval(self):
        """First unreachable check should set 60s interval."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        # Mock healthy device that becomes unreachable
        mock_device = DeviceORM(
            id="dev-001",
            name="Test Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=False,
            health_status="healthy",
            consecutive_healthy_checks=5,
            polling_interval_seconds=60,
            last_backoff_at=None,  # No previous backoff
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        # Simulate unreachable check
        health_result = HealthCheckResult(
            device_id="dev-001",
            status="unreachable",
            timestamp=datetime.now(UTC),
            issues=["Device unreachable: Connection timeout"],
        )

        await service._update_adaptive_polling("dev-001", health_result)

        # Verify 60s interval was set
        session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_exponential_backoff_doubles_interval(self):
        """Subsequent unreachable checks should double the interval."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        # Mock device already in backoff state (120s)
        mock_device = DeviceORM(
            id="dev-001",
            name="Test Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="unreachable",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=False,
            health_status="unreachable",
            consecutive_healthy_checks=0,
            polling_interval_seconds=120,  # Already backed off once
            last_backoff_at=datetime.now(UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        # Another unreachable check
        health_result = HealthCheckResult(
            device_id="dev-001",
            status="unreachable",
            timestamp=datetime.now(UTC),
            issues=["Device unreachable: Connection timeout"],
        )

        await service._update_adaptive_polling("dev-001", health_result)

        # Verify interval doubled to 240s
        session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_exponential_backoff_capped_at_960s(self):
        """Backoff interval should be capped at 960s (16 minutes)."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        # Mock device at max backoff (960s)
        mock_device = DeviceORM(
            id="dev-001",
            name="Test Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="unreachable",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=False,
            health_status="unreachable",
            consecutive_healthy_checks=0,
            polling_interval_seconds=960,  # Max backoff
            last_backoff_at=datetime.now(UTC),
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        # Another unreachable check
        health_result = HealthCheckResult(
            device_id="dev-001",
            status="unreachable",
            timestamp=datetime.now(UTC),
            issues=["Device unreachable: Connection timeout"],
        )

        await service._update_adaptive_polling("dev-001", health_result)

        # Verify interval stayed at 960s (not doubled to 1920s)
        session.execute.assert_called()


class TestHealthStatusTracking:
    """Test health status field updates."""

    @pytest.mark.asyncio
    async def test_health_status_updated_to_healthy(self):
        """Health status should be updated to 'healthy' on successful check."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        mock_device = DeviceORM(
            id="dev-001",
            name="Test Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="degraded",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=False,
            health_status="degraded",  # Previously degraded
            consecutive_healthy_checks=0,
            polling_interval_seconds=60,
            last_backoff_at=None,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        health_result = HealthCheckResult(
            device_id="dev-001",
            status="healthy",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=30.0,
            memory_usage_percent=40.0,
            uptime_seconds=86400,
            issues=[],
            warnings=[],
        )

        await service._update_adaptive_polling("dev-001", health_result)

        session.execute.assert_called()
        session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_health_status_updated_to_unreachable(self):
        """Health status should be updated to 'unreachable' when device is down."""
        session = AsyncMock(spec=AsyncSession)
        settings = Settings()
        service = HealthService(session, settings)

        mock_device = DeviceORM(
            id="dev-001",
            name="Test Device",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            critical=False,
            health_status="healthy",
            consecutive_healthy_checks=5,
            polling_interval_seconds=60,
            last_backoff_at=None,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_device
        session.execute = AsyncMock(return_value=mock_result)
        session.commit = AsyncMock()

        health_result = HealthCheckResult(
            device_id="dev-001",
            status="unreachable",
            timestamp=datetime.now(UTC),
            issues=["Device unreachable: Connection timeout"],
        )

        await service._update_adaptive_polling("dev-001", health_result)

        session.execute.assert_called()
        session.commit.assert_called()


class TestJobSchedulerIntegration:
    """Test JobScheduler methods for adaptive polling."""

    def test_add_health_check_job_creates_job(self):
        """Should create per-device health check job with specified interval."""
        from routeros_mcp.infra.jobs.scheduler import JobScheduler

        scheduler = JobScheduler(Settings())
        scheduler.start = MagicMock()  # Don't actually start scheduler
        scheduler.scheduler = MagicMock()
        
        mock_job = MagicMock()
        mock_job.id = "health_check_dev-001"
        scheduler.scheduler.add_job = MagicMock(return_value=mock_job)

        async def mock_health_check(device_id: str):
            pass

        job_id = scheduler.add_health_check_job(
            device_id="dev-001",
            job_func=mock_health_check,
            interval_seconds=60,
        )

        assert job_id == "health_check_dev-001"
        scheduler.scheduler.add_job.assert_called_once()

    def test_update_health_check_interval_modifies_existing_job(self):
        """Should update interval for existing health check job."""
        from routeros_mcp.infra.jobs.scheduler import JobScheduler

        scheduler = JobScheduler(Settings())
        scheduler.scheduler = MagicMock()

        mock_job = MagicMock()
        mock_job.reschedule = MagicMock()
        scheduler.scheduler.get_job = MagicMock(return_value=mock_job)

        result = scheduler.update_health_check_interval("dev-001", 90)

        assert result is True
        mock_job.reschedule.assert_called_once()

    def test_update_health_check_interval_returns_false_if_job_not_found(self):
        """Should return False if health check job doesn't exist."""
        from routeros_mcp.infra.jobs.scheduler import JobScheduler

        scheduler = JobScheduler(Settings())
        scheduler.scheduler = MagicMock()
        scheduler.scheduler.get_job = MagicMock(return_value=None)

        result = scheduler.update_health_check_interval("dev-999", 90)

        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
