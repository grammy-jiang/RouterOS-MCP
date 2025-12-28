"""Admin API routes for browser-based UI.

Provides HTTP endpoints for device management, plan review, and approval
workflows. All endpoints require OIDC authentication.

See docs/09-operations-deployment-self-update-and-runbook.md for design.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse

from routeros_mcp.api.admin_models import RejectionRequest

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
    device_service = Depends(get_device_service),
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

        # Convert to JSON-serializable format
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
                "status": "online" if device.last_seen else "offline",
            }
            for device in devices
        ]

        return JSONResponse(content={"devices": devices_data})

    except Exception as e:
        logger.error(f"Error listing devices: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list devices",
        )


@router.get("/api/plans")
async def list_plans(
    status_filter: str | None = None,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    plan_service = Depends(get_plan_service),
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
        logger.error(f"Error listing plans: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list plans",
        )


@router.get("/api/plans/{plan_id}")
async def get_plan_detail(
    plan_id: str,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    plan_service = Depends(get_plan_service),
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
        logger.error(f"Error getting plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get plan",
        )


@router.post("/api/plans/{plan_id}/approve")
async def approve_plan(
    plan_id: str,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    plan_service = Depends(get_plan_service),
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
        logger.error(f"Error approving plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to approve plan",
        )


@router.post("/api/plans/{plan_id}/reject")
async def reject_plan(
    plan_id: str,
    rejection: RejectionRequest,
    user: dict[str, Any] = Depends(get_current_user_dep()),
    plan_service = Depends(get_plan_service),
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
        logger.error(f"Error rejecting plan {plan_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reject plan",
        )


__all__ = ["router"]
