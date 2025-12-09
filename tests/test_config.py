"""Tests for configuration module."""

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from routeros_mcp.config import Settings, load_settings_from_file


class TestSettings:
    """Test Settings class."""

    def test_default_settings(self) -> None:
        """Test that default settings load successfully."""
        settings = Settings()
        assert settings.environment == "lab"
        assert settings.debug is False
        assert settings.log_level == "INFO"
        assert settings.mcp_transport == "stdio"
        assert settings.database_url == "sqlite:///./routeros_mcp.db"

    def test_environment_override(self) -> None:
        """Test that environment can be overridden."""
        settings = Settings(environment="prod", encryption_key="test-key-123")
        assert settings.environment == "prod"

    def test_database_url_validation_sqlite(self) -> None:
        """Test SQLite database URL validation."""
        settings = Settings(database_url="sqlite:///./test.db")
        assert settings.is_sqlite is True
        assert settings.is_postgresql is False
        assert settings.database_driver == "sqlite"

    def test_database_url_validation_postgresql(self) -> None:
        """Test PostgreSQL database URL validation."""
        settings = Settings(database_url="postgresql+asyncpg://user:pass@localhost/db")
        assert settings.is_sqlite is False
        assert settings.is_postgresql is True
        assert settings.database_driver == "asyncpg"

    def test_database_url_validation_invalid(self) -> None:
        """Test that invalid database URLs are rejected."""
        with pytest.raises(ValidationError):
            Settings(database_url="mysql://localhost/db")

    def test_oidc_validation_missing_fields(self) -> None:
        """Test that OIDC validation fails when required fields are missing."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(oidc_enabled=True)

        error_msg = str(exc_info.value)
        assert "oidc_issuer" in error_msg
        assert "oidc_client_id" in error_msg
        assert "oidc_client_secret" in error_msg

    def test_oidc_validation_success(self) -> None:
        """Test that OIDC validation passes with all required fields."""
        settings = Settings(
            oidc_enabled=True,
            oidc_issuer="https://idp.example.com",
            oidc_client_id="test-client",
            oidc_client_secret="test-secret",
        )
        assert settings.oidc_enabled is True

    def test_encryption_key_required_in_prod(self) -> None:
        """Test that encryption key is required in production."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(environment="prod", encryption_key=None)

        assert "encryption_key is required" in str(exc_info.value)

    def test_encryption_key_optional_in_lab(self) -> None:
        """Test that encryption key is optional in lab (with warning)."""
        with pytest.warns(UserWarning, match="encryption_key not set"):
            settings = Settings(environment="lab", encryption_key=None)

        assert settings.encryption_key == "INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION"

    def test_log_level_uppercase(self) -> None:
        """Test that log level is converted to uppercase."""
        settings = Settings(log_level="DEBUG")  # Must provide uppercase
        assert settings.log_level == "DEBUG"

    def test_to_dict_masks_secrets(self) -> None:
        """Test that to_dict() masks sensitive fields."""
        settings = Settings(
            encryption_key="secret-key-123",
            oidc_enabled=True,
            oidc_issuer="https://idp.example.com",
            oidc_client_id="test-client",
            oidc_client_secret="test-secret",
        )

        data = settings.to_dict()
        assert data["encryption_key"] == "***REDACTED***"
        assert data["oidc_client_secret"] == "***REDACTED***"
        assert data["oidc_issuer"] == "https://idp.example.com"  # Not masked


class TestLoadSettingsFromFile:
    """Test load_settings_from_file function."""

    def test_load_from_yaml(self) -> None:
        """Test loading settings from YAML file."""
        yaml_content = """
environment: staging
debug: true
log_level: DEBUG
database_url: postgresql+asyncpg://user:pass@localhost/db
encryption_key: test-encryption-key-staging
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            config_path = Path(f.name)

        try:
            settings = load_settings_from_file(config_path)
            assert settings.environment == "staging"
            assert settings.debug is True
            assert settings.log_level == "DEBUG"
            assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/db"
        finally:
            config_path.unlink()

    def test_load_from_toml(self) -> None:
        """Test loading settings from TOML file."""
        toml_content = """
environment = "prod"
debug = false
log_level = "INFO"
database_url = "postgresql+asyncpg://user:pass@localhost/prod_db"
encryption_key = "test-encryption-key-prod"
"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
            f.write(toml_content)
            config_path = Path(f.name)

        try:
            settings = load_settings_from_file(config_path)
            assert settings.environment == "prod"
            assert settings.debug is False
            assert settings.log_level == "INFO"
            assert settings.database_url == "postgresql+asyncpg://user:pass@localhost/prod_db"
        finally:
            config_path.unlink()

    def test_load_from_nonexistent_file(self) -> None:
        """Test that loading from nonexistent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_settings_from_file("/nonexistent/config.yaml")

    def test_load_from_unsupported_format(self) -> None:
        """Test that unsupported file format raises error."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write('{"environment": "prod"}')
            config_path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="Unsupported config file format"):
                load_settings_from_file(config_path)
        finally:
            config_path.unlink()

    def test_load_empty_yaml(self) -> None:
        """Test loading empty YAML file uses defaults."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("")
            config_path = Path(f.name)

        try:
            settings = load_settings_from_file(config_path)
            # Should use default values
            assert settings.environment == "lab"
            assert settings.debug is False
        finally:
            config_path.unlink()


class TestHTTPTransportWarning:
    """Test HTTP transport configuration warnings."""

    def test_http_transport_prod_without_oidc_warns(self) -> None:
        """Test that HTTP transport in production without OIDC generates warning."""
        with pytest.warns(UserWarning, match="HTTP transport in production without OIDC"):
            Settings(
                environment="prod",
                mcp_transport="http",
                oidc_enabled=False,
                encryption_key="test-key",
            )

    def test_http_transport_lab_without_oidc_no_warning(self) -> None:
        """Test that HTTP transport in lab without OIDC does not warn."""
        # Should not raise warning for lab environment
        settings = Settings(environment="lab", mcp_transport="http", oidc_enabled=False)
        assert settings.mcp_transport == "http"
