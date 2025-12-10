"""Authorization helpers for role-based and device-based access control.

This module provides authorization decision logic for:
- Device capability checks (environment, tier flags)
- Tool tier enforcement (fundamental/advanced/professional)
- Phase 1: Device-level authorization only
- Phase 4: Add user role checks and device scoping

Key principles:
- All authorization is server-side (never trust client)
- Device capability flags control tool access per device
- Environment isolation prevents cross-environment operations
- Fail-safe: deny by default, explicit allow required

See docs/02-security-oauth-integration-and-access-control.md for details.
"""

import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ToolTier(str, Enum):
    """MCP tool tier classification.

    Fundamental: Read-only operations, always allowed
    Advanced: Low-risk writes, requires device flag
    Professional: High-risk/multi-device, requires device flag + approval
    """

    FUNDAMENTAL = "fundamental"
    ADVANCED = "advanced"
    PROFESSIONAL = "professional"


class AuthorizationError(Exception):
    """Base exception for authorization failures."""

    pass


class EnvironmentMismatchError(AuthorizationError):
    """Raised when device environment doesn't match service environment."""

    pass


class CapabilityDeniedError(AuthorizationError):
    """Raised when device doesn't have required capability flag."""

    pass


class TierRestrictedError(AuthorizationError):
    """Raised when tool tier is not allowed for device."""

    pass


def check_environment_match(
    device_environment: str,
    service_environment: str,
    device_id: str | None = None,
) -> None:
    """Check that device environment matches service environment.

    Args:
        device_environment: Device's configured environment (lab/staging/prod)
        service_environment: Service's deployment environment
        device_id: Optional device ID for error messages

    Raises:
        EnvironmentMismatchError: If environments don't match

    Example:
        check_environment_match(device.environment, settings.environment, device.id)
    """
    if device_environment != service_environment:
        device_info = f" (device: {device_id})" if device_id else ""
        raise EnvironmentMismatchError(
            f"Environment mismatch{device_info}: device is in '{device_environment}' "
            f"but service is running in '{service_environment}'. "
            "Cross-environment operations are not allowed."
        )

    logger.debug(
        f"Environment check passed: {device_environment}",
        extra={"device_id": device_id, "environment": device_environment},
    )


def check_device_capability(
    tool_tier: ToolTier,
    allow_advanced_writes: bool,
    allow_professional_workflows: bool,
    device_id: str | None = None,
    tool_name: str | None = None,
) -> None:
    """Check that device has required capability for tool tier.

    Args:
        tool_tier: Tool's tier classification
        allow_advanced_writes: Device's advanced writes capability flag
        allow_professional_workflows: Device's professional workflows capability flag
        device_id: Optional device ID for error messages
        tool_name: Optional tool name for error messages

    Raises:
        CapabilityDeniedError: If device doesn't have required capability

    Example:
        check_device_capability(
            ToolTier.ADVANCED,
            device.allow_advanced_writes,
            device.allow_professional_workflows,
            device.id,
            "dns/update-servers"
        )
    """
    device_info = f" device {device_id}" if device_id else ""
    tool_info = f" (tool: {tool_name})" if tool_name else ""

    if tool_tier == ToolTier.FUNDAMENTAL:
        # Always allowed
        logger.debug(f"Fundamental tier tool allowed{tool_info}")
        return

    elif tool_tier == ToolTier.ADVANCED:
        if not allow_advanced_writes:
            raise CapabilityDeniedError(
                f"Advanced tier tool{tool_info} not allowed on{device_info}. "
                f"Device capability 'allow_advanced_writes' is disabled. "
                "Enable this flag to allow advanced tier operations."
            )
        logger.debug(f"Advanced tier tool allowed{tool_info} on{device_info}")

    elif tool_tier == ToolTier.PROFESSIONAL:
        if not allow_professional_workflows:
            raise CapabilityDeniedError(
                f"Professional tier tool{tool_info} not allowed on{device_info}. "
                f"Device capability 'allow_professional_workflows' is disabled. "
                "Enable this flag to allow professional tier operations."
            )
        logger.debug(f"Professional tier tool allowed{tool_info} on{device_info}")

    else:
        raise ValueError(f"Unknown tool tier: {tool_tier}")


def check_tool_authorization(
    device_environment: str,
    service_environment: str,
    tool_tier: ToolTier,
    allow_advanced_writes: bool,
    allow_professional_workflows: bool,
    device_id: str | None = None,
    tool_name: str | None = None,
) -> None:
    """Comprehensive authorization check for tool execution on device.

    Combines environment and capability checks into single call.

    Args:
        device_environment: Device's environment
        service_environment: Service's environment
        tool_tier: Tool's tier classification
        allow_advanced_writes: Device's advanced writes flag
        allow_professional_workflows: Device's professional workflows flag
        device_id: Optional device ID for error messages
        tool_name: Optional tool name for error messages

    Raises:
        EnvironmentMismatchError: If environment mismatch
        CapabilityDeniedError: If capability not allowed
        TierRestrictedError: If tier not allowed

    Example:
        check_tool_authorization(
            device.environment,
            settings.environment,
            ToolTier.ADVANCED,
            device.allow_advanced_writes,
            device.allow_professional_workflows,
            device.id,
            "dns/update-servers"
        )
    """
    # Check 1: Environment match
    check_environment_match(device_environment, service_environment, device_id)

    # Check 2: Device capability for tool tier
    check_device_capability(
        tool_tier,
        allow_advanced_writes,
        allow_professional_workflows,
        device_id,
        tool_name,
    )

    logger.info(
        f"Authorization check passed for tool{' ' + tool_name if tool_name else ''}",
        extra={
            "device_id": device_id,
            "tool_name": tool_name,
            "tool_tier": tool_tier.value,
            "environment": device_environment,
        },
    )


# Phase 4: User role checks (placeholder for future implementation)
class UserRole(str, Enum):
    """User role classification for Phase 4.

    Phase 1: Not implemented (single-user OS-level auth)
    Phase 4: OAuth/OIDC integration with role-based access control
    """

    READ_ONLY = "read_only"
    OPS_RW = "ops_rw"
    ADMIN = "admin"


def check_user_role(
    user_role: UserRole,
    required_role: UserRole,
    user_sub: str | None = None,
) -> None:
    """Check that user has required role (Phase 4 only).

    Args:
        user_role: User's current role
        required_role: Minimum required role
        user_sub: Optional user subject for error messages

    Raises:
        AuthorizationError: If user doesn't have required role

    Note:
        Phase 1: Not implemented (raises NotImplementedError)
        Phase 4: Enforces role-based access control
    """
    raise NotImplementedError(
        "User role checks not implemented in Phase 1. "
        "Phase 1 uses OS-level authentication with implicit admin role. "
        "User role enforcement will be added in Phase 4 with OAuth/OIDC integration."
    )
