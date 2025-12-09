"""Tests for configuration module."""

import os
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from routeros_mcp.config import Settings, load_settings_from_file


class TestSettings:
    """Tests for Settings class."""

    def test_default_settings(self) -> None:
        """Test that default settings are valid."""
        settings = Settings()
        assert settings.environment == "lab"
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.mcp_transport == "stdio"
        assert settings.database_url == "sqlite:///./routeros_mcp.db"

    def test_environment_override(self) -> None:
        """Test environment variable override."""
        # Save original env vars
        orig_env = os.environ.get("ROUTEROS_MCP_ENVIRONMENT")
        orig_key = os.environ.get("ROUTEROS_MCP_ENCRYPTION_KEY")

        try:
            os.environ["ROUTEROS_MCP_ENVIRONMENT"] = "prod"
            os.environ["ROUTEROS_MCP_ENCRYPTION_KEY"] = "test-key-for-prod"
            settings = Settings()
            assert settings.environment == "prod"
        finally:
            # Restore original
            if orig_env is not None:
                os.environ["ROUTEROS_MCP_ENVIRONMENT"] = orig_env
            else:
                os.environ.pop("ROUTEROS_MCP_ENVIRONMENT", None)
            if orig_key is not None:
                os.environ["ROUTEROS_MCP_ENCRYPTION_KEY"] = orig_key
            else:
                os.environ.pop("ROUTEROS_MCP_ENCRYPTION_KEY", None)

    def test_explicit_override(self) -> None:
        """Test explicit parameter override."""
        settings = Settings(
            environment="staging", debug=True, encryption_key="test-key-for-staging"
        )
        assert settings.environment == "staging"
        assert settings.debug is True

    def test_database_url_validation(self) -> None:
        """Test database URL validation."""
        # Valid URLs
        Settings(database_url="sqlite:///./test.db")
        Settings(database_url="postgresql://localhost/test")
        Settings(database_url="postgresql+asyncpg://localhost/test")
        Settings(database_url="postgresql+psycopg://localhost/test")

        # Invalid URL
        with pytest.raises(ValidationError, match="database_url must be SQLite"):
            Settings(database_url="mysql://localhost/test")

    def test_oidc_validation(self) -> None:
        """Test OIDC configuration validation."""
        # OIDC enabled without required fields
        with pytest.raises(ValidationError, match="OIDC enabled but missing required fields"):
            Settings(oidc_enabled=True)

        # OIDC enabled with all required fields
        settings = Settings(
            oidc_enabled=True,
            oidc_issuer="https://idp.example.com",
            oidc_client_id="test-client",
            oidc_client_secret="test-secret",
        )
        assert settings.oidc_enabled is True

    def test_encryption_key_validation_lab(self) -> None:
        """Test encryption key validation in lab environment."""
        # Lab environment without key should work with warning
        with pytest.warns(UserWarning, match="encryption_key not set"):
            settings = Settings(environment="lab", encryption_key=None)
            assert settings.encryption_key == "INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION"

    def test_encryption_key_validation_prod(self) -> None:
        """Test encryption key validation in prod environment."""
        # Prod environment without key should fail
        with pytest.raises(ValidationError, match="encryption_key is required"):
            Settings(environment="prod", encryption_key=None)

        # Prod with key should work
        settings = Settings(environment="prod", encryption_key="secure-key-here")
        assert settings.encryption_key == "secure-key-here"

    def test_http_transport_warning(self) -> None:
        """Test HTTP transport without OIDC in prod gives warning."""
        with pytest.warns(UserWarning, match="HTTP transport in production without OIDC"):
            Settings(
                environment="prod",
                mcp_transport="http",
                oidc_enabled=False,
                encryption_key="test-key",
            )

    def test_is_sqlite_property(self) -> None:
        """Test is_sqlite property."""
        settings = Settings(database_url="sqlite:///./test.db")
        assert settings.is_sqlite is True
        assert settings.is_postgresql is False

    def test_is_postgresql_property(self) -> None:
        """Test is_postgresql property."""
        settings = Settings(database_url="postgresql://localhost/test")
        assert settings.is_sqlite is False
        assert settings.is_postgresql is True

    def test_database_driver_property(self) -> None:
        """Test database_driver property."""
        settings = Settings(database_url="sqlite:///./test.db")
        assert settings.database_driver == "sqlite"

        settings = Settings(database_url="postgresql+asyncpg://localhost/test")
        assert settings.database_driver == "asyncpg"

        settings = Settings(database_url="postgresql+psycopg://localhost/test")
        assert settings.database_driver == "psycopg"

        # Plain PostgreSQL URL without driver specification returns "unknown"
        settings = Settings(database_url="postgresql://localhost/test")
        assert settings.database_driver == "unknown"

    def test_to_dict_masks_secrets(self) -> None:
        """Test to_dict masks sensitive fields."""
        settings = Settings(
            encryption_key="secret-key",
            oidc_enabled=True,
            oidc_issuer="https://idp.example.com",
            oidc_client_id="test-client",
            oidc_client_secret="secret-client-secret",
        )
        config_dict = settings.to_dict()

        assert config_dict["encryption_key"] == "***REDACTED***"
        assert config_dict["oidc_client_secret"] == "***REDACTED***"
        assert config_dict["oidc_client_id"] == "test-client"  # Not masked


class TestLoadSettingsFromFile:
    """Tests for load_settings_from_file function."""

    def test_load_yaml_file(self) -> None:
        """Test loading settings from YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(
                """
environment: staging
debug: true
log_level: DEBUG
database_url: postgresql://localhost/test
encryption_key: test-key-for-staging
"""
            )
            f.flush()

            try:
                settings = load_settings_from_file(f.name)
                assert settings.environment == "staging"
                assert settings.debug is True
                assert settings.log_level == "DEBUG"
                assert settings.database_url == "postgresql://localhost/test"
            finally:
                Path(f.name).unlink()

    def test_load_toml_file(self) -> None:
        """Test loading settings from TOML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(
                """
environment = "staging"
debug = true
log_level = "DEBUG"
database_url = "postgresql://localhost/test"
encryption_key = "test-key-for-staging"
"""
            )
            f.flush()

            try:
                settings = load_settings_from_file(f.name)
                assert settings.environment == "staging"
                assert settings.debug is True
                assert settings.log_level == "DEBUG"
                assert settings.database_url == "postgresql://localhost/test"
            finally:
                Path(f.name).unlink()

    def test_file_not_found(self) -> None:
        """Test error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            load_settings_from_file("/nonexistent/config.yaml")

    def test_unsupported_format(self) -> None:
        """Test error for unsupported file format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"environment": "staging"}')
            f.flush()

            try:
                with pytest.raises(ValueError, match="Unsupported config file format"):
                    load_settings_from_file(f.name)
            finally:
                Path(f.name).unlink()

    def test_empty_yaml_file(self) -> None:
        """Test loading empty YAML file uses defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            f.flush()

            try:
                settings = load_settings_from_file(f.name)
                assert settings.environment == "lab"  # Default
                assert settings.debug is False  # Default
            finally:
                Path(f.name).unlink()
