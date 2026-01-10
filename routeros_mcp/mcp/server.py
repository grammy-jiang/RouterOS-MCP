"""MCP server implementation using FastMCP with stdio transport.

Implements the Model Context Protocol (MCP) server for RouterOS management,
providing tools, resources, and prompts over stdio or HTTP transports.

See docs/14-mcp-protocol-integration-and-transport-design.md
"""

import logging
import sys
from typing import TYPE_CHECKING, Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.domain.services.system import SystemService
from routeros_mcp.infra.db.session import (
    DatabaseSessionManager,
    get_session_factory,
    initialize_session_manager,
)
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result

if TYPE_CHECKING:
    from routeros_mcp.mcp.transport.sse_manager import SSEManager

logger = logging.getLogger(__name__)

# Global SSE manager instance (initialized by HTTP/SSE transport)
_sse_manager: "SSEManager | None" = None


def get_sse_manager() -> "SSEManager | None":
    """Get the global SSE manager instance.

    Returns:
        SSEManager instance if HTTP/SSE transport is active, None otherwise
    """
    return _sse_manager


def set_sse_manager(manager: "SSEManager") -> None:
    """Set the global SSE manager instance.

    Args:
        manager: SSEManager instance to use
    """
    global _sse_manager
    _sse_manager = manager


class RouterOSMCPServer:
    """RouterOS MCP server wrapper around FastMCP.

    Provides:
    - Tool registration and execution
    - Error handling and JSON-RPC compliance
    - Session and service management
    - Stdio transport integration

    Example:
        settings = Settings()
        server = RouterOSMCPServer(settings)
        await server.start()
    """

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        """Initialize MCP server.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.session_factory: DatabaseSessionManager | None = None  # Will be initialized in start()
        self.scheduler: Any = None  # Will be initialized in start() if snapshot_capture_enabled

        # Create FastMCP instance
        self.mcp = FastMCP(
            name="routeros-mcp",
            version="0.1.0",
            instructions="""
RouterOS MCP Service - Manage MikroTik RouterOS devices via MCP protocol.

This service provides tools for:
- Device health monitoring and diagnostics
- System information and metrics collection
- Network configuration and management
- DNS and NTP configuration
- Firewall and security management

