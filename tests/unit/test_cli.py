"""Tests for CLI module."""

import tempfile
from pathlib import Path

import pytest

from routeros_mcp.cli import create_argument_parser, load_config_from_cli


class TestCreateArgumentParser:
    """Tests for create_argument_parser function."""

    def test_parser_creation(self) -> None:
        """Test that parser is created successfully."""
        parser = create_argument_parser()
        assert parser is not None
        assert parser.prog == "routeros-mcp"

    def test_parser_help(self) -> None:
        """Test that help text is available."""
        parser = create_argument_parser()
        help_text = parser.format_help()
        assert "RouterOS MCP Service" in help_text
        assert "--config" in help_text
        assert "--environment" in help_text


class TestLoadConfigFromCli:
    """Tests for load_config_from_cli function."""

    def test_load_default_config(self) -> None:
        """Test loading default configuration."""
        settings = load_config_from_cli([])
        assert settings.environment == "lab"
        assert settings.debug is False

    def test_cli_override_environment(self) -> None:
        """Test CLI override for environment."""
        settings = load_config_from_cli(["--environment", "staging"])
        assert settings.environment == "staging"

    def test_cli_override_debug(self) -> None:
        """Test CLI override for debug flag."""
        settings = load_config_from_cli(["--debug"])
        assert settings.debug is True

    def test_cli_override_log_level(self) -> None:
        """Test CLI override for log level."""
        settings = load_config_from_cli(["--log-level", "DEBUG"])
        assert settings.log_level == "DEBUG"

    def test_cli_override_log_format(self) -> None:
        """Test CLI override for log format."""
        settings = load_config_from_cli(["--log-format", "text"])
        assert settings.log_format == "text"

    def test_cli_override_transport(self) -> None:
        """Test CLI override for MCP transport."""
        settings = load_config_from_cli(["--mcp-transport", "http"])
        assert settings.mcp_transport == "http"

    def test_cli_override_mcp_host(self) -> None:
        """Test CLI override for MCP HTTP host."""
        settings = load_config_from_cli(["--mcp-host", "0.0.0.0"])
        assert settings.mcp_http_host == "0.0.0.0"

    def test_cli_override_mcp_port(self) -> None:
        """Test CLI override for MCP HTTP port."""
        settings = load_config_from_cli(["--mcp-port", "9090"])
        assert settings.mcp_http_port == 9090

    def test_cli_override_database_url(self) -> None:
        """Test CLI override for database URL."""
        settings = load_config_from_cli(["--database-url", "postgresql://localhost/test"])
        assert settings.database_url == "postgresql://localhost/test"

    def test_cli_override_oidc_enabled(self) -> None:
        """Test CLI override for OIDC enabled flag."""
        # This should fail validation since OIDC requires other fields
        from pydantic import ValidationError

        with pytest.raises(ValidationError):  # Will raise ValidationError
            load_config_from_cli(["--oidc-enabled"])

    def test_config_file_loading(self) -> None:
        """Test loading configuration from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
environment: staging
debug: true
log_level: WARNING
database_url: postgresql://localhost/testdb
encryption_key: test-key-for-staging
"""
            )
            f.flush()

            try:
                settings = load_config_from_cli(["--config", f.name])
                assert settings.environment == "staging"
                assert settings.debug is True
                assert settings.log_level == "WARNING"
                assert settings.database_url == "postgresql://localhost/testdb"
            finally:
                Path(f.name).unlink()

    def test_config_file_with_cli_override(self) -> None:
        """Test that CLI arguments override config file values."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
environment: staging
debug: false
log_level: INFO
encryption_key: test-key-for-staging
"""
            )
            f.flush()

            try:
                settings = load_config_from_cli(
                    ["--config", f.name, "--environment", "prod", "--debug", "--log-level", "DEBUG"]
                )
                assert settings.environment == "prod"  # CLI override
                assert settings.debug is True  # CLI override
                assert settings.log_level == "DEBUG"  # CLI override
            finally:
                Path(f.name).unlink()

    def test_multiple_overrides(self) -> None:
        """Test multiple CLI overrides at once."""
        settings = load_config_from_cli(
            [
                "--environment",
                "staging",
                "--debug",
                "--log-level",
                "DEBUG",
                "--mcp-transport",
                "http",
                "--mcp-port",
                "8888",
            ]
        )
        assert settings.environment == "staging"
        assert settings.debug is True
        assert settings.log_level == "DEBUG"
        assert settings.mcp_transport == "http"
        assert settings.mcp_http_port == 8888
