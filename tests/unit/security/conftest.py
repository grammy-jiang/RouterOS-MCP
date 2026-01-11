"""Shared fixtures for security tests."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import Device
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp.middleware.auth import AuthorizationMiddleware
from routeros_mcp.security.auth import User


@pytest.fixture
def settings():
    """Create test settings with lab environment."""
    return Settings(environment="lab")


@pytest.fixture
def mock_session_factory():
    """Create mock database session factory."""
    factory = MagicMock(spec=DatabaseSessionManager)
    factory.session = MagicMock()
    return factory


@pytest.fixture
def middleware(mock_session_factory, settings):
    """Create authorization middleware instance."""
    return AuthorizationMiddleware(mock_session_factory, settings)


@pytest.fixture
def approver_user():
    """Create approver user with full device access."""
    return User(
        sub="user-approver-001",
        email="approver@example.com",
        role="approver",
        device_scope=None,  # Full device access (not the limiting factor)
        name="Approver User",
    )


@pytest.fixture
def lab_device():
    """Create test device in lab environment with all capabilities."""
    return Device(
        id="dev-lab-01",
        name="Lab Device 01",
        management_ip="192.168.1.1",
        management_port=443,
        environment="lab",
        status="healthy",
        tags={},
        allow_advanced_writes=True,
        allow_professional_workflows=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def setup_device_mock(mock_session_factory):
    """Create a fixture that returns a context manager for mocking device service.

    This fixture is designed to be used with device instances to mock
    the DeviceService.get_device method in authorization middleware tests.

    Usage:
        def test_something(setup_device_mock, lab_device):
            with setup_device_mock(lab_device):
                # Test code that uses DeviceService
    """

    def _setup_mock(device):
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        mock_device_service = MagicMock()
        mock_device_service.get_device = AsyncMock(return_value=device)

        return patch(
            "routeros_mcp.mcp.middleware.auth.DeviceService",
            return_value=mock_device_service,
        )

    return _setup_mock
