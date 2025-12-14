"""IP address management MCP tools.

Provides MCP tools for querying IP address configuration and ARP table.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.ip import IPService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_ip_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register IP address management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def list_ip_addresses(device_id: str) -> dict[str, Any]:
        """List all IP addresses configured on the device.

        Use when:
        - User asks "what IPs are configured?" or "show me all addresses"
        - Finding which interfaces have which IP addresses
        - Auditing IP address assignments
        - Planning IP address additions (checking for conflicts)
        - Troubleshooting IP connectivity issues
        - Verifying address configuration after changes

        Returns: List of IP addresses with CIDR notation, network, interface, disabled status,
        and comment.

        Tip: Returns both primary and secondary addresses on all interfaces.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with IP address list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                ip_service = IPService(session, settings)

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
                    tool_name="ip/list-addresses",
                )

                # Get IP addresses
                addresses = await ip_service.list_addresses(device_id)

                content = f"Found {len(addresses)} IP address(es) on {device.name}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "addresses": addresses,
                        "total_count": len(addresses),
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
    async def get_ip_address(device_id: str, address_id: str) -> dict[str, Any]:
        """Get details of a specific IP address configuration.

        Use when:
        - User asks about a specific IP address
        - Verifying address properties (network, interface binding)
        - Checking if address is dynamic or static
        - Detailed investigation of address configuration

        Returns: Complete IP address details including network, interface, disabled/dynamic/invalid flags.

        Note: Requires address ID (from ip/list-addresses).

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            address_id: Address ID (e.g., '*2')

        Returns:
            Formatted tool result with IP address details
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                ip_service = IPService(session, settings)

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
                    tool_name="ip/get-address",
                )

                # Get IP address
                address = await ip_service.get_address(device_id, address_id)

                # Defensive check for empty dict (should not happen with proper exception handling)
                if not address or "address" not in address:
                    raise ValueError(f"Address {address_id} not found or invalid response")

                content = f"IP address {address['address']} on {address['interface']}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "address": address,
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
    async def get_arp_table(device_id: str) -> dict[str, Any]:
        """Get ARP (Address Resolution Protocol) table entries.

        Use when:
        - User asks "what devices are on the network?" or "show me ARP table"
        - Troubleshooting connectivity to specific hosts (verifying MAC address resolution)
        - Identifying connected devices by MAC address
        - Detecting IP/MAC conflicts
        - Network discovery (seeing active hosts)

        Returns: List of ARP entries with IP address, MAC address, interface, status, and comment.

        Tip: Only shows devices that have recently communicated with the router.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with ARP table
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                ip_service = IPService(session, settings)

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
                    tool_name="ip/get-arp-table",
                )

                # Get ARP table
                arp_entries = await ip_service.get_arp_table(device_id)

                content = f"Found {len(arp_entries)} ARP entries"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "arp_entries": arp_entries,
                        "total_count": len(arp_entries),
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

    logger.info("Registered IP address management tools")

    # Register write tools
    register_ip_write_tools(mcp, settings)


def register_ip_write_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register IP write tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def add_secondary_ip_address(
        device_id: str,
        address: str,
        interface: str,
        comment: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add a secondary IP address to an interface.

        Use when:
        - User asks "add IP address X to interface Y"
        - Adding management or service IPs
        - Configuring additional subnets on interface
        - Testing connectivity on different networks

        Side effects:
        - Adds IP address immediately (unless dry_run=True)
        - No impact on existing addresses or routes
        - Audit logged

        Safety:
        - Advanced tier (requires allow_advanced_writes=true)
        - Medium risk operation
        - Checks for IP overlap on same interface
        - Validates IP format (CIDR notation)
        - Supports dry_run for preview

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            address: IP address in CIDR notation (e.g., "192.168.1.10/24")
            interface: Interface name (e.g., "ether1")
            comment: Optional comment
            dry_run: If True, only return planned changes without applying

        Returns:
            Formatted tool result with add status
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                ip_service = IPService(session, settings)

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
                    tool_name="ip/add-secondary-address",
                )

                # Add address
                result = await ip_service.add_secondary_address(
                    device_id, address, interface, comment, dry_run
                )

                # Format content
                if dry_run:
                    content = (
                        f"DRY RUN: Would add IP address {address} to interface {interface}"
                    )
                else:
                    content = f"Added IP address {address} to interface {interface}"

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

    @mcp.tool()
    async def remove_secondary_ip_address(
        device_id: str, address_id: str, dry_run: bool = False
    ) -> dict[str, Any]:
        """Remove a secondary IP address.

        Use when:
        - User asks "remove IP address X" or "delete address on interface Y"
        - Cleaning up unused IPs
        - Reconfiguring network addressing
        - Decommissioning services

        Side effects:
        - Removes IP address immediately (unless dry_run=True)
        - May break services using this IP
        - Audit logged

        Safety:
        - Advanced tier (requires allow_advanced_writes=true)
        - Medium-high risk operation
        - Management path protection (prevents removing management IP)
        - Supports dry_run for preview
        - Use with caution in production

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            address_id: Address ID to remove (from ip/list-addresses)
            dry_run: If True, only return planned changes without applying

        Returns:
            Formatted tool result with remove status
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                ip_service = IPService(session, settings)

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
                    tool_name="ip/remove-secondary-address",
                )

                # Remove address
                result = await ip_service.remove_secondary_address(
                    device_id, address_id, dry_run
                )

                # Format content
                if dry_run:
                    content = (
                        f"DRY RUN: Would remove IP address {result['planned_changes']['address']} "
                        f"from interface {result['planned_changes']['interface']}"
                    )
                else:
                    content = (
                        f"Removed IP address {result['address']} "
                        f"from interface {result['interface']}"
                    )

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

    logger = logging.getLogger(__name__)
    logger.info("Registered IP write tools")
