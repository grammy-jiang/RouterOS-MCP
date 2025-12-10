"""Firewall address list management MCP tools.

Provides MCP tools for managing firewall address lists (MCP-owned only).
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.firewall import FirewallService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_firewall_write_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register firewall write tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings.database_url)

    @mcp.tool()
    async def update_firewall_address_list(
        device_id: str,
        list_name: str,
        address: str,
        action: str = "add",
        comment: str = "",
        timeout: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update firewall address-list entry (add or remove).

        Use when:
        - User asks "add IP X to whitelist Y" or "block IP Z"
        - Managing access control lists
        - Updating firewall allow/deny lists
        - Dynamic IP blocking/allowing

        Side effects:
        - Adds or removes address list entry immediately (unless dry_run=True)
        - May affect active firewall rules referencing this list
        - Can impact connectivity if list is used in blocking rules
        - Audit logged

        Safety:
        - Advanced tier (requires allow_advanced_writes=true)
        - Medium risk operation
        - Only modifies MCP-owned lists (prefix: mcp-)
        - Cannot modify system or user-managed lists
        - Supports dry_run for preview

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            list_name: Address list name (must start with 'mcp-')
            address: IP address or network (CIDR notation)
            action: Action to perform ("add" or "remove", default: "add")
            comment: Optional comment (for add)
            timeout: Optional timeout (for add, e.g., "1d", "1h")
            dry_run: If True, only return planned changes without applying

        Returns:
            Formatted tool result with update status

        Examples:
            # Add IP to managed whitelist
            update_firewall_address_list(
                "dev-lab-01",
                "mcp-managed-hosts",
                "10.0.1.100",
                action="add",
                comment="MCP server"
            )

            # Remove IP from list
            update_firewall_address_list(
                "dev-lab-01",
                "mcp-managed-hosts",
                "10.0.1.100",
                action="remove"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                firewall_service = FirewallService(session, settings)

                # Get device first to validate it exists
                device = await device_service.get_device(device_id)

                # Authorization check - advanced tier
                check_tool_authorization(
                    device_environment=device.environment,
                    service_environment=settings.environment,
                    tool_tier=ToolTier.ADVANCED,
                    allow_advanced_writes=device.allow_advanced_writes,
                    allow_professional_workflows=device.allow_professional_workflows,
                    device_id=device_id,
                    tool_name="firewall/update-address-list",
                )

                # Update address list
                result = await firewall_service.update_address_list_entry(
                    device_id, list_name, address, action, comment, timeout, dry_run
                )

                # Format content
                if dry_run:
                    content = (
                        f"DRY RUN: Would {action} {address} "
                        f"{'to' if action == 'add' else 'from'} address list '{list_name}'"
                    )
                elif result["changed"]:
                    verb = "Added" if action == "add" else "Removed"
                    preposition = "to" if action == "add" else "from"
                    content = f"{verb} {address} {preposition} address list '{list_name}'"
                else:
                    content = "No change needed (entry already in desired state)"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **result,
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

    logger.info("Registered firewall write tools")
