"""Main entry point for RouterOS MCP Service.

This module provides the main entry point that:
1. Loads and validates configuration
2. Sets up logging
3. Prepares to start the MCP server (implementation in later tasks)
4. Handles graceful shutdown on SIGTERM/SIGINT
"""

import asyncio
import contextlib
import logging
import signal
import sys
from urllib.parse import urlparse, urlunparse

from routeros_mcp.cli import load_config_from_cli
from routeros_mcp.config import Settings, set_settings


def sanitize_database_url(url: str) -> str:  # pragma: no cover
    """Sanitize database URL by redacting password.

    Args:
        url: Database URL that may contain credentials

    Returns:
        Sanitized URL with password redacted
    """
    try:
        parsed = urlparse(url)
        if parsed.password:
            # Reconstruct netloc with password redacted
            netloc = parsed.username or ""
            if parsed.password:
                netloc += ":***"
            if parsed.hostname:
                netloc += f"@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            parsed = parsed._replace(netloc=netloc)
        return urlunparse(parsed)
    except Exception:
        # If parsing fails, just return a generic message
        return "***REDACTED***"


def setup_logging(settings: Settings) -> None:  # pragma: no cover
    """Configure logging based on settings.

    For stdio transport, logs go to stderr only (stdout is for MCP protocol).
    For http transport, logs can go to stdout.

    Args:
        settings: Settings instance with log configuration
    """
    # Determine log stream based on transport mode
    # CRITICAL: Only logs to stderr for stdio transport (stdout is for MCP protocol messages)
    log_stream = sys.stderr if settings.mcp_transport == "stdio" else sys.stdout

    # Configure basic logging
    log_level = getattr(logging, settings.log_level)

    if settings.log_format == "json":
        # JSON structured logging (basic implementation, can be enhanced with structlog)
        logging.basicConfig(
            level=log_level,
            format='{"timestamp":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
            stream=log_stream,
            force=True,
        )
    else:
        # Human-readable text logging
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            stream=log_stream,
            force=True,
        )


def print_startup_banner(settings: Settings) -> None:  # pragma: no cover
    """Print startup banner with configuration information.

    Args:
        settings: Settings instance
    """
    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("RouterOS MCP Service")
    logger.info("Version: 0.1.0")
    logger.info("=" * 60)
    logger.info("")
    logger.info("Configuration:")
    logger.info(f"  Environment: {settings.environment}")
    logger.info(f"  Debug: {settings.debug}")
    logger.info(f"  Log Level: {settings.log_level}")
    logger.info(f"  Log Format: {settings.log_format}")
    logger.info("")
    logger.info("MCP Settings:")
    logger.info(f"  Transport: {settings.mcp_transport}")
    if settings.mcp_transport == "http":
        logger.info(f"  HTTP Host: {settings.mcp_http_host}")
        logger.info(f"  HTTP Port: {settings.mcp_http_port}")
        logger.info(f"  HTTP Base Path: {settings.mcp_http_base_path}")
    logger.info("")
    logger.info("Database:")
    logger.info(f"  URL: {sanitize_database_url(settings.database_url)}")
    logger.info(f"  Driver: {settings.database_driver}")
    logger.info(f"  Pool Size: {settings.database_pool_size}")
    logger.info("")

    if settings.oidc_enabled:
        logger.info("OIDC Authentication:")
        logger.info(f"  Enabled: {settings.oidc_enabled}")
        logger.info(f"  Issuer: {settings.oidc_issuer}")
        logger.info(f"  Client ID: {settings.oidc_client_id}")
        logger.info("")

    logger.info("=" * 60)


