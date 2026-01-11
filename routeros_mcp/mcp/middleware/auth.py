"""Authorization middleware for MCP tool execution.

This module provides per-tool authorization enforcement that validates:
- User role vs tool tier (read_only/ops_rw/admin/approver)
- Device scope (user's allowed devices)
- Environment isolation (lab/staging/prod)
- Device capability flags (advanced writes, professional workflows)

All authorization decisions are logged for audit and compliance.

See docs/02-security-oauth-integration-and-access-control.md for design.
"""

import logging

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import DatabaseSessionManager
from routeros_mcp.mcp.errors import (
    AuthorizationError as MCPAuthorizationError,
    DeviceNotFoundError,
)
from routeros_mcp.security.auth import User
from routeros_mcp.security.authz import (
    CapabilityDeniedError,
    DeviceScopeError,
    EnvironmentMismatchError,
    RoleInsufficientError,
    ToolTier,
    UserRole,
    check_comprehensive_authorization,
)

logger = logging.getLogger(__name__)


class AuthorizationMiddleware:
    """Middleware for per-tool authorization enforcement.

    Validates user permissions before tool execution and logs all
    authorization decisions (allow/deny) for audit compliance.

    Example:
        middleware = AuthorizationMiddleware(session_factory, settings)
        await middleware.check_authorization(
            user=user,
            tool_name="dns/update-servers",
            tool_tier=ToolTier.ADVANCED,
            device_id="dev-lab-01"
        )
    """

    def __init__(
        self,
        session_factory: DatabaseSessionManager,
        settings: Settings,
    ) -> None:
        """Initialize authorization middleware.

        Args:
            session_factory: Database session factory
            settings: Application settings
        """
        self.session_factory = session_factory
        self.settings = settings

    async def check_authorization(
        self,
        user: User,
        tool_name: str,
        tool_tier: ToolTier,
        device_id: str,
    ) -> None:
        """Check if user is authorized to execute tool on device.

        Args:
            user: Authenticated user
            tool_name: Tool name (e.g., "dns/update-servers")
            tool_tier: Tool tier (fundamental/advanced/professional)
            device_id: Target device ID

        Raises:
            RoleInsufficientError: If user role is insufficient (403)
            DeviceScopeError: If device not in user's scope (403)
            EnvironmentMismatchError: If environment mismatch (403)
            CapabilityDeniedError: If device capability not allowed (403)
            AuthorizationError: For other authorization failures (403)

        Example:
            try:
                await middleware.check_authorization(
                    user=user,
                    tool_name="dns/update-servers",
                    tool_tier=ToolTier.ADVANCED,
                    device_id="dev-lab-01"
                )
            except AuthorizationError as e:
                # Tool execution blocked with 403
                logger.error(f"Authorization denied: {e}")
        """
        # Convert user role string to enum
        try:
            user_role = UserRole(user.role)
        except ValueError as e:
            logger.error(
                "Invalid user role",
                extra={
                    "user_sub": user.sub,
                    "user_role": user.role,
                    "tool_name": tool_name,
                    "device_id": device_id,
                },
            )
            raise MCPAuthorizationError(
                f"Invalid user role '{user.role}'. "
                f"Valid roles: {', '.join([r.value for r in UserRole])}"
            ) from e

        # Fetch device from database
        try:
            async with self.session_factory.session() as session:
                device_service = DeviceService(session, self.settings)
                device = await device_service.get_device(device_id)
        except DeviceNotFoundError:
            # Log device not found as authorization failure
            logger.warning(
                "Authorization denied: device not found",
                extra={
                    "user_sub": user.sub,
                    "user_role": user.role,
                    "tool_name": tool_name,
                    "device_id": device_id,
                    "decision": "DENY",
                    "reason": "DeviceNotFoundError",
                },
            )
            # Re-raise as-is since it's already an MCPError
            raise

        # Log authorization attempt
        logger.info(
            "Checking authorization",
            extra={
                "user_sub": user.sub,
                "user_role": user.role,
                "user_email": user.email,
                "tool_name": tool_name,
                "tool_tier": tool_tier.value,
                "device_id": device_id,
                "device_environment": device.environment,
            },
        )

        try:
            # Perform comprehensive authorization check
            check_comprehensive_authorization(
                user_role=user_role,
                device_id=device_id,
                device_environment=device.environment,
                service_environment=self.settings.environment,
                tool_tier=tool_tier,
                allow_advanced_writes=device.allow_advanced_writes,
                allow_professional_workflows=device.allow_professional_workflows,
                device_scopes=user.device_scope,
                user_sub=user.sub,
                tool_name=tool_name,
            )

            # Log successful authorization
            logger.info(
                "Authorization granted",
                extra={
                    "user_sub": user.sub,
                    "user_role": user.role,
                    "tool_name": tool_name,
                    "tool_tier": tool_tier.value,
                    "device_id": device_id,
                    "decision": "ALLOW",
                },
            )

        except (
            RoleInsufficientError,
            DeviceScopeError,
            EnvironmentMismatchError,
            CapabilityDeniedError,
        ) as e:
            # Log denied authorization with context
            log_extra = {
                "user_sub": user.sub,
                "user_role": user.role,
                "user_email": user.email,
                "tool_name": tool_name,
                "tool_tier": tool_tier.value,
                "device_id": device_id,
                "decision": "DENY",
                "reason": type(e).__name__,
                "denial_message": str(e),
            }
            # Add device_environment if device was fetched successfully
            if "device" in locals():
                log_extra["device_environment"] = device.environment

            logger.warning("Authorization denied", extra=log_extra)
            # Convert to MCPError for proper JSON-RPC handling
            raise MCPAuthorizationError(str(e)) from e

    async def check_authorization_batch(
        self,
        user: User,
        tool_name: str,
        tool_tier: ToolTier,
        device_ids: list[str],
    ) -> dict[str, str | None]:
        """Check authorization for multiple devices (batch operations).

        Args:
            user: Authenticated user
            tool_name: Tool name
            tool_tier: Tool tier
            device_ids: List of device IDs to check

        Returns:
            Dictionary mapping device_id to error message (None if authorized)

        Example:
            results = await middleware.check_authorization_batch(
                user=user,
                tool_name="system/reboot",
                tool_tier=ToolTier.PROFESSIONAL,
                device_ids=["dev-1", "dev-2", "dev-3"]
            )
            # Returns: {"dev-1": None, "dev-2": "Device not in scope", "dev-3": None}
        """
        results: dict[str, str | None] = {}

        for device_id in device_ids:
            try:
                await self.check_authorization(
                    user=user,
                    tool_name=tool_name,
                    tool_tier=tool_tier,
                    device_id=device_id,
                )
                results[device_id] = None  # Authorized
            except (MCPAuthorizationError, DeviceNotFoundError) as e:
                # Handle authorization failures and device not found
                results[device_id] = str(e)
            except Exception as e:
                # Handle unexpected errors gracefully
                logger.exception(
                    "Unexpected error during batch authorization",
                    extra={
                        "device_id": device_id,
                        "tool_name": tool_name,
                        "user_sub": user.sub,
                    },
                )
                results[device_id] = f"Unexpected error: {str(e)}"

        return results


def create_authorization_middleware(
    session_factory: DatabaseSessionManager,
    settings: Settings,
) -> AuthorizationMiddleware:
    """Factory function to create authorization middleware.

    Args:
        session_factory: Database session factory
        settings: Application settings

    Returns:
        Configured authorization middleware instance

    Example:
        middleware = create_authorization_middleware(session_factory, settings)
    """
    return AuthorizationMiddleware(session_factory, settings)
