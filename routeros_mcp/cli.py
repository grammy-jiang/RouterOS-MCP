"""Command-line interface for RouterOS MCP service.

This module provides CLI argument parsing and configuration loading for the
RouterOS MCP server. It supports loading configuration from files, environment
variables, and command-line arguments with proper precedence.
"""

import argparse
import logging
import sys
from pathlib import Path

from routeros_mcp.config import Settings, load_settings_from_file, set_settings


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="routeros-mcp",
        description="RouterOS MCP Service - Manage MikroTik RouterOS devices via MCP",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Config file
    parser.add_argument(
        "--config", "-c", type=Path, help="Path to configuration file (YAML or TOML)"
    )

    # Application settings
    parser.add_argument(
        "--environment", choices=["lab", "staging", "prod"], help="Deployment environment"
    )

    parser.add_argument("--debug", action="store_true", help="Enable debug mode")

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    parser.add_argument("--log-format", choices=["json", "text"], help="Log output format")

    # MCP configuration
    parser.add_argument("--mcp-transport", choices=["stdio", "http"], help="MCP transport mode")

    parser.add_argument("--mcp-host", help="HTTP server bind address")

    parser.add_argument("--mcp-port", type=int, help="HTTP server port")

    # Database
    parser.add_argument("--database-url", help="Database connection URL (SQLite or PostgreSQL)")

    # OIDC
    parser.add_argument("--oidc-enabled", action="store_true", help="Enable OIDC authentication")

    # Version
    parser.add_argument("--version", "-v", action="version", version="%(prog)s 0.1.0")

    return parser


def load_config_from_cli(args: list[str] | None = None) -> Settings:
    """Load configuration from CLI arguments and environment.

    Args:
        args: Command-line arguments (defaults to sys.argv[1:])

    Returns:
        Configured Settings instance

    Example:
        settings = load_config_from_cli()
        settings = load_config_from_cli(["--config", "config/prod.yaml"])
    """
    parser = create_argument_parser()
    parsed_args = parser.parse_args(args)

    # Step 1: Load from config file if provided
    if parsed_args.config:
        settings = load_settings_from_file(parsed_args.config)
    else:
        # Load from environment variables and defaults
        settings = Settings()

    # Step 2: Override with CLI arguments
    cli_overrides = {}

    if parsed_args.environment is not None:
        cli_overrides["environment"] = parsed_args.environment

    if parsed_args.debug:
        cli_overrides["debug"] = True

    if parsed_args.log_level is not None:
        cli_overrides["log_level"] = parsed_args.log_level

    if parsed_args.log_format is not None:
        cli_overrides["log_format"] = parsed_args.log_format

    if parsed_args.mcp_transport is not None:
        cli_overrides["mcp_transport"] = parsed_args.mcp_transport

    if parsed_args.mcp_host is not None:
        cli_overrides["mcp_http_host"] = parsed_args.mcp_host

    if parsed_args.mcp_port is not None:
        cli_overrides["mcp_http_port"] = parsed_args.mcp_port

    if parsed_args.database_url is not None:
        cli_overrides["database_url"] = parsed_args.database_url

    if parsed_args.oidc_enabled:
        cli_overrides["oidc_enabled"] = True

    # Create new settings with overrides
    if cli_overrides:
        settings = Settings(**{**settings.model_dump(), **cli_overrides})

    return settings


def setup_logging(settings: Settings) -> None:
    """Configure logging based on settings.

    Args:
        settings: Application settings

    Note:
        For stdio transport, logs are sent to stderr to avoid interfering
        with the MCP protocol on stdout.
    """
    log_level = getattr(logging, settings.log_level)

    # For stdio transport, logs MUST go to stderr (not stdout)
    # to avoid interfering with MCP JSON-RPC protocol
    if settings.mcp_transport == "stdio":
        stream = sys.stderr
    else:
        stream = sys.stdout

    if settings.log_format == "json":
        # TODO: Use structlog for structured JSON logging in future enhancement
        # For now, use simple format
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    else:
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(level=log_level, format=log_format, stream=stream, force=True)

    # Log effective configuration (masking secrets)
    logger = logging.getLogger(__name__)
    logger.info("RouterOS MCP Service starting")
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"MCP Transport: {settings.mcp_transport}")
    logger.info(f"Database Driver: {settings.database_driver}")

    if settings.mcp_transport == "http":
        logger.info(f"HTTP Server: {settings.mcp_http_host}:{settings.mcp_http_port}")

    if settings.debug:
        logger.warning("Debug mode enabled - not for production use")


def main() -> int:
    """Main entry point for RouterOS MCP CLI.

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    try:
        # Load configuration from CLI arguments and environment
        settings = load_config_from_cli()

        # Set global settings
        set_settings(settings)

        # Setup logging
        setup_logging(settings)

        logger = logging.getLogger(__name__)

        # Log configuration loaded successfully
        logger.info("Configuration loaded and validated successfully")

        # TODO: Start MCP server (to be implemented in later tasks)
        logger.info("MCP server would start here (to be implemented)")
        logger.info("Press Ctrl+C to stop")

        # For now, just wait for interrupt
        try:
            import time

            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
