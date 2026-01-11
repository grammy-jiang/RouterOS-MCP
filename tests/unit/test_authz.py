"""Tests for authorization module."""

import pytest

from routeros_mcp.security.authz import (
    CapabilityDeniedError,
    EnvironmentMismatchError,
    RoleInsufficientError,
    ToolTier,
    UserRole,
    check_device_capability,
    check_environment_match,
    check_tool_authorization,
    check_user_role,
)


class TestCheckEnvironmentMatch:
    """Tests for check_environment_match function."""

    def test_matching_environments_pass(self) -> None:
        """Test that matching environments pass."""
        check_environment_match("lab", "lab")
        check_environment_match("staging", "staging")
        check_environment_match("prod", "prod")

    def test_mismatched_environments_raise_error(self) -> None:
        """Test that mismatched environments raise EnvironmentMismatchError."""
        with pytest.raises(EnvironmentMismatchError, match="Environment mismatch"):
            check_environment_match("lab", "prod")

    def test_error_includes_device_id_when_provided(self) -> None:
        """Test that error message includes device_id when provided."""
        with pytest.raises(EnvironmentMismatchError, match="device: test-device"):
            check_environment_match("lab", "staging", device_id="test-device")

    def test_all_environment_combinations(self) -> None:
        """Test all invalid environment combinations."""
        environments = ["lab", "staging", "prod"]

        for device_env in environments:
            for service_env in environments:
                if device_env != service_env:
                    with pytest.raises(EnvironmentMismatchError):
                        check_environment_match(device_env, service_env)


class TestCheckDeviceCapability:
    """Tests for check_device_capability function."""

    def test_fundamental_tier_always_allowed(self) -> None:
        """Test that fundamental tier is always allowed."""
        check_device_capability(
            ToolTier.FUNDAMENTAL,
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )

    def test_advanced_tier_requires_advanced_writes(self) -> None:
        """Test that advanced tier requires allow_advanced_writes=True."""
        # Should pass with advanced writes enabled
        check_device_capability(
            ToolTier.ADVANCED,
            allow_advanced_writes=True,
            allow_professional_workflows=False,
        )

        # Should fail with advanced writes disabled
        with pytest.raises(CapabilityDeniedError, match="allow_advanced_writes"):
            check_device_capability(
                ToolTier.ADVANCED,
                allow_advanced_writes=False,
                allow_professional_workflows=False,
            )

    def test_professional_tier_requires_professional_workflows(self) -> None:
        """Test that professional tier requires allow_professional_workflows=True."""
        # Should pass with professional workflows enabled
        check_device_capability(
            ToolTier.PROFESSIONAL,
            allow_advanced_writes=True,
            allow_professional_workflows=True,
        )

        # Should fail with professional workflows disabled
        with pytest.raises(CapabilityDeniedError, match="allow_professional_workflows"):
            check_device_capability(
                ToolTier.PROFESSIONAL,
                allow_advanced_writes=True,
                allow_professional_workflows=False,
            )

    def test_error_includes_device_id_and_tool_name(self) -> None:
        """Test that error includes device_id and tool_name when provided."""
        with pytest.raises(CapabilityDeniedError, match=r"test-dev"):
            check_device_capability(
                ToolTier.ADVANCED,
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                device_id="test-dev",
                tool_name="dns/update-servers",
            )

    def test_professional_tier_doesnt_check_advanced_writes(self) -> None:
        """Test that professional tier only checks professional_workflows flag."""
        # This should fail even though advanced_writes is True
        with pytest.raises(CapabilityDeniedError):
            check_device_capability(
                ToolTier.PROFESSIONAL,
                allow_advanced_writes=True,
                allow_professional_workflows=False,
            )


