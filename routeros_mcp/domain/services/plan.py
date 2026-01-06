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

    def _generate_approval_token(self, plan_id: str, created_by: str, timestamp: str) -> str:
        """Generate cryptographically signed approval token using HMAC.

        Args:
            plan_id: Plan identifier
            created_by: User who created the plan
            timestamp: ISO format timestamp for token generation

        Returns:
            HMAC-signed approval token
        """
        # Create message to sign: plan_id:created_by:timestamp
        message = f"{plan_id}:{created_by}:{timestamp}"

        # Use encryption key as HMAC secret (or fallback for lab/test environments)
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
        self, plan_id: str, created_by: str, token: str, expires_at: datetime, token_timestamp: str
    ) -> None:
        """Validate approval token signature and expiration.

        Args:
            plan_id: Plan identifier
            created_by: User who created the plan
            token: Token to validate
            expires_at: Token expiration timestamp
            token_timestamp: Timestamp used when generating the token

        Raises:
            ValueError: If token is invalid or expired
        """
        # Check expiration first
        if datetime.now(UTC) > expires_at:
            raise ValueError("Approval token has expired")

        # Regenerate expected signature using stored timestamp
        message = f"{plan_id}:{created_by}:{token_timestamp}"
        secret_key = self.settings.encryption_key or "INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION"
        expected_signature = hmac.new(
            secret_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:16]

        # Extract signature from token
        # Token format: approve-{signature}-{random}
        if not token.startswith("approve-"):
            raise ValueError("Invalid approval token format")

        parts = token.split("-", 2)  # Split on first 2 hyphens only
        if len(parts) < 3 or not parts[1] or not parts[2]:
            raise ValueError("Invalid approval token format")

        token_signature = parts[1]

        # Verify signature using constant-time comparison
        if not secrets.compare_digest(token_signature, expected_signature):
            raise ValueError("Invalid approval token")

    def _log_audit_event(
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

        Note: This method adds the audit event to the session but does NOT commit.
        The caller is responsible for committing the transaction to ensure
        atomicity between the business operation and its audit log.

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
                "warnings": [],  # Initialize warnings list from start
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
                f"Pre-checks failed for devices: {', '.join(failed_devices)}."
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

            # Generate token timestamp (stored with token for validation)
            token_timestamp = datetime.now(UTC).isoformat()
            approval_token = self._generate_approval_token(plan_id, created_by, token_timestamp)

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
                    "approval_token_timestamp": token_timestamp,  # Store timestamp for validation
                    "approval_expires_at": expires_at.isoformat(),
                    "pre_check_results": pre_check_results,
                },
            )

            self.session.add(plan)

            # Log audit event (part of same transaction)
            self._log_audit_event(
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

            # Commit both plan creation and audit event atomically
            await self.session.commit()
            await self.session.refresh(plan)

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
            # Log failed plan creation (best effort - don't mask original error)
            try:
                self._log_audit_event(
                    action="PLAN_CREATED",
                    user_sub=created_by,
                    tool_name=tool_name,
                    result="FAILURE",
                    error_message=str(e),
                    metadata={"device_ids": device_ids, "risk_level": risk_level},
                )
                await self.session.commit()
            except Exception as audit_error:
                logger.warning(f"Failed to log audit event for plan creation failure: {audit_error}")
            raise

    async def create_multi_device_plan(
        self,
        tool_name: str,
        created_by: str,
        device_ids: list[str],
        summary: str,
        changes: dict[str, Any],
        change_type: str,
        risk_level: str = "medium",
        batch_size: int = 5,
        pause_seconds_between_batches: int = 60,
        rollback_on_failure: bool = True,
    ) -> dict[str, Any]:
        """Create a new multi-device plan with batched execution configuration.

        Args:
            tool_name: Name of the tool creating the plan
            created_by: User sub who created the plan
            device_ids: List of target device IDs (2-50 devices)
            summary: Human-readable plan summary
            changes: Detailed change specifications
            change_type: Type of change (e.g., 'dns_ntp', 'firewall', 'routing')
            risk_level: Risk level (low/medium/high)
            batch_size: Number of devices to process per batch (default: 5)
            pause_seconds_between_batches: Seconds to wait between batches (default: 60)
            rollback_on_failure: Whether to rollback changes on failure (default: True)

        Returns:
            Plan details including plan_id, approval_token, batches, and pre-check results

        Raises:
            ValueError: If validation or pre-checks fail
        """
        try:
            # Validate device count (2-50 devices)
            if len(device_ids) < 2:
                raise ValueError("Multi-device plans require at least 2 devices")
            if len(device_ids) > 50:
                raise ValueError("Multi-device plans support maximum 50 devices")

            # Validate batch configuration
            if not isinstance(batch_size, int):
                raise ValueError("batch_size must be an integer")
            if batch_size < 1:
                raise ValueError("batch_size must be at least 1")
            # Enforce a reasonable maximum batch size relative to the plan size
            max_batch_size = min(50, len(device_ids))
            if batch_size > max_batch_size:
                raise ValueError(
                    f"batch_size must not exceed {max_batch_size} for this plan"
                )

            # Validate pause between batches is non-negative
            if pause_seconds_between_batches < 0:
                raise ValueError("pause_seconds_between_batches cannot be negative")

            # Validate devices exist and get device models
            devices = await self._validate_devices(device_ids)

            # Validate all devices are in same environment
            environments = {d.environment for d in devices}
            if len(environments) > 1:
                raise ValueError(
                    f"All devices must be in the same environment. Found: {', '.join(sorted(environments))}"
                )

            # Run pre-checks on devices (includes reachability validation)
            pre_check_results = await self._run_pre_checks(devices, tool_name, risk_level)

            # Calculate batches
            batches = []
            for i in range(0, len(device_ids), batch_size):
                batch_devices = device_ids[i:i + batch_size]
                batches.append({
                    "batch_number": len(batches) + 1,
                    "device_ids": batch_devices,
                    "device_count": len(batch_devices),
                })

            # Generate plan ID and approval token
            plan_id = f"plan-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

            # Generate token timestamp (stored with token for validation)
            token_timestamp = datetime.now(UTC).isoformat()
            approval_token = self._generate_approval_token(plan_id, created_by, token_timestamp)

            # Token expires in 15 minutes
            expires_at = datetime.now(UTC) + timedelta(minutes=self.TOKEN_EXPIRATION_MINUTES)

            # Initialize device statuses
            device_statuses = dict.fromkeys(device_ids, "pending")

            # Create plan record with Phase 4 fields
            plan = PlanModel(
                id=plan_id,
                created_by=created_by,
                tool_name=tool_name,
                status=PlanStatus.PENDING.value,
                device_ids=device_ids,
                summary=summary,
                batch_size=batch_size,
                pause_seconds_between_batches=pause_seconds_between_batches,
                rollback_on_failure=rollback_on_failure,
                device_statuses=device_statuses,
                changes={
                    **changes,
                    "change_type": change_type,
                    "risk_level": risk_level,
                    "approval_token": approval_token,
                    "approval_token_timestamp": token_timestamp,
                    "approval_expires_at": expires_at.isoformat(),
                    "pre_check_results": pre_check_results,
                    "batches": batches,
                    "batch_count": len(batches),
                },
            )

            self.session.add(plan)

            # Log audit event (part of same transaction)
            self._log_audit_event(
                action="PLAN_CREATED",
                user_sub=created_by,
                plan_id=plan_id,
                tool_name=tool_name,
                result="SUCCESS",
                metadata={
                    "device_count": len(device_ids),
                    "risk_level": risk_level,
                    "device_ids": device_ids,
                    "change_type": change_type,
                    "batch_count": len(batches),
                    "batch_size": batch_size,
                    "multi_device": True,
                },
            )

            # Commit both plan creation and audit event atomically
            await self.session.commit()
            await self.session.refresh(plan)

            logger.info(
                f"Created multi-device plan {plan_id}",
                extra={
                    "plan_id": plan_id,
                    "tool_name": tool_name,
                    "device_count": len(device_ids),
                    "batch_count": len(batches),
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
                "batch_size": batch_size,
                "batch_count": len(batches),
                "batches": batches,
                "pause_seconds_between_batches": pause_seconds_between_batches,
                "rollback_on_failure": rollback_on_failure,
                "pre_check_results": pre_check_results,
            }

        except Exception as e:
            # Log failed plan creation (best effort - don't mask original error)
            try:
                self._log_audit_event(
                    action="PLAN_CREATED",
                    user_sub=created_by,
                    tool_name=tool_name,
                    result="FAILURE",
                    error_message=str(e),
                    metadata={
                        "device_ids": device_ids,
                        "risk_level": risk_level,
                        "change_type": change_type,
                        "multi_device": True,
                    },
                )
                await self.session.commit()
            except Exception as audit_error:
                logger.warning(f"Failed to log audit event for plan creation failure: {audit_error}")
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

    def validate_approval_token(
        self, plan_id: str, created_by: str, approval_token: str, expires_at: datetime, token_timestamp: str
    ) -> None:
        """Validate approval token signature and expiration (public interface).

        Args:
            plan_id: Plan identifier
            created_by: User who created the plan
            approval_token: Token to validate
            expires_at: Token expiration timestamp
            token_timestamp: Timestamp used when generating the token

        Raises:
            ValueError: If token is invalid or expired
        """
        self._validate_approval_token(plan_id, created_by, approval_token, expires_at, token_timestamp)

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

            # Validate approval token signature and expiration
            # We rely solely on HMAC validation rather than exact token comparison
            # to avoid storing the full token unnecessarily
            expires_at_str = plan.changes.get("approval_expires_at")
            token_timestamp = plan.changes.get("approval_token_timestamp")
            if not expires_at_str or not token_timestamp:
                raise ValueError("Invalid approval token metadata")

            expires_at = datetime.fromisoformat(expires_at_str)
            self._validate_approval_token(
                plan_id, plan.created_by, approval_token, expires_at, token_timestamp
            )

            # Update plan status
            plan.status = PlanStatus.APPROVED.value
            plan.approved_by = approved_by
            plan.approved_at = datetime.now(UTC)

            # Log audit event (part of same transaction)
            self._log_audit_event(
                action="PLAN_APPROVED",
                user_sub=approved_by,
                plan_id=plan_id,
                tool_name=plan.tool_name,
                result="SUCCESS",
                metadata={"device_count": len(plan.device_ids)},
            )

            # Commit both approval and audit event atomically
            await self.session.commit()
            await self.session.refresh(plan)

            logger.info(
                f"Approved plan {plan_id}",
                extra={
                    "plan_id": plan_id,
                    "approved_by": approved_by,
                },
            )

            return await self.get_plan(plan_id)

        except Exception as e:
            # Log failed approval (best effort - don't mask original error)
            try:
                self._log_audit_event(
                    action="PLAN_APPROVED",
                    user_sub=approved_by,
                    plan_id=plan_id,
                    result="FAILURE",
                    error_message=str(e),
                )
                await self.session.commit()
            except Exception as audit_error:
                logger.warning(f"Failed to log audit event for plan approval failure: {audit_error}")
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
            def normalize_status(status_value: str) -> PlanStatus:
                """Normalize legacy statuses to current enum values."""
                legacy_aliases = {
                    "applied": PlanStatus.COMPLETED,
                }
                try:
                    return PlanStatus(status_value)
                except ValueError:
                    if status_value in legacy_aliases:
                        return legacy_aliases[status_value]
                    valid_values = [s.value for s in PlanStatus] + list(legacy_aliases.keys())
                    raise ValueError(
                        f"Invalid status: {status_value}. Must be one of: {', '.join(valid_values)}"
                    )

            # Validate status is a valid enum value
            new_status = normalize_status(status)

            stmt = select(PlanModel).where(PlanModel.id == plan_id)
            result = await self.session.execute(stmt)
            plan = result.scalar_one_or_none()

            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")

            # Validate state transition
            current_status = normalize_status(plan.status)
            if new_status not in self.VALID_TRANSITIONS.get(current_status, set()):
                raise ValueError(
                    f"Invalid status transition from {current_status.value} to {new_status.value}"
                )

            plan.status = new_status.value

            # Log audit event (part of same transaction)
            self._log_audit_event(
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

            # Commit both status update and audit event atomically
            await self.session.commit()

            logger.info(
                f"Updated plan {plan_id} status to {status}",
                extra={
                    "plan_id": plan_id,
                    "status": status,
                },
            )

        except Exception as e:
            # Log failed status update (best effort - don't mask original error)
            try:
                self._log_audit_event(
                    action="PLAN_STATUS_UPDATE",
                    user_sub=updated_by,
                    plan_id=plan_id,
                    result="FAILURE",
                    error_message=str(e),
                    metadata={"attempted_status": status},
                )
                await self.session.commit()
            except Exception as audit_error:
                logger.warning(f"Failed to log audit event for plan status update failure: {audit_error}")
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
