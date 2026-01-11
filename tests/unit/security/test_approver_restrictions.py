"""Tests for approver role enforcement and restrictions.

This module validates that the approver role:
1. Cannot execute any MCP tools (fundamental, advanced, or professional tier)
2. Can only approve/reject approval requests via API endpoints
3. All unauthorized access attempts are logged in audit logs

See Phase 5 Issue #8 for requirements.

Note: This test file provides comprehensive coverage for approver role restrictions,
complementing the existing test in test_authz_middleware.py::test_approver_cannot_execute_any_tools.
While that test validates the basic blocking behavior, this suite provides:
- Detailed validation across all tool tiers (fundamental, advanced, professional)
- Batch authorization denial testing
- Comprehensive audit logging validation
- Role comparison tests
- Error message clarity verification
This separation allows for better organization and more thorough testing of the approver
role enforcement requirements from Phase 5 Issue #8.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from routeros_mcp.domain.models import Device
from routeros_mcp.mcp.errors import AuthorizationError as MCPAuthorizationError
from routeros_mcp.security.auth import User
from routeros_mcp.security.authz import (
    RoleInsufficientError,
    ToolTier,
    UserRole,
    check_user_role,
    get_allowed_tool_tier,
)


def create_test_device(
    device_id: str,
    name: str,
    environment: str = "lab",
    allow_advanced_writes: bool = True,
    allow_professional_workflows: bool = True,
) -> Device:
    """Helper function to create test device instances."""
    return Device(
        id=device_id,
        name=name,
        management_ip="192.168.1.1",
        management_port=443,
        environment=environment,
        status="healthy",
        tags={},
        allow_advanced_writes=allow_advanced_writes,
        allow_professional_workflows=allow_professional_workflows,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestApproverRoleMapping:
    """Test approver role tier mapping in authorization logic."""

    def test_get_allowed_tool_tier_returns_none_for_approver(self):
        """Test that approver role maps to None (no tool execution allowed)."""
        allowed_tier = get_allowed_tool_tier(UserRole.APPROVER)
        assert allowed_tier is None, "Approver role should not be allowed to execute any tools"

    def test_approver_role_enum_exists(self):
        """Test that APPROVER role exists in UserRole enum."""
        assert hasattr(UserRole, "APPROVER")
        assert UserRole.APPROVER.value == "approver"


class TestApproverRoleChecks:
    """Test role checks for approver attempting tool execution."""

    def test_check_user_role_denies_approver_fundamental_tier(self):
        """Test approver cannot execute fundamental tier tools."""
        with pytest.raises(RoleInsufficientError) as exc_info:
            check_user_role(
                user_role=UserRole.APPROVER,
                tool_tier=ToolTier.FUNDAMENTAL,
                user_sub="approver-001",
                tool_name="device/list",
            )

        error_msg = str(exc_info.value)
        assert "approver" in error_msg.lower()
        assert "cannot execute tools" in error_msg.lower()
        assert "user: approver-001" in error_msg

    def test_check_user_role_denies_approver_advanced_tier(self):
        """Test approver cannot execute advanced tier tools."""
        with pytest.raises(RoleInsufficientError) as exc_info:
            check_user_role(
                user_role=UserRole.APPROVER,
                tool_tier=ToolTier.ADVANCED,
                user_sub="approver-002",
                tool_name="dns/update-servers",
            )

        error_msg = str(exc_info.value)
        assert "approver" in error_msg.lower()
        assert "cannot execute tools" in error_msg.lower()

    def test_check_user_role_denies_approver_professional_tier(self):
        """Test approver cannot execute professional tier tools."""
        with pytest.raises(RoleInsufficientError) as exc_info:
            check_user_role(
                user_role=UserRole.APPROVER,
                tool_tier=ToolTier.PROFESSIONAL,
                user_sub="approver-003",
                tool_name="plan/apply",
            )

        error_msg = str(exc_info.value)
        assert "approver" in error_msg.lower()
        assert "cannot execute tools" in error_msg.lower()


class TestApproverMiddlewareEnforcement:
    """Test authorization middleware enforcement for approver role.

    Uses shared fixtures from conftest.py: settings, mock_session_factory,
    middleware, approver_user, lab_device, setup_device_mock.
    """

    @pytest.mark.asyncio
    async def test_approver_denied_fundamental_tool_via_middleware(
        self, middleware, setup_device_mock, approver_user, lab_device
    ):
        """Test approver is denied fundamental tier tool execution via middleware."""
        with setup_device_mock(lab_device):
            with pytest.raises(MCPAuthorizationError) as exc_info:
                await middleware.check_authorization(
                    user=approver_user,
                    tool_name="device/list",
                    tool_tier=ToolTier.FUNDAMENTAL,
                    device_id="dev-lab-01",
                )

            error_msg = str(exc_info.value)
            assert "approver" in error_msg.lower()
            assert "cannot execute tools" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_approver_denied_advanced_tool_via_middleware(
        self, middleware, setup_device_mock, approver_user, lab_device
    ):
        """Test approver is denied advanced tier tool execution via middleware."""
        with setup_device_mock(lab_device):
            with pytest.raises(MCPAuthorizationError) as exc_info:
                await middleware.check_authorization(
                    user=approver_user,
                    tool_name="dns/update-servers",
                    tool_tier=ToolTier.ADVANCED,
                    device_id="dev-lab-01",
                )

            error_msg = str(exc_info.value)
            assert "approver" in error_msg.lower()
            assert "cannot execute tools" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_approver_denied_professional_tool_via_middleware(
        self, middleware, setup_device_mock, approver_user, lab_device
    ):
        """Test approver is denied professional tier tool execution via middleware."""
        with setup_device_mock(lab_device):
            with pytest.raises(MCPAuthorizationError) as exc_info:
                await middleware.check_authorization(
                    user=approver_user,
                    tool_name="plan/apply",
                    tool_tier=ToolTier.PROFESSIONAL,
                    device_id="dev-lab-01",
                )

            error_msg = str(exc_info.value)
            assert "approver" in error_msg.lower()
            assert "cannot execute tools" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_approver_denied_batch_authorization(
        self, middleware, mock_session_factory, approver_user
    ):
        """Test approver is denied for all devices in batch authorization."""

        async def get_device_by_id(device_id):
            return create_test_device(
                device_id=device_id,
                name=f"Device {device_id}",
                environment="lab",
            )

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        mock_device_service = MagicMock()
        mock_device_service.get_device = AsyncMock(side_effect=get_device_by_id)

        with patch(
            "routeros_mcp.mcp.middleware.auth.DeviceService",
            return_value=mock_device_service,
        ):
            results = await middleware.check_authorization_batch(
                user=approver_user,
                tool_name="system/reboot",
                tool_tier=ToolTier.PROFESSIONAL,
                device_ids=["dev-1", "dev-2", "dev-3"],
            )

            # All devices should be denied
            assert len(results) == 3
            for device_id, error in results.items():
                assert error is not None, f"Device {device_id} should be denied"
                assert "approver" in error.lower()
                assert "cannot execute tools" in error.lower()


class TestApproverAuditLogging:
    """Test that approver unauthorized access attempts are logged.

    Uses shared fixtures from conftest.py: settings, mock_session_factory,
    middleware, setup_device_mock.
    """

    @pytest.fixture
    def approver_audit_user(self):
        """Create approver user for audit testing (separate from shared fixture)."""
        return User(
            sub="user-approver-audit",
            email="approver-audit@example.com",
            role="approver",
            device_scope=None,
            name="Approver Audit Test",
        )

    @pytest.fixture
    def lab_audit_device(self):
        """Create test device for audit testing (separate from shared fixture)."""
        return create_test_device(
            device_id="dev-lab-audit",
            name="Lab Device Audit",
        )

    @pytest.mark.asyncio
    async def test_approver_denial_logged_with_context(
        self, middleware, mock_session_factory, approver_audit_user, lab_audit_device
    ):
        """Test that approver denial is logged with full context."""
        # Set up device mock
        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock()
        mock_session_factory.session.return_value = mock_session

        mock_device_service = MagicMock()
        mock_device_service.get_device = AsyncMock(return_value=lab_audit_device)

        # Capture log calls
        with (
            patch(
                "routeros_mcp.mcp.middleware.auth.DeviceService",
                return_value=mock_device_service,
            ),
            patch("routeros_mcp.mcp.middleware.auth.logger") as mock_logger,
        ):
            # Attempt to execute tool as approver
            with pytest.raises(MCPAuthorizationError):
                await middleware.check_authorization(
                    user=approver_audit_user,
                    tool_name="system/backup",
                    tool_tier=ToolTier.ADVANCED,
                    device_id="dev-lab-audit",
                )

            # Verify warning log was called for authorization denial
            assert mock_logger.warning.called, "Authorization denial should be logged"

            # Get the log call arguments
            log_calls = list(mock_logger.warning.call_args_list)
            assert len(log_calls) > 0, "At least one warning log should exist"

            # Find the authorization denied log call
            denial_log = None
            for call in log_calls:
                if len(call[0]) > 0 and "Authorization denied" in str(call[0][0]):
                    denial_log = call
                    break

            assert denial_log is not None, "Authorization denied log should exist"

            # Verify log context includes required fields and fail if format is unexpected
            assert len(denial_log) > 1, "Authorization denied log should include keyword arguments"
            assert isinstance(
                denial_log[1], dict
            ), "Authorization denied log kwargs should be a dict"
            assert (
                "extra" in denial_log[1]
            ), "Authorization denied log should include 'extra' context"

            log_extra = denial_log[1]["extra"]
            assert "user_sub" in log_extra
            assert log_extra["user_sub"] == "user-approver-audit"
            assert "user_role" in log_extra
            assert log_extra["user_role"] == "approver"
            assert "tool_name" in log_extra
            assert log_extra["tool_name"] == "system/backup"
            assert "decision" in log_extra
            assert log_extra["decision"] == "DENY"
            assert "reason" in log_extra
            assert log_extra["reason"] == "RoleInsufficientError"


class TestApproverVsOtherRoles:
    """Test that approver role behaves differently from other roles."""

    def test_read_only_can_execute_fundamental_but_approver_cannot(self):
        """Test read_only user can execute fundamental but approver cannot."""
        # read_only should be allowed fundamental tier
        allowed_tier_readonly = get_allowed_tool_tier(UserRole.READ_ONLY)
        assert allowed_tier_readonly == ToolTier.FUNDAMENTAL

        # approver should not be allowed any tier
        allowed_tier_approver = get_allowed_tool_tier(UserRole.APPROVER)
        assert allowed_tier_approver is None

    def test_ops_rw_can_execute_advanced_but_approver_cannot(self):
        """Test ops_rw user can execute advanced but approver cannot."""
        # ops_rw should be allowed up to advanced tier
        allowed_tier_ops = get_allowed_tool_tier(UserRole.OPS_RW)
        assert allowed_tier_ops == ToolTier.ADVANCED

        # approver should not be allowed any tier
        allowed_tier_approver = get_allowed_tool_tier(UserRole.APPROVER)
        assert allowed_tier_approver is None

    def test_admin_can_execute_professional_but_approver_cannot(self):
        """Test admin user can execute professional but approver cannot."""
        # admin should be allowed all tiers including professional
        allowed_tier_admin = get_allowed_tool_tier(UserRole.ADMIN)
        assert allowed_tier_admin == ToolTier.PROFESSIONAL

        # approver should not be allowed any tier
        allowed_tier_approver = get_allowed_tool_tier(UserRole.APPROVER)
        assert allowed_tier_approver is None


class TestApproverDocumentation:
    """Test that approver role is properly documented in error messages."""

    def test_error_message_mentions_approver_purpose(self):
        """Test that error message explains what approvers can do."""
        with pytest.raises(RoleInsufficientError) as exc_info:
            check_user_role(
                user_role=UserRole.APPROVER,
                tool_tier=ToolTier.FUNDAMENTAL,
            )

        error_msg = str(exc_info.value)
        # Error should mention what approvers CAN do
        assert "approve" in error_msg.lower() or "plan" in error_msg.lower()