class TestCheckToolAuthorization:
    """Tests for check_tool_authorization function."""

    def test_full_authorization_check_passes(self) -> None:
        """Test that full authorization check passes with valid inputs."""
        check_tool_authorization(
            device_environment="lab",
            service_environment="lab",
            tool_tier=ToolTier.ADVANCED,
            allow_advanced_writes=True,
            allow_professional_workflows=False,
            device_id="test-dev",
            tool_name="dns/update-servers",
        )

    def test_environment_mismatch_fails(self) -> None:
        """Test that environment mismatch causes failure."""
        with pytest.raises(EnvironmentMismatchError):
            check_tool_authorization(
                device_environment="lab",
                service_environment="prod",
                tool_tier=ToolTier.FUNDAMENTAL,
                allow_advanced_writes=False,
                allow_professional_workflows=False,
            )

    def test_capability_check_fails(self) -> None:
        """Test that capability check failure is caught."""
        with pytest.raises(CapabilityDeniedError):
            check_tool_authorization(
                device_environment="lab",
                service_environment="lab",
                tool_tier=ToolTier.ADVANCED,
                allow_advanced_writes=False,
                allow_professional_workflows=False,
            )

    def test_all_three_tiers(self) -> None:
        """Test authorization for all three tool tiers."""
        # Fundamental - should always pass
        check_tool_authorization("lab", "lab", ToolTier.FUNDAMENTAL, False, False)

        # Advanced - requires advanced writes
        check_tool_authorization("lab", "lab", ToolTier.ADVANCED, True, False)

        # Professional - requires professional workflows
        check_tool_authorization("lab", "lab", ToolTier.PROFESSIONAL, True, True)


class TestCheckUserRole:
    """Tests for check_user_role function."""

    def test_read_only_can_execute_fundamental(self) -> None:
        """Test that read_only role can execute fundamental tier tools."""
        check_user_role(
            UserRole.READ_ONLY,
            ToolTier.FUNDAMENTAL,
        )

    def test_read_only_cannot_execute_advanced(self) -> None:
        """Test that read_only role cannot execute advanced tier tools."""
        with pytest.raises(RoleInsufficientError, match="read_only.*cannot execute advanced"):
            check_user_role(
                UserRole.READ_ONLY,
                ToolTier.ADVANCED,
            )

    def test_ops_rw_can_execute_advanced(self) -> None:
        """Test that ops_rw role can execute advanced tier tools."""
        check_user_role(
            UserRole.OPS_RW,
            ToolTier.ADVANCED,
        )

    def test_ops_rw_cannot_execute_professional(self) -> None:
        """Test that ops_rw role cannot execute professional tier tools."""
        with pytest.raises(RoleInsufficientError, match="ops_rw.*cannot execute professional"):
            check_user_role(
                UserRole.OPS_RW,
                ToolTier.PROFESSIONAL,
            )

    def test_admin_can_execute_professional(self) -> None:
        """Test that admin role can execute professional tier tools."""
        check_user_role(
            UserRole.ADMIN,
            ToolTier.PROFESSIONAL,
        )

    def test_approver_cannot_execute_any_tools(self) -> None:
        """Test that approver role cannot execute any tools."""
        with pytest.raises(RoleInsufficientError, match="approver.*cannot execute tools"):
            check_user_role(
                UserRole.APPROVER,
                ToolTier.FUNDAMENTAL,
            )


class TestToolTierEnum:
    """Tests for ToolTier enum."""

    def test_tier_values(self) -> None:
        """Test that tier values are correct."""
        assert ToolTier.FUNDAMENTAL.value == "fundamental"
        assert ToolTier.ADVANCED.value == "advanced"
        assert ToolTier.PROFESSIONAL.value == "professional"

    def test_tier_comparison(self) -> None:
        """Test that tiers can be compared."""
        assert ToolTier.FUNDAMENTAL == ToolTier.FUNDAMENTAL
        assert ToolTier.ADVANCED != ToolTier.FUNDAMENTAL


class TestUserRoleEnum:
    """Tests for UserRole enum."""

    def test_role_values(self) -> None:
        """Test that role values are correct."""
        assert UserRole.READ_ONLY.value == "read_only"
        assert UserRole.OPS_RW.value == "ops_rw"
        assert UserRole.ADMIN.value == "admin"
