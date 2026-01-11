"""Tests for authorization middleware."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import Device
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp.middleware.auth import AuthorizationMiddleware
from routeros_mcp.mcp.errors import AuthorizationError as MCPAuthorizationError
from routeros_mcp.security.auth import User
from routeros_mcp.security.authz import (
    ToolTier,
)


def create_test_device(
    device_id: str,
    name: str,
    environment: str = "lab",
    allow_advanced_writes: bool = True,
    allow_professional_workflows: bool = True,
    management_ip: str = "192.168.1.1",
) -> Device:
    """Helper function to create test device instances.

    Args:
        device_id: Device ID
        name: Device name
        environment: Device environment (lab/staging/prod)
        allow_advanced_writes: Advanced writes capability
        allow_professional_workflows: Professional workflows capability
        management_ip: Management IP address

    Returns:
        Device instance with test data
    """
    return Device(
        id=device_id,
        name=name,
        management_ip=management_ip,
        management_port=443,
        environment=environment,
        status="healthy",
        tags={},
        allow_advanced_writes=allow_advanced_writes,
        allow_professional_workflows=allow_professional_workflows,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestAuthorizationMiddleware:
    """Tests for AuthorizationMiddleware class."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return Settings(environment="lab")

    @pytest.fixture
    def mock_session_factory(self):
        """Create mock database session factory."""
        factory = MagicMock(spec=DatabaseSessionManager)
        factory.session = MagicMock()
        return factory

    @pytest.fixture
    def mock_device_service(self):
        """Create mock device service."""
        service = MagicMock()
        service.get_device = AsyncMock()
        return service

    @pytest.fixture
    def middleware(self, mock_session_factory, settings):
        """Create authorization middleware instance."""
        return AuthorizationMiddleware(mock_session_factory, settings)

    def setup_device_service_mock(self, mock_session_factory, device):
        """Helper to set up device service mock with proper session handling.

        Args:
            mock_session_factory: Mock session factory fixture
            device: Device instance to return from get_device

        Returns:
            Context manager for patching DeviceService
        """
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

    @pytest.fixture
    def lab_device(self):
        """Create test device in lab environment."""
        return create_test_device(
            device_id="dev-lab-01",
            name="Lab Device 01",
        )

    @pytest.fixture
    def prod_device(self):
        """Create test device in prod environment."""
        return create_test_device(
            device_id="dev-prod-01",
            name="Prod Device 01",
            environment="prod",
            management_ip="10.0.0.1",
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )

    @pytest.fixture
    def read_only_user(self):
        """Create read-only user."""
        return User(
            sub="user-readonly-001",
            email="readonly@example.com",
            role="read_only",
            device_scope=None,  # Full access
            name="Read Only User",
        )

    @pytest.fixture
    def ops_rw_user(self):
        """Create ops_rw user with device scope."""
        return User(
            sub="user-ops-001",
            email="ops@example.com",
            role="ops_rw",
            device_scope=["dev-lab-01", "dev-lab-02"],  # Limited scope
            name="Ops User",
        )

    @pytest.fixture
    def admin_user(self):
        """Create admin user."""
        return User(
            sub="user-admin-001",
            email="admin@example.com",
            role="admin",
            device_scope=None,  # Full access
            name="Admin User",
        )

    @pytest.fixture
    def approver_user(self):
        """Create approver user."""
        return User(
            sub="user-approver-001",
            email="approver@example.com",
            role="approver",
            device_scope=None,  # Full access but cannot execute tools
            name="Approver User",
        )

    @pytest.mark.asyncio
    async def test_read_only_user_can_execute_fundamental_tools(
        self,
        middleware,
        mock_session_factory,
        mock_device_service,
        read_only_user,
        lab_device,
    ):
        """Test read_only user can execute fundamental tier tools."""
        # Mock device service to return test device
        mock_device_service.get_device.return_value = lab_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Use patch as context manager to mock DeviceService
        with patch("routeros_mcp.mcp.middleware.auth.DeviceService") as MockDeviceService:
            MockDeviceService.return_value.get_device = mock_device_service.get_device

            # Should succeed
            await middleware.check_authorization(
                user=read_only_user,
                tool_name="device/list",
                tool_tier=ToolTier.FUNDAMENTAL,
                device_id="dev-lab-01",
            )

    @pytest.mark.asyncio
    async def test_read_only_user_cannot_execute_advanced_tools(
        self, middleware, mock_session_factory, mock_device_service, read_only_user, lab_device
    ):
        """Test read_only user cannot execute advanced tier tools."""
        # Mock device service
        mock_device_service.get_device.return_value = lab_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise RoleInsufficientError
            with pytest.raises(MCPAuthorizationError, match="read_only.*cannot execute advanced"):
                await middleware.check_authorization(
                    user=read_only_user,
                    tool_name="dns/update-servers",
                    tool_tier=ToolTier.ADVANCED,
                    device_id="dev-lab-01",
                )
        finally:
            DeviceService.__init__ = original_init

    @pytest.mark.asyncio
    async def test_ops_rw_user_can_execute_advanced_tools(
        self, middleware, mock_session_factory, mock_device_service, ops_rw_user, lab_device
    ):
        """Test ops_rw user can execute advanced tier tools."""
        # Mock device service
        mock_device_service.get_device.return_value = lab_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should succeed
            await middleware.check_authorization(
                user=ops_rw_user,
                tool_name="dns/update-servers",
                tool_tier=ToolTier.ADVANCED,
                device_id="dev-lab-01",
            )
        finally:
            DeviceService.__init__ = original_init

    @pytest.mark.asyncio
    async def test_ops_rw_user_cannot_execute_professional_tools(
        self, middleware, mock_session_factory, mock_device_service, ops_rw_user, lab_device
    ):
        """Test ops_rw user cannot execute professional tier tools."""
        # Mock device service
        mock_device_service.get_device.return_value = lab_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise RoleInsufficientError
            with pytest.raises(MCPAuthorizationError, match="ops_rw.*cannot execute professional"):
                await middleware.check_authorization(
                    user=ops_rw_user,
                    tool_name="plan/apply",
                    tool_tier=ToolTier.PROFESSIONAL,
                    device_id="dev-lab-01",
                )
        finally:
            DeviceService.__init__ = original_init

    @pytest.mark.asyncio
    async def test_admin_user_can_execute_all_tiers(
        self, middleware, mock_session_factory, mock_device_service, admin_user, lab_device
    ):
        """Test admin user can execute all tool tiers."""
        # Mock device service
        mock_device_service.get_device.return_value = lab_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Test fundamental tier
            await middleware.check_authorization(
                user=admin_user,
                tool_name="device/list",
                tool_tier=ToolTier.FUNDAMENTAL,
                device_id="dev-lab-01",
            )

            # Test advanced tier
            await middleware.check_authorization(
                user=admin_user,
                tool_name="dns/update-servers",
                tool_tier=ToolTier.ADVANCED,
                device_id="dev-lab-01",
            )

            # Test professional tier
            await middleware.check_authorization(
                user=admin_user,
                tool_name="plan/apply",
                tool_tier=ToolTier.PROFESSIONAL,
                device_id="dev-lab-01",
            )
        finally:
            DeviceService.__init__ = original_init

    @pytest.mark.asyncio
    async def test_approver_cannot_execute_any_tools(
        self, middleware, mock_session_factory, mock_device_service, approver_user, lab_device
    ):
        """Test approver role cannot execute any tools."""
        # Mock device service
        mock_device_service.get_device.return_value = lab_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise RoleInsufficientError for fundamental tier
            with pytest.raises(MCPAuthorizationError, match="approver.*cannot execute tools"):
                await middleware.check_authorization(
                    user=approver_user,
                    tool_name="device/list",
                    tool_tier=ToolTier.FUNDAMENTAL,
                    device_id="dev-lab-01",
                )
        finally:
            DeviceService.__init__ = original_init

    @pytest.mark.asyncio
    async def test_device_scope_restriction(
        self, middleware, mock_session_factory, mock_device_service, ops_rw_user, lab_device
    ):
        """Test device scope restriction blocks unauthorized devices."""
        # Mock device service with device NOT in scope
        out_of_scope_device = create_test_device(
            device_id="dev-lab-99",
            name="Lab Device 99",
            management_ip="192.168.1.99",
        )
        mock_device_service.get_device.return_value = out_of_scope_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise MCPAuthorizationError (originally DeviceScopeError)
            with pytest.raises(MCPAuthorizationError, match="not in allowed scope"):
                await middleware.check_authorization(
                    user=ops_rw_user,
                    tool_name="dns/update-servers",
                    tool_tier=ToolTier.ADVANCED,
                    device_id="dev-lab-99",
                )
        finally:
            DeviceService.__init__ = original_init

    @pytest.mark.asyncio
    async def test_environment_mismatch_blocks_execution(
        self, middleware, mock_session_factory, mock_device_service, admin_user, prod_device
    ):
        """Test environment mismatch blocks tool execution."""
        # Middleware is in "lab" environment, device is in "prod"
        # Use admin user to bypass device scope restriction
        mock_device_service.get_device.return_value = prod_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise EnvironmentMismatchError
            with pytest.raises(MCPAuthorizationError, match="Environment mismatch"):
                await middleware.check_authorization(
                    user=admin_user,
                    tool_name="device/list",
                    tool_tier=ToolTier.FUNDAMENTAL,
                    device_id="dev-prod-01",
                )
        finally:
            DeviceService.__init__ = original_init

    @pytest.mark.asyncio
    async def test_device_capability_flags_block_execution(
        self, middleware, mock_session_factory, mock_device_service, admin_user
    ):
        """Test device capability flags block tool execution."""
        # Device with professional workflows disabled
        restricted_device = create_test_device(
            device_id="dev-lab-restricted",
            name="Restricted Lab Device",
            management_ip="192.168.1.50",
            allow_professional_workflows=False,  # Professional disabled
        )
        mock_device_service.get_device.return_value = restricted_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise CapabilityDeniedError
            with pytest.raises(MCPAuthorizationError, match="allow_professional_workflows"):
                await middleware.check_authorization(
                    user=admin_user,
                    tool_name="plan/apply",
                    tool_tier=ToolTier.PROFESSIONAL,
                    device_id="dev-lab-restricted",
                )
        finally:
            DeviceService.__init__ = original_init

    @pytest.mark.asyncio
    async def test_batch_authorization(
        self,
        middleware,
        mock_session_factory,
        mock_device_service,
        ops_rw_user,
        lab_device,
    ):
        """Test batch authorization for multiple devices."""

        # Mock device service with helper function
        async def get_device_by_id(device_id):
            if device_id in ["dev-lab-01", "dev-lab-02"]:
                return create_test_device(
                    device_id=device_id,
                    name=f"Lab Device {device_id[-2:]}",
                    management_ip="192.168.1.1",
                )
            else:
                return create_test_device(
                    device_id=device_id,
                    name=f"Lab Device {device_id[-2:]}",
                    management_ip="192.168.1.99",
                )

        mock_device_service.get_device.side_effect = get_device_by_id
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService

        original_init = DeviceService.__init__

        def mock_init(self, session, settings=None):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Check authorization for multiple devices
            results = await middleware.check_authorization_batch(
                user=ops_rw_user,
                tool_name="dns/update-servers",
                tool_tier=ToolTier.ADVANCED,
                device_ids=["dev-lab-01", "dev-lab-02", "dev-lab-99"],
            )

            # dev-lab-01 and dev-lab-02 should be authorized
            assert results["dev-lab-01"] is None
            assert results["dev-lab-02"] is None

            # dev-lab-99 should be denied (not in device_scope)
            assert results["dev-lab-99"] is not None
            assert "not in allowed scope" in results["dev-lab-99"]
        finally:
            DeviceService.__init__ = original_init
