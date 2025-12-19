"""Tests for health service SSE broadcast functionality."""

import pytest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import HealthCheckResult
from routeros_mcp.domain.services.health import HealthService


@pytest.fixture
def settings() -> Settings:
    """Create test settings."""
    return Settings(
        environment="lab",
        database_url="sqlite+aiosqlite:///:memory:",
    )


@pytest.fixture
def mock_session() -> AsyncMock:
    """Create mock database session."""
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def health_service(mock_session: AsyncMock, settings: Settings) -> HealthService:
    """Create health service instance."""
    return HealthService(mock_session, settings)


@pytest.mark.asyncio
async def test_broadcast_health_update_with_sse_manager(
    health_service: HealthService,
) -> None:
    """Test health update broadcasts to SSE subscribers."""
    # Create mock SSE manager
    mock_sse_manager = AsyncMock()
    mock_sse_manager.broadcast = AsyncMock(return_value=2)  # 2 subscribers

    # Patch get_sse_manager where it's imported in the method
    with patch("routeros_mcp.mcp.server.get_sse_manager") as mock_get:
        mock_get.return_value = mock_sse_manager

        # Create health check result
        result = HealthCheckResult(
            device_id="dev-001",
            status="healthy",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=25.5,
            memory_usage_percent=60.2,
            uptime_seconds=86400,
            issues=[],
            warnings=[],
            metadata={},
        )

        # Broadcast update
        await health_service._broadcast_health_update("dev-001", result)

        # Verify broadcast was called
        mock_sse_manager.broadcast.assert_called_once()
        call_args = mock_sse_manager.broadcast.call_args

        # Check resource URI
        assert call_args.kwargs["resource_uri"] == "device://dev-001/health"

        # Check event type
        assert call_args.kwargs["event_type"] == "resource_updated"

        # Check notification data (lightweight!)
        data = call_args.kwargs["data"]
        assert data["uri"] == "device://dev-001/health"
        assert "etag" in data
        assert data["etag"] == result.timestamp.isoformat()
        assert data["status_hint"] == "healthy"

        # Verify no full payload in notification
        assert "cpu_usage_percent" not in data
        assert "memory_usage_percent" not in data
        assert "metrics" not in data


@pytest.mark.asyncio
async def test_broadcast_health_update_without_sse_manager(
    health_service: HealthService,
) -> None:
    """Test health update when SSE manager is not active (stdio mode)."""
    # Patch get_sse_manager to return None
    with patch("routeros_mcp.mcp.server.get_sse_manager") as mock_get:
        mock_get.return_value = None

        result = HealthCheckResult(
            device_id="dev-001",
            status="healthy",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=25.5,
        )

        # Should not raise error
        await health_service._broadcast_health_update("dev-001", result)

        # No broadcast should have been attempted
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_broadcast_health_update_handles_errors(
    health_service: HealthService,
) -> None:
    """Test broadcast errors don't fail health check."""
    # Create mock SSE manager that raises error
    mock_sse_manager = AsyncMock()
    mock_sse_manager.broadcast = AsyncMock(side_effect=RuntimeError("Broadcast failed"))

    with patch("routeros_mcp.mcp.server.get_sse_manager") as mock_get:
        mock_get.return_value = mock_sse_manager

        result = HealthCheckResult(
            device_id="dev-001",
            status="degraded",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=85.5,
            issues=["High CPU usage"],
        )

        # Should not raise error (exception caught and logged)
        await health_service._broadcast_health_update("dev-001", result)

        # Broadcast was attempted
        mock_sse_manager.broadcast.assert_called_once()


@pytest.mark.asyncio
async def test_broadcast_notification_data_format(
    health_service: HealthService,
) -> None:
    """Test notification data follows lightweight format."""
    mock_sse_manager = AsyncMock()
    mock_sse_manager.broadcast = AsyncMock(return_value=1)

    with patch("routeros_mcp.mcp.server.get_sse_manager") as mock_get:
        mock_get.return_value = mock_sse_manager

        result = HealthCheckResult(
            device_id="dev-lab-01",
            status="unreachable",
            timestamp=datetime(2025, 1, 15, 14, 30, 0, tzinfo=UTC),
            issues=["Device unreachable"],
        )

        await health_service._broadcast_health_update("dev-lab-01", result)

        call_args = mock_sse_manager.broadcast.call_args
        data = call_args.kwargs["data"]

        # Verify required fields
        assert "uri" in data
        assert data["uri"] == "device://dev-lab-01/health"

        # Verify optional version hint
        assert "etag" in data
        assert data["etag"] == "2025-01-15T14:30:00+00:00"

        # Verify status hint (allows clients to avoid re-read if unchanged)
        assert "status_hint" in data
        assert data["status_hint"] == "unreachable"

        # Verify NO payload fields
        assert "cpu_usage_percent" not in data
        assert "memory_usage_percent" not in data
        assert "uptime_seconds" not in data
        assert "issues" not in data
        assert "warnings" not in data
        assert "checks" not in data


@pytest.mark.asyncio
async def test_broadcast_multiple_subscribers(
    health_service: HealthService,
) -> None:
    """Test broadcast to multiple subscribers."""
    mock_sse_manager = AsyncMock()
    mock_sse_manager.broadcast = AsyncMock(return_value=5)  # 5 subscribers

    with patch("routeros_mcp.mcp.server.get_sse_manager") as mock_get:
        mock_get.return_value = mock_sse_manager

        result = HealthCheckResult(
            device_id="dev-prod-01",
            status="healthy",
            timestamp=datetime.now(UTC),
            cpu_usage_percent=15.0,
        )

        await health_service._broadcast_health_update("dev-prod-01", result)

        # Verify broadcast was called
        mock_sse_manager.broadcast.assert_called_once()

        # Verify resource URI
        call_args = mock_sse_manager.broadcast.call_args
        assert call_args.kwargs["resource_uri"] == "device://dev-prod-01/health"


@pytest.mark.asyncio
async def test_broadcast_zero_subscribers(
    health_service: HealthService,
) -> None:
    """Test broadcast when no subscribers are active."""
    mock_sse_manager = AsyncMock()
    mock_sse_manager.broadcast = AsyncMock(return_value=0)  # No subscribers

    with patch("routeros_mcp.mcp.server.get_sse_manager") as mock_get:
        mock_get.return_value = mock_sse_manager

        result = HealthCheckResult(
            device_id="dev-001",
            status="healthy",
            timestamp=datetime.now(UTC),
        )

        # Should still broadcast (manager handles no-subscribers case)
        await health_service._broadcast_health_update("dev-001", result)

        mock_sse_manager.broadcast.assert_called_once()
