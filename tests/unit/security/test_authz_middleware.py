"""Tests for authorization middleware."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import Device
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp.middleware.auth import AuthorizationMiddleware
from routeros_mcp.security.auth import User
from routeros_mcp.security.authz import (
    CapabilityDeniedError,
    DeviceScopeError,
    EnvironmentMismatchError,
    RoleInsufficientError,
    ToolTier,
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

    @pytest.fixture
    def lab_device(self):
        """Create test device in lab environment."""
        from datetime import datetime
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
    def prod_device(self):
        """Create test device in prod environment."""
        from datetime import datetime
        return Device(
            id="dev-prod-01",
            name="Prod Device 01",
            management_ip="10.0.0.1",
            management_port=443,
            environment="prod",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            created_at=datetime.now(),
            updated_at=datetime.now(),
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
        self, middleware, mock_session_factory, mock_device_service, read_only_user, lab_device
    ):
        """Test read_only user can execute fundamental tier tools."""
        # Mock device service
        mock_device_service.get_device.return_value = lab_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService
        original_init = DeviceService.__init__

        def mock_init(self, session):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should succeed
            await middleware.check_authorization(
                user=read_only_user,
                tool_name="device/list",
                tool_tier=ToolTier.FUNDAMENTAL,
                device_id="dev-lab-01",
            )
        finally:
            DeviceService.__init__ = original_init

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

        def mock_init(self, session):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise RoleInsufficientError
            with pytest.raises(RoleInsufficientError, match="read_only.*cannot execute advanced"):
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

        def mock_init(self, session):
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

        def mock_init(self, session):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise RoleInsufficientError
            with pytest.raises(RoleInsufficientError, match="ops_rw.*cannot execute professional"):
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

        def mock_init(self, session):
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

        def mock_init(self, session):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise RoleInsufficientError for fundamental tier
            with pytest.raises(RoleInsufficientError, match="approver.*cannot execute tools"):
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
        from datetime import datetime
        out_of_scope_device = Device(
            id="dev-lab-99",
            name="Lab Device 99",
            management_ip="192.168.1.99",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=True,
            allow_professional_workflows=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_device_service.get_device.return_value = out_of_scope_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService
        original_init = DeviceService.__init__

        def mock_init(self, session):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise DeviceScopeError
            with pytest.raises(DeviceScopeError, match="not in allowed scope"):
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

        def mock_init(self, session):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise EnvironmentMismatchError
            with pytest.raises(EnvironmentMismatchError, match="Environment mismatch"):
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
        from datetime import datetime
        restricted_device = Device(
            id="dev-lab-restricted",
            name="Restricted Lab Device",
            management_ip="192.168.1.50",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=True,
            allow_professional_workflows=False,  # Professional disabled
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        mock_device_service.get_device.return_value = restricted_device
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService
        original_init = DeviceService.__init__

        def mock_init(self, session):
            self.get_device = mock_device_service.get_device

        DeviceService.__init__ = mock_init

        try:
            # Should raise CapabilityDeniedError
            with pytest.raises(CapabilityDeniedError, match="allow_professional_workflows"):
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
        self, middleware, mock_session_factory, mock_device_service, ops_rw_user, lab_device
    ):
        """Test batch authorization for multiple devices."""
        # Mock device service
        from datetime import datetime
        async def get_device_by_id(device_id):
            if device_id in ["dev-lab-01", "dev-lab-02"]:
                return Device(
                    id=device_id,
                    name=f"Lab Device {device_id[-2:]}",
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
            else:
                return Device(
                    id=device_id,
                    name=f"Lab Device {device_id[-2:]}",
                    management_ip="192.168.1.99",
                    management_port=443,
                    environment="lab",
                    status="healthy",
                    tags={},
                    allow_advanced_writes=True,
                    allow_professional_workflows=True,
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )

        mock_device_service.get_device.side_effect = get_device_by_id
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        # Mock device service creation
        from routeros_mcp.domain.services.device import DeviceService
        original_init = DeviceService.__init__

        def mock_init(self, session):
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
