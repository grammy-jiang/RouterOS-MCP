"""Admin API routes for browser-based UI.

Provides HTTP endpoints for device management, plan review, and approval
workflows. All endpoints require OIDC authentication.

See docs/09-operations-deployment-self-update-and-runbook.md for design.
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse

from routeros_mcp.api.admin_models import (
    DeviceCreateRequest,
    DeviceUpdateRequest,
    RejectionRequest,
)
from routeros_mcp.mcp.errors import DeviceNotFoundError

logger = logging.getLogger(__name__)


# Admin router
router = APIRouter(prefix="/admin", tags=["admin"])


def get_current_user_dep():
    """Get current user dependency - import here to avoid namespace pollution."""
    from routeros_mcp.api.http import get_current_user
    return get_current_user


async def get_session_dep():
    """Get database session dependency - import here to avoid namespace pollution."""
    from routeros_mcp.infra.db.session import get_session
    async for session in get_session():
        yield session


async def get_device_service():
    """Dependency to get DeviceService."""
    # Import here to avoid namespace pollution
    from routeros_mcp.config import Settings
    from routeros_mcp.domain.services.device import DeviceService
    from routeros_mcp.infra.db.session import get_session
    
    async for session in get_session():
        settings = Settings()
        yield DeviceService(session, settings)


async def get_plan_service():
    """Dependency to get PlanService."""
    # Import here to avoid namespace pollution
    from routeros_mcp.config import Settings
    from routeros_mcp.domain.services.plan import PlanService
    from routeros_mcp.infra.db.session import get_session
    
    async for session in get_session():
        settings = Settings()
        yield PlanService(session, settings)


async def get_job_service():
    """Dependency to get JobService."""
    # Import here to avoid namespace pollution
    from routeros_mcp.domain.services.job import JobService
    from routeros_mcp.infra.db.session import get_session
    
    async for session in get_session():
        yield JobService(session)


@router.get("", response_class=HTMLResponse)
async def admin_dashboard(
    user: dict[str, Any] = Depends(get_current_user_dep()),
) -> HTMLResponse:
    """Serve admin dashboard HTML.

    Returns:
        HTML page with device and plan management interface
    """
    # Read static HTML file
    from pathlib import Path

    static_dir = Path(__file__).parent / "static"
    html_file = static_dir / "admin.html"

    if not html_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Admin UI not found",
        )

    return HTMLResponse(content=html_file.read_text())


@router.get("/api/devices")
async def list_devices(
    user: dict[str, Any] = Depends(get_current_user_dep()),
    device_service: Any = Depends(get_device_service),
) -> JSONResponse:
    """Get list of all devices.

    Args:
        user: Current authenticated user
        device_service: Device service dependency

    Returns:
        JSON list of devices with metadata
    """
    try:
        devices = await device_service.list_devices()

        # Convert to JSON-serializable format with staleness checking
        from datetime import UTC, datetime, timedelta
        
        # Consider devices stale if not seen in 10 minutes
        stale_threshold = datetime.now(UTC) - timedelta(minutes=10)
        
        devices_data = [
            {
                "id": device.id,
                "name": device.name,
                "management_ip": device.management_ip,
                "management_port": device.management_port,
                "environment": device.environment,
                "tags": device.tags,
                "capabilities": device.capabilities,
                "last_seen": device.last_seen.isoformat() if device.last_seen else None,
                "status": (
                    "online" if device.last_seen and device.last_seen > stale_threshold 
                    else "offline"
                ),
            }
            for device in devices
        ]

        return JSONResponse(content={"devices": devices_data})

    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error listing devices: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list devices. Correlation ID: {correlation_id}",
        )


@router.post("/api/admin/devices")
async def create_device(
    device_data: DeviceCreateRequest,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    device_service: Any = Depends(get_device_service),
) -> JSONResponse:
    """Create a new device with credentials.

    Args:
        device_data: Device creation request
        user: Current authenticated user (must have admin role)
        device_service: Device service dependency

    Returns:
        JSON with created device details
    """
    # Check user role
    if user.get("role") not in ["admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to create devices",
        )

    try:
        # Generate device ID from name
        import re
        device_id = f"dev-{re.sub(r'[^a-z0-9-]', '-', device_data.name.lower())}"
        
        # Create device with credentials
        device = await device_service.create_device(
            device_id=device_id,
            name=device_data.name,
            management_ip=device_data.hostname,
            username=device_data.username,
            password=device_data.password,
            environment=device_data.environment,
            management_port=device_data.port,
        )

        return JSONResponse(
            status_code=status.HTTP_201_CREATED,
            content={
                "message": "Device created successfully",
                "device": {
                    "id": device.id,
                    "name": device.name,
                    "management_ip": device.management_ip,
                    "management_port": device.management_port,
                    "environment": device.environment,
                    "status": device.status,
                },
            },
        )

    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error creating device: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create device. Correlation ID: {correlation_id}",
        )


@router.put("/api/admin/devices/{device_id}")
async def update_device(
    device_id: str,
    device_data: DeviceUpdateRequest,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    device_service: Any = Depends(get_device_service),
) -> JSONResponse:
    """Update an existing device.

    Args:
        device_id: Device identifier
        device_data: Device update request
        user: Current authenticated user (must have admin role)
        device_service: Device service dependency

    Returns:
        JSON with updated device details
    """
    # Check user role
    if user.get("role") not in ["admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update devices",
        )

    try:
        from routeros_mcp.domain.models import DeviceUpdate, CredentialCreate
        
        # Build device update
        update_fields = {}
        if device_data.name is not None:
            update_fields["name"] = device_data.name
        if device_data.hostname is not None:
            update_fields["management_ip"] = device_data.hostname
        if device_data.port is not None:
            update_fields["management_port"] = device_data.port
        
        if update_fields:
            device = await device_service.update_device(
                device_id=device_id,
                updates=DeviceUpdate(**update_fields),
            )
        else:
            device = await device_service.get_device(device_id)
        
        # Update credentials if provided
        if device_data.username is not None and device_data.password is not None:
            await device_service.add_credential(
                CredentialCreate(
                    device_id=device_id,
                    credential_type="rest",
                    username=device_data.username,
                    password=device_data.password,
                )
            )

        return JSONResponse(
            content={
                "message": "Device updated successfully",
                "device": {
                    "id": device.id,
                    "name": device.name,
                    "management_ip": device.management_ip,
                    "management_port": device.management_port,
                    "environment": device.environment,
                    "status": device.status,
                },
            }
        )

    except DeviceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error updating device {device_id}: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update device. Correlation ID: {correlation_id}",
        )


@router.delete("/api/admin/devices/{device_id}")
async def delete_device(
    device_id: str,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    device_service: Any = Depends(get_device_service),
) -> JSONResponse:
    """Delete a device and its credentials.

    Args:
        device_id: Device identifier
        user: Current authenticated user (must have admin role)
        device_service: Device service dependency

    Returns:
        JSON confirmation
    """
    # Check user role
    if user.get("role") not in ["admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to delete devices",
        )

    try:
        from sqlalchemy import delete as sql_delete
        from routeros_mcp.infra.db.models import Device as DeviceORM, Credential as CredentialORM
        
        # Verify device exists
        device = await device_service.get_device(device_id)
        
        # Delete credentials
        await device_service.session.execute(
            sql_delete(CredentialORM).where(CredentialORM.device_id == device_id)
        )
        
        # Delete device
        await device_service.session.execute(
            sql_delete(DeviceORM).where(DeviceORM.id == device_id)
        )
        
        await device_service.session.commit()
        
        logger.info(
            "Deleted device",
            extra={"device_id": device_id, "device_name": device.name},
        )

        return JSONResponse(
            content={
                "message": f"Device '{device.name}' deleted successfully",
                "device_id": device_id,
            }
        )

    except DeviceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error deleting device {device_id}: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete device. Correlation ID: {correlation_id}",
        )


@router.post("/api/admin/devices/{device_id}/test")
async def test_device_connectivity(
    device_id: str,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    device_service: Any = Depends(get_device_service),
) -> JSONResponse:
    """Test connectivity to a device.

    Args:
        device_id: Device identifier
        user: Current authenticated user
        device_service: Device service dependency

    Returns:
        JSON with connectivity test results
    """
    try:
        is_reachable, metadata = await device_service.check_connectivity(device_id)

        return JSONResponse(
            content={
                "device_id": device_id,
                "reachable": is_reachable,
                "metadata": metadata,
                "message": "Device is reachable" if is_reachable else "Device is not reachable",
            }
        )

    except DeviceNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error testing connectivity for device {device_id}: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test connectivity. Correlation ID: {correlation_id}",
        )


@router.get("/api/plans")
async def list_plans(
    status_filter: str | None = None,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    plan_service: Any = Depends(get_plan_service),
) -> JSONResponse:
    """Get list of plans with optional filtering.

    Args:
        status_filter: Optional status filter (pending/approved/executing/completed/failed/cancelled)
        user: Current authenticated user
        plan_service: Plan service dependency

    Returns:
        JSON list of plans
    """
    try:
        filters = {}
        if status_filter:
            filters["status"] = status_filter

        plans = await plan_service.list_plans(filters=filters)

        # Convert to JSON-serializable format
        plans_data = [
            {
                "id": plan["id"],
                "created_by": plan["created_by"],
                "tool_name": plan["tool_name"],
                "status": plan["status"],
                "summary": plan["summary"],
                "device_ids": plan["device_ids"],
                "created_at": plan["created_at"].isoformat(),
                "approved_by": plan.get("approved_by"),
                "approved_at": plan["approved_at"].isoformat() if plan.get("approved_at") else None,
            }
            for plan in plans
        ]

        return JSONResponse(content={"plans": plans_data})

    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error listing plans: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list plans. Correlation ID: {correlation_id}",
        )


@router.get("/api/plans/{plan_id}")
async def get_plan_detail(
    plan_id: str,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    plan_service: Any = Depends(get_plan_service),
) -> JSONResponse:
    """Get detailed information about a specific plan.

    Args:
        plan_id: Plan identifier
        user: Current authenticated user
        plan_service: Plan service dependency

    Returns:
        JSON plan details with preview
    """
    try:
        plan = await plan_service.get_plan(plan_id)

        # Convert to JSON-serializable format
        plan_data = {
            "id": plan["id"],
            "created_by": plan["created_by"],
            "tool_name": plan["tool_name"],
            "status": plan["status"],
            "summary": plan["summary"],
            "device_ids": plan["device_ids"],
            "changes": plan["changes"],
            "created_at": plan["created_at"].isoformat(),
            "approved_by": plan.get("approved_by"),
            "approved_at": plan["approved_at"].isoformat() if plan.get("approved_at") else None,
            "approval_token": plan.get("approval_token"),
            "approval_token_expires_at": (
                plan["approval_token_expires_at"].isoformat()
                if plan.get("approval_token_expires_at")
                else None
            ),
        }

        return JSONResponse(content=plan_data)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error getting plan {plan_id}: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get plan. Correlation ID: {correlation_id}",
        )


@router.post("/api/plans/{plan_id}/approve")
async def approve_plan(
    plan_id: str,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    plan_service: Any = Depends(get_plan_service),
) -> JSONResponse:
    """Approve a plan and generate approval token.

    Args:
        plan_id: Plan identifier
        user: Current authenticated user (must have admin role)
        plan_service: Plan service dependency

    Returns:
        JSON with approval token and expiration
    """
    # Check user role
    if user.get("role") not in ["admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to approve plans",
        )

    try:
        approved_by = user.get("sub", "anonymous")
        result = await plan_service.approve_plan(
            plan_id=plan_id,
            approved_by=approved_by,
        )

        return JSONResponse(
            content={
                "message": "Plan approved successfully",
                "plan_id": plan_id,
                "approval_token": result["approval_token"],
                "expires_at": result["expires_at"].isoformat(),
            }
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error approving plan {plan_id}: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to approve plan. Correlation ID: {correlation_id}",
        )


@router.post("/api/plans/{plan_id}/reject")
async def reject_plan(
    plan_id: str,
    rejection: RejectionRequest,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    plan_service: Any = Depends(get_plan_service),
) -> JSONResponse:
    """Reject a plan with a reason.

    Args:
        plan_id: Plan identifier
        rejection: Rejection request with reason
        user: Current authenticated user (must have admin role)
        plan_service: Plan service dependency

    Returns:
        JSON confirmation
    """
    # Check user role
    if user.get("role") not in ["admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to reject plans",
        )

    try:
        # Update plan status to cancelled
        from routeros_mcp.domain.models import PlanStatus

        await plan_service.update_plan_status(
            plan_id=plan_id,
            new_status=PlanStatus.CANCELLED,
            user_sub=user.get("sub", "anonymous"),
            metadata={"rejection_reason": rejection.reason},
        )

        return JSONResponse(
            content={
                "message": "Plan rejected successfully",
                "plan_id": plan_id,
                "reason": rejection.reason,
            }
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error rejecting plan {plan_id}: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reject plan. Correlation ID: {correlation_id}",
        )


@router.get("/api/admin/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    job_service: Any = Depends(get_job_service),
) -> JSONResponse:
    """Get job status and progress.

    Args:
        job_id: Job identifier
        user: Current authenticated user (must have admin or operator role)
        job_service: Job service dependency

    Returns:
        JSON with job status, progress, and results
    """
    # Check user role - job status may contain sensitive infrastructure details
    if user.get("role") not in ["admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view job status",
        )

    try:
        job = await job_service.get_job(job_id)

        # Calculate progress percentage
        total_devices = len(job["device_ids"])
        progress_percent = 0
        
        if job["status"] == "success":
            progress_percent = 100
        elif job["status"] in ["running", "cancelled"]:
            # Try to parse result_summary to get devices processed.
            #
            # IMPORTANT: This logic depends on the exact string format produced by the
            # job execution code (execute_job in JobService). The expected formats are:
            #   - "Cancelled after processing X/Y devices in A/B batches"
            #   - "Cancelled before starting: 0/Y devices, 0/Z batches processed"
            #   - "Completed X devices in Y batches"
            # Any change to the result_summary wording or structure MUST be coordinated
            # with this parsing logic; otherwise, progress_percent will remain 0 and a
            # warning will be logged.
            result_summary = job.get("result_summary", "")
            if result_summary:
                matched_progress = False
                try:
                    # Match "X/Y devices" first, e.g. "10/20 devices"
                    match = re.search(r'(\d+)/(\d+)\s+devices', result_summary)
                    if match:
                        processed = int(match.group(1))
                        matched_progress = True
                        progress_percent = (
                            int((processed / total_devices) * 100) if total_devices > 0 else 0
                        )
                    else:
                        # Try alternative format "Completed X devices"
                        match = re.search(r'Completed\s+(\d+)\s+devices', result_summary)
                        if match:
                            processed = int(match.group(1))
                            matched_progress = True
                            progress_percent = (
                                int((processed / total_devices) * 100) if total_devices > 0 else 0
                            )
                except (ValueError, AttributeError):
                    # If parsing fails due to an unexpected numeric/attribute issue,
                    # keep progress_percent at 0 but emit a warning for observability.
                    logger.warning(
                        "Failed to parse progress from result_summary due to exception; "
                        "progress defaulted to 0",
                        extra={"job_id": job_id, "result_summary": result_summary},
                    )
                else:
                    if not matched_progress:
                        # The result_summary format did not match any known patterns.
                        # This commonly indicates that result_summary was changed
                        # without updating this parsing logic.
                        logger.warning(
                            "Unable to infer progress from result_summary; "
                            "no known patterns matched and progress defaulted to 0",
                            extra={"job_id": job_id, "result_summary": result_summary},
                        )

        job_data = {
            "job_id": job["job_id"],
            "plan_id": job["plan_id"],
            "job_type": job["job_type"],
            "status": job["status"],
            "progress_percent": progress_percent,
            "device_ids": job["device_ids"],
            "total_devices": total_devices,
            "attempts": job["attempts"],
            "max_attempts": job["max_attempts"],
            "result_summary": job["result_summary"],
            "error_message": job["error_message"],
            "cancellation_requested": job["cancellation_requested"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
        }

        return JSONResponse(content=job_data)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error getting job {job_id}: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status. Correlation ID: {correlation_id}",
        )


@router.post("/api/admin/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    job_service: Any = Depends(get_job_service),
) -> JSONResponse:
    """Request cancellation of a running job.

    Args:
        job_id: Job identifier
        user: Current authenticated user (must have admin or operator role)
        job_service: Job service dependency

    Returns:
        JSON confirmation with updated job status
    """
    # Check user role
    if user.get("role") not in ["admin", "operator"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to cancel jobs",
        )

    try:
        job = await job_service.request_cancellation(job_id)

        return JSONResponse(
            content={
                "message": "Job cancellation requested",
                "job_id": job_id,
                "status": job["status"],
                "cancellation_requested": job["cancellation_requested"],
            }
        )

    except ValueError as e:
        message = str(e)
        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        )
    except Exception as e:
        from routeros_mcp.infra.observability.logging import get_correlation_id
        correlation_id = get_correlation_id()
        logger.error(
            f"Error cancelling job {job_id}: {e}",
            exc_info=True,
            extra={"correlation_id": correlation_id}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel job. Correlation ID: {correlation_id}",
        )


__all__ = ["router"]
