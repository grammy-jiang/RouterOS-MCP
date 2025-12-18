"""Wireless management MCP tools.

Provides MCP tools for querying wireless interface information and connected clients.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.wireless import WirelessService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_wireless_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register wireless management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    capsman_hint = (
        "CAPsMAN note: This router appears to manage one or more CAP devices (APs) via CAPsMAN. "
        "These results only reflect wireless interfaces/clients local to this device. "
        "To view SSIDs/clients on CAP-managed APs, inspect CAPsMAN state (e.g., the CAPsMAN "
        "registration table) or query the CAP device(s) directly."
    )

    @mcp.tool()
    async def get_wireless_interfaces(device_id: str) -> dict[str, Any]:
        """List wireless interfaces with SSID, frequency, and power configuration.

        Use when:
        - User asks "show me wireless interfaces" or "what are the WiFi settings?"
        - Finding wireless networks and their configuration
        - Checking wireless interface status (enabled/disabled, running)
        - Reviewing SSID names, frequencies, channels, and TX power
        - Auditing wireless network inventory
        - Troubleshooting wireless connectivity (checking if AP is running)

        Returns: List of wireless interfaces with ID, name, SSID, frequency, band,
        channel width, TX power, mode, running status, disabled status, and client counts.

        Note:
        - TX power is device-specific and may be in dBm or percentage
        - Frequency is in MHz (e.g., 2412 for channel 1)
        - Signal strength in client info is RSSI in negative dBm (e.g., -65 dBm)

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with wireless interface list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                wireless_service = WirelessService(session, settings)

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
                    tool_name="wireless/get-interfaces",
                )

                # Get wireless interfaces
                interfaces = await wireless_service.get_wireless_interfaces(device_id)

                # Add CAPsMAN hint only when CAPsMAN-managed APs are detected.
                capsman_has_aps = await wireless_service.has_capsman_managed_aps(device_id)

                content = f"Found {len(interfaces)} wireless interface(s) on {device.name}"
                if capsman_has_aps:
                    content = f"{content}\n\n{capsman_hint}"

                return format_tool_result(
                    content=content,
                    meta=(
                        {
                            "device_id": device_id,
                            "interfaces": interfaces,
                            "total_count": len(interfaces),
                            **({"hints": [capsman_hint]} if capsman_has_aps else {}),
                        }
                    ),
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
    async def get_wireless_clients(device_id: str) -> dict[str, Any]:
        """List connected wireless clients with signal strength and connection rates.

        Use when:
        - User asks "show me connected WiFi clients" or "who is on the wireless?"
        - Monitoring wireless network usage and client connections
        - Troubleshooting client connectivity (checking signal strength)
        - Identifying devices by MAC address on wireless networks
        - Reviewing connection quality (signal strength, rates)
        - Capacity planning (number of clients per AP)

        Returns: List of connected wireless clients with interface, MAC address,
        signal strength (RSSI in dBm), signal-to-noise ratio, TX/RX rates (Mbps),
        uptime, and traffic statistics.

        Note:
        - Signal strength is RSSI in negative dBm (e.g., -65 dBm is typical for good signal)
        - Stronger signals are closer to 0 (e.g., -30 dBm is excellent, -80 dBm is poor)
        - Rates are in Mbps (e.g., "54Mbps", "144.4Mbps")
        - Empty list means no clients currently connected

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with connected client list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                wireless_service = WirelessService(session, settings)

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
                    tool_name="wireless/get-clients",
                )

                # Get wireless clients
                clients = await wireless_service.get_wireless_clients(device_id)

                # Add CAPsMAN hint only when CAPsMAN-managed APs are detected.
                capsman_has_aps = await wireless_service.has_capsman_managed_aps(device_id)

                content = f"Found {len(clients)} connected wireless client(s) on {device.name}"
                if capsman_has_aps:
                    content = f"{content}\n\n{capsman_hint}"

                return format_tool_result(
                    content=content,
                    meta=(
                        {
                            "device_id": device_id,
                            "clients": clients,
                            "total_count": len(clients),
                            **({"hints": [capsman_hint]} if capsman_has_aps else {}),
                        }
                    ),
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

    logger.info("Registered wireless management tools")
