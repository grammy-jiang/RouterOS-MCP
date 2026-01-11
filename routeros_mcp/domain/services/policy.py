"""Policy engine for enforcing organizational policies and validation rules.

This module implements a policy engine that validates user actions against
role/scope restrictions and enforces governance rules. It provides:

- Tier validation: Ensures users can only perform operations within their role tier
- Self-approval prevention: Blocks users from approving their own requests
- Device scope enforcement: Validates device access permissions
- Admin override capability: Allows admins to override with audit trail

See Phase 5 #12 requirements for detailed specifications.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.infra.db.models import AuditEvent as AuditEventModel
from routeros_mcp.security.authz import ToolTier, UserRole, _TIER_HIERARCHY

logger = logging.getLogger(__name__)


class PolicyViolation(Exception):
    """Base exception for policy violations."""

    pass


class TierPolicyViolation(PolicyViolation):
    """Raised when user role tier is insufficient for operation."""

    pass


class SelfApprovalPolicyViolation(PolicyViolation):
    """Raised when user attempts to approve their own request."""

    pass


class DeviceScopePolicyViolation(PolicyViolation):
    """Raised when device is not in user's allowed scope."""

    pass


class PolicyEngine:
    """Policy engine for validating user actions and enforcing governance rules.

    The policy engine provides centralized policy validation with support for:
    - Role-based tier restrictions (read_only, ops_rw, admin)
    - Self-approval prevention for separation of duties
    - Device scope enforcement for access control
    - Admin override with comprehensive audit logging

    Example:
        async with get_session() as session:
            engine = PolicyEngine(session)

            # Validate tier access
            await engine.validate_tier_access(
                user_role=UserRole.READ_ONLY,
                operation="plan_create",
                user_sub="user-123"
            )

            # Validate approval request
            await engine.validate_approval(
                requester_sub="user-123",
                approver_sub="user-456"
            )

            # Admin override with audit
            await engine.admin_override(
                admin_sub="admin-001",
                policy_type="tier_restriction",
                reason="Emergency fix required",
                context={"device_id": "dev-prod-01"}
            )
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize policy engine.

        Args:
            session: Database session for audit logging
        """
        self.session = session

    async def validate_tier_access(
        self,
        user_role: UserRole,
        operation: str,
        user_sub: str | None = None,
    ) -> None:
        """Validate that user's role tier allows the requested operation.

        Enforces tier-based access control:
        - READ_ONLY: Can only perform read operations (cannot plan/execute changes)
        - OPS_RW: Can perform single-device writes and create plans
        - ADMIN: Full access to all operations
        - APPROVER: Can approve plans but cannot execute operations

        Args:
            user_role: User's current role
            operation: Operation being attempted (e.g., "plan_create", "plan_execute")
            user_sub: Optional user subject for audit logging
            context: Optional context dict for audit logging

        Raises:
            TierPolicyViolation: If user role is insufficient for operation

        Example:
            await engine.validate_tier_access(
                user_role=UserRole.READ_ONLY,
                operation="plan_create",
                user_sub="user-123"
            )  # Raises TierPolicyViolation
        """
        # Define operations that require write access (ops_rw or higher)
        write_operations = {
            "plan_create",
            "plan_execute",
            "device_write",
            "config_change",
        }

        # Define operations that require admin access
        admin_operations = {
            "multi_device_plan",
            "professional_tier_operation",
        }

        user_info = f" (user: {user_sub})" if user_sub else ""
        operation_info = f"'{operation}'"

        # Check if read-only user is attempting write operation
        if user_role == UserRole.READ_ONLY and (
            operation in write_operations or operation in admin_operations
        ):
            logger.warning(
                f"Tier policy violation: read_only user{user_info} attempted {operation}",
                extra={
                    "user_sub": user_sub,
                    "user_role": user_role.value,
                    "operation": operation,
                    "policy_type": "tier_restriction",
                },
            )
            raise TierPolicyViolation(
                f"Role 'read_only'{user_info} cannot perform operation {operation_info}. "
                f"Read-only users can only perform read operations. "
                "Contact an administrator to request elevated privileges."
            )

        # Check if ops_rw user is attempting admin operation
        if user_role == UserRole.OPS_RW and operation in admin_operations:
            logger.warning(
                f"Tier policy violation: ops_rw user{user_info} attempted {operation}",
                extra={
                    "user_sub": user_sub,
                    "user_role": user_role.value,
                    "operation": operation,
                    "policy_type": "tier_restriction",
                },
            )
            raise TierPolicyViolation(
                f"Role 'ops_rw'{user_info} cannot perform operation {operation_info}. "
                f"This operation requires admin privileges. "
                "Contact an administrator to request elevated privileges."
            )

        # Check if approver is attempting to execute operations
        if user_role == UserRole.APPROVER and (
            operation in write_operations or operation in admin_operations
        ):
            logger.warning(
                f"Tier policy violation: approver{user_info} attempted {operation}",
                extra={
                    "user_sub": user_sub,
                    "user_role": user_role.value,
                    "operation": operation,
                    "policy_type": "tier_restriction",
                },
            )
            raise TierPolicyViolation(
                f"Role 'approver'{user_info} cannot execute operations. "
                f"Approvers can only approve plans but cannot execute {operation_info}. "
                "Use an ops_rw or admin account to execute operations."
            )

        logger.debug(
            f"Tier policy check passed: {user_role.value} can perform {operation}",
            extra={
                "user_sub": user_sub,
                "user_role": user_role.value,
                "operation": operation,
            },
        )

    async def validate_approval(
        self,
        requester_sub: str,
        approver_sub: str,
        approval_request_id: str | None = None,
        plan_id: str | None = None,
    ) -> None:
        """Validate that approver is not the same as requester (self-approval prevention).

        Enforces separation of duties by preventing users from approving their
        own requests. This is a critical security control for change management.

        Args:
            requester_sub: User subject who created the request
            approver_sub: User subject attempting to approve
            approval_request_id: Optional approval request ID for audit logging
            plan_id: Optional plan ID for audit logging

        Raises:
            SelfApprovalPolicyViolation: If requester and approver are the same

        Example:
            await engine.validate_approval(
                requester_sub="user-123",
                approver_sub="user-123"  # Same user
            )  # Raises SelfApprovalPolicyViolation
        """
        if requester_sub == approver_sub:
            logger.warning(
                f"Self-approval policy violation: user {requester_sub} attempted to approve own request",
                extra={
                    "user_sub": requester_sub,
                    "approval_request_id": approval_request_id,
                    "plan_id": plan_id,
                    "policy_type": "self_approval_prevention",
                },
            )
            raise SelfApprovalPolicyViolation(
                f"Users cannot approve their own requests (user: {requester_sub}). "
                "Self-approval is not permitted to maintain separation of duties. "
                "Another user must approve this request."
            )

        logger.debug(
            f"Self-approval policy check passed: requester {requester_sub} != approver {approver_sub}",
            extra={
                "requester_sub": requester_sub,
                "approver_sub": approver_sub,
                "approval_request_id": approval_request_id,
                "plan_id": plan_id,
            },
        )

    async def validate_device_scope(
        self,
        device_id: str,
        device_scopes: list[str] | None,
        user_sub: str | None = None,
        user_role: UserRole | None = None,
    ) -> None:
        """Validate that device is in user's allowed device scope.

        Enforces device-level access control by checking if the requested device
        is in the user's permitted scope. Admin users and users with no scope
        restrictions have full access.

        Args:
            device_id: Device ID being accessed
            device_scopes: User's allowed device IDs (None or empty = full access)
            user_sub: Optional user subject for audit logging
            user_role: Optional user role for audit logging

        Raises:
            DeviceScopePolicyViolation: If device is not in user's scope

        Example:
            await engine.validate_device_scope(
                device_id="dev-prod-01",
                device_scopes=["dev-lab-01", "dev-staging-01"],
                user_sub="user-123"
            )  # Raises DeviceScopePolicyViolation
        """
        # None or empty list means full access (typically for admins)
        if device_scopes is None or len(device_scopes) == 0:
            logger.debug(
                "Device scope policy check passed: user has full access",
                extra={
                    "user_sub": user_sub,
                    "user_role": user_role.value if user_role else None,
                    "device_id": device_id,
                },
            )
            return

        # Check if device is in scope
        if device_id not in device_scopes:
            user_info = f" (user: {user_sub})" if user_sub else ""
            device_list = ", ".join(device_scopes[:5])
            more_indicator = "..." if len(device_scopes) > 5 else ""

            logger.warning(
                f"Device scope policy violation: user{user_info} attempted access to out-of-scope device",
                extra={
                    "user_sub": user_sub,
                    "user_role": user_role.value if user_role else None,
                    "device_id": device_id,
                    "device_scope_count": len(device_scopes),
                    "policy_type": "device_scope_restriction",
                },
            )

            raise DeviceScopePolicyViolation(
                f"Device '{device_id}' is not in allowed scope{user_info}. "
                f"User has access to {len(device_scopes)} device(s): {device_list}{more_indicator}. "
                "Contact an administrator to request access to this device."
            )

        logger.debug(
            "Device scope policy check passed: device in user's scope",
            extra={
                "user_sub": user_sub,
                "user_role": user_role.value if user_role else None,
                "device_id": device_id,
                "device_scope_count": len(device_scopes),
            },
        )

    async def admin_override(
        self,
        admin_sub: str,
        policy_type: str,
        reason: str,
        context: dict[str, Any] | None = None,
        admin_email: str | None = None,
    ) -> str:
        """Record an admin override of a policy restriction with audit trail.

        Allows admins to override policy restrictions in exceptional circumstances
        while maintaining a comprehensive audit trail. This should be used sparingly
        and only with proper justification.

        Args:
            admin_sub: Admin user subject performing override
            policy_type: Type of policy being overridden (e.g., "tier_restriction")
            reason: Justification for override (required, non-empty)
            context: Optional context dict with additional details
            admin_email: Optional admin email for audit logging

        Returns:
            Audit event ID for the override

        Raises:
            ValueError: If reason is empty or policy_type is invalid

        Example:
            audit_id = await engine.admin_override(
                admin_sub="admin-001",
                policy_type="tier_restriction",
                reason="Emergency fix required for production outage",
                context={"device_id": "dev-prod-01", "operation": "plan_execute"}
            )
        """
        if not reason or not reason.strip():
            raise ValueError("Admin override requires a non-empty reason")

        valid_policy_types = {
            "tier_restriction",
            "self_approval_prevention",
            "device_scope_restriction",
            "rate_limit",
            "time_window",
        }

        if policy_type not in valid_policy_types:
            raise ValueError(
                f"Invalid policy_type '{policy_type}'. "
                f"Valid types: {', '.join(sorted(valid_policy_types))}"
            )

        # Create audit event for override
        audit_event = AuditEventModel(
            id=f"audit-{uuid.uuid4().hex[:16]}",
            timestamp=datetime.now(UTC),
            user_sub=admin_sub,
            user_email=admin_email,
            user_role="admin",  # Admins can override policies
            action="POLICY_OVERRIDE",
            tool_name="policy_engine",
            tool_tier="professional",  # Policy overrides are admin-level operations
            result="SUCCESS",
            meta={
                "policy_type": policy_type,
                "reason": reason,
                "context": context or {},
            },
        )

        self.session.add(audit_event)
        await self.session.commit()

        logger.warning(
            f"Admin override: {admin_sub} overrode {policy_type} policy",
            extra={
                "admin_sub": admin_sub,
                "admin_email": admin_email,
                "policy_type": policy_type,
                "reason": reason,
                "context": context,
                "audit_event_id": audit_event.id,
            },
        )

        return audit_event.id

    async def validate_tool_tier_access(
        self,
        user_role: UserRole,
        tool_tier: ToolTier,
        user_sub: str | None = None,
        tool_name: str | None = None,
    ) -> None:
        """Validate that user role allows access to tool tier.

        This is a convenience method that wraps the tier hierarchy check
        from the authz module with policy engine semantics.

        Args:
            user_role: User's current role
            tool_tier: Tool's tier classification
            user_sub: Optional user subject for audit logging
            tool_name: Optional tool name for audit logging

        Raises:
            TierPolicyViolation: If user role is insufficient for tool tier

        Example:
            await engine.validate_tool_tier_access(
                user_role=UserRole.READ_ONLY,
                tool_tier=ToolTier.ADVANCED,
                user_sub="user-123"
            )  # Raises TierPolicyViolation
        """
        from routeros_mcp.security.authz import get_allowed_tool_tier

        allowed_tier = get_allowed_tool_tier(user_role)

        # Approvers cannot execute any tools
        if allowed_tier is None:
            user_info = f" (user: {user_sub})" if user_sub else ""
            tool_info = f" '{tool_name}'" if tool_name else ""
            logger.warning(
                f"Tier policy violation: approver{user_info} attempted to execute tool",
                extra={
                    "user_sub": user_sub,
                    "user_role": user_role.value,
                    "tool_tier": tool_tier.value,
                    "tool_name": tool_name,
                    "policy_type": "tier_restriction",
                },
            )
            raise TierPolicyViolation(
                f"Role 'approver'{user_info} cannot execute tools{tool_info}. "
                "Approvers can only approve plans but not execute operations."
            )

        # Check if tool tier exceeds user's allowed tier
        if _TIER_HIERARCHY[tool_tier.value] > _TIER_HIERARCHY[allowed_tier.value]:
            user_info = f" (user: {user_sub})" if user_sub else ""
            tool_info = f" '{tool_name}'" if tool_name else ""
            logger.warning(
                f"Tier policy violation: {user_role.value}{user_info} attempted {tool_tier.value} tier tool",
                extra={
                    "user_sub": user_sub,
                    "user_role": user_role.value,
                    "tool_tier": tool_tier.value,
                    "tool_name": tool_name,
                    "policy_type": "tier_restriction",
                },
            )
            raise TierPolicyViolation(
                f"Role '{user_role.value}'{user_info} cannot execute {tool_tier.value} tier tools{tool_info}. "
                f"Maximum allowed tier is {allowed_tier.value}. "
                "Contact an administrator to request elevated privileges."
            )

        logger.debug(
            f"Tool tier policy check passed: {user_role.value} can execute {tool_tier.value} tier",
            extra={
                "user_sub": user_sub,
                "user_role": user_role.value,
                "tool_tier": tool_tier.value,
                "tool_name": tool_name,
            },
        )