class GracefulShutdown:
    """Graceful shutdown coordinator.

    Manages shutdown signal handling and resource cleanup with
    configurable drain window for in-flight requests.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        """Initialize shutdown coordinator.

        Args:
            timeout: Drain window timeout in seconds
        """
        self.timeout = timeout
        self._shutdown_event = asyncio.Event()
        self._server: any = None
        self._http_app: any = None

    def set_server(self, server: any) -> None:
        """Register MCP server for shutdown.

        Args:
            server: MCP server instance
        """
        self._server = server

    def set_http_app(self, app: any) -> None:
        """Register HTTP app for shutdown.

        Args:
            app: FastAPI app instance
        """
        self._http_app = app

    def _handle_signal(self, signum: int) -> None:
        """Signal handler that triggers shutdown.

        Args:
            signum: Signal number
        """
        signal_name = signal.Signals(signum).name
        logger = logging.getLogger(__name__)
        logger.info(
            f"Received {signal_name}, initiating graceful shutdown",
            extra={"signal": signal_name, "timeout": self.timeout},
        )
        self._shutdown_event.set()

    def register_handlers(self) -> None:
        """Register signal handlers for SIGTERM and SIGINT."""
        signal.signal(signal.SIGTERM, lambda s, _f: self._handle_signal(s))
        signal.signal(signal.SIGINT, lambda s, _f: self._handle_signal(s))

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    async def cleanup(self) -> None:
        """Cleanup resources during shutdown."""
        logger = logging.getLogger(__name__)

        # Mark HTTP app as shutting down (for health endpoint)
        if self._http_app:
            self._http_app.state._is_shutting_down = True
            logger.info("HTTP app marked as shutting down")

        # Wait for drain window
        logger.info(f"Waiting {self.timeout}s for in-flight requests to complete")
        await asyncio.sleep(self.timeout)

        # Stop MCP server
        if self._server:
            await self._server.stop()
            logger.info("MCP server stopped")

        # Close database connections
        try:
            from routeros_mcp.infra.db.session import get_session_manager

            manager = get_session_manager()
            await manager.close()
            logger.info("Database connections closed")
        except RuntimeError:
            # Session manager not initialized
            pass

        # Close Redis cache if enabled
        try:
            from routeros_mcp.infra.cache import get_redis_cache, reset_redis_cache

            cache = get_redis_cache()
            await cache.close()
            reset_redis_cache()
            logger.info("Redis cache closed")
        except RuntimeError:
            # Cache not initialized
            pass

        logger.info("Graceful shutdown complete")


def main() -> int:  # pragma: no cover
    """Main entry point for RouterOS MCP Service.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Step 1: Load configuration from CLI and environment
        settings = load_config_from_cli()
        set_settings(settings)

        # Step 2: Setup logging
        setup_logging(settings)

        # Step 3: Print startup banner
        print_startup_banner(settings)

        logger = logging.getLogger(__name__)

        # Step 4: Validate configuration (basic validation already done by Pydantic)
        logger.info("Configuration validation passed")

        # Step 5: Start MCP server based on transport mode
        if settings.mcp_transport in ("stdio", "http"):
            logger.info(f"Starting MCP server in {settings.mcp_transport} mode")

            # Import here to avoid circular dependencies
            from routeros_mcp.mcp.server import create_mcp_server

            # Run async server with graceful shutdown
            async def run_server() -> None:
                # Create shutdown coordinator
                shutdown = GracefulShutdown(timeout=30.0)
                shutdown.register_handlers()

                # Create and start server
                server = await create_mcp_server(settings)
                shutdown.set_server(server)

                # For HTTP transport, get the FastAPI app for shutdown state
                if settings.mcp_transport == "http":
                    # The HTTP app is created inside server.start(), so we
                    # can't access it here. The shutdown state will be checked
                    # via app.state._is_shutting_down in the health endpoint.
                    pass

                # Start server in background task
                server_task = asyncio.create_task(server.start())

                # Wait for shutdown signal
                await shutdown.wait_for_shutdown()

                # Cleanup resources
                await shutdown.cleanup()

                # Cancel server task if still running
                if not server_task.done():
                    server_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await server_task

            # Ensure an event loop exists without using deprecated get_event_loop()
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            asyncio.run(run_server())
            return 0
        else:
            logger.error(f"Unknown transport mode: {settings.mcp_transport}")
            return 1

    except KeyboardInterrupt:
        print("\nShutdown requested... exiting", file=sys.stderr)
        return 0
    except Exception as e:
        # Log the error and exit with error code
        if "settings" in locals():
            logger = logging.getLogger(__name__)
            logger.exception(f"Fatal error: {e}")
        else:
            # Logging not yet configured, print to stderr
            print(f"Fatal error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