All operations respect environment boundaries (lab/staging/prod) and
require appropriate device capabilities and permissions.
""".strip(),
        )

        # Register tools
        self._register_tools()

        # Register prompts (can be done immediately)
        self._register_prompts()

        logger.info(
            "Initialized RouterOS MCP server",
            extra={
                "environment": settings.environment,
                "transport": settings.mcp_transport,
            },
        )

    def _register_tools(self) -> None:
        """Register MCP tools with the server."""
        # Import tool registration functions
        from routeros_mcp.mcp_tools import (
            register_bridge_tools,
            register_config_tools,
            register_device_tools,
            register_dhcp_tools,
            register_diagnostics_tools,
            register_dns_ntp_tools,
            register_firewall_logs_tools,
            register_firewall_write_tools,
            register_interface_tools,
            register_ip_tools,
            register_routing_tools,
            register_system_tools,
            register_wireless_tools,
        )

        # Echo tool for testing
        @self.mcp.tool()
        async def echo(message: str) -> dict[str, Any]:
            """Echo back a message (for testing).

            Args:
                message: Message to echo back

            Returns:
                Echo response with metadata
            """
            return format_tool_result(
                content=f"Echo: {message}",
                meta={
                    "original_message": message,
                    "environment": self.settings.environment,
                },
            )

        # Service health tool
        @self.mcp.tool()
        async def service_health() -> dict[str, Any]:
            """Get service health status and configuration.

            Returns:
                Service health information
            """
            return format_tool_result(
                content="Service is running",
                meta={
                    "environment": self.settings.environment,
                    "transport": self.settings.mcp_transport,
                    "database": "connected",
                },
            )

        # Device health tool
        @self.mcp.tool()
        async def device_health(device_id: str) -> dict[str, Any]:
            """Check health of a specific device.

            Args:
                device_id: Device identifier (e.g., 'dev-lab-01')

            Returns:
                Device health status with metrics
            """
            try:
                if self.session_factory is None:
                    return format_tool_result(
                        content="Error: session factory not initialized",
                        is_error=True,
                    )
                async with self.session_factory.session() as session:
                    health_service = HealthService(session, self.settings)
                    result = await health_service.run_health_check(device_id)

                    # Format content
                    content_parts = [
                        f"Device: {device_id}",
                        f"Status: {result.status}",
                    ]

                    if result.cpu_usage_percent is not None:
                        content_parts.append(
                            f"CPU: {result.cpu_usage_percent:.1f}%"
                        )

                    if result.memory_usage_percent is not None:
                        content_parts.append(
                            f"Memory: {result.memory_usage_percent:.1f}%"
                        )

                    if result.uptime_seconds is not None:
                        uptime_hours = result.uptime_seconds / 3600
                        content_parts.append(f"Uptime: {uptime_hours:.1f}h")

                    if result.issues:
                        content_parts.append(f"Issues: {', '.join(result.issues)}")

                    if result.warnings:
                        content_parts.append(
                            f"Warnings: {', '.join(result.warnings)}"
                        )

                    content = "\n".join(content_parts)

                    return format_tool_result(
                        content=content,
                        is_error=result.status != "healthy",
                        meta={
                            "device_id": device_id,
                            "status": result.status,
                            "timestamp": result.timestamp.isoformat(),
                            "cpu_usage_percent": result.cpu_usage_percent,
                            "memory_usage_percent": result.memory_usage_percent,
                            "uptime_seconds": result.uptime_seconds,
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

        # Register all fundamental read-only tools by topic
        register_device_tools(self.mcp, self.settings)
        register_system_tools(self.mcp, self.settings)
        register_interface_tools(self.mcp, self.settings)
        register_bridge_tools(self.mcp, self.settings)
        register_ip_tools(self.mcp, self.settings)
        register_dns_ntp_tools(self.mcp, self.settings)
        register_dhcp_tools(self.mcp, self.settings)
        register_routing_tools(self.mcp, self.settings)
        register_firewall_logs_tools(self.mcp, self.settings)
        register_firewall_write_tools(self.mcp, self.settings)
        register_config_tools(self.mcp, self.settings)
        register_wireless_tools(self.mcp, self.settings)
        register_diagnostics_tools(self.mcp, self.settings)

        logger.info("Registered all MCP tools")

    def _register_resources(self) -> None:
        """Register MCP resources with the server."""
        # Import resource registration functions
        from routeros_mcp.mcp_resources import (
            register_device_resources,
            register_fleet_resources,
            register_plan_resources,
            register_audit_resources,
        )

        # Note: Resources need session_factory which is initialized in start()
        # We'll register them in start() instead
        logger.info("Resource registration deferred to start()")

    def _register_prompts(self) -> None:
        """Register MCP prompts with the server."""
        # Import prompts registration function
        from routeros_mcp.mcp_prompts import register_prompts

        # Register YAML-backed prompts
        try:
            register_prompts(self.mcp, self.settings)
            logger.info("Registered MCP prompts")
        except Exception as e:
            logger.error(f"Failed to register prompts: {e}", exc_info=True)

    async def start(self) -> None:
        """Start the MCP server.

        For stdio transport, this runs the FastMCP server which handles
        JSON-RPC messages on stdin/stdout.
        """
        logger.info(
            "Starting MCP server",
            extra={
                "transport": self.settings.mcp_transport,
                "environment": self.settings.environment,
            },
        )

        # Initialize database session factory
        self.session_factory = await initialize_session_manager(self.settings)
        logger.info("Database session manager initialized")

        # Initialize resource cache
        from routeros_mcp.infra.observability.resource_cache import initialize_cache

        initialize_cache(
            ttl_seconds=self.settings.mcp_resource_cache_ttl_seconds,
            max_entries=self.settings.mcp_resource_cache_max_entries,
            enabled=self.settings.mcp_resource_cache_enabled,
        )
        logger.info(
            "Resource cache initialized",
            extra={
                "enabled": self.settings.mcp_resource_cache_enabled,
                "ttl_seconds": self.settings.mcp_resource_cache_ttl_seconds,
                "max_entries": self.settings.mcp_resource_cache_max_entries,
            },
        )

        # Register resources (now that we have session_factory)
        from routeros_mcp.mcp_resources import (
            register_device_resources,
            register_bridge_resources,
            register_dhcp_resources,
            register_fleet_resources,
            register_plan_resources,
            register_audit_resources,
            register_wireless_resources,
        )

        try:
            register_device_resources(self.mcp, self.session_factory, self.settings)
            register_bridge_resources(self.mcp, self.session_factory, self.settings)
            register_dhcp_resources(self.mcp, self.session_factory, self.settings)
            register_fleet_resources(self.mcp, self.session_factory, self.settings)
            register_plan_resources(self.mcp, self.session_factory, self.settings)
            register_audit_resources(self.mcp, self.session_factory, self.settings)
            register_wireless_resources(self.mcp, self.session_factory, self.settings)
            logger.info("Registered MCP resources")
        except Exception as e:
            logger.error(f"Failed to register resources: {e}", exc_info=True)

        # Initialize and start job scheduler (Phase 2.1)
        if self.settings.snapshot_capture_enabled:
            from routeros_mcp.infra.jobs.scheduler import JobScheduler
            from routeros_mcp.infra.jobs.runner import (
                run_snapshot_capture_job,
                run_retention_cleanup_job,
            )

            self.scheduler = JobScheduler(self.settings)
            await self.scheduler.start()
            logger.info("Job scheduler started")

            # Register periodic snapshot capture job
            async def snapshot_capture_job() -> None:
                assert self.session_factory is not None
                await run_snapshot_capture_job(self.session_factory, self.settings)

            self.scheduler.add_snapshot_capture_job(snapshot_capture_job)
            logger.info(
                "Snapshot capture job registered",
                extra={
                    "interval_seconds": self.settings.snapshot_capture_interval_seconds,
                },
            )

            # Register retention cleanup job (hourly)
            async def retention_cleanup_job() -> None:
                assert self.session_factory is not None
                await run_retention_cleanup_job(self.session_factory, self.settings)

            self.scheduler.add_retention_cleanup_job(retention_cleanup_job)
            logger.info("Retention cleanup job registered")
        else:
            logger.info("Snapshot capture disabled, scheduler not started")

        if self.settings.mcp_transport == "stdio":
            # Configure logging to stderr only for stdio mode
            # This is critical - stdout is reserved for JSON-RPC messages
            for handler in logging.root.handlers[:]:
                logging.root.removeHandler(handler)

            stderr_handler = logging.StreamHandler(sys.stderr)
            stderr_handler.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                )
            )
            logging.root.addHandler(stderr_handler)
            logging.root.setLevel(
                logging.DEBUG if self.settings.debug else logging.INFO
            )

            logger.info("MCP server running in stdio mode")

            # Run FastMCP server using the async stdio helper when available, otherwise fall back
            # to a generic run() for test doubles that do not implement run_stdio_async.
            run_stdio = getattr(self.mcp, "run_stdio_async", None)
            if callable(run_stdio):
                await run_stdio(
                    show_banner=True,
                    log_level=self.settings.log_level.lower(),
                )
            elif hasattr(self.mcp, "run"):
                await self.mcp.run()
            else:  # pragma: no cover - defensive branch
                raise AttributeError("MCP instance missing run/run_stdio_async")

        elif self.settings.mcp_transport == "http":
            # HTTP/SSE transport mode
            from routeros_mcp.mcp.transport.http_sse import HTTPSSETransport

            logger.info("MCP server running in HTTP/SSE mode")

            # Create and run HTTP/SSE transport
            transport = HTTPSSETransport(self.settings, self.mcp)
            await transport.run()

        else:
            raise NotImplementedError(
                f"Transport mode '{self.settings.mcp_transport}' not yet implemented"
            )

    async def stop(self) -> None:
        """Stop the MCP server gracefully."""
        logger.info("Stopping MCP server")
        
        # Stop job scheduler if running
        if self.scheduler:
            await self.scheduler.shutdown(wait=True)
            logger.info("Job scheduler stopped")
        
        # FastMCP handles cleanup automatically


async def create_mcp_server(settings: Settings | None = None) -> RouterOSMCPServer:
    """Create and initialize MCP server.

    Args:
        settings: Application settings (defaults to global settings)

    Returns:
        Initialized MCP server
    """
    if settings is None:
        from routeros_mcp.config import get_settings
        settings = get_settings()

    server = RouterOSMCPServer(settings)
    return server
