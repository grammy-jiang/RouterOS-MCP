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


# Phase 5: User role checks and RBAC
class UserRole(str, Enum):
    """User role classification for RBAC.

    Roles define hierarchical access to tool tiers:
    - READ_ONLY: Fundamental tier only (read-only operations)
    - OPS_RW: Fundamental + Advanced tier (single-device writes)
    - ADMIN: All tiers including Professional (multi-device operations)
    - APPROVER: Can approve plans but cannot execute tools
    """

    READ_ONLY = "read_only"
    OPS_RW = "ops_rw"
    ADMIN = "admin"
    APPROVER = "approver"


class RoleInsufficientError(AuthorizationError):
    """Raised when user role is insufficient for operation."""

    pass


class DeviceScopeError(AuthorizationError):
    """Raised when device is not in user's allowed device scope."""

    pass


def get_allowed_tool_tier(user_role: UserRole) -> ToolTier:
    """Get the maximum allowed tool tier for a user role.

    Args:
        user_role: User's role

    Returns:
        Maximum tool tier allowed for the role

    Example:
        tier = get_allowed_tool_tier(UserRole.OPS_RW)
        # Returns ToolTier.ADVANCED
    """
    role_tier_map = {
        UserRole.READ_ONLY: ToolTier.FUNDAMENTAL,
        UserRole.OPS_RW: ToolTier.ADVANCED,
        UserRole.ADMIN: ToolTier.PROFESSIONAL,
        UserRole.APPROVER: None,  # Approvers cannot execute tools
    }
    return role_tier_map.get(user_role)


def check_user_role(
    user_role: UserRole,
    tool_tier: ToolTier,
    user_sub: str | None = None,
    tool_name: str | None = None,
) -> None:
    """Check that user role is sufficient for tool tier.

    Args:
        user_role: User's current role
        tool_tier: Tool's tier classification
        user_sub: Optional user subject for error messages
        tool_name: Optional tool name for error messages

    Raises:
        RoleInsufficientError: If user role is insufficient for tool tier

    Example:
        check_user_role(
            UserRole.READ_ONLY,
            ToolTier.ADVANCED,
            "user-123",
            "dns/update-servers"
        )  # Raises RoleInsufficientError
    """
    allowed_tier = get_allowed_tool_tier(user_role)

    # Approvers cannot execute any tools
    if allowed_tier is None:
        user_info = f" (user: {user_sub})" if user_sub else ""
        tool_info = f" '{tool_name}'" if tool_name else ""
        raise RoleInsufficientError(
            f"Role 'approver'{user_info} cannot execute tools{tool_info}. "
            f"Approvers can only approve plans but not execute operations."
        )

    # Check if tool tier exceeds user's allowed tier
    tier_hierarchy = {
        ToolTier.FUNDAMENTAL: 1,
        ToolTier.ADVANCED: 2,
        ToolTier.PROFESSIONAL: 3,
    }

    if tier_hierarchy[tool_tier] > tier_hierarchy[allowed_tier]:
        user_info = f" (user: {user_sub})" if user_sub else ""
        tool_info = f" '{tool_name}'" if tool_name else ""
        raise RoleInsufficientError(
            f"Role '{user_role.value}'{user_info} cannot execute {tool_tier.value} tier tools{tool_info}. "
            f"Maximum allowed tier is {allowed_tier.value}. "
            f"Contact an administrator to request elevated privileges."
        )

    logger.debug(
        f"User role check passed: {user_role.value} can execute {tool_tier.value} tier",
        extra={
            "user_sub": user_sub,
            "user_role": user_role.value,
            "tool_tier": tool_tier.value,
            "tool_name": tool_name,
        },
    )


def check_device_scope(
    device_id: str,
    device_scopes: list[str] | None,
    user_sub: str | None = None,
) -> None:
    """Check that device is in user's allowed device scope.

    Args:
        device_id: Device ID to check
        device_scopes: User's allowed device IDs (None or empty = full access)
        user_sub: Optional user subject for error messages

    Raises:
        DeviceScopeError: If device is not in user's scope

    Example:
        check_device_scope(
            "dev-prod-01",
            ["dev-lab-01", "dev-staging-01"],
            "user-123"
        )  # Raises DeviceScopeError
    """
    # None or empty list means full access (typically for admins)
    if device_scopes is None or len(device_scopes) == 0:
        logger.debug(
            f"Device scope check passed: user has full access",
            extra={"user_sub": user_sub, "device_id": device_id},
        )
        return

    # Check if device is in scope
    if device_id not in device_scopes:
        user_info = f" (user: {user_sub})" if user_sub else ""
        raise DeviceScopeError(
            f"Device '{device_id}' is not in allowed scope{user_info}. "
            f"User has access to {len(device_scopes)} device(s): {', '.join(device_scopes[:5])}"
            f"{'...' if len(device_scopes) > 5 else ''}. "
            f"Contact an administrator to request access to this device."
        )

    logger.debug(
        f"Device scope check passed: device in user's scope",
        extra={
            "user_sub": user_sub,
            "device_id": device_id,
            "device_scope_count": len(device_scopes),
        },
    )


def check_comprehensive_authorization(
    user_role: UserRole,
    device_id: str,
    device_environment: str,
    service_environment: str,
    tool_tier: ToolTier,
    allow_advanced_writes: bool,
    allow_professional_workflows: bool,
    device_scopes: list[str] | None = None,
    user_sub: str | None = None,
    tool_name: str | None = None,
) -> None:
    """Comprehensive authorization check combining all authorization layers.

    Performs authorization checks in the following order:
    1. User role vs tool tier
    2. Device scope (if restricted)
    3. Environment match
    4. Device capability flags

    Args:
        user_role: User's role
        device_id: Device ID
        device_environment: Device's environment
        service_environment: Service's environment
        tool_tier: Tool's tier classification
        allow_advanced_writes: Device's advanced writes flag
        allow_professional_workflows: Device's professional workflows flag
        device_scopes: User's allowed device IDs (None = full access)
        user_sub: Optional user subject for error messages
        tool_name: Optional tool name for error messages

    Raises:
        RoleInsufficientError: If user role is insufficient
        DeviceScopeError: If device not in user's scope
        EnvironmentMismatchError: If environment mismatch
        CapabilityDeniedError: If device capability not allowed

    Example:
        check_comprehensive_authorization(
            user_role=UserRole.OPS_RW,
            device_id="dev-lab-01",
            device_environment="lab",
            service_environment="lab",
            tool_tier=ToolTier.ADVANCED,
            allow_advanced_writes=True,
            allow_professional_workflows=False,
            device_scopes=["dev-lab-01", "dev-lab-02"],
            user_sub="user-123",
            tool_name="dns/update-servers"
        )
    """
    # Check 1: User role vs tool tier
    check_user_role(user_role, tool_tier, user_sub, tool_name)

    # Check 2: Device scope
    check_device_scope(device_id, device_scopes, user_sub)

    # Check 3: Environment match
    check_environment_match(device_environment, service_environment, device_id)

    # Check 4: Device capability flags
    check_device_capability(
        tool_tier,
        allow_advanced_writes,
        allow_professional_workflows,
        device_id,
        tool_name,
    )

    logger.info(
        f"Comprehensive authorization check passed",
        extra={
            "user_sub": user_sub,
            "user_role": user_role.value,
            "device_id": device_id,
            "tool_name": tool_name,
            "tool_tier": tool_tier.value,
            "environment": device_environment,
        },
    )
