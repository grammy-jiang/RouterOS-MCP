"""Command-line interface for RouterOS MCP Service.

Provides CLI argument parsing and configuration loading with support for:
- Configuration files (YAML/TOML via --config)
- Environment variables (ROUTEROS_MCP_* prefix)
- Command-line argument overrides

Configuration priority (later overrides earlier):
1. Built-in defaults
2. Config file
3. Environment variables
4. CLI arguments
"""

import argparse
from pathlib import Path

from routeros_mcp.config import Settings, load_settings_from_file


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
        "--config",
        "-c",
        type=Path,
        help="Path to configuration file (YAML or TOML)",
    )

    # Application settings
    parser.add_argument(
        "--environment",
        choices=["lab", "staging", "prod"],
        help="Deployment environment",
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    parser.add_argument(
        "--log-format",
        choices=["json", "text"],
        help="Log output format",
    )

    # MCP configuration
    parser.add_argument(
        "--mcp-transport",
        choices=["stdio", "http"],
        help="MCP transport mode",
    )

    parser.add_argument(
        "--mcp-host",
        help="HTTP server bind address",
    )

    parser.add_argument(
        "--mcp-port",
        type=int,
        help="HTTP server port",
    )

    # Database
    parser.add_argument(
        "--database-url",
        help="Database connection URL (SQLite or PostgreSQL)",
    )

    # OIDC
    parser.add_argument(
        "--oidc-enabled",
        action="store_true",
        help="Enable OIDC authentication",
    )

    # Version
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="%(prog)s 0.1.0",
    )

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
    settings = load_settings_from_file(parsed_args.config) if parsed_args.config else Settings()

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
