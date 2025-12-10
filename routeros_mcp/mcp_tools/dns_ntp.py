"""DNS and NTP management MCP tools.

Provides MCP tools for querying DNS and NTP configuration and status.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.dns_ntp import DNSNTPService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result
from routeros_mcp.security.authz import ToolTier, check_tool_authorization

logger = logging.getLogger(__name__)


def register_dns_ntp_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register DNS and NTP tools with the MCP server.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings.database_url)

    @mcp.tool()
    async def get_dns_status(device_id: str) -> dict[str, Any]:
        """Get DNS server configuration and cache statistics.

        Use when:
        - User asks "what DNS servers are configured?" or "is DNS working?"
        - Troubleshooting DNS resolution issues
        - Verifying DNS configuration after changes
        - Checking DNS cache utilization
        - Before planning DNS server updates
        - Auditing DNS settings across fleet

        Returns: DNS server list, remote request allowance, cache size/usage.

        Tip: Use with tool/ping to verify DNS server reachability.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with DNS status
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                dns_ntp_service = DNSNTPService(session, settings)

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
                    tool_name="dns/get-status",
                )

                # Get DNS status
                dns_status = await dns_ntp_service.get_dns_status(device_id)

                servers_str = ", ".join(dns_status["dns_servers"])
                content = f"DNS servers: {servers_str}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **dns_status,
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
    async def get_dns_cache(device_id: str, limit: int = 100) -> dict[str, Any]:
        """View DNS cache entries (recently resolved domains).

        Use when:
        - User asks "what's in the DNS cache?" or "has domain X been resolved?"
        - Troubleshooting DNS resolution (verifying cache entries)
        - Checking TTL values for cached records
        - Investigating DNS-related connectivity issues
        - Before/after flushing DNS cache

        Returns: List of cached DNS records with name, type (A/AAAA/CNAME), data (IP), and TTL.

        Note: Limited to 1000 entries max. Use limit parameter to control result size.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')
            limit: Maximum number of entries to return (default 100, max 1000)

        Returns:
            Formatted tool result with DNS cache entries
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                dns_ntp_service = DNSNTPService(session, settings)

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
                    tool_name="dns/get-cache",
                )

                # Get DNS cache
                cache_entries, total_count = await dns_ntp_service.get_dns_cache(device_id, limit)

                content = f"DNS cache contains {len(cache_entries)} entries (showing {limit}, total {total_count})"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        "cache_entries": cache_entries,
                        "total_count": total_count,
                        "returned_count": len(cache_entries),
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
    async def get_ntp_status(device_id: str) -> dict[str, Any]:
        """Get NTP client configuration and synchronization status.

        Use when:
        - User asks "is NTP working?" or "what time servers are configured?"
        - Troubleshooting time synchronization issues
        - Verifying NTP configuration after changes
        - Checking sync status (synchronized vs not synchronized)
        - Diagnosing time drift problems
        - Before planning NTP server updates

        Returns: Enabled status, NTP server list, mode, sync status, stratum, time offset.

        Tip: Check offset_ms - large values indicate sync problems. Compare with system/get-clock.

        Args:
            device_id: Device identifier (e.g., 'dev-lab-01')

        Returns:
            Formatted tool result with NTP status
        """
        try:
            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                dns_ntp_service = DNSNTPService(session, settings)

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
                    tool_name="ntp/get-status",
                )

                # Get NTP status
                ntp_status = await dns_ntp_service.get_ntp_status(device_id)

                if ntp_status["status"] == "synchronized":
                    content = f"NTP synchronized, stratum {ntp_status['stratum']}, offset {ntp_status['offset_ms']:.3f}ms"
                else:
                    content = f"NTP status: {ntp_status['status']}"

                return format_tool_result(
                    content=content,
                    meta={
                        "device_id": device_id,
                        **ntp_status,
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

    logger.info("Registered DNS and NTP tools")
