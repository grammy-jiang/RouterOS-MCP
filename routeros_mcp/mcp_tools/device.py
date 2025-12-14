"""Device management MCP tools.

Provides MCP tools for device registry operations and connectivity checks.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_device_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register device management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def list_devices(
        environment: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """List all registered RouterOS devices in the MCP service.

        Use when:
        - User asks "what devices are available?" or "show me all routers"
        - Beginning device selection workflows (user needs to choose a target)
        - Filtering devices by environment (lab/staging/prod) or tags (site, role, region)
        - Checking device health status across the fleet
        - Auditing device inventory

        Returns: List of devices with ID, name, management address, environment, 
        status, RouterOS version, tags, and capability flags.

        Tip: Use tags parameter to narrow results (e.g., {"site": "datacenter-1"}).

        Args:
            environment: Optional filter by environment (lab/staging/prod)
            tags: Optional filter by tags (key-value pairs)

        Returns:
            Formatted tool result with device list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

                # List devices with optional filters
                devices = await device_service.list_devices(
                    environment=environment,
                )

                # Filter by tags if provided
                if tags:
                    filtered_devices = []
                    for device in devices:
                        device_tags = device.tags or {}
                        if all(device_tags.get(k) == v for k, v in tags.items()):
                            filtered_devices.append(device)
                    devices = filtered_devices

                # Format devices for output
                devices_data = []
                for device in devices:
                    devices_data.append({
                        "id": device.id,
                        "name": device.name,
                        "management_ip": device.management_ip,
                        "management_port": device.management_port,
                        "environment": device.environment,
                        "status": device.status,
                        "routeros_version": device.routeros_version,
                        "hardware_model": device.hardware_model,
                        "tags": device.tags,
                        "allow_advanced_writes": device.allow_advanced_writes,
                        "allow_professional_workflows": device.allow_professional_workflows,
                    })

                content = f"Found {len(devices)} device(s)"
                if environment:
                    content += f" in {environment} environment"
                if tags:
                    content += f" with tags {tags}"

                return format_tool_result(
                    content=content,
                    meta={
                        "devices": devices_data,
                        "total_count": len(devices),
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
    async def check_connectivity(device_id: str) -> dict[str, Any]:
        """Verify if a device is reachable and responsive.

        Returns actionable guidance in failure cases (reason + suggestions).
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

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
                    tool_name="device/check-connectivity",
                )

                reachable, details = await device_service.check_connectivity(device_id)

                transport = details.get("transport") or "rest"
                if transport == "ssh":
                    response_time_ms = details.get("ssh_time_ms")
                else:
                    response_time_ms = details.get("rest_time_ms")

                if response_time_ms is None:
                    # Fallback to a generic total if provided (defensive)
                    response_time_ms = details.get("response_time_ms")
                if response_time_ms is None:
                    response_time_ms = 0.0

                failure_reason = details.get("failure_reason")
                suggestions_map = {
                    "timeout": [
                        "Verify device is powered on and reachable on the management IP/port",
                        "Check firewall or NAT rules blocking HTTPS/SSH to the device",
                        "Increase routeros_rest_timeout_seconds for slow links",
                    ],
                    "network_error": [
                        "Confirm DNS/IP/port are correct and reachable",
                        "Check physical connectivity and routing to the device",
                        "Inspect upstream firewalls for HTTPS/SSH blocks",
                    ],
                    "auth_failed": [
                        "Validate username/password for the device",
                        "Ensure credentials are active for RouterOS REST and SSH (if used)",
                        "Rotate credentials if recently changed",
                    ],
                    "authz_failed": [
                        "Verify user permissions for RouterOS REST",
                        "Try an account with REST API rights",
                    ],
                    "client_error": [
                        "Confirm REST API path is enabled on the device",
                        "Check RouterOS version and REST API availability",
                    ],
                    "server_error": [
                        "Retry later; device REST service may be overloaded",
                        "Check device health or restart API service",
                    ],
                    "not_found": [
                        "Confirm device registration and ID",
                        "Ensure credentials exist for this device",
                    ],
                    "unknown": [
                        "Review server logs for stack traces",
                        "Validate device network access and credentials",
                    ],
                }

                suggestions = suggestions_map.get(failure_reason, [])

                if reachable:
                    device = await device_service.get_device(device_id)
                    transport_label = "REST API" if transport == "rest" else "SSH fallback"
                    return format_tool_result(
                        content=f"Device {device_id} is reachable via {transport_label}",
                        meta={
                            **details,
                            "device_id": device_id,
                            "reachable": True,
                            "response_time_ms": round(response_time_ms, 2),
                            "routeros_version": device.routeros_version,
                            "suggestions": [],
                        },
                    )

                return format_tool_result(
                    content=(
                        f"Device {device_id} is not reachable via REST/SSH"
                        f" (reason: {failure_reason or 'unknown'})"
                    ),
                    is_error=True,
                    meta={
                        **details,
                        "device_id": device_id,
                        "reachable": False,
                        "response_time_ms": round(response_time_ms, 2),
                        "transport": transport,
                        "suggestions": suggestions,
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

    logger.info("Registered device management tools")
