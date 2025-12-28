"""Wireless management MCP tools.

Provides MCP tools for querying wireless interface information and connected clients.
Also provides plan/apply workflow for wireless SSID and RF configuration (Phase 3).
"""

import logging
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS, DeviceCapability, ToolHint
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.domain.services.wireless import WirelessService
from routeros_mcp.domain.services.wireless_plan import WirelessPlanService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)

# TODO: Replace with actual user from auth context when authentication is implemented
DEFAULT_MCP_USER = "mcp-user"


def register_wireless_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register wireless management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

    # Standard CAPsMAN guidance hint
    capsman_hint = ToolHint(
        code="capsman_detected",
        message=(
            "CAPsMAN note: This router appears to manage one or more CAP devices (APs) via CAPsMAN. "
            "These results only reflect wireless interfaces/clients local to this device. "
            "To view SSIDs/clients on CAP-managed APs, inspect CAPsMAN state (e.g., the CAPsMAN "
            "registration table) or query the CAP device(s) directly."
        ),
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
                    content = f"{content}\n\n{capsman_hint.message}"

                return format_tool_result(
                    content=content,
                    meta=(
                        {
                            "device_id": device_id,
                            "interfaces": interfaces,
                            "total_count": len(interfaces),
                            **(
                                {"hints": [capsman_hint.model_dump()]}
                                if capsman_has_aps
                                else {}
                            ),
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
                    content = f"{content}\n\n{capsman_hint.message}"

                return format_tool_result(
                    content=content,
                    meta=(
                        {
                            "device_id": device_id,
                            "clients": clients,
                            "total_count": len(clients),
                            **(
                                {"hints": [capsman_hint.model_dump()]}
                                if capsman_has_aps
                                else {}
                            ),
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
    async def get_capsman_remote_caps(device_id: str) -> dict[str, Any]:
        """List remote CAP devices managed by CAPsMAN controller.

        Use when:
        - User asks "show me CAPsMAN remote CAPs" or "what CAP devices are connected?"
        - Checking CAPsMAN-managed Access Points inventory
        - Monitoring CAPsMAN controller topology
        - Troubleshooting CAP connectivity to controller
        - Auditing wireless infrastructure in CAPsMAN deployments

        Returns: List of remote CAP devices with identity, address, state, version,
        board info, and connection metrics. Returns empty list when CAPsMAN is not
        present on the device.

        Note:
        - This shows CAP devices (managed APs) registered with the CAPsMAN controller
        - Different from local wireless interfaces (which show only this router's radios)
        - State indicates CAP connection status (e.g., "authorized", "provisioning")
        - Empty list is normal if device is not a CAPsMAN controller

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with remote CAP list
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
                    tool_name="wireless/get-capsman-remote-caps",
                )

                # Get CAPsMAN remote CAPs
                caps = await wireless_service.get_capsman_remote_caps(device_id)

                if len(caps) == 0:
                    content = (
                        f"No remote CAPs found on {device.name}. "
                        "This device may not be a CAPsMAN controller, or no CAP devices are currently registered."
                    )
                else:
                    content = f"Found {len(caps)} remote CAP device(s) managed by CAPsMAN on {device.name}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "remote_caps": caps,
                        "total_count": len(caps),
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
    async def get_capsman_registrations(device_id: str) -> dict[str, Any]:
        """List active CAPsMAN client registrations.

        Use when:
        - User asks "show me CAPsMAN registrations" or "what clients are on CAPsMAN?"
        - Monitoring client connections in CAPsMAN deployments
        - Troubleshooting wireless client connectivity via CAPsMAN
        - Reviewing which CAP/radio clients are connected to
        - Getting accurate WiFi client counts across CAPsMAN infrastructure

        Returns: List of active CAPsMAN registrations with interface, MAC address,
        SSID, AP name, signal strength, and traffic statistics. Returns empty list
        when CAPsMAN is not present or no clients are registered.

        Note:
        - This shows clients registered via CAPsMAN controller
        - More accurate than local registration-table in CAPsMAN deployments
        - Includes clients on all managed CAP devices
        - Signal strength in RSSI (negative dBm, e.g., -65 dBm)
        - Empty list is normal if no clients connected or device is not a CAPsMAN controller

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with registration list
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
                    tool_name="wireless/get-capsman-registrations",
                )

                # Get CAPsMAN registrations
                registrations = await wireless_service.get_capsman_registrations(device_id)

                if len(registrations) == 0:
                    content = (
                        f"No CAPsMAN registrations found on {device.name}. "
                        "This device may not be a CAPsMAN controller, or no clients are currently connected."
                    )
                else:
                    content = f"Found {len(registrations)} active CAPsMAN registration(s) on {device.name}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "registrations": registrations,
                        "total_count": len(registrations),
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

    # Phase 3: Plan/Apply workflow for wireless SSID and RF configuration

    async def _validate_devices_for_wireless_plan(
        device_service: DeviceService,
        settings: Settings,
        device_ids: list[str],
        tool_name: str,
    ) -> list[Any]:
        """Validate devices for wireless plan operations.

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
                    f"Wireless changes are only allowed in: "
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

            # Check wireless write capability
            if not device.allow_wireless_writes:
                raise ValueError(
                    f"Device {device_id} does not have wireless write capability enabled. "
                    f"Set {DeviceCapability.WIRELESS_WRITES.value}=true to enable."
                )

        return devices

    @mcp.tool()
    async def plan_create_wireless_ssid(
        device_ids: list[str],
        ssid: str,
        security_profile: str = "default",
        band: str = "",
        channel: int = 0,
    ) -> dict[str, Any]:
        """Create plan for adding a wireless SSID across multiple devices.

        Use when:
        - User asks "plan to create WiFi network X" or "prepare to add SSID Y"
        - Need to preview wireless SSID changes before applying
        - Setting up new wireless networks

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use wireless/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_wireless_writes)
        - Medium/high risk depending on environment
        - Lab/staging only by default
        - Plan expires after 15 minutes

        Args:
            device_ids: List of device identifiers (e.g., ['dev-lab-01', 'dev-lab-02'])
            ssid: SSID name (1-32 characters)
            security_profile: Security profile name (default: "default")
            band: Wireless band (e.g., "2ghz-n", "5ghz-ac") - optional
            channel: Wireless channel (0 for auto) - optional

        Returns:
            Formatted tool result with plan details and approval token
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                wireless_plan_service = WirelessPlanService()

                # Validate SSID parameters first
                wireless_plan_service.validate_ssid_params(
                    ssid=ssid,
                    security_profile=security_profile,
                    band=band if band else None,
                    channel=channel if channel > 0 else None,
                )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_wireless_plan(
                    device_service,
                    settings,
                    device_ids,
                    "wireless/plan-create-ssid",
                )

                # Assess risk level
                device_environments = [d.environment for d in devices]
                highest_risk_env = "prod" if "prod" in device_environments else (
                    "staging" if "staging" in device_environments else "lab"
                )

                risk_level = wireless_plan_service.assess_risk(
                    operation="create_ssid",
                    device_environment=highest_risk_env,
                    has_active_clients=False,
                )

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = wireless_plan_service.generate_preview(
                        operation="create_ssid",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        ssid=ssid,
                        security_profile=security_profile,
                        band=band if band else None,
                        channel=channel if channel > 0 else None,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="wireless/plan-create-ssid",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Create wireless SSID '{ssid}'",
                    changes={
                        "operation": "create_ssid",
                        "ssid": ssid,
                        "security_profile": security_profile,
                        "band": band if band else None,
                        "channel": channel if channel > 0 else None,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Wireless SSID creation plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"SSID: {ssid}\n"
                    f"Security Profile: {security_profile}\n\n"
                    f"To apply this plan, use wireless/apply-plan with:\n"
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
                        "tool_name": "wireless/plan-create-ssid",
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
    async def plan_modify_wireless_ssid(
        device_ids: list[str],
        ssid_id: str,
        ssid: str = "",
        security_profile: str = "",
        band: str = "",
        channel: int = 0,
    ) -> dict[str, Any]:
        """Create plan for modifying a wireless SSID across multiple devices.

        Use when:
        - User asks "plan to change SSID X" or "prepare to modify WiFi Y"
        - Need to preview SSID modifications before applying
        - Updating wireless network settings

        Pattern: This is the PLAN step (no changes applied).

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_wireless_writes)
        - High risk if SSID has active clients
        - Lab/staging only by default

        Args:
            device_ids: List of device identifiers
            ssid_id: SSID/interface ID (e.g., "*1" or interface name)
            ssid: New SSID name (optional)
            security_profile: New security profile (optional)
            band: New wireless band (optional)
            channel: New channel (0 to skip, optional)

        Returns:
            Formatted tool result with plan details and approval token
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                wireless_plan_service = WirelessPlanService()

                # Build modifications dict
                modifications = {}
                if ssid:
                    modifications["ssid"] = ssid
                if security_profile:
                    modifications["security_profile"] = security_profile
                if band:
                    modifications["band"] = band
                if channel > 0:
                    modifications["channel"] = channel

                if not modifications:
                    raise ValueError("At least one modification must be specified")

                # Validate modified parameters if SSID is being changed
                if "ssid" in modifications:
                    wireless_plan_service.validate_ssid_params(
                        ssid=modifications["ssid"],
                        security_profile=modifications.get("security_profile"),
                        band=modifications.get("band"),
                        channel=modifications.get("channel"),
                    )

                # Validate all devices
                devices = await _validate_devices_for_wireless_plan(
                    device_service,
                    settings,
                    device_ids,
                    "wireless/plan-modify-ssid",
                )

                # Assess risk level - modification is always high risk
                risk_level = "high"

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = wireless_plan_service.generate_preview(
                        operation="modify_ssid",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        ssid_id=ssid_id,
                        modifications=modifications,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="wireless/plan-modify-ssid",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Modify wireless SSID {ssid_id}",
                    changes={
                        "operation": "modify_ssid",
                        "ssid_id": ssid_id,
                        "modifications": modifications,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Wireless SSID modification plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"SSID ID: {ssid_id}\n"
                    f"Modifications: {', '.join(modifications.keys())}\n\n"
                    f"To apply this plan, use wireless/apply-plan with:\n"
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
                        "tool_name": "wireless/plan-modify-ssid",
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
    async def plan_remove_wireless_ssid(
        device_ids: list[str],
        ssid_id: str,
    ) -> dict[str, Any]:
        """Create plan for removing a wireless SSID across multiple devices.

        Use when:
        - User asks "plan to remove SSID X" or "prepare to delete WiFi Y"
        - Need to preview SSID removal before applying
        - Decommissioning wireless networks

        Pattern: This is the PLAN step (no changes applied).

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_wireless_writes)
        - High risk operation
        - Lab/staging only by default

        Args:
            device_ids: List of device identifiers
            ssid_id: SSID/interface ID to remove (e.g., "*1" or interface name)

        Returns:
            Formatted tool result with plan details and approval token
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                wireless_plan_service = WirelessPlanService()

                # Validate all devices
                devices = await _validate_devices_for_wireless_plan(
                    device_service,
                    settings,
                    device_ids,
                    "wireless/plan-remove-ssid",
                )

                # Assess risk level - removal is always high risk
                risk_level = "high"

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = wireless_plan_service.generate_preview(
                        operation="remove_ssid",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        ssid_id=ssid_id,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="wireless/plan-remove-ssid",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Remove wireless SSID {ssid_id}",
                    changes={
                        "operation": "remove_ssid",
                        "ssid_id": ssid_id,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Wireless SSID removal plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"SSID ID: {ssid_id}\n\n"
                    f"To apply this plan, use wireless/apply-plan with:\n"
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
                        "tool_name": "wireless/plan-remove-ssid",
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
    async def plan_wireless_rf_settings(
        device_ids: list[str],
        interface: str,
        channel: int = 0,
        tx_power: int = 0,
        band: str = "",
    ) -> dict[str, Any]:
        """Create plan for updating wireless RF settings (channel, TX power) across multiple devices.

        Use when:
        - User asks "plan to change WiFi channel" or "prepare to adjust TX power"
        - Need to preview RF parameter changes before applying
        - Optimizing wireless performance

        Pattern: This is the PLAN step (no changes applied).

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_wireless_writes)
        - Medium/high risk depending on environment
        - Lab/staging only by default
        - DFS channels are blocked for safety
        - TX power limited to regulatory range

        Args:
            device_ids: List of device identifiers
            interface: Wireless interface name or ID (e.g., "wlan1", "*1")
            channel: New channel (0 to skip)
            tx_power: New TX power in dBm (0 to skip, range: 0-30)
            band: Wireless band for channel validation (optional, e.g., "5ghz-ac")

        Returns:
            Formatted tool result with plan details and approval token
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                wireless_plan_service = WirelessPlanService()

                # Validate RF parameters
                wireless_plan_service.validate_rf_params(
                    channel=channel if channel > 0 else None,
                    tx_power=tx_power if tx_power > 0 else None,
                    band=band if band else None,
                )

                # Validate all devices
                devices = await _validate_devices_for_wireless_plan(
                    device_service,
                    settings,
                    device_ids,
                    "wireless/plan-rf-settings",
                )

                # Assess risk level
                device_environments = [d.environment for d in devices]
                highest_risk_env = "prod" if "prod" in device_environments else (
                    "staging" if "staging" in device_environments else "lab"
                )

                risk_level = wireless_plan_service.assess_risk(
                    operation="rf_settings",
                    device_environment=highest_risk_env,
                    has_active_clients=False,
                )

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = wireless_plan_service.generate_preview(
                        operation="rf_settings",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        interface=interface,
                        channel=channel if channel > 0 else None,
                        tx_power=tx_power if tx_power > 0 else None,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="wireless/plan-rf-settings",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Update RF settings on interface {interface}",
                    changes={
                        "operation": "rf_settings",
                        "interface": interface,
                        "channel": channel if channel > 0 else None,
                        "tx_power": tx_power if tx_power > 0 else None,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                rf_changes = []
                if channel > 0:
                    rf_changes.append(f"Channel: {channel}")
                if tx_power > 0:
                    rf_changes.append(f"TX Power: {tx_power} dBm")

                content = (
                    f"Wireless RF settings plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Interface: {interface}\n"
                    f"Changes: {', '.join(rf_changes)}\n\n"
                    f"To apply this plan, use wireless/apply-plan with:\n"
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
                        "tool_name": "wireless/plan-rf-settings",
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
    async def apply_wireless_plan(
        plan_id: str,
        approval_token: str,
    ) -> dict[str, Any]:
        """Apply approved wireless plan with health checks and automatic rollback.

        Use when:
        - User provides plan_id and approval_token from plan creation
        - Ready to execute wireless changes after review
        - Implementing wireless SSID or RF changes across devices

        Pattern: This is the APPLY step (executes changes with safety checks).

        Safety:
        - Professional tier (requires approved plan with valid token)
        - Creates snapshot before changes for rollback
        - Performs health check after each device
        - Automatic rollback on health check failure
        - Updates plan status to completed/failed
        - Comprehensive audit logging

        Args:
            plan_id: Plan identifier from plan creation (e.g., 'plan-wireless-20250115-001')
            approval_token: Approval token from plan creation (must be valid and unexpired)

        Returns:
            Formatted tool result with execution status and results per device
        """
        try:
            async with session_factory.session() as session:
                plan_service = PlanService(session, settings)
                device_service = DeviceService(session, settings)
                wireless_plan_service = WirelessPlanService()

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
                        logger.info(f"Creating wireless snapshot for device {device_id}")
                        snapshot = await wireless_plan_service.create_wireless_snapshot(
                            device_id, device.name, rest_client
                        )
                        snapshots[device_id] = snapshot
                        device_result["snapshot_id"] = snapshot["snapshot_id"]

                        # Step 2: Apply changes
                        logger.info(f"Applying wireless changes to device {device_id}")
                        apply_result = await wireless_plan_service.apply_plan(
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
                            health_check = await wireless_plan_service.perform_health_check(
                                device_id, rest_client
                            )
                            device_result["health_check"] = health_check

                            if health_check["status"] not in ["healthy", "degraded"]:
                                # Health check failed - rollback
                                logger.warning(
                                    f"Health check {health_check['status']} for device {device_id}, initiating rollback"
                                )
                                rollback_result = await wireless_plan_service.rollback_from_snapshot(
                                    device_id, snapshot["data"], rest_client, operation
                                )
                                device_result["rollback"] = rollback_result
                                device_result["status"] = "rolled_back"
                                failed_devices.append(device_id)
                            else:
                                # Success (or degraded but acceptable)
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
                                if rest_client is None:
                                    rest_client = await device_service.get_rest_client(device_id)
                                rollback_result = await wireless_plan_service.rollback_from_snapshot(
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
                            await rest_client.close()

                    device_results.append(device_result)

                # Update plan status based on results
                if len(failed_devices) == 0:
                    final_status = "completed"
                elif len(successful_devices) == 0:
                    final_status = "failed"
                else:
                    final_status = "failed"  # Partial success treated as failed

                await plan_service.update_plan_status(plan_id, final_status, DEFAULT_MCP_USER)

                # Format content
                content = (
                    f"Wireless plan execution {'completed' if final_status == 'completed' else 'finished with errors'}.\n\n"
                    f"Plan ID: {plan_id}\n"
                    f"Status: {final_status.upper()}\n"
                    f"Successful: {len(successful_devices)}/{len(device_ids)}\n"
                    f"Failed: {len(failed_devices)}/{len(device_ids)}\n\n"
                )

                if successful_devices:
                    content += f"Successfully updated devices: {', '.join(successful_devices)}\n"
                if failed_devices:
                    content += f"Failed devices: {', '.join(failed_devices)}\n"

                return format_tool_result(
                    content=content,
                    meta={
                        "plan_id": plan_id,
                        "final_status": final_status,
                        "successful_devices": successful_devices,
                        "failed_devices": failed_devices,
                        "device_results": device_results,
                        "total_devices": len(device_ids),
                        "success_count": len(successful_devices),
                        "fail_count": len(failed_devices),
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

    logger.info("Registered wireless management tools (including plan/apply workflow)")
