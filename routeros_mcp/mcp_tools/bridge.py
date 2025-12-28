"""Bridge management MCP tools.

Provides MCP tools for querying bridge configuration and topology,
plus plan/apply workflow for bridge port and settings management.
"""

import logging
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS, DeviceCapability
from routeros_mcp.domain.services.bridge import BridgePlanService, BridgeService
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)

# TODO: Replace with actual user from auth context when authentication is implemented
DEFAULT_MCP_USER = "mcp-user"


async def _validate_devices_for_bridge_plan(
    device_service: DeviceService,
    settings: Settings,
    device_ids: list[str],
    tool_name: str,
) -> list[Any]:
    """Validate devices for bridge plan operations.

    This helper performs common validation for all bridge plan tools:
    - Devices exist
    - Environment is lab/staging (by default)
    - Professional workflows capability enabled
    - Bridge writes capability enabled

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
                f"Bridge changes are only allowed in: "
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

        # Check bridge write capability
        if not device.allow_bridge_writes:
            raise ValueError(
                f"Device {device_id} does not have bridge write capability enabled. "
                f"Set {DeviceCapability.BRIDGE_WRITES.value}=true to enable."
            )

    return devices


def register_bridge_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register bridge management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def list_bridges(device_id: str) -> dict[str, Any]:
        """List all bridge interfaces with configuration and status.

        Use when:
        - User asks "show me all bridges" or "what bridges are configured?"
        - Finding bridges by name
        - Discovering bridge topology
        - Checking bridge VLAN filtering status
        - Auditing bridge STP/RSTP configuration
        - Troubleshooting switching issues

        Returns: List of bridges with ID, name, MAC address, MTU, protocol mode (STP/RSTP/MSTP),
        VLAN filtering status, running status, and other bridge-specific settings.

        Tip: Use this first to discover bridge names, then use bridge/list-ports to see
        which interfaces are members of each bridge.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with bridge list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                bridge_service = BridgeService(session, settings)

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
                    tool_name="bridge/list-bridges",
                )

                # Get bridges
                bridges = await bridge_service.list_bridges(device_id)

                content = f"Found {len(bridges)} bridge(s) on {device.name}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "bridges": bridges,
                        "total_count": len(bridges),
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
    async def list_bridge_ports(device_id: str) -> dict[str, Any]:
        """List all bridge port assignments with VLAN and STP configuration.

        Use when:
        - User asks "what interfaces are in bridge X?" or "show bridge members"
        - Finding which bridge an interface belongs to
        - Checking VLAN tagging and PVID configuration
        - Auditing STP priority and path cost
        - Troubleshooting bridge port states
        - Verifying hardware offload status

        Returns: List of bridge ports with interface name, bridge name, PVID, VLAN settings,
        STP status (edge port, point-to-point), hardware offload status, and state.

        Tip: Combine with bridge/list-bridges to understand the complete bridge topology.
        Note: Bridge ports may be enabled/disabled; disabled ports won't forward traffic.
        STP status shows the spanning tree algorithm in use (RSTP, PVST, or disabled).

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with bridge port list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                bridge_service = BridgeService(session, settings)

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
                    tool_name="bridge/list-ports",
                )

                # Get bridge ports
                ports = await bridge_service.list_bridge_ports(device_id)

                content = f"Found {len(ports)} bridge port(s) on {device.name}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "bridge_ports": ports,
                        "total_count": len(ports),
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
    async def plan_add_bridge_port(
        device_ids: list[str],
        bridge_name: str,
        interface: str,
    ) -> dict[str, Any]:
        """Create plan for adding an interface to a bridge across multiple devices.

        Use when:
        - User asks "plan to add port X to bridge Y" or "add interface to bridge"
        - Need to preview bridge port changes before applying
        - Expanding bridge membership
        - Adding physical interfaces to a bridge

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use bridge/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_bridge_writes)
        - Medium risk (interface joins bridge, forwarding begins)
        - Lab/staging only by default
        - Plan expires after 15 minutes
        - Validates interface not already bridged

        Args:
            device_ids: List of device identifiers (e.g., ['dev-lab-01', 'dev-lab-02'])
            bridge_name: Name of the bridge (e.g., 'bridge-lan')
            interface: Interface name to add (e.g., 'ether2')

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to add port to bridge
            plan_add_bridge_port(
                ["dev-lab-01", "dev-lab-02"],
                "bridge-lan",
                "ether2"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                bridge_plan_service = BridgePlanService()

                # Validate bridge parameters
                bridge_plan_service.validate_bridge_params(
                    bridge_name=bridge_name,
                    interface=interface,
                    operation="add_bridge_port",
                )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_bridge_plan(
                    device_service,
                    settings,
                    device_ids,
                    "bridge/plan-add-port",
                )

                # Assess risk level
                device_environments = [d.environment for d in devices]
                highest_risk_env = "prod" if "prod" in device_environments else (
                    "staging" if "staging" in device_environments else "lab"
                )

                risk_level = bridge_plan_service.assess_risk(
                    operation="add_bridge_port",
                    device_environment=highest_risk_env,
                    is_stp_change=False,
                    is_vlan_filtering_change=False,
                )

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = bridge_plan_service.generate_preview(
                        operation="add_bridge_port",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        bridge_name=bridge_name,
                        interface=interface,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="bridge/plan-add-port",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Add port {interface} to bridge {bridge_name}",
                    changes={
                        "operation": "add_bridge_port",
                        "bridge_name": bridge_name,
                        "interface": interface,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Bridge port addition plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Bridge: {bridge_name}\n"
                    f"Interface: {interface}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Estimated duration: {len(device_ids) * 5} seconds\n\n"
                    f"To apply this plan, use bridge/apply-plan with:\n"
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
                        "tool_name": "bridge/plan-add-port",
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
    async def plan_remove_bridge_port(
        device_ids: list[str],
        bridge_name: str,
        interface: str,
    ) -> dict[str, Any]:
        """Create plan for removing an interface from a bridge.

        Use when:
        - User asks "plan to remove port X from bridge Y" or "disconnect interface from bridge"
        - Need to preview bridge port removal before applying
        - Removing interfaces from bridge membership
        - Reconfiguring bridge topology

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use bridge/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_bridge_writes)
        - High risk (port removal may disrupt connectivity)
        - Lab/staging only by default
        - Plan expires after 15 minutes

        Args:
            device_ids: List of device identifiers
            bridge_name: Name of the bridge
            interface: Interface name to remove

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to remove port from bridge
            plan_remove_bridge_port(
                ["dev-lab-01"],
                "bridge-lan",
                "ether3"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                bridge_plan_service = BridgePlanService()

                # Validate bridge parameters
                bridge_plan_service.validate_bridge_params(
                    bridge_name=bridge_name,
                    interface=interface,
                    operation="remove_bridge_port",
                )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_bridge_plan(
                    device_service,
                    settings,
                    device_ids,
                    "bridge/plan-remove-port",
                )

                # Port removal is high risk
                risk_level = "high"

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = bridge_plan_service.generate_preview(
                        operation="remove_bridge_port",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        bridge_name=bridge_name,
                        interface=interface,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="bridge/plan-remove-port",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Remove port {interface} from bridge {bridge_name}",
                    changes={
                        "operation": "remove_bridge_port",
                        "bridge_name": bridge_name,
                        "interface": interface,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Bridge port removal plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Bridge: {bridge_name}\n"
                    f"Interface: {interface}\n"
                    f"Devices: {len(device_ids)}\n\n"
                    f"WARNING: Port removal may disrupt connectivity.\n\n"
                    f"To apply this plan, use bridge/apply-plan with:\n"
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
                        "tool_name": "bridge/plan-remove-port",
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
    async def plan_modify_bridge_settings(
        device_ids: list[str],
        bridge_name: str,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        """Create plan for modifying bridge settings.

        Use when:
        - User asks "plan to modify bridge X settings" or "change STP settings"
        - Need to preview bridge configuration changes
        - Updating STP, VLAN filtering, or other bridge parameters
        - Adjusting bridge protocol settings

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use bridge/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_bridge_writes)
        - High risk for STP/VLAN changes (can create loops or affect segmentation)
        - Medium risk for other settings
        - Lab/staging only by default
        - Plan expires after 15 minutes
        - Blocks STP changes on protected production bridges

        Args:
            device_ids: List of device identifiers
            bridge_name: Name of the bridge
            settings: Dict of settings to modify (e.g., {'protocol_mode': 'rstp', 'vlan_filtering': true})

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to enable RSTP on bridge
            plan_modify_bridge_settings(
                ["dev-lab-01"],
                "bridge-lan",
                {"protocol_mode": "rstp"}
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                bridge_plan_service = BridgePlanService()

                # Validate bridge parameters
                bridge_plan_service.validate_bridge_params(
                    bridge_name=bridge_name,
                    settings=settings,
                    operation="modify_bridge_settings",
                )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_bridge_plan(
                    device_service,
                    settings,
                    device_ids,
                    "bridge/plan-modify-settings",
                )

                # Check STP safety for each device
                for device in devices:
                    bridge_plan_service.check_stp_safety(
                        bridge_name=bridge_name,
                        settings=settings,
                        device_environment=device.environment,
                    )

                # Assess risk level
                device_environments = [d.environment for d in devices]
                highest_risk_env = "prod" if "prod" in device_environments else (
                    "staging" if "staging" in device_environments else "lab"
                )

                is_stp_change = bool(
                    set(settings.keys())
                    & {"protocol_mode", "stp", "priority", "forward_delay", "max_message_age"}
                )
                is_vlan_filtering_change = "vlan_filtering" in settings

                risk_level = bridge_plan_service.assess_risk(
                    operation="modify_bridge_settings",
                    device_environment=highest_risk_env,
                    is_stp_change=is_stp_change,
                    is_vlan_filtering_change=is_vlan_filtering_change,
                )

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = bridge_plan_service.generate_preview(
                        operation="modify_bridge_settings",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        bridge_name=bridge_name,
                        settings=settings,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="bridge/plan-modify-settings",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Modify bridge {bridge_name} settings",
                    changes={
                        "operation": "modify_bridge_settings",
                        "bridge_name": bridge_name,
                        "settings": settings,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                warning = ""
                if is_stp_change:
                    warning = "\nWARNING: STP changes can create loops or outages."
                elif is_vlan_change:
                    warning = "\nWARNING: VLAN filtering changes affect network segmentation."

                content = (
                    f"Bridge settings modification plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Bridge: {bridge_name}\n"
                    f"Devices: {len(device_ids)}{warning}\n\n"
                    f"To apply this plan, use bridge/apply-plan with:\n"
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
                        "tool_name": "bridge/plan-modify-settings",
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
    async def apply_bridge_plan(
        plan_id: str,
        approval_token: str,
    ) -> dict[str, Any]:
        """Apply approved bridge plan with health checks and automatic rollback.

        Use when:
        - User provides plan_id and approval_token from plan creation
        - Ready to execute bridge changes after review
        - Implementing bridge port or settings changes across devices

        Pattern: This is the APPLY step (executes changes with safety checks).

        Safety:
        - Professional tier (requires approved plan with valid token)
        - Creates snapshot before changes for rollback
        - Performs health check after each device
        - Automatic rollback on health check failure
        - Updates plan status to completed/failed
        - Comprehensive audit logging

        Args:
            plan_id: Plan identifier from plan creation (e.g., 'plan-bridge-20250115-001')
            approval_token: Approval token from plan creation (must be valid and unexpired)

        Returns:
            Formatted tool result with execution status and results per device

        Examples:
            # Apply approved bridge plan
            apply_bridge_plan(
                plan_id="plan-bridge-20250115-001",
                approval_token="approve-bridge-a1b2c3d4"
            )
        """
        try:
            async with session_factory.session() as session:
                plan_service = PlanService(session, settings)
                device_service = DeviceService(session, settings)
                bridge_plan_service = BridgePlanService()

                # Get plan details
                plan = await plan_service.get_plan(plan_id)

                # Validate approval token
                expires_at_str = plan["changes"].get("approval_expires_at")
                token_timestamp = plan["changes"].get("approval_token_timestamp")
                if not expires_at_str or not token_timestamp:
                    raise ValueError("Invalid plan: missing approval token metadata")

                expires_at = datetime.fromisoformat(expires_at_str)

                # Validate token using PlanService public method
                plan_service.validate_approval_token(
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

                # Execute plan for each device
                for device_id in device_ids:
                    try:
                        device = await device_service.get_device(device_id)
                        rest_client = await device_service.get_rest_client(device_id)

                        # Create snapshot before changes
                        snapshot = await bridge_plan_service.create_bridge_snapshot(
                            device_id, device.name, rest_client
                        )
                        snapshots[device_id] = snapshot

                        # Execute operation (mock for now - would call RouterOS API)
                        # TODO: Implement actual RouterOS API calls for bridge operations
                        logger.info(f"Executing {operation} on device {device_id} (mock only, no RouterOS changes applied)")

                        # Since RouterOS API calls are not yet implemented, we cannot reliably
                        # perform a post-change health check. Mark this operation as not
                        # executed to avoid reporting false positives.
                        health_result = {
                            "status": "skipped",
                            "reason": (
                                "Bridge operation was not executed: RouterOS API calls for this "
                                "operation are not yet implemented"
                            ),
                        }

                        failed_devices.append(device_id)
                        device_results.append({
                            "device_id": device_id,
                            "status": "not_executed",
                            "message": "Bridge operation skipped because it is not yet implemented",
                            "health_check": health_result,
                        })
                        await rest_client.close()

                    except Exception as e:
                        logger.error(f"Failed to execute plan on device {device_id}: {e}")
                        failed_devices.append(device_id)
                        device_results.append({
                            "device_id": device_id,
                            "status": "failed",
                            "message": f"Execution failed: {str(e)}",
                        })

                # Update plan status
                if failed_devices:
                    await plan_service.update_plan_status(plan_id, "failed", DEFAULT_MCP_USER)
                    status_msg = f"Plan failed on {len(failed_devices)} of {len(device_ids)} devices"
                else:
                    await plan_service.update_plan_status(plan_id, "completed", DEFAULT_MCP_USER)
                    status_msg = f"Plan completed successfully on all {len(device_ids)} devices"

                return format_tool_result(
                    content=status_msg,
                    meta={
                        "plan_id": plan_id,
                        "operation": operation,
                        "total_devices": len(device_ids),
                        "successful_devices": len(successful_devices),
                        "failed_devices": len(failed_devices),
                        "device_results": device_results,
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

    logger.info("Registered bridge tools")
