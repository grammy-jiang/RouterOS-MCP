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
        PlanStatus.EXECUTING: {
            PlanStatus.COMPLETED,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
            PlanStatus.ROLLING_BACK,
        },
        PlanStatus.ROLLING_BACK: {PlanStatus.ROLLED_BACK},  # Phase 4: Rollback in progress
        PlanStatus.COMPLETED: set(),  # Terminal state
        PlanStatus.FAILED: set(),  # Terminal state
        PlanStatus.CANCELLED: set(),  # Terminal state
        PlanStatus.ROLLED_BACK: set(),  # Terminal state (Phase 4)
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
        signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()[
            :16
        ]  # Take first 16 chars for brevity

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
            secret_key.encode(), message.encode(), hashlib.sha256
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
                device_result["checks"].append(
                    {
                        "check": "professional_workflows_enabled",
                        "status": "failed",
                        "message": f"Device {device.id} does not allow professional workflows",
                    }
                )
                pre_check_results["status"] = "failed"

            # Check 2: Environment restrictions for high-risk operations
            if risk_level == "high" and device.environment == "prod":
                device_result["warnings"].append(
                    {
                        "check": "environment_restriction",
                        "message": f"High-risk operation on production device {device.id} - proceed with extreme caution",
                    }
                )
                pre_check_results["warnings"].append(
                    f"High-risk operation on production device {device.id}"
                )

            # Check 3: Device reachability
            if device.status in ["unreachable", "decommissioned"]:
                device_result["status"] = "failed"
                device_result["checks"].append(
                    {
                        "check": "device_reachable",
                        "status": "failed",
                        "message": f"Device {device.id} is {device.status}",
                    }
                )
                pre_check_results["status"] = "failed"

            # Check 4: Device health status
            if device.status == "degraded":
                device_result["warnings"].append(
                    {
                        "check": "device_health",
                        "message": f"Device {device.id} is in degraded state",
                    }
                )
                pre_check_results["warnings"].append(f"Device {device.id} is degraded")

            pre_check_results["device_checks"][device.id] = device_result

        # Fail if any critical checks failed
        if pre_check_results["status"] == "failed":
            failed_devices = [
                dev_id
                for dev_id, result in pre_check_results["device_checks"].items()
                if result["status"] == "failed"
            ]
            raise ValueError(f"Pre-checks failed for devices: {', '.join(failed_devices)}.")

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
                logger.warning(
                    f"Failed to log audit event for plan creation failure: {audit_error}"
                )
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
                raise ValueError(f"batch_size must not exceed {max_batch_size} for this plan")

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
            batches: list[dict[str, Any]] = []
            for i in range(0, len(device_ids), batch_size):
                batch_devices = device_ids[i : i + batch_size]
                batches.append(
                    {
                        "batch_number": len(batches) + 1,
                        "device_ids": batch_devices,
                        "device_count": len(batch_devices),
                    }
                )

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
                logger.warning(
                    f"Failed to log audit event for plan creation failure: {audit_error}"
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

    async def get_plan(
        self,
        plan_id: str,
        allowed_device_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Get plan details.

        Args:
            plan_id: Plan identifier
            allowed_device_ids: Optional list of allowed device IDs for scope filtering
                               (None or empty list = full access)

        Returns:
            Plan details

        Raises:
            ValueError: If plan not found or contains devices not in allowed scope
        """
        stmt = select(PlanModel).where(PlanModel.id == plan_id)
        result = await self.session.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            raise ValueError(f"Plan not found: {plan_id}")

        # Check device scope if provided
        # None or empty list means full access (typically for admins)
        if allowed_device_ids is not None and len(allowed_device_ids) > 0:
            plan_device_ids = plan.device_ids or []
            unauthorized_devices = [
                dev_id for dev_id in plan_device_ids if dev_id not in allowed_device_ids
            ]
            if unauthorized_devices:
                raise ValueError(
                    f"Plan '{plan_id}' contains devices not in allowed scope: "
                    f"{', '.join(unauthorized_devices[:3])}"
                    f"{'...' if len(unauthorized_devices) > 3 else ''}"
                )

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
        self,
        plan_id: str,
        created_by: str,
        approval_token: str,
        expires_at: datetime,
        token_timestamp: str,
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
        self._validate_approval_token(
            plan_id, created_by, approval_token, expires_at, token_timestamp
        )

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
                raise ValueError(f"Plan {plan_id} cannot be approved from status {plan.status}")

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
                logger.warning(
                    f"Failed to log audit event for plan approval failure: {audit_error}"
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
                logger.warning(
                    f"Failed to log audit event for plan status update failure: {audit_error}"
                )
            raise

    async def rollback_plan(
        self,
        plan_id: str,
        reason: str,
        triggered_by: str = "system",
        max_retries: int = 3,
        dns_ntp_service: Any | None = None,
    ) -> dict[str, Any]:
        """Rollback a plan that failed health checks.

        This method implements automatic rollback on health check failure (Phase 4).
        It restores previous DNS/NTP settings from plan metadata.

        Args:
            plan_id: Plan identifier
            reason: Reason for rollback (e.g., "health_check_failed")
            triggered_by: User or system that triggered rollback
            max_retries: Maximum rollback attempts per device (default: 3)
            dns_ntp_service: Optional DNS/NTP service instance (for dependency injection)

        Returns:
            Rollback results including per-device status

        Raises:
            ValueError: If plan not found or not eligible for rollback
        """
        from routeros_mcp.domain.services.dns_ntp import DNSNTPService

        try:
            stmt = select(PlanModel).where(PlanModel.id == plan_id)
            result = await self.session.execute(stmt)
            plan = result.scalar_one_or_none()

            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")

            # Check if rollback is enabled for this plan
            if not plan.rollback_on_failure:
                message = f"Rollback not enabled for plan {plan_id}"
                logger.warning(
                    message,
                    extra={"plan_id": plan_id, "reason": reason},
                )
                raise ValueError(message)

            # Validate state transition
            current_status = PlanStatus(plan.status)
            if PlanStatus.ROLLING_BACK not in self.VALID_TRANSITIONS.get(current_status, set()):
                raise ValueError(f"Plan {plan_id} cannot be rolled back from status {plan.status}")

            # Update plan status to rolling_back
            plan.status = PlanStatus.ROLLING_BACK.value

            # Log audit event for rollback initiation
            self._log_audit_event(
                action="PLAN_ROLLBACK_INITIATED",
                user_sub=triggered_by,
                plan_id=plan_id,
                tool_name=plan.tool_name,
                result="SUCCESS",
                metadata={"reason": reason, "device_count": len(plan.device_ids)},
            )

            await self.session.commit()

            logger.info(
                f"Starting rollback for plan {plan_id}",
                extra={"plan_id": plan_id, "reason": reason, "device_count": len(plan.device_ids)},
            )

            # Initialize rollback results
            rollback_results: dict[str, Any] = {
                "plan_id": plan_id,
                "rollback_enabled": True,
                "reason": reason,
                "devices": {},
                "summary": {
                    "total": 0,
                    "success": 0,
                    "failed": 0,
                },
            }

            try:
                # Get devices that need rollback (only those in "applied" status)
                device_statuses = plan.device_statuses or {}
                devices_to_rollback = [
                    device_id
                    for device_id, status in device_statuses.items()
                    if status == "applied"
                ]

                rollback_results["summary"]["total"] = len(devices_to_rollback)

                # Extract previous state from plan metadata
                previous_state = plan.changes.get("previous_state", {})
                if not previous_state:
                    logger.error(
                        f"No previous state found in plan {plan_id} metadata",
                        extra={"plan_id": plan_id},
                    )
                    raise ValueError(f"No previous state available for rollback: {plan_id}")

                # Initialize DNS/NTP service for rollback operations (if not provided)
                if dns_ntp_service is None:
                    dns_ntp_service = DNSNTPService(self.session, self.settings)

                # Rollback each device
                # Note: We batch status updates to reduce database commits
                for device_id in devices_to_rollback:
                    device_result = {
                        "device_id": device_id,
                        "status": "rolling_back",
                        "attempts": 0,
                        "errors": [],
                    }

                    # Update device status to rolling_back (will be committed in batch)
                    device_statuses[device_id] = "rolling_back"

                    # Get previous state for this device
                    device_previous_state = previous_state.get(device_id, {})
                    if not device_previous_state:
                        logger.warning(
                            f"No previous state for device {device_id} in plan {plan_id}",
                            extra={"plan_id": plan_id, "device_id": device_id},
                        )
                        device_result["status"] = "rollback_failed"
                        device_result["errors"].append("No previous state found")
                        device_statuses[device_id] = "rollback_failed"
                        rollback_results["devices"][device_id] = device_result
                        rollback_results["summary"]["failed"] += 1
                        continue

                    # Attempt rollback with retries and exponential backoff
                    success = False
                    dns_rollback_success = False
                    ntp_rollback_success = False
                    for attempt in range(1, max_retries + 1):
                        device_result["attempts"] = attempt
                        try:
                            # Rollback DNS servers if present in previous state
                            if "dns_servers" in device_previous_state and not dns_rollback_success:
                                logger.info(
                                    f"Rolling back DNS servers for device {device_id} (attempt {attempt})",
                                    extra={
                                        "plan_id": plan_id,
                                        "device_id": device_id,
                                        "dns_servers": device_previous_state["dns_servers"],
                                    },
                                )
                                await dns_ntp_service.update_dns_servers(
                                    device_id=device_id,
                                    dns_servers=device_previous_state["dns_servers"],
                                    dry_run=False,
                                )
                                dns_rollback_success = True

                            # Rollback NTP servers if present in previous state
                            if "ntp_servers" in device_previous_state and not ntp_rollback_success:
                                logger.info(
                                    f"Rolling back NTP servers for device {device_id} (attempt {attempt})",
                                    extra={
                                        "plan_id": plan_id,
                                        "device_id": device_id,
                                        "ntp_servers": device_previous_state["ntp_servers"],
                                    },
                                )
                                ntp_enabled = device_previous_state.get("ntp_enabled", True)
                                await dns_ntp_service.update_ntp_servers(
                                    device_id=device_id,
                                    ntp_servers=device_previous_state["ntp_servers"],
                                    enabled=ntp_enabled,
                                    dry_run=False,
                                )
                                ntp_rollback_success = True

                            # Rollback succeeded - update status (will be committed in batch)
                            device_result["status"] = "rolled_back"
                            device_result["dns_rollback"] = dns_rollback_success
                            device_result["ntp_rollback"] = ntp_rollback_success
                            device_statuses[device_id] = "rolled_back"
                            rollback_results["summary"]["success"] += 1
                            success = True

                            logger.info(
                                f"Successfully rolled back device {device_id}",
                                extra={
                                    "plan_id": plan_id,
                                    "device_id": device_id,
                                    "attempt": attempt,
                                },
                            )
                            break

                        except Exception as e:
                            error_msg = f"Attempt {attempt} failed: {str(e)}"
                            device_result["errors"].append(error_msg)
                            logger.warning(
                                f"Rollback attempt {attempt} failed for device {device_id}: {e}",
                                extra={
                                    "plan_id": plan_id,
                                    "device_id": device_id,
                                    "attempt": attempt,
                                    "max_retries": max_retries,
                                },
                            )

                            if attempt >= max_retries:
                                # Track partial success if any component succeeded
                                if dns_rollback_success or ntp_rollback_success:
                                    device_result["status"] = "partially_rolled_back"
                                    device_result["dns_rollback"] = dns_rollback_success
                                    device_result["ntp_rollback"] = ntp_rollback_success
                                    device_statuses[device_id] = "partially_rolled_back"
                                    rollback_results["summary"]["success"] += 1
                                else:
                                    device_result["status"] = "rollback_failed"
                                    device_statuses[device_id] = "rollback_failed"
                                    rollback_results["summary"]["failed"] += 1

                                logger.error(
                                    f"Rollback failed for device {device_id} after {max_retries} attempts",
                                    extra={
                                        "plan_id": plan_id,
                                        "device_id": device_id,
                                        "dns_rollback": dns_rollback_success,
                                        "ntp_rollback": ntp_rollback_success,
                                    },
                                )
                            else:
                                # Exponential backoff: wait 2^attempt seconds before retry
                                import asyncio

                                backoff_delay = 2**attempt
                                logger.info(
                                    f"Waiting {backoff_delay}s before retry {attempt + 1}",
                                    extra={"plan_id": plan_id, "device_id": device_id},
                                )
                                await asyncio.sleep(backoff_delay)

                    rollback_results["devices"][device_id] = device_result

                # Commit all device status updates in a single transaction
                plan.device_statuses = device_statuses
                await self.session.commit()

                # Update plan status based on rollback results
                if rollback_results["summary"]["failed"] == 0:
                    # All devices rolled back successfully
                    plan.status = PlanStatus.ROLLED_BACK.value
                    result_status = "SUCCESS"
                else:
                    # Some devices failed to rollback
                    plan.status = PlanStatus.ROLLED_BACK.value  # Still mark as rolled_back
                    result_status = "PARTIAL"

                # Log final audit event
                self._log_audit_event(
                    action="PLAN_ROLLBACK_COMPLETED",
                    user_sub=triggered_by,
                    plan_id=plan_id,
                    tool_name=plan.tool_name,
                    result=result_status,
                    metadata={
                        "reason": reason,
                        "total_devices": rollback_results["summary"]["total"],
                        "success": rollback_results["summary"]["success"],
                        "failed": rollback_results["summary"]["failed"],
                    },
                )

                await self.session.commit()

                logger.info(
                    f"Rollback completed for plan {plan_id}",
                    extra={
                        "plan_id": plan_id,
                        "success": rollback_results["summary"]["success"],
                        "failed": rollback_results["summary"]["failed"],
                    },
                )

                return rollback_results

            except Exception as rollback_error:
                # Ensure plan status is updated even if rollback fails
                try:
                    plan.status = PlanStatus.ROLLED_BACK.value
                    await self.session.commit()
                    logger.warning(
                        f"Plan {plan_id} marked as ROLLED_BACK despite errors",
                        extra={"plan_id": plan_id},
                    )
                except Exception as commit_error:
                    logger.error(
                        f"Failed to update plan status after rollback error: {commit_error}",
                        extra={"plan_id": plan_id},
                    )
                raise rollback_error

        except ValueError as ve:
            # Validation errors (e.g., plan not found, wrong state) - log but don't commit
            logger.warning(
                f"Rollback validation error for plan {plan_id}: {ve}",
                extra={"plan_id": plan_id, "reason": reason},
            )
            # Don't log audit event for validation errors - they're expected failures
            raise
        except Exception as e:
            # Unexpected system errors - log audit event for tracking
            logger.error(
                f"Unexpected error during rollback for plan {plan_id}: {e}",
                exc_info=True,
                extra={"plan_id": plan_id, "reason": reason},
            )
            # Rollback session to clean state before attempting audit log
            try:
                await self.session.rollback()
            except Exception as rollback_error:
                logger.warning(f"Failed to rollback session: {rollback_error}")

            # Log failed rollback audit event (best effort - don't mask original error)
            try:
                self._log_audit_event(
                    action="PLAN_ROLLBACK_COMPLETED",
                    user_sub=triggered_by,
                    plan_id=plan_id,
                    tool_name=plan.tool_name if plan else "plan_service",
                    result="FAILURE",
                    error_message=str(e),
                    metadata={"reason": reason},
                )
                await self.session.commit()
            except Exception as audit_error:
                logger.warning(f"Failed to log audit event for rollback failure: {audit_error}")
            raise

    async def apply_multi_device_plan(
        self,
        plan_id: str,
        approval_token: str,
        applied_by: str = "system",
        dns_ntp_service: Any | None = None,
    ) -> dict[str, Any]:
        """Apply a multi-device plan with staged rollout and health checks.

        This method implements Phase 4 staged rollout:
        1. Divides devices into batches based on plan.batch_size
        2. Applies changes to batch devices in parallel
        3. Runs health checks after each batch completes
        4. Halts rollout if devices are degraded (CPU ≥80%, memory ≥85%)
        5. Triggers rollback if rollback_on_failure=true

        Args:
            plan_id: Plan identifier
            approval_token: Approval token from plan creation
            applied_by: User sub who is applying (default: "system")
            dns_ntp_service: Optional DNS/NTP service instance (for dependency injection)

        Returns:
            Application results with per-device status and batch execution summary

        Raises:
            ValueError: If plan not found, not approved, or validation fails
        """
        import asyncio
        from routeros_mcp.domain.services.dns_ntp import DNSNTPService
        from routeros_mcp.domain.services.health import HealthService

        try:
            # Get plan
            stmt = select(PlanModel).where(PlanModel.id == plan_id)
            result = await self.session.execute(stmt)
            plan = result.scalar_one_or_none()

            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")

            # Validate plan is approved
            if plan.status != PlanStatus.APPROVED.value:
                raise ValueError(
                    f"Plan must be approved before applying. Current status: {plan.status}"
                )

            # Validate approval token
            expires_at_str = plan.changes.get("approval_expires_at")
            token_timestamp = plan.changes.get("approval_token_timestamp")
            if not expires_at_str or not token_timestamp:
                raise ValueError("Invalid approval token metadata")

            expires_at = datetime.fromisoformat(expires_at_str)
            self._validate_approval_token(
                plan_id, plan.created_by, approval_token, expires_at, token_timestamp
            )

            # Update plan status to executing
            plan.status = PlanStatus.EXECUTING.value

            # Get batches from plan metadata
            batches = plan.changes.get("batches", [])

            # Log audit event for plan execution start
            self._log_audit_event(
                action="PLAN_EXECUTION_STARTED",
                user_sub=applied_by,
                plan_id=plan_id,
                tool_name=plan.tool_name,
                result="SUCCESS",
                metadata={
                    "device_count": len(plan.device_ids),
                    "batch_size": plan.batch_size,
                    "batch_count": len(batches),
                },
            )
            await self.session.commit()

            # Initialize services
            if dns_ntp_service is None:
                dns_ntp_service = DNSNTPService(self.session, self.settings)
            health_service = HealthService(self.session, self.settings)

            # Initialize execution results
            execution_results: dict[str, Any] = {
                "plan_id": plan_id,
                "status": "executing",
                "batches_completed": 0,
                "total_batches": 0,
                "devices": {},
                "summary": {
                    "total": len(plan.device_ids),
                    "applied": 0,
                    "failed": 0,
                    "rolled_back": 0,
                },
                "halt_reason": None,
            }

            execution_results["total_batches"] = len(batches)

            # Get change type and configuration
            change_type = plan.changes.get("change_type", "unknown")
            changes_config = plan.changes.copy()

            # Initialize device statuses
            device_statuses = plan.device_statuses or {}
            for device_id in plan.device_ids:
                if device_id not in device_statuses:
                    device_statuses[device_id] = "pending"

            # Save previous state for rollback
            previous_state = {}

            logger.info(
                f"Starting staged rollout for plan {plan_id}",
                extra={
                    "plan_id": plan_id,
                    "batch_count": len(batches),
                    "device_count": len(plan.device_ids),
                    "change_type": change_type,
                },
            )

            # Define device application function outside the batch loop
            async def apply_to_device(device_id: str) -> dict[str, Any]:
                """Apply changes to a single device."""
                device_result: dict[str, Any] = {
                    "device_id": device_id,
                    "status": "applying",
                    "errors": [],
                }

                try:
                    # Capture previous state before applying changes
                    if change_type == "dns_ntp":
                        # Get current DNS/NTP configuration
                        try:
                            current_dns = await dns_ntp_service.get_dns_servers(device_id)
                            current_ntp = await dns_ntp_service.get_ntp_status(device_id)
                            previous_state[device_id] = {
                                "dns_servers": current_dns.get("servers", []),
                                "ntp_servers": current_ntp.get("servers", []),
                                "ntp_enabled": current_ntp.get("enabled", True),
                            }
                        except Exception as e:
                            logger.warning(
                                f"Failed to capture previous state for device {device_id}: {e}",
                                extra={"plan_id": plan_id, "device_id": device_id},
                            )

                        # Apply DNS/NTP changes
                        if "dns_servers" in changes_config:
                            await dns_ntp_service.update_dns_servers(
                                device_id=device_id,
                                dns_servers=changes_config["dns_servers"],
                                dry_run=False,
                            )
                        if "ntp_servers" in changes_config:
                            await dns_ntp_service.update_ntp_servers(
                                device_id=device_id,
                                ntp_servers=changes_config["ntp_servers"],
                                enabled=changes_config.get("ntp_enabled", True),
                                dry_run=False,
                            )

                    # Mark device as applied
                    device_result["status"] = "applied"
                    device_statuses[device_id] = "applied"

                    logger.info(
                        f"Successfully applied changes to device {device_id}",
                        extra={"plan_id": plan_id, "device_id": device_id},
                    )

                except Exception as e:
                    error_msg = f"Failed to apply changes: {str(e)}"
                    device_result["errors"].append(error_msg)
                    device_result["status"] = "failed"
                    device_statuses[device_id] = "failed"

                    logger.error(
                        f"Failed to apply changes to device {device_id}: {e}",
                        extra={"plan_id": plan_id, "device_id": device_id},
                    )

                return device_result

            # Process batches sequentially
            for batch_idx, batch in enumerate(batches):
                batch_number = batch["batch_number"]
                batch_device_ids = batch["device_ids"]

                logger.info(
                    f"Processing batch {batch_number}/{len(batches)}",
                    extra={
                        "plan_id": plan_id,
                        "batch_number": batch_number,
                        "device_count": len(batch_device_ids),
                    },
                )

                # Update device statuses to "applying" for this batch
                for device_id in batch_device_ids:
                    device_statuses[device_id] = "applying"
                plan.device_statuses = device_statuses
                await self.session.commit()

                # Apply to all devices in batch in parallel
                apply_tasks = [apply_to_device(device_id) for device_id in batch_device_ids]
                batch_results = await asyncio.gather(*apply_tasks, return_exceptions=False)

                # Update execution results with batch results
                for device_result in batch_results:
                    device_id = device_result["device_id"]
                    execution_results["devices"][device_id] = device_result

                    if device_result["status"] == "applied":
                        execution_results["summary"]["applied"] += 1
                    elif device_result["status"] == "failed":
                        execution_results["summary"]["failed"] += 1

                # Save device statuses and previous state to plan
                plan.device_statuses = device_statuses
                plan.changes["previous_state"] = previous_state
                await self.session.commit()

                # Check if any devices failed in this batch
                failed_devices = [
                    device_id
                    for device_id in batch_device_ids
                    if device_statuses[device_id] == "failed"
                ]

                if failed_devices:
                    logger.warning(
                        f"Batch {batch_number} had {len(failed_devices)} failed devices",
                        extra={
                            "plan_id": plan_id,
                            "batch_number": batch_number,
                            "failed_devices": failed_devices,
                        },
                    )
                    # Continue to health checks even with failures

                # Run health checks on batch devices
                logger.info(
                    f"Running health checks on batch {batch_number}",
                    extra={"plan_id": plan_id, "batch_number": batch_number},
                )

                health_results = await health_service.run_batch_health_checks(
                    device_ids=batch_device_ids,
                    cpu_threshold=80.0,
                    memory_threshold=85.0,
                )

                # Check for degraded or unreachable devices
                degraded_devices = [
                    device_id
                    for device_id, health in health_results.items()
                    if health.status in ["degraded", "unreachable"]
                ]

                if degraded_devices:
                    # Health checks failed - halt rollout
                    logger.error(
                        f"Health checks failed for {len(degraded_devices)} devices in batch {batch_number}",
                        extra={
                            "plan_id": plan_id,
                            "batch_number": batch_number,
                            "degraded_devices": degraded_devices,
                        },
                    )

                    execution_results["status"] = "halted"
                    execution_results["halt_reason"] = (
                        f"Health checks failed for devices: {', '.join(degraded_devices)}"
                    )
                    execution_results["batches_completed"] = batch_number

                    # Trigger rollback if enabled (before setting plan to FAILED)
                    if plan.rollback_on_failure:
                        logger.info(
                            f"Triggering rollback for plan {plan_id}",
                            extra={"plan_id": plan_id, "reason": "health_check_failed"},
                        )

                        try:
                            rollback_results = await self.rollback_plan(
                                plan_id=plan_id,
                                reason="health_check_failed",
                                triggered_by=applied_by,
                                dns_ntp_service=dns_ntp_service,
                            )

                            # Update execution results with rollback info
                            execution_results["rollback"] = rollback_results
                            execution_results["summary"]["rolled_back"] = rollback_results[
                                "summary"
                            ]["success"]

                        except Exception as rollback_error:
                            logger.error(
                                f"Rollback failed for plan {plan_id}: {rollback_error}",
                                extra={"plan_id": plan_id},
                            )
                            execution_results["rollback_error"] = str(rollback_error)
                            # Ensure plan does not remain in EXECUTING state if rollback fails
                            plan.status = PlanStatus.FAILED.value
                            await self.session.commit()
                    else:
                        # Update plan status to failed (only if not rolling back)
                        plan.status = PlanStatus.FAILED.value
                        await self.session.commit()

                    # Log audit event for halted execution
                    self._log_audit_event(
                        action="PLAN_EXECUTION_HALTED",
                        user_sub=applied_by,
                        plan_id=plan_id,
                        tool_name=plan.tool_name,
                        result="FAILURE",
                        error_message=execution_results["halt_reason"],
                        metadata={
                            "batches_completed": batch_number,
                            "degraded_devices": degraded_devices,
                        },
                    )
                    await self.session.commit()

                    return execution_results

                # All devices healthy - mark batch as complete
                execution_results["batches_completed"] = batch_number

                logger.info(
                    f"Batch {batch_number} completed successfully",
                    extra={"plan_id": plan_id, "batch_number": batch_number},
                )

                # Pause between batches (except after last batch)
                if batch_idx < len(batches) - 1:
                    pause_seconds = plan.pause_seconds_between_batches
                    if pause_seconds > 0:
                        logger.info(
                            f"Pausing {pause_seconds}s before next batch",
                            extra={"plan_id": plan_id, "pause_seconds": pause_seconds},
                        )
                        await asyncio.sleep(pause_seconds)

            # All batches completed successfully
            execution_results["status"] = "completed"
            plan.status = PlanStatus.COMPLETED.value

            # Log audit event for successful completion
            self._log_audit_event(
                action="PLAN_EXECUTION_COMPLETED",
                user_sub=applied_by,
                plan_id=plan_id,
                tool_name=plan.tool_name,
                result="SUCCESS",
                metadata={
                    "batches_completed": len(batches),
                    "devices_applied": execution_results["summary"]["applied"],
                    "devices_failed": execution_results["summary"]["failed"],
                },
            )
            await self.session.commit()

            logger.info(
                f"Plan {plan_id} executed successfully",
                extra={
                    "plan_id": plan_id,
                    "batches_completed": len(batches),
                    "devices_applied": execution_results["summary"]["applied"],
                },
            )

            return execution_results

        except ValueError as ve:
            # Validation errors - log but don't commit
            logger.warning(
                f"Plan execution validation error: {ve}",
                extra={"plan_id": plan_id},
            )
            raise
        except Exception as e:
            # Unexpected errors - try to update plan status
            logger.error(
                f"Unexpected error during plan execution: {e}",
                exc_info=True,
                extra={"plan_id": plan_id},
            )

            try:
                # Try to mark plan as failed
                stmt = select(PlanModel).where(PlanModel.id == plan_id)
                result = await self.session.execute(stmt)
                plan = result.scalar_one_or_none()

                if plan:
                    plan.status = PlanStatus.FAILED.value
                    self._log_audit_event(
                        action="PLAN_EXECUTION_FAILED",
                        user_sub=applied_by,
                        plan_id=plan_id,
                        tool_name=plan.tool_name,
                        result="FAILURE",
                        error_message=str(e),
                    )
                    await self.session.commit()
            except Exception as commit_error:
                logger.warning(
                    f"Failed to update plan status after error: {commit_error}",
                    extra={"plan_id": plan_id},
                )

            raise

    async def list_plans(
        self,
        created_by: str | None = None,
        status: str | None = None,
        limit: int = 50,
        allowed_device_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List plans with optional filtering.

        Args:
            created_by: Filter by creator user sub
            status: Filter by status
            limit: Maximum number of results
            allowed_device_ids: Optional list of allowed device IDs for scope filtering
                               (None or empty list = full access)

        Returns:
            List of plan summaries (filtered by device scope if provided)
        """
        stmt = select(PlanModel)

        if created_by:
            stmt = stmt.where(PlanModel.created_by == created_by)
        if status:
            stmt = stmt.where(PlanModel.status == status)

        stmt = stmt.order_by(PlanModel.created_at.desc()).limit(limit)

        result = await self.session.execute(stmt)
        plans = result.scalars().all()

        # Filter plans by device scope
        # None or empty list means full access (typically for admins)
        filtered_plans = []
        for p in plans:
            if allowed_device_ids is not None and len(allowed_device_ids) > 0:
                plan_device_ids = p.device_ids or []
                # Only include plans where ALL devices are in allowed scope
                if all(dev_id in allowed_device_ids for dev_id in plan_device_ids):
                    filtered_plans.append(p)
            else:
                filtered_plans.append(p)

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
            for p in filtered_plans
        ]
