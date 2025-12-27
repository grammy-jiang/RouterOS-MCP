"""Routing management MCP tools.

Provides MCP tools for querying routing table information and planning
static route changes with plan/apply workflow.
"""

import logging
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS, DeviceCapability
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.domain.services.routing import RoutingService
from routeros_mcp.domain.services.routing_plan import RoutingPlanService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)

# TODO: Replace with actual user from auth context when authentication is implemented
DEFAULT_MCP_USER = "mcp-user"


def register_routing_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register routing management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def get_routing_summary(device_id: str) -> dict[str, Any]:
        """Get routing table summary with route counts and key routes.

        Use when:
        - User asks "show me routes" or "what's the default gateway?"
        - Overview of routing configuration
        - Counting routes by type (static, connected, dynamic)
        - Finding default route quickly
        - Before planning routing changes
        - Troubleshooting routing issues (verifying routes exist)

        Returns: Total route count, counts by type (static/connected/dynamic), list of routes 
        with destination, gateway, distance, comment.

        Tip: For detailed single route info, use routing/get-route.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with routing summary
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                routing_service = RoutingService(session, settings)

                # Get device first to validate it exists
                device = await device_service.get_device(device_id)

                # Authorization check - fundamental tier, read-only
                check_tool_authorization(
                    device_environment=device.environment,
                    service_environment=settings.environment,
                    tool_tier=ToolTier.FUNDAMENTAL,
                    allow_advanced_writes=device.allow_advanced_writes,
                    allow_professional_workflows=device.allow_professional_workflows,
                    device_id=device_id,
                    tool_name="routing/get-summary",
                )

                # Get routing summary
                summary = await routing_service.get_routing_summary(device_id)

                content = (
                    f"Routing table: {summary['total_routes']} routes "
                    f"({summary['static_routes']} static, "
                    f"{summary['connected_routes'] + summary['dynamic_routes']} connected/dynamic)"
                )

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **summary,
                    },
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    @mcp.tool()
    async def get_route(device_id: str, route_id: str) -> dict[str, Any]:
        """Get detailed information about a specific route.

        Use when:
        - User asks about a specific route destination
        - Investigating route properties (scope, distance, active/inactive status)
        - Verifying route configuration
        - Detailed troubleshooting of routing behavior

        Returns: Complete route details including destination, gateway, distance, scope, 
        active status, dynamic flag.

        Note: Requires route ID (from routing/get-summary).

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            route_id: Route ID (e.g., '*3')

        Returns:
            Formatted tool result with route details
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                routing_service = RoutingService(session, settings)

                # Get device first to validate it exists
                device = await device_service.get_device(device_id)

                # Authorization check - fundamental tier, read-only
                check_tool_authorization(
                    device_environment=device.environment,
                    service_environment=settings.environment,
                    tool_tier=ToolTier.FUNDAMENTAL,
                    allow_advanced_writes=device.allow_advanced_writes,
                    allow_professional_workflows=device.allow_professional_workflows,
                    device_id=device_id,
                    tool_name="routing/get-route",
                )

                # Get route
                route = await routing_service.get_route(device_id, route_id)

                if not route:
                    # Provide helpful message if route not found
                    # First get the routing summary to see available routes
                    summary = await routing_service.get_routing_summary(device_id)
                    route_count = summary.get("total_routes", 0)
                    
                    if route_count > 0:
                        return format_tool_result(
                            content=(
                                f"Route {route_id} not found on {device_id}. "
                                f"Device has {route_count} routes. "
                                f"Use routing/get-summary to see available routes."
                            ),
                            is_error=False,
                            meta={
                                "device_id": device_id,
                                "route_id": route_id,
                                "found": False,
                                "available_routes": route_count,
                            },
                        )
                    else:
                        return format_tool_result(
                            content=f"No routes found on {device_id}",
                            is_error=False,
                            meta={
                                "device_id": device_id,
                                "found": False,
                            },
                        )

                # Safely access route keys
                dst_address = route.get("dst_address", "")
                gateway = route.get("gateway", "")
                content = f"Route: {dst_address} via {gateway}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "route": route,
                    },
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    def _normalize_empty_string(value: str) -> str | None:
        """Convert empty strings to None for consistency.

        Args:
            value: String value to normalize

        Returns:
            None if value is empty string, otherwise the original value
        """
        return None if value == "" else value

    async def _validate_devices_for_routing_plan(
        device_service: DeviceService,
        settings: Settings,
        device_ids: list[str],
        tool_name: str,
    ) -> list[Any]:
        """Validate devices for routing plan operations.

        This helper performs common validation for all routing plan tools:
        - Devices exist
        - Environment is lab/staging (by default)
        - Professional workflows capability enabled
        - Routing writes capability enabled

        Args:
            device_service: Device service instance
            settings: Application settings
            device_ids: List of device identifiers
            tool_name: Name of the tool being executed

        Returns:
            List of validated device models

        Raises:
            ValueError: If validation fails
        """
        devices = []
        for device_id in device_ids:
            device = await device_service.get_device(device_id)
            devices.append(device)

            # Check environment (lab/staging by default)
            if device.environment not in PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS:
                raise ValueError(
                    f"Device {device_id} is in {device.environment} environment. "
                    f"Routing changes are only allowed in: "
                    f"{', '.join(PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS)}"
                )

            # Authorization check - professional tier
            check_tool_authorization(
                device_environment=device.environment,
                service_environment=settings.environment,
                tool_tier=ToolTier.PROFESSIONAL,
                allow_advanced_writes=device.allow_advanced_writes,
                allow_professional_workflows=device.allow_professional_workflows,
                device_id=device_id,
                tool_name=tool_name,
            )

            # Check routing write capability
            if not device.allow_routing_writes:
                raise ValueError(
                    f"Device {device_id} does not have routing write capability enabled. "
                    f"Set {DeviceCapability.ROUTING_WRITES.value}=true to enable."
                )

        return devices

    @mcp.tool()
    async def plan_add_static_route(
        device_ids: list[str],
        dst_address: str,
        gateway: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        """Create plan for adding a static route across multiple devices.

        Use when:
        - User asks "plan to add route to X" or "prepare to route traffic via Y"
        - Need to preview routing changes before applying
        - Adding static routes for network connectivity
        - Creating routing policies

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use routing/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_routing_writes)
        - High/medium risk depending on destination and environment
        - Lab/staging only by default
        - Plan expires after 15 minutes
        - Blocks default routes (0.0.0.0/0, ::/0)
        - Warns on management network overlap
        - Creates Plan entity with risk assessment

        Args:
            device_ids: List of device identifiers (e.g., ['dev-lab-01', 'dev-lab-02'])
            dst_address: Destination network in CIDR notation (e.g., "10.0.0.0/8")
            gateway: Gateway IP address (optional if using interface route)
            comment: Optional route comment

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to add static route
            plan_add_static_route(
                ["dev-lab-01", "dev-lab-02"],
                "10.0.0.0/8",
                "192.168.1.1",
                "Route to internal network"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                routing_plan_service = RoutingPlanService()

                # Validate route parameters first
                routing_plan_service.validate_route_params(
                    dst_address=dst_address,
                    gateway=_normalize_empty_string(gateway),
                    comment=_normalize_empty_string(comment),
                )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_routing_plan(
                    device_service,
                    settings,
                    device_ids,
                    "routing/plan-add-static-route",
                )

                # Assess risk level based on destination and highest risk environment
                device_environments = [d.environment for d in devices]
                highest_risk_env = "prod" if "prod" in device_environments else (
                    "staging" if "staging" in device_environments else "lab"
                )

                # Use first device's management IP for risk assessment
                management_ip = devices[0].management_ip if devices else None

                risk_level = routing_plan_service.assess_risk(
                    dst_address=dst_address,
                    device_environment=highest_risk_env,
                    management_ip=management_ip,
                )

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = routing_plan_service.generate_preview(
                        operation="add_static_route",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        dst_address=dst_address,
                        gateway=_normalize_empty_string(gateway),
                        comment=_normalize_empty_string(comment),
                        management_ip=device.management_ip,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="routing/plan-add-static-route",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Add static route: dst={dst_address} gateway={gateway}",
                    changes={
                        "operation": "add_static_route",
                        "dst_address": dst_address,
                        "gateway": _normalize_empty_string(gateway),
                        "comment": _normalize_empty_string(comment),
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Static route plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Destination: {dst_address}\n"
                    f"Gateway: {gateway or '(interface route)'}\n"
                    f"Estimated duration: {len(device_ids) * 5} seconds\n\n"
                    f"To apply this plan, use routing/apply-plan with:\n"
                    f"  plan_id: {plan['plan_id']}\n"
                    f"  approval_token: {plan['approval_token']}"
                )

                return format_tool_result(
                    content=content,
                    meta={
                        "correlation_id": f"corr-{plan['plan_id']}",
                        "plan_id": plan["plan_id"],
                        "approval_token": plan["approval_token"],
                        "approval_expires_at": plan["approval_expires_at"],
                        "risk_level": risk_level,
                        "tool_name": "routing/plan-add-static-route",
                        "device_count": len(device_ids),
                        "devices": device_previews,
                    },
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    @mcp.tool()
    async def plan_modify_static_route(
        device_ids: list[str],
        route_id: str,
        dst_address: str = "",
        gateway: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        """Create plan for modifying an existing static route.

        Use when:
        - User asks "plan to modify route X" or "update route Y gateway"
        - Need to change existing static routes
        - Adjusting routing policies
        - Updating route properties

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use routing/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_routing_writes)
        - High risk (route modification may affect active traffic)
        - Lab/staging only by default
        - Plan expires after 15 minutes
        - Blocks default routes
        - Warns on management network overlap

        Args:
            device_ids: List of device identifiers
            route_id: ID of route to modify (e.g., "*1")
            dst_address: Optional new destination address
            gateway: Optional new gateway
            comment: Optional new comment

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to modify route gateway
            plan_modify_static_route(
                ["dev-lab-01"],
                "*5",
                gateway="192.168.1.2",
                comment="Updated gateway"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                routing_plan_service = RoutingPlanService()

                # Build modifications dict
                modifications = {}
                if dst_address:
                    modifications["dst_address"] = dst_address
                if gateway:
                    modifications["gateway"] = gateway
                if comment:
                    modifications["comment"] = comment

                if not modifications:
                    raise ValueError("At least one modification must be specified")

                # Validate modified destination address if provided
                if "dst_address" in modifications:
                    routing_plan_service.validate_route_params(
                        dst_address=modifications["dst_address"],
                        gateway=modifications.get("gateway"),
                    )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_routing_plan(
                    device_service,
                    settings,
                    device_ids,
                    "routing/plan-modify-static-route",
                )

                # Route modification is always high risk
                risk_level = "high"

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = routing_plan_service.generate_preview(
                        operation="modify_static_route",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        route_id=route_id,
                        modifications=modifications,
                        management_ip=device.management_ip,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="routing/plan-modify-static-route",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Modify static route {route_id}",
                    changes={
                        "operation": "modify_static_route",
                        "route_id": route_id,
                        "modifications": modifications,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Static route modification plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Route ID: {route_id}\n"
                    f"Modifications: {', '.join(modifications.keys())}\n\n"
                    f"To apply this plan, use routing/apply-plan with:\n"
                    f"  plan_id: {plan['plan_id']}\n"
                    f"  approval_token: {plan['approval_token']}"
                )

                return format_tool_result(
                    content=content,
                    meta={
                        "correlation_id": f"corr-{plan['plan_id']}",
                        "plan_id": plan["plan_id"],
                        "approval_token": plan["approval_token"],
                        "approval_expires_at": plan["approval_expires_at"],
                        "risk_level": risk_level,
                        "tool_name": "routing/plan-modify-static-route",
                        "device_count": len(device_ids),
                        "devices": device_previews,
                    },
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    @mcp.tool()
    async def plan_remove_static_route(
        device_ids: list[str],
        route_id: str,
    ) -> dict[str, Any]:
        """Create plan for removing a static route.

        Use when:
        - User asks "plan to remove route X" or "delete route Y"
        - Need to clean up obsolete routes
        - Removing temporary routing rules
        - Simplifying routing configuration

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use routing/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_routing_writes)
        - High risk (route removal may make destination unreachable)
        - Lab/staging only by default
        - Plan expires after 15 minutes
        - Validates route exists before creating plan

        Args:
            device_ids: List of device identifiers
            route_id: ID of route to remove (e.g., "*1")

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to remove static route
            plan_remove_static_route(
                ["dev-lab-01", "dev-lab-02"],
                "*5"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                routing_plan_service = RoutingPlanService()

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_routing_plan(
                    device_service,
                    settings,
                    device_ids,
                    "routing/plan-remove-static-route",
                )

                # Route removal is always high risk
                risk_level = "high"

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = routing_plan_service.generate_preview(
                        operation="remove_static_route",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        route_id=route_id,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="routing/plan-remove-static-route",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Remove static route {route_id}",
                    changes={
                        "operation": "remove_static_route",
                        "route_id": route_id,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Static route removal plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Route ID: {route_id}\n\n"
                    f"WARNING: Removing routes may make destinations unreachable.\n\n"
                    f"To apply this plan, use routing/apply-plan with:\n"
                    f"  plan_id: {plan['plan_id']}\n"
                    f"  approval_token: {plan['approval_token']}"
                )

                return format_tool_result(
                    content=content,
                    meta={
                        "correlation_id": f"corr-{plan['plan_id']}",
                        "plan_id": plan["plan_id"],
                        "approval_token": plan["approval_token"],
                        "approval_expires_at": plan["approval_expires_at"],
                        "risk_level": risk_level,
                        "tool_name": "routing/plan-remove-static-route",
                        "device_count": len(device_ids),
                        "devices": device_previews,
                    },
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    @mcp.tool()
    async def apply_routing_plan(
        plan_id: str,
        approval_token: str,
    ) -> dict[str, Any]:
        """Apply approved routing plan with health checks and automatic rollback.

        Use when:
        - User provides plan_id and approval_token from plan creation
        - Ready to execute routing changes after review
        - Implementing static route changes across devices

        Pattern: This is the APPLY step (executes changes with safety checks).

        Safety:
        - Professional tier (requires approved plan with valid token)
        - Creates snapshot before changes for rollback
        - Performs health check after each device
        - Automatic rollback on health check failure
        - Updates plan status to completed/failed
        - Comprehensive audit logging

        Args:
            plan_id: Plan identifier from plan creation (e.g., 'plan-rt-20250115-001')
            approval_token: Approval token from plan creation (must be valid and unexpired)

        Returns:
            Formatted tool result with execution status and results per device

        Examples:
            # Apply approved routing plan
            apply_routing_plan(
                plan_id="plan-rt-20250115-001",
                approval_token="approve-rt-a1b2c3d4"
            )
        """
        try:
            async with session_factory.session() as session:
                plan_service = PlanService(session, settings)
                device_service = DeviceService(session, settings)
                routing_plan_service = RoutingPlanService()

                # Get plan details
                plan = await plan_service.get_plan(plan_id)

                # Validate approval token
                expires_at_str = plan["changes"].get("approval_expires_at")
                token_timestamp = plan["changes"].get("approval_token_timestamp")
                if not expires_at_str or not token_timestamp:
                    raise ValueError("Invalid plan: missing approval token metadata")

                expires_at = datetime.fromisoformat(expires_at_str)

                # Validate token using PlanService internal method
                plan_service._validate_approval_token(
                    plan_id, plan["created_by"], approval_token, expires_at, token_timestamp
                )

                # Check plan status
                if plan["status"] != "pending":
                    raise ValueError(
                        f"Plan cannot be applied from status '{plan['status']}'. "
                        f"Plan must be in 'pending' status."
                    )

                # Update plan status to executing
                await plan_service.update_plan_status(plan_id, "executing", DEFAULT_MCP_USER)

                # Get operation details from plan
                operation = plan["changes"].get("operation")
                if not operation:
                    raise ValueError("Invalid plan: missing operation type")

                device_ids = plan["device_ids"]
                device_results = []
                snapshots = {}
                failed_devices = []
                successful_devices = []

                # Process each device
                for device_id in device_ids:
                    device_result = {
                        "device_id": device_id,
                        "status": "pending",
                    }

                    rest_client = None
                    try:
                        # Get device
                        device = await device_service.get_device(device_id)
                        rest_client = await device_service.get_rest_client(device_id)

                        # Step 1: Create snapshot before changes
                        logger.info(f"Creating snapshot for device {device_id}")
                        snapshot = await routing_plan_service.create_routing_snapshot(
                            device_id, device.name, rest_client
                        )
                        snapshots[device_id] = snapshot
                        device_result["snapshot_id"] = snapshot["snapshot_id"]

                        # Step 2: Apply changes
                        logger.info(f"Applying changes to device {device_id}")
                        apply_result = await routing_plan_service.apply_plan(
                            device_id,
                            device.name,
                            operation,
                            plan["changes"],
                            rest_client,
                        )
                        device_result["apply_result"] = apply_result

                        if apply_result["status"] != "success":
                            device_result["status"] = "failed"
                            device_result["error"] = apply_result.get("error", "Apply failed")
                            failed_devices.append(device_id)
                            device_results.append(device_result)
                        else:
                            # Step 3: Perform health check
                            logger.info(f"Performing health check for device {device_id}")
                            health_check = await routing_plan_service.perform_health_check(
                                device_id, rest_client
                            )
                            device_result["health_check"] = health_check

                            if health_check["status"] != "healthy":
                                # Health check failed or degraded - rollback
                                logger.warning(
                                    f"Health check {health_check['status']} for device {device_id}, initiating rollback"
                                )
                                rollback_result = await routing_plan_service.rollback_from_snapshot(
                                    device_id, snapshot["data"], rest_client, operation
                                )
                                device_result["rollback"] = rollback_result
                                device_result["status"] = "rolled_back"
                                failed_devices.append(device_id)
                            else:
                                # Success
                                device_result["status"] = "success"
                                successful_devices.append(device_id)

                    except Exception as e:
                        logger.error(
                            f"Failed to process device {device_id}: {e}",
                            exc_info=True,
                        )
                        device_result["status"] = "failed"
                        device_result["error"] = str(e)

                        # Attempt rollback if snapshot exists
                        if device_id in snapshots:
                            try:
                                # rest_client may already be set, otherwise get a new one
                                if rest_client is None:
                                    rest_client = await device_service.get_rest_client(device_id)
                                rollback_result = await routing_plan_service.rollback_from_snapshot(
                                    device_id, snapshots[device_id]["data"], rest_client, operation
                                )
                                device_result["rollback"] = rollback_result
                                device_result["status"] = "rolled_back"
                            except Exception as rollback_error:
                                logger.error(
                                    f"Rollback failed for device {device_id}: {rollback_error}",
                                    exc_info=True,
                                )
                                device_result["rollback"] = {
                                    "status": "failed",
                                    "error": str(rollback_error),
                                }

                        failed_devices.append(device_id)

                    finally:
                        # Ensure REST client is always closed
                        if rest_client is not None:
                            try:
                                await rest_client.close()
                            except Exception as close_error:
                                logger.warning(
                                    f"Failed to close REST client for device {device_id}: {close_error}"
                                )

                    device_results.append(device_result)

                # Determine final plan status
                if len(successful_devices) == len(device_ids):
                    final_status = "completed"
                    content = (
                        f"Routing plan applied successfully to all {len(device_ids)} device(s).\n\n"
                        f"Operation: {operation}\n"
                        f"Successful: {len(successful_devices)}\n"
                        f"Failed: {len(failed_devices)}"
                    )
                elif len(successful_devices) > 0:
                    final_status = "failed"
                    content = (
                        f"Routing plan partially applied.\n\n"
                        f"Operation: {operation}\n"
                        f"Successful: {len(successful_devices)}\n"
                        f"Failed: {len(failed_devices)}\n\n"
                        f"Successful devices: {', '.join(successful_devices)}\n"
                        f"Failed devices: {', '.join(failed_devices)}"
                    )
                else:
                    final_status = "failed"
                    content = (
                        f"Routing plan failed on all devices.\n\n"
                        f"Operation: {operation}\n"
                        f"Failed: {len(failed_devices)}\n"
                        f"Failed devices: {', '.join(failed_devices)}"
                    )

                # Update plan status
                await plan_service.update_plan_status(plan_id, final_status, DEFAULT_MCP_USER)

                return format_tool_result(
                    content=content,
                    meta={
                        "plan_id": plan_id,
                        "operation": operation,
                        "device_count": len(device_ids),
                        "successful_count": len(successful_devices),
                        "failed_count": len(failed_devices),
                        "final_status": final_status,
                        "device_results": device_results,
                    },
                    is_error=(final_status == "failed" and len(successful_devices) == 0),
                )

        except MCPError as e:
            return format_tool_result(
                content=e.message,
                is_error=True,
                meta=e.data,
            )
        except Exception as e:
            error = map_exception_to_error(e)
            return format_tool_result(
                content=error.message,
                is_error=True,
                meta=error.data,
            )

    logger.info("Registered routing management tools")
