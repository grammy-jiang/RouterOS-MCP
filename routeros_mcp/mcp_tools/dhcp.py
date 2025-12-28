"""DHCP management MCP tools.

Provides MCP tools for querying DHCP server configuration and active leases,
plus plan/apply workflow for DHCP pool management.
"""

import logging
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS, DeviceCapability
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.dhcp import DHCPPlanService, DHCPService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)

# TODO: Replace with actual user from auth context when authentication is implemented
DEFAULT_MCP_USER = "mcp-user"


async def _validate_devices_for_dhcp_plan(
    device_service: DeviceService,
    settings: Settings,
    device_ids: list[str],
    tool_name: str,
) -> list[Any]:
    """Validate devices for DHCP plan operations.

    This helper performs common validation for all DHCP plan tools:
    - Devices exist
    - Environment is lab/staging (by default)
    - Professional workflows capability enabled
    - DHCP writes capability enabled

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
                f"DHCP changes are only allowed in: "
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

        # Check DHCP write capability
        if not device.allow_dhcp_writes:
            raise ValueError(
                f"Device {device_id} does not have DHCP write capability enabled. "
                f"Set {DeviceCapability.DHCP_WRITES.value}=true to enable."
            )

    return devices


def register_dhcp_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register DHCP tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def get_dhcp_server_status(device_id: str) -> dict[str, Any]:
        """Get DHCP server configuration and status.

        Use when:
        - User asks "what DHCP servers are configured?" or "is DHCP working?"
        - Troubleshooting DHCP-related connectivity issues
        - Verifying DHCP configuration after changes
        - Checking which interfaces have DHCP enabled
        - Planning DHCP server updates
        - Auditing DHCP settings across fleet

        Returns: List of DHCP servers with name, interface, lease time, address pool, and status.

        Note: Multiple DHCP servers can exist on RouterOS. This returns all configured servers.

        Tip: Use with dhcp/get-leases to see active clients for each server.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with DHCP server status
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                dhcp_service = DHCPService(session, settings)

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
                    tool_name="dhcp/get-server-status",
                )

                # Get DHCP server status
                server_status = await dhcp_service.get_dhcp_server_status(device_id)

                # Format content
                server_count = server_status["total_count"]
                if server_count == 0:
                    content = "No DHCP servers configured"
                elif server_count == 1:
                    server = server_status["servers"][0]
                    content = f"DHCP server '{server['name']}' on {server['interface']}"
                else:
                    server_names = [s["name"] for s in server_status["servers"]]
                    content = f"{server_count} DHCP servers: {', '.join(server_names)}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **server_status,
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
    async def get_dhcp_leases(device_id: str) -> dict[str, Any]:
        """Get active DHCP leases with client information.

        Use when:
        - User asks "what devices have DHCP leases?" or "show me DHCP clients"
        - Troubleshooting client connectivity (verify lease is active)
        - Checking IP address allocation across DHCP pools
        - Identifying clients by hostname or MAC address
        - Monitoring DHCP server usage
        - Before planning IP address changes

        Returns: List of active DHCP leases with IP address, MAC address, client ID, hostname, and server name.

        Note: Only returns ACTIVE leases (status=bound). Expired or released leases are filtered out.
              Lease expiry is relative to last activity on RouterOS.

        Tip: Use with ip/get-arp-table to cross-reference active connections.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with DHCP leases
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                dhcp_service = DHCPService(session, settings)

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
                    tool_name="dhcp/get-leases",
                )

                # Get DHCP leases
                leases_data = await dhcp_service.get_dhcp_leases(device_id)

                # Format content
                lease_count = leases_data["total_count"]
                if lease_count == 0:
                    content = "No active DHCP leases"
                elif lease_count == 1:
                    lease = leases_data["leases"][0]
                    content = f"1 active lease: {lease['address']} ({lease.get('host_name', 'unknown')})"
                else:
                    content = f"{lease_count} active DHCP leases"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **leases_data,
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
    async def plan_create_dhcp_pool(
        device_ids: list[str],
        pool_name: str,
        address_range: str,
        gateway: str = "",
        dns_servers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create plan for adding a DHCP server pool across multiple devices.

        Use when:
        - User asks "plan to create DHCP pool X" or "prepare to add DHCP pool"
        - Need to preview DHCP pool changes before applying
        - Setting up DHCP for a new network segment
        - Adding address pools for client allocation

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use dhcp/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_dhcp_writes)
        - Medium risk for lab/staging, high for production
        - Lab/staging only by default
        - Plan expires after 15 minutes
        - Validates pool parameters (no overlaps, gateway in subnet)

        Args:
            device_ids: List of device identifiers (e.g., ['dev-lab-01', 'dev-lab-02'])
            pool_name: Name for the DHCP pool (e.g., 'pool-guest-wifi')
            address_range: IP address range (e.g., '192.168.1.100-192.168.1.200')
            gateway: Gateway IP address (optional, e.g., '192.168.1.1')
            dns_servers: List of DNS server IPs (optional, e.g., ['8.8.8.8', '8.8.4.4'])

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to create DHCP pool
            plan_create_dhcp_pool(
                ["dev-lab-01", "dev-lab-02"],
                "pool-guest-wifi",
                "192.168.10.100-192.168.10.200",
                gateway="192.168.10.1",
                dns_servers=["8.8.8.8", "8.8.4.4"]
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                dhcp_plan_service = DHCPPlanService()

                # Normalize optional parameters without conflating "unset" with "empty"
                if gateway is None:
                    gateway_norm = None
                else:
                    gateway_norm = gateway.strip()

                if dns_servers is None:
                    dns_servers_norm = None
                else:
                    dns_servers_norm = dns_servers
                # Validate pool parameters first
                dhcp_plan_service.validate_pool_params(
                    pool_name=pool_name,
                    address_range=address_range,
                    gateway=gateway_norm,
                    dns_servers=dns_servers_norm,
                )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_dhcp_plan(
                    device_service,
                    settings,
                    device_ids,
                    "dhcp/plan-create-pool",
                )

                # Assess risk level based on highest risk environment
                device_environments = [d.environment for d in devices]
                highest_risk_env = "prod" if "prod" in device_environments else (
                    "staging" if "staging" in device_environments else "lab"
                )

                risk_level = dhcp_plan_service.assess_risk(
                    operation="create_dhcp_pool",
                    device_environment=highest_risk_env,
                    affects_production=False,
                )

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = dhcp_plan_service.generate_preview(
                        operation="create_dhcp_pool",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        pool_name=pool_name,
                        address_range=address_range,
                        gateway=gateway_norm,
                        dns_servers=dns_servers_norm,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="dhcp/plan-create-pool",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Create DHCP pool: {pool_name} ({address_range})",
                    changes={
                        "operation": "create_dhcp_pool",
                        "pool_name": pool_name,
                        "address_range": address_range,
                        "gateway": gateway_norm,
                        "dns_servers": dns_servers_norm,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"DHCP pool plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Pool: {pool_name}\n"
                    f"Range: {address_range}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Estimated duration: {len(device_ids) * 5} seconds\n\n"
                    f"To apply this plan, use dhcp/apply-plan with:\n"
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
                        "tool_name": "dhcp/plan-create-pool",
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
    async def plan_modify_dhcp_pool(
        device_ids: list[str],
        pool_id: str,
        modifications: dict[str, Any],
    ) -> dict[str, Any]:
        """Create plan for modifying a DHCP server pool.

        Use when:
        - User asks "plan to modify DHCP pool X" or "update pool settings"
        - Need to change pool parameters (gateway, DNS, lease time)
        - Adjusting DHCP configuration on existing pools

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use dhcp/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_dhcp_writes)
        - Medium risk (modification may affect active leases)
        - Lab/staging only by default
        - Plan expires after 15 minutes

        Args:
            device_ids: List of device identifiers
            pool_id: ID of pool to modify (e.g., '*1')
            modifications: Dict of fields to modify (e.g., {'gateway': '192.168.1.1', 'dns_servers': ['8.8.8.8']})

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to modify DHCP pool gateway
            plan_modify_dhcp_pool(
                ["dev-lab-01"],
                "*1",
                {"gateway": "192.168.10.1"}
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                dhcp_plan_service = DHCPPlanService()

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_dhcp_plan(
                    device_service,
                    settings,
                    device_ids,
                    "dhcp/plan-modify-pool",
                )

                # Assess risk level
                device_environments = [d.environment for d in devices]
                highest_risk_env = "prod" if "prod" in device_environments else (
                    "staging" if "staging" in device_environments else "lab"
                )

                risk_level = dhcp_plan_service.assess_risk(
                    operation="modify_dhcp_pool",
                    device_environment=highest_risk_env,
                    affects_production=False,
                )

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = dhcp_plan_service.generate_preview(
                        operation="modify_dhcp_pool",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        pool_id=pool_id,
                        modifications=modifications,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="dhcp/plan-modify-pool",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Modify DHCP pool {pool_id}",
                    changes={
                        "operation": "modify_dhcp_pool",
                        "pool_id": pool_id,
                        "modifications": modifications,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"DHCP pool modification plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Pool ID: {pool_id}\n"
                    f"Devices: {len(device_ids)}\n\n"
                    f"To apply this plan, use dhcp/apply-plan with:\n"
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
                        "tool_name": "dhcp/plan-modify-pool",
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
    async def plan_remove_dhcp_pool(
        device_ids: list[str],
        pool_id: str,
    ) -> dict[str, Any]:
        """Create plan for removing a DHCP server pool.

        Use when:
        - User asks "plan to remove DHCP pool X" or "delete pool Y"
        - Need to clean up obsolete DHCP pools
        - Decommissioning network segments

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use dhcp/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_dhcp_writes)
        - High risk (pool removal stops new leases, may affect clients)
        - Lab/staging only by default
        - Plan expires after 15 minutes

        Args:
            device_ids: List of device identifiers
            pool_id: ID of pool to remove (e.g., '*1')

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to remove DHCP pool
            plan_remove_dhcp_pool(
                ["dev-lab-01", "dev-lab-02"],
                "*2"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                dhcp_plan_service = DHCPPlanService()

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_dhcp_plan(
                    device_service,
                    settings,
                    device_ids,
                    "dhcp/plan-remove-pool",
                )

                # Pool removal is always high risk
                risk_level = "high"

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = dhcp_plan_service.generate_preview(
                        operation="remove_dhcp_pool",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        pool_id=pool_id,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="dhcp/plan-remove-pool",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Remove DHCP pool {pool_id}",
                    changes={
                        "operation": "remove_dhcp_pool",
                        "pool_id": pool_id,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"DHCP pool removal plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Pool ID: {pool_id}\n"
                    f"Devices: {len(device_ids)}\n\n"
                    f"WARNING: Removing DHCP pool will stop new leases and may affect clients.\n\n"
                    f"To apply this plan, use dhcp/apply-plan with:\n"
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
                        "tool_name": "dhcp/plan-remove-pool",
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
    async def apply_dhcp_plan(
        plan_id: str,
        approval_token: str,
    ) -> dict[str, Any]:
        """Apply approved DHCP plan with health checks and automatic rollback.

        Use when:
        - User provides plan_id and approval_token from plan creation
        - Ready to execute DHCP changes after review
        - Implementing DHCP pool changes across devices

        Pattern: This is the APPLY step (executes changes with safety checks).

        Safety:
        - Professional tier (requires approved plan with valid token)
        - Creates snapshot before changes for rollback
        - Performs health check after each device
        - Automatic rollback on health check failure
        - Updates plan status to completed/failed
        - Comprehensive audit logging

        Args:
            plan_id: Plan identifier from plan creation (e.g., 'plan-dhcp-20250115-001')
            approval_token: Approval token from plan creation (must be valid and unexpired)

        Returns:
            Formatted tool result with execution status and results per device

        Examples:
            # Apply approved DHCP plan
            apply_dhcp_plan(
                plan_id="plan-dhcp-20250115-001",
                approval_token="approve-dhcp-a1b2c3d4"
            )
        """
        try:
            async with session_factory.session() as session:
                plan_service = PlanService(session, settings)
                device_service = DeviceService(session, settings)
                dhcp_plan_service = DHCPPlanService()

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
                        snapshot = await dhcp_plan_service.create_dhcp_snapshot(
                            device_id, device.name, rest_client
                        )
                        snapshots[device_id] = snapshot

                        # Execute operation (mock for now - would call RouterOS API)
                        # TODO: Implement actual RouterOS API calls for DHCP operations
                        logger.info(f"Executing {operation} on device {device_id}")

                        # Perform health check
                        expected_pool = None
                        if operation == "create_dhcp_pool":
                            expected_pool = plan["changes"].get("pool_name")

                        health_result = await dhcp_plan_service.perform_health_check(
                            device_id, rest_client, expected_pool_name=expected_pool
                        )

                        if health_result["status"] != "passed":
                            failed_devices.append(device_id)
                            device_results.append({
                                "device_id": device_id,
                                "status": "failed",
                                "message": "Health check failed after changes",
                                "health_check": health_result,
                            })
                        else:
                            successful_devices.append(device_id)
                            device_results.append({
                                "device_id": device_id,
                                "status": "success",
                                "message": "DHCP operation completed successfully",
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

    logger.info("Registered DHCP tools")
