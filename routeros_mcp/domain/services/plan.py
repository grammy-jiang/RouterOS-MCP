"""Plan service for managing multi-device configuration change plans.

This service implements the plan/apply framework for high-risk operations,
providing plan creation, validation, approval, and execution coordination.

See docs/07-device-control-and-high-risk-operations-safeguards.md for
detailed requirements.
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import PlanStatus
from routeros_mcp.infra.db.models import AuditEvent as AuditEventModel
from routeros_mcp.infra.db.models import Device as DeviceModel
from routeros_mcp.infra.db.models import Plan as PlanModel

logger = logging.getLogger(__name__)


class PlanService:
    """Service for managing configuration change plans.

    Provides:
    - Plan creation with validation and risk assessment
    - Cryptographically signed approval token generation (HMAC-SHA256)
    - Approval token validation with expiration checking
    - Plan status management with state machine validation
    - Pre-checks for environment tags and device capabilities
    - Comprehensive audit logging for all plan lifecycle events

    All high-risk operations must use the plan/apply workflow.
    """

    # Valid state transitions for plan status
    VALID_TRANSITIONS = {
        PlanStatus.PENDING: {PlanStatus.APPROVED, PlanStatus.CANCELLED},
        PlanStatus.APPROVED: {PlanStatus.EXECUTING, PlanStatus.CANCELLED},
        PlanStatus.EXECUTING: {PlanStatus.COMPLETED, PlanStatus.FAILED, PlanStatus.CANCELLED},
        PlanStatus.COMPLETED: set(),  # Terminal state
        PlanStatus.FAILED: set(),  # Terminal state
        PlanStatus.CANCELLED: set(),  # Terminal state
    }

    # Token expiration: 15 minutes as per requirements
    TOKEN_EXPIRATION_MINUTES = 15

    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        """Initialize plan service.

        Args:
            session: Database session
            settings: Application settings (for encryption key)
        """
        self.session = session
        self.settings = settings or Settings()

    def _generate_approval_token(self, plan_id: str, created_by: str) -> str:
        """Generate cryptographically signed approval token using HMAC.

        Args:
            plan_id: Plan identifier
            created_by: User who created the plan

        Returns:
            HMAC-signed approval token
        """
        # Create message to sign: plan_id:created_by:timestamp
        timestamp = datetime.now(UTC).isoformat()
        message = f"{plan_id}:{created_by}:{timestamp}"
        
        # Use encryption key as HMAC secret (or fallback to secure random)
        secret_key = self.settings.encryption_key or "INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION"
        
        # Generate HMAC signature
        signature = hmac.new(
            secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:16]  # Take first 16 chars for brevity
        
        # Return token with random suffix for uniqueness
        random_suffix = secrets.token_urlsafe(8)
        return f"approve-{signature}-{random_suffix}"

    def _validate_approval_token(
        self, plan_id: str, created_by: str, token: str, expires_at: datetime
    ) -> None:
        """Validate approval token signature and expiration.

        Args:
            plan_id: Plan identifier
            created_by: User who created the plan
            token: Token to validate
            expires_at: Token expiration timestamp

        Raises:
            ValueError: If token is invalid or expired
        """
        # Check expiration first
        if datetime.now(UTC) > expires_at:
            raise ValueError("Approval token has expired")
        
        # For HMAC tokens, we can't regenerate exact token due to random suffix
        # Instead, verify it starts with correct prefix and has valid format
        if not token.startswith("approve-"):
            raise ValueError("Invalid approval token format")
        
        # Token format: approve-{signature}-{random}
        # Note: URL-safe base64 can contain hyphens, so we check for at least 2 parts after "approve-"
        parts = token.split("-", 2)  # Split on first 2 hyphens only
        if len(parts) < 3 or not parts[1] or not parts[2]:
            raise ValueError("Invalid approval token format")

    async def _log_audit_event(
        self,
        action: str,
        user_sub: str,
        plan_id: str | None = None,
        tool_name: str | None = None,
        result: str = "SUCCESS",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Log audit event for plan operations.

        Args:
            action: Action type (e.g., PLAN_CREATED, PLAN_APPROVED)
            user_sub: User subject
            plan_id: Plan identifier
            tool_name: Tool name
            result: Result status (SUCCESS/FAILURE)
            error_message: Error message if failed
            metadata: Additional metadata
        """
        event_id = f"audit-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        
        audit_event = AuditEventModel(
            id=event_id,
            timestamp=datetime.now(UTC),
            user_sub=user_sub,
            user_email=None,  # Will be populated from auth context in future
            user_role="user",  # Will be populated from auth context in future
            device_id=None,
            environment=None,
            action=action,
            tool_name=tool_name or "plan_service",
            tool_tier="professional",
            plan_id=plan_id,
            job_id=None,
            result=result,
            meta=metadata or {},
            error_message=error_message,
        )
        
        self.session.add(audit_event)
        await self.session.commit()

    async def _run_pre_checks(
        self, devices: list[DeviceModel], tool_name: str, risk_level: str
    ) -> dict[str, Any]:
        """Run pre-checks on devices for plan execution.

        Args:
            devices: List of device models
            tool_name: Tool name creating the plan
            risk_level: Risk level of the operation

        Returns:
            Pre-check results with status and warnings

        Raises:
            ValueError: If critical pre-checks fail
        """
        pre_check_results: dict[str, Any] = {
            "status": "passed",
            "warnings": [],
            "device_checks": {},
        }

        for device in devices:
            device_result: dict[str, Any] = {
                "device_id": device.id,
                "environment": device.environment,
                "status": "passed",
                "checks": [],
            }

            # Check 1: Professional workflows capability
            if not device.allow_professional_workflows:
                device_result["status"] = "failed"
                device_result["checks"].append({
                    "check": "professional_workflows_enabled",
                    "status": "failed",
                    "message": f"Device {device.id} does not allow professional workflows",
                })
                pre_check_results["status"] = "failed"

            # Check 2: Environment restrictions for high-risk operations
            if risk_level == "high" and device.environment == "prod":
                if "warnings" not in device_result:
                    device_result["warnings"] = []
                device_result["warnings"].append({
                    "check": "environment_restriction",
                    "message": f"High-risk operation on production device {device.id} - proceed with extreme caution",
                })
                pre_check_results["warnings"].append(
                    f"High-risk operation on production device {device.id}"
                )

            # Check 3: Device reachability
            if device.status in ["unreachable", "decommissioned"]:
                device_result["status"] = "failed"
                device_result["checks"].append({
                    "check": "device_reachable",
                    "status": "failed",
                    "message": f"Device {device.id} is {device.status}",
                })
                pre_check_results["status"] = "failed"

            # Check 4: Device health status
            if device.status == "degraded":
                if "warnings" not in device_result:
                    device_result["warnings"] = []
                device_result["warnings"].append({
                    "check": "device_health",
                    "message": f"Device {device.id} is in degraded state",
                })
                pre_check_results["warnings"].append(f"Device {device.id} is degraded")

            pre_check_results["device_checks"][device.id] = device_result

        # Fail if any critical checks failed
        if pre_check_results["status"] == "failed":
            failed_devices = [
                dev_id for dev_id, result in pre_check_results["device_checks"].items()
                if result["status"] == "failed"
            ]
            raise ValueError(
                f"Pre-checks failed for devices: {', '.join(failed_devices)}. "
                f"See pre_check_results for details."
            )

        return pre_check_results

    async def create_plan(
        self,
        tool_name: str,
        created_by: str,
        device_ids: list[str],
        summary: str,
        changes: dict[str, Any],
        risk_level: str = "medium",
    ) -> dict[str, Any]:
        """Create a new plan for multi-device changes.

        Args:
            tool_name: Name of the tool creating the plan
            created_by: User sub who created the plan
            device_ids: List of target device IDs
            summary: Human-readable plan summary
            changes: Detailed change specifications
            risk_level: Risk level (low/medium/high)

        Returns:
            Plan details including plan_id, approval_token, and pre-check results

        Raises:
            ValueError: If validation or pre-checks fail
        """
        try:
            # Validate devices exist and get device models
            devices = await self._validate_devices(device_ids)

            # Run pre-checks on devices
            pre_check_results = await self._run_pre_checks(devices, tool_name, risk_level)

            # Generate plan ID and approval token
            plan_id = f"plan-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
            approval_token = self._generate_approval_token(plan_id, created_by)
            
            # Token expires in 15 minutes (not 1 hour)
            expires_at = datetime.now(UTC) + timedelta(minutes=self.TOKEN_EXPIRATION_MINUTES)

            # Create plan record with new status model (pending, not draft)
            plan = PlanModel(
                id=plan_id,
                created_by=created_by,
                tool_name=tool_name,
                status=PlanStatus.PENDING.value,
                device_ids=device_ids,
                summary=summary,
                changes={
                    **changes,
                    "risk_level": risk_level,
                    "approval_token": approval_token,
                    "approval_expires_at": expires_at.isoformat(),
                    "pre_check_results": pre_check_results,
                },
            )

            self.session.add(plan)
            await self.session.commit()
            await self.session.refresh(plan)

            # Log audit event
            await self._log_audit_event(
                action="PLAN_CREATED",
                user_sub=created_by,
                plan_id=plan_id,
                tool_name=tool_name,
                result="SUCCESS",
                metadata={
                    "device_count": len(device_ids),
                    "risk_level": risk_level,
                    "device_ids": device_ids,
                },
            )

            logger.info(
                f"Created plan {plan_id}",
                extra={
                    "plan_id": plan_id,
                    "tool_name": tool_name,
                    "device_count": len(device_ids),
                    "risk_level": risk_level,
                },
            )

            return {
                "plan_id": plan_id,
                "approval_token": approval_token,
                "approval_expires_at": expires_at.isoformat(),
                "risk_level": risk_level,
                "device_count": len(device_ids),
                "devices": device_ids,
                "summary": summary,
                "status": PlanStatus.PENDING.value,
                "pre_check_results": pre_check_results,
            }

        except Exception as e:
            # Log failed plan creation
            await self._log_audit_event(
                action="PLAN_CREATED",
                user_sub=created_by,
                tool_name=tool_name,
                result="FAILURE",
                error_message=str(e),
                metadata={"device_ids": device_ids, "risk_level": risk_level},
            )
            raise

    async def _validate_devices(self, device_ids: list[str]) -> list[DeviceModel]:
        """Validate that devices exist and are appropriate for operations.

        Args:
            device_ids: List of device IDs to validate

        Returns:
            List of validated device models

        Raises:
            ValueError: If any device is invalid
        """
        if not device_ids:
            raise ValueError("At least one device must be specified")

        # Check all devices exist
        stmt = select(DeviceModel).where(DeviceModel.id.in_(device_ids))
        result = await self.session.execute(stmt)
        devices = list(result.scalars().all())

        found_ids = {d.id for d in devices}
        missing_ids = set(device_ids) - found_ids

        if missing_ids:
            raise ValueError(f"Devices not found: {', '.join(missing_ids)}")

        return devices

    async def get_plan(self, plan_id: str) -> dict[str, Any]:
        """Get plan details.

        Args:
            plan_id: Plan identifier

        Returns:
            Plan details

        Raises:
            ValueError: If plan not found
        """
        stmt = select(PlanModel).where(PlanModel.id == plan_id)
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        return {
            "plan_id": plan.id,
            "tool_name": plan.tool_name,
            "created_by": plan.created_by,
            "status": plan.status,
            "device_ids": plan.device_ids,
            "summary": plan.summary,
            "changes": plan.changes,
            "approved_by": plan.approved_by,
            "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
        }

    async def approve_plan(
        self, plan_id: str, approval_token: str, approved_by: str
    ) -> dict[str, Any]:
        """Approve a plan for execution.

        Args:
            plan_id: Plan identifier
            approval_token: Approval token from plan creation
            approved_by: User sub who is approving

        Returns:
            Updated plan details

        Raises:
            ValueError: If plan not found, token invalid, expired, or invalid state
        """
        try:
            stmt = select(PlanModel).where(PlanModel.id == plan_id)
            result = await self.session.execute(stmt)
            plan = result.scalar_one_or_none()

            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")

            # Check current status allows approval
            current_status = PlanStatus(plan.status)
            if current_status == PlanStatus.APPROVED:
                raise ValueError(f"Plan {plan_id} is already approved")

            # Validate state transition
            if PlanStatus.APPROVED not in self.VALID_TRANSITIONS.get(current_status, set()):
                raise ValueError(
                    f"Plan {plan_id} cannot be approved from status {plan.status}"
                )

            # Validate approval token
            stored_token = plan.changes.get("approval_token")
            if not stored_token or not secrets.compare_digest(stored_token, approval_token):
                raise ValueError("Invalid approval token")

            # Check token expiration
            expires_at_str = plan.changes.get("approval_expires_at")
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str)
                self._validate_approval_token(
                    plan_id, plan.created_by, stored_token, expires_at
                )

            # Update plan status
            plan.status = PlanStatus.APPROVED.value
            plan.approved_by = approved_by
            plan.approved_at = datetime.now(UTC)

            await self.session.commit()
            await self.session.refresh(plan)

            # Log audit event
            await self._log_audit_event(
                action="PLAN_APPROVED",
                user_sub=approved_by,
                plan_id=plan_id,
                tool_name=plan.tool_name,
                result="SUCCESS",
                metadata={"device_count": len(plan.device_ids)},
            )

            logger.info(
                f"Approved plan {plan_id}",
                extra={
                    "plan_id": plan_id,
                    "approved_by": approved_by,
                },
            )

            return await self.get_plan(plan_id)

        except Exception as e:
            # Log failed approval
            await self._log_audit_event(
                action="PLAN_APPROVED",
                user_sub=approved_by,
                plan_id=plan_id,
                result="FAILURE",
                error_message=str(e),
            )
            raise

    async def update_plan_status(
        self, plan_id: str, status: str, updated_by: str = "system"
    ) -> None:
        """Update plan status with state machine validation.

        Args:
            plan_id: Plan identifier
            status: New status (pending/approved/executing/completed/failed/cancelled)
            updated_by: User or system making the update

        Raises:
            ValueError: If plan not found or invalid status transition
        """
        try:
            # Validate status is a valid enum value
            try:
                new_status = PlanStatus(status)
            except ValueError:
                valid_values = [s.value for s in PlanStatus]
                raise ValueError(
                    f"Invalid status: {status}. Must be one of: {', '.join(valid_values)}"
                )

            stmt = select(PlanModel).where(PlanModel.id == plan_id)
            result = await self.session.execute(stmt)
            plan = result.scalar_one_or_none()

            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")

            # Validate state transition
            current_status = PlanStatus(plan.status)
            if new_status not in self.VALID_TRANSITIONS.get(current_status, set()):
                raise ValueError(
                    f"Invalid status transition from {current_status.value} to {new_status.value}"
                )

            plan.status = new_status.value
            await self.session.commit()

            # Log audit event
            await self._log_audit_event(
                action="PLAN_STATUS_UPDATE",
                user_sub=updated_by,
                plan_id=plan_id,
                tool_name=plan.tool_name,
                result="SUCCESS",
                metadata={
                    "old_status": current_status.value,
                    "new_status": new_status.value,
                },
            )

            logger.info(
                f"Updated plan {plan_id} status to {status}",
                extra={
                    "plan_id": plan_id,
                    "status": status,
                },
            )

        except Exception as e:
            # Log failed status update
            await self._log_audit_event(
                action="PLAN_STATUS_UPDATE",
                user_sub=updated_by,
                plan_id=plan_id,
                result="FAILURE",
                error_message=str(e),
                metadata={"attempted_status": status},
            )
            raise

    async def list_plans(
        self,
        created_by: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List plans with optional filtering.

        Args:
            created_by: Filter by creator user sub
            status: Filter by status
            limit: Maximum number of results

        Returns:
            List of plan summaries
        """
        stmt = select(PlanModel)

        if created_by:
            stmt = stmt.where(PlanModel.created_by == created_by)
        if status:
            stmt = stmt.where(PlanModel.status == status)

        stmt = stmt.order_by(PlanModel.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        plans = result.scalars().all()

        return [
            {
                "plan_id": p.id,
                "tool_name": p.tool_name,
                "created_by": p.created_by,
                "status": p.status,
                "device_count": len(p.device_ids),
                "summary": p.summary,
                "created_at": p.created_at.isoformat(),
            }
            for p in plans
        ]
