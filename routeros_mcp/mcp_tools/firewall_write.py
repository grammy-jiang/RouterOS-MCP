"""Firewall address list management and rule planning MCP tools.

Provides MCP tools for:
- Managing firewall address lists (MCP-owned only)
- Planning firewall rule changes (plan/apply workflow)
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS, DeviceCapability
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.firewall import FirewallService
from routeros_mcp.domain.services.firewall_plan import FirewallPlanService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)

# TODO: Replace with actual user from auth context when authentication is implemented
DEFAULT_MCP_USER = "mcp-user"


async def _validate_devices_for_firewall_plan(
    device_service: DeviceService,
    settings: Settings,
    device_ids: list[str],
    tool_name: str,
) -> list[Any]:
    """Validate devices for firewall plan operations.

    This helper performs common validation for all firewall plan tools:
    - Devices exist
    - Environment is lab/staging (by default)
    - Professional workflows capability enabled
    - Firewall writes capability enabled

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
                f"Firewall rule changes are only allowed in: "
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

        # Check firewall write capability
        if not device.allow_firewall_writes:
            raise ValueError(
                f"Device {device_id} does not have firewall write capability enabled. "
                f"Set {DeviceCapability.FIREWALL_WRITES.value}=true to enable."
            )

    return devices


def register_firewall_write_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register firewall write tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings)

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

    @mcp.tool()
    async def plan_add_firewall_rule(
        device_ids: list[str],
        chain: str,
        action: str,
        src_address: str = "",
        dst_address: str = "",
        protocol: str = "",
        dst_port: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        """Create plan for adding a firewall filter rule across multiple devices.

        Use when:
        - User asks "plan to add firewall rule allowing X" or "prepare to block Y"
        - Need to preview firewall changes before applying
        - Adding access control rules
        - Creating security policies

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use firewall/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_firewall_writes)
        - High/medium risk depending on chain and action
        - Lab/staging only by default
        - Plan expires after 15 minutes
        - Creates Plan entity with risk assessment

        Args:
            device_ids: List of device identifiers (e.g., ['dev-lab-01', 'dev-lab-02'])
            chain: Firewall chain (input/forward/output)
            action: Rule action (accept/drop/reject/jump/return/passthrough/log)
            src_address: Optional source address (IP or CIDR notation)
            dst_address: Optional destination address (IP or CIDR notation)
            protocol: Optional protocol (tcp/udp/icmp/etc.)
            dst_port: Optional destination port (single or range, e.g., "443" or "8000-9000")
            comment: Optional rule comment

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to add HTTPS allow rule
            plan_add_firewall_rule(
                ["dev-lab-01", "dev-lab-02"],
                "forward",
                "accept",
                src_address="192.168.1.0/24",
                dst_address="10.0.0.0/8",
                protocol="tcp",
                dst_port="443",
                comment="Allow internal to app subnet HTTPS"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                firewall_plan_service = FirewallPlanService()

                # Validate rule parameters first
                firewall_plan_service.validate_rule_params(
                    chain=chain,
                    action=action,
                    src_address=src_address or None,
                    dst_address=dst_address or None,
                    protocol=protocol or None,
                    dst_port=dst_port or None,
                )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_firewall_plan(
                    device_service,
                    settings,
                    device_ids,
                    "firewall/plan-add-rule",
                )

                # Assess risk level based on chain and action
                risk_level = firewall_plan_service.assess_risk(
                    chain=chain,
                    action=action,
                    device_environment=devices[0].environment,
                )

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = firewall_plan_service.generate_preview(
                        operation="add_firewall_rule",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        chain=chain,
                        action=action,
                        src_address=src_address or None,
                        dst_address=dst_address or None,
                        protocol=protocol or None,
                        dst_port=dst_port or None,
                        comment=comment or None,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="firewall/plan-add-rule",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Add firewall rule: chain={chain} action={action}",
                    changes={
                        "operation": "add_firewall_rule",
                        "chain": chain,
                        "action": action,
                        "src_address": src_address,
                        "dst_address": dst_address,
                        "protocol": protocol,
                        "dst_port": dst_port,
                        "comment": comment,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Firewall rule plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Estimated duration: {len(device_ids) * 5} seconds\n\n"
                    f"To apply this plan, use firewall/apply-plan with:\n"
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
                        "tool_name": "firewall/plan-add-rule",
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
    async def plan_modify_firewall_rule(
        device_ids: list[str],
        rule_id: str,
        chain: str = "",
        action: str = "",
        src_address: str = "",
        dst_address: str = "",
        protocol: str = "",
        dst_port: str = "",
        comment: str = "",
    ) -> dict[str, Any]:
        """Create plan for modifying an existing firewall filter rule.

        Use when:
        - User asks "plan to modify firewall rule X" or "update rule Y"
        - Need to change existing firewall rules
        - Adjusting access control policies
        - Updating security rules

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use firewall/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_firewall_writes)
        - High/medium risk depending on modifications
        - Lab/staging only by default
        - Plan expires after 15 minutes

        Args:
            device_ids: List of device identifiers
            rule_id: ID of rule to modify (e.g., "*1")
            chain: Optional new chain
            action: Optional new action
            src_address: Optional new source address
            dst_address: Optional new destination address
            protocol: Optional new protocol
            dst_port: Optional new destination port
            comment: Optional new comment

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to modify rule action
            plan_modify_firewall_rule(
                ["dev-lab-01"],
                "*5",
                action="drop",
                comment="Updated to drop instead of reject"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                firewall_plan_service = FirewallPlanService()

                # Build modifications dict
                modifications = {}
                if chain:
                    modifications["chain"] = chain
                if action:
                    modifications["action"] = action
                if src_address:
                    modifications["src_address"] = src_address
                if dst_address:
                    modifications["dst_address"] = dst_address
                if protocol:
                    modifications["protocol"] = protocol
                if dst_port:
                    modifications["dst_port"] = dst_port
                if comment:
                    modifications["comment"] = comment

                if not modifications:
                    raise ValueError("At least one modification must be specified")

                # Validate modified parameters
                validate_chain = modifications.get("chain", "forward")
                validate_action = modifications.get("action", "accept")
                firewall_plan_service.validate_rule_params(
                    chain=validate_chain,
                    action=validate_action,
                    src_address=modifications.get("src_address"),
                    dst_address=modifications.get("dst_address"),
                    protocol=modifications.get("protocol"),
                    dst_port=modifications.get("dst_port"),
                )

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_firewall_plan(
                    device_service,
                    settings,
                    device_ids,
                    "firewall/plan-modify-rule",
                )

                # Assess risk level
                risk_level = "high"  # Rule modification is always high risk

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = firewall_plan_service.generate_preview(
                        operation="modify_firewall_rule",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        chain=validate_chain,
                        action=validate_action,
                        rule_id=rule_id,
                        modifications=modifications,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="firewall/plan-modify-rule",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Modify firewall rule {rule_id}",
                    changes={
                        "operation": "modify_firewall_rule",
                        "rule_id": rule_id,
                        "modifications": modifications,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Firewall rule modification plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Rule ID: {rule_id}\n"
                    f"Modifications: {', '.join(modifications.keys())}\n\n"
                    f"To apply this plan, use firewall/apply-plan with:\n"
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
                        "tool_name": "firewall/plan-modify-rule",
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
    async def plan_remove_firewall_rule(
        device_ids: list[str],
        rule_id: str,
    ) -> dict[str, Any]:
        """Create plan for removing a firewall filter rule.

        Use when:
        - User asks "plan to remove firewall rule X" or "delete rule Y"
        - Need to clean up obsolete rules
        - Removing temporary access rules
        - Simplifying firewall configuration

        Pattern: This is the PLAN step (no changes applied).

        Returns: Plan ID, approval token, risk level, and detailed preview per device.

        Next step: Review plan, then use firewall/apply-plan to execute.

        Safety:
        - Professional tier (requires allow_professional_workflows + allow_firewall_writes)
        - High risk (rule removal may allow previously blocked traffic)
        - Lab/staging only by default
        - Plan expires after 15 minutes
        - Validates rule exists before creating plan

        Args:
            device_ids: List of device identifiers
            rule_id: ID of rule to remove (e.g., "*1")

        Returns:
            Formatted tool result with plan details and approval token

        Examples:
            # Plan to remove firewall rule
            plan_remove_firewall_rule(
                ["dev-lab-01", "dev-lab-02"],
                "*5"
            )
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                plan_service = PlanService(session, settings)
                firewall_plan_service = FirewallPlanService()

                # Validate all devices and check capabilities
                devices = await _validate_devices_for_firewall_plan(
                    device_service,
                    settings,
                    device_ids,
                    "firewall/plan-remove-rule",
                )

                # Rule removal is always high risk
                risk_level = "high"

                # Generate preview for each device
                device_previews = []
                for device in devices:
                    preview = firewall_plan_service.generate_preview(
                        operation="remove_firewall_rule",
                        device_id=device.id,
                        device_name=device.name,
                        device_environment=device.environment,
                        chain="unknown",  # Will be determined during apply
                        action="unknown",
                        rule_id=rule_id,
                    )
                    device_previews.append(preview)

                # Create plan
                plan = await plan_service.create_plan(
                    tool_name="firewall/plan-remove-rule",
                    created_by=DEFAULT_MCP_USER,
                    device_ids=device_ids,
                    summary=f"Remove firewall rule {rule_id}",
                    changes={
                        "operation": "remove_firewall_rule",
                        "rule_id": rule_id,
                        "device_previews": device_previews,
                    },
                    risk_level=risk_level,
                )

                # Format content
                content = (
                    f"Firewall rule removal plan created successfully.\n\n"
                    f"Risk Level: {risk_level.upper()}\n"
                    f"Devices: {len(device_ids)}\n"
                    f"Rule ID: {rule_id}\n\n"
                    f"WARNING: Removing firewall rules may allow previously blocked traffic.\n\n"
                    f"To apply this plan, use firewall/apply-plan with:\n"
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
                        "tool_name": "firewall/plan-remove-rule",
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

    logger.info("Registered firewall write tools")
