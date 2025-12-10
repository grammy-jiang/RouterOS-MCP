"""Firewall and logs management MCP tools.

Provides MCP tools for querying firewall rules and system logs.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.firewall_logs import FirewallLogsService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_firewall_logs_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register firewall and logs management tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings.database_url)

    @mcp.tool()
    async def list_firewall_filter_rules(device_id: str) -> dict[str, Any]:
        """List firewall filter rules (input/forward/output chains).

        Use when:
        - User asks "what firewall rules are configured?" or "show me filter rules"
        - Auditing firewall security configuration
        - Troubleshooting blocked connections (finding which rule blocks traffic)
        - Verifying firewall rule order
        - Before planning firewall changes
        - Security compliance checks

        Returns: List of filter rules with ID, chain, action, protocol, ports, comment, disabled status.

        Note: Read-only in Phase 1. Modification requires Phase 2+.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with filter rules list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                fw_logs_service = FirewallLogsService(session, settings)

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
                    tool_name="firewall/list-filter-rules",
                )

                # Get filter rules
                filter_rules = await fw_logs_service.list_filter_rules(device_id)

                content = f"Found {len(filter_rules)} firewall filter rules"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "filter_rules": filter_rules,
                        "total_count": len(filter_rules),
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
    async def list_firewall_nat_rules(device_id: str) -> dict[str, Any]:
        """List NAT (Network Address Translation) rules.

        Use when:
        - User asks "show me NAT config" or "what masquerade rules exist?"
        - Troubleshooting NAT issues (port forwarding, masquerading)
        - Auditing NAT configuration
        - Verifying srcnat/dstnat rules
        - Before planning NAT changes

        Returns: List of NAT rules with ID, chain, action, interfaces, comment, disabled status.

        Note: Read-only in Phase 1.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with NAT rules list
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                fw_logs_service = FirewallLogsService(session, settings)

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
                    tool_name="firewall/list-nat-rules",
                )

                # Get NAT rules
                nat_rules = await fw_logs_service.list_nat_rules(device_id)

                content = f"Found {len(nat_rules)} NAT rules"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "nat_rules": nat_rules,
                        "total_count": len(nat_rules),
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
    async def list_firewall_address_lists(
        device_id: str,
        list_name: str | None = None,
    ) -> dict[str, Any]:
        """List firewall address-list entries (IP-based allow/deny lists).

        Use when:
        - User asks "show me address lists" or "what IPs are in list X?"
        - Auditing firewall IP whitelists/blacklists
        - Verifying address-list entries
        - Troubleshooting access control (checking if IP is in list)
        - Before adding/removing address-list entries
        - Checking MCP-managed lists (prefix: mcp-)

        Returns: List of address-list entries with ID, list name, address, comment, timeout.

        Tip: Filter by list_name parameter to view specific list. Only MCP-managed lists 
        (prefix: mcp-) can be modified.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            list_name: Optional filter by list name (e.g., 'mcp-managed-hosts')

        Returns:
            Formatted tool result with address-list entries
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                fw_logs_service = FirewallLogsService(session, settings)

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
                    tool_name="firewall/list-address-lists",
                )

                # Get address lists
                address_lists = await fw_logs_service.list_address_lists(device_id, list_name)

                if list_name:
                    content = f"Address list '{list_name}' contains {len(address_lists)} entries"
                else:
                    content = f"Found {len(address_lists)} address-list entries"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "address_lists": address_lists,
                        "total_count": len(address_lists),
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
    async def get_recent_logs(
        device_id: str,
        limit: int = 100,
        topics: list[str] | None = None,
    ) -> dict[str, Any]:
        """Retrieve recent system logs with optional filtering.

        Use when:
        - User asks "show me recent logs" or "check logs for errors"
        - Troubleshooting issues (looking for error messages)
        - Auditing system events
        - Investigating security incidents
        - Verifying recent configuration changes
        - Checking specific topics (system, error, warning, firewall, etc.)

        Returns: List of log entries with ID, timestamp, topics, and message.

        Constraints:
        - Max 1000 entries per call (use limit parameter)
        - Filter by topics to narrow results (e.g., ["system", "error"])
        - Bounded query - cannot stream unlimited logs

        Tip: Start with small limit (e.g., 100) and specific topics to avoid overwhelming response.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            limit: Maximum number of entries to return (default 100, max 1000)
            topics: Optional list of topics to filter by (e.g., ['system', 'error'])

        Returns:
            Formatted tool result with log entries
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                fw_logs_service = FirewallLogsService(session, settings)

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
                    tool_name="logs/get-recent",
                )

                # Get recent logs
                log_entries, total_count = await fw_logs_service.get_recent_logs(
                    device_id, limit, topics
                )

                content = f"Retrieved {len(log_entries)} log entries"
                if topics:
                    content += f" for topics: {', '.join(topics)}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "log_entries": log_entries,
                        "total_count": total_count,
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
    async def get_logging_config(device_id: str) -> dict[str, Any]:
        """Get logging configuration (which topics log to which destinations).

        Use when:
        - User asks "what logging is configured?" or "where do logs go?"
        - Auditing logging configuration
        - Troubleshooting missing logs (verifying topic is logged)
        - Understanding log architecture
        - Before modifying logging configuration (Phase 2+)

        Returns: List of logging actions with topics, action type (memory/disk/remote), and prefix.

        Note: Configuration is read-only in Phase 1.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with logging configuration
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                fw_logs_service = FirewallLogsService(session, settings)

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
                    tool_name="logs/get-config",
                )

                # Get logging config
                logging_actions = await fw_logs_service.get_logging_config(device_id)

                content = f"Logging configuration: {len(logging_actions)} actions defined"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "logging_actions": logging_actions,
                        "total_count": len(logging_actions),
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

    logger.info("Registered firewall and logs management tools")
