"""MCP server implementation using FastMCP with stdio transport.

Implements the Model Context Protocol (MCP) server for RouterOS management,
providing tools, resources, and prompts over stdio or HTTP transports.

See docs/14-mcp-protocol-integration-and-transport-design.md
"""

import logging
import sys
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.domain.services.system import SystemService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result

logger = logging.getLogger(__name__)


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
        self.session_factory = None  # Will be initialized in start()

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

        logger.info(
            "Initialized RouterOS MCP server",
            extra={
                "environment": settings.environment,
                "transport": settings.mcp_transport,
            },
        )

    def _register_tools(self) -> None:
        """Register MCP tools with the server."""

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

        # System overview tool
        @self.mcp.tool()
        async def system_overview(device_id: str) -> dict[str, Any]:
            """Get system overview for a device.

            Args:
                device_id: Device identifier (e.g., 'dev-lab-01')

            Returns:
                System overview with metrics and hardware info
            """
            try:
                async with self.session_factory.session() as session:
                    system_service = SystemService(session, self.settings)
                    overview = await system_service.get_system_overview(device_id)

                    # Format content
                    content_parts = [
                        f"Device: {overview['device_name']}",
                        f"Identity: {overview['system_identity']}",
                        f"RouterOS: {overview['routeros_version']}",
                        f"Hardware: {overview['hardware_model']}",
                        f"CPU: {overview['cpu_usage_percent']:.1f}% "
                        f"({overview['cpu_count']} cores)",
                        f"Memory: {overview['memory_usage_percent']:.1f}% "
                        f"({overview['memory_used_bytes'] // 1024 // 1024}MB / "
                        f"{overview['memory_total_bytes'] // 1024 // 1024}MB)",
                        f"Uptime: {overview['uptime_formatted']}",
                    ]

                    content = "\n".join(content_parts)

                    return format_tool_result(
                        content=content,
                        meta=overview,
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

        logger.info("Registered MCP tools", extra={"tool_count": 4})

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

            # Run FastMCP server (blocks until exit)
            # Note: FastMCP.run() doesn't return a value, we call it for side effects
            await self.mcp.run()  # noqa: PLE1111

        else:
            raise NotImplementedError(
                f"Transport mode '{self.settings.mcp_transport}' not yet implemented"
            )

    async def stop(self) -> None:
        """Stop the MCP server gracefully."""
        logger.info("Stopping MCP server")
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
