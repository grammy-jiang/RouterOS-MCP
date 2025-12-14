"""Configuration module for RouterOS MCP Service.

Implements Pydantic v2 Settings for configuration management with support for:
- Environment variables (ROUTEROS_MCP_* prefix)
- YAML/TOML configuration files
- Command-line argument overrides
- Fail-fast validation at startup

Configuration priority (later overrides earlier):
1. Built-in defaults
2. Configuration file (YAML/TOML)
3. Environment variables
4. Command-line arguments
"""

import warnings
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration with sensible defaults.

    Configuration priority (later overrides earlier):
    1. Built-in defaults
    2. Config file (specified via --config or ROUTEROS_MCP_CONFIG_FILE)
    3. Environment variables (ROUTEROS_MCP_* prefix)
    4. Command-line arguments (passed after loading)

    Example:
        # Load from environment only
        settings = Settings()

        # Load from config file
        settings = Settings(_env_file="config/prod.yaml")

        # Override specific values
        settings = Settings(environment="prod", debug=False)
    """

    model_config = SettingsConfigDict(
        env_prefix="ROUTEROS_MCP_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore unknown fields
    )

    # ========================================
    # Application Settings
    # ========================================

    environment: Literal["lab", "staging", "prod"] = Field(
        default="lab", description="Deployment environment"
    )

    debug: bool = Field(default=False, description="Enable debug mode with verbose logging")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", description="Logging level"
    )

    log_format: Literal["json", "text"] = Field(default="json", description="Log output format")

    # ========================================
    # MCP Configuration
    # ========================================

    mcp_transport: Literal["stdio", "http"] = Field(
        default="stdio", description="MCP transport mode"
    )

    mcp_description: str = Field(
        default="RouterOS MCP Service", description="Service description for MCP"
    )

    mcp_http_host: str = Field(
        default="127.0.0.1",
        description="HTTP server bind address (0.0.0.0 for all interfaces)",
    )

    mcp_http_port: int = Field(default=8080, ge=1, le=65535, description="HTTP server port")

    mcp_http_base_path: str = Field(default="/mcp", description="Base path for MCP HTTP endpoints")

    # ========================================
    # Database Configuration
    # ========================================

    database_url: str = Field(
        default="sqlite+aiosqlite:///./routeros_mcp.db",
        description="Database connection URL (SQLite or PostgreSQL)",
    )

    database_pool_size: int = Field(
        default=5, ge=1, le=100, description="Database connection pool size"
    )

    database_max_overflow: int = Field(
        default=10, ge=0, le=100, description="Max overflow connections beyond pool size"
    )

    database_echo: bool = Field(
        default=False, description="Echo SQL statements to logs (debug only)"
    )

    # ========================================
    # OIDC Authentication (HTTP Transport)
    # ========================================

    oidc_enabled: bool = Field(default=False, description="Enable OIDC authentication")

    oidc_issuer: str | None = Field(default=None, description="OIDC issuer URL")

    oidc_client_id: str | None = Field(default=None, description="OIDC client ID")

    oidc_client_secret: str | None = Field(default=None, description="OIDC client secret")

    oidc_audience: str | None = Field(default=None, description="Expected token audience")

    # ========================================
    # RouterOS Integration
    # ========================================

    routeros_rest_timeout_seconds: float = Field(
        default=5.0, ge=1.0, le=60.0, description="REST API call timeout"
    )

    routeros_max_concurrent_per_device: int = Field(
        default=3, ge=1, le=10, description="Max concurrent REST calls per device"
    )

    routeros_retry_attempts: int = Field(
        default=3, ge=0, le=10, description="Number of retry attempts for failed calls"
    )

    routeros_retry_backoff_seconds: float = Field(
        default=1.0, ge=0.1, le=60.0, description="Exponential backoff base for retries"
    )

    routeros_verify_ssl: bool = Field(
        default=True,
        description="Verify SSL certificates for RouterOS REST API. "
        "Set to False for self-signed certificates (lab environments only)",
    )

    # ========================================
    # Health Checks & Metrics
    # ========================================

    health_check_interval_seconds: int = Field(
        default=60, ge=10, le=3600, description="Health check interval"
    )

    health_check_jitter_seconds: int = Field(
        default=10, ge=0, le=300, description="Random jitter added to health check interval"
    )

    metrics_collection_interval_seconds: int = Field(
        default=300, ge=60, le=3600, description="Metrics collection interval"
    )

    # ========================================
    # Security & Encryption
    # ========================================

    encryption_key: str | None = Field(
        default=None,
        description="Master encryption key for secrets (base64, 32+ bytes)",
    )

    encryption_algorithm: Literal["fernet"] = Field(
        default="fernet", description="Encryption algorithm for secrets"
    )

    # ========================================
    # Validators
    # ========================================

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not (
            v.startswith("sqlite:///")
            or v.startswith("sqlite+aiosqlite:///")
            or v.startswith("sqlite://")
            or v.startswith("sqlite+aiosqlite://")
            or v.startswith("postgresql://")
            or v.startswith("postgresql+asyncpg://")
            or v.startswith("postgresql+psycopg://")
        ):
            raise ValueError(
                "database_url must be SQLite (sqlite:///, sqlite+aiosqlite:///) or PostgreSQL "
                "(postgresql://, postgresql+asyncpg://, postgresql+psycopg://)"
            )
        return v

    @model_validator(mode="after")
    def validate_oidc_config(self) -> "Settings":
        """Validate OIDC configuration if enabled."""
        if self.oidc_enabled:
            required_fields = {
                "oidc_issuer": self.oidc_issuer,
                "oidc_client_id": self.oidc_client_id,
                "oidc_client_secret": self.oidc_client_secret,
            }
            missing = [k for k, v in required_fields.items() if not v]
            if missing:
                raise ValueError(f"OIDC enabled but missing required fields: {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def validate_http_transport(self) -> "Settings":
        """Validate HTTP transport configuration."""
        # HTTP transport in production should use OIDC
        if self.mcp_transport == "http" and self.environment == "prod" and not self.oidc_enabled:
            warnings.warn(
                "HTTP transport in production without OIDC authentication is not recommended",
                UserWarning,
                stacklevel=2,
            )
        return self

    @model_validator(mode="after")
    def validate_encryption_key(self) -> "Settings":
        """Validate encryption key is provided."""
        if self.encryption_key is None:
            # Generate a warning in lab, require in staging/prod
            if self.environment in ["staging", "prod"]:
                raise ValueError("encryption_key is required for staging/prod environments")
            else:
                warnings.warn(
                    "encryption_key not set, using insecure default for lab only",
                    UserWarning,
                    stacklevel=2,
                )
                # Set insecure default for lab
                self.encryption_key = "INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION"
        return self

    # ========================================
    # Helper Methods
    # ========================================

    @property
    def is_sqlite(self) -> bool:
        """Check if database is SQLite."""
        return self.database_url.startswith("sqlite")

    @property
    def is_postgresql(self) -> bool:
        """Check if database is PostgreSQL."""
        return self.database_url.startswith("postgresql")

    @property
    def database_driver(self) -> str:
        """Get database driver name."""
        # Check SQLite variants
        if self.database_url.startswith("sqlite+aiosqlite://"):
            return "aiosqlite"
        elif self.database_url.startswith("sqlite://"):
            return "sqlite"
        # Check PostgreSQL variants
        elif self.database_url.startswith("postgresql+asyncpg://"):
            return "asyncpg"
        elif self.database_url.startswith("postgresql+psycopg://"):
            return "psycopg"
        elif self.database_url.startswith("postgresql://"):
            # No explicit driver, could be psycopg2 or psycopg3
            return "postgresql"
        else:
            return "unknown"

    def to_dict(self) -> dict:
        """Convert settings to dictionary, masking secrets."""
        data = self.model_dump()
        # Mask sensitive fields
        if data.get("encryption_key"):
            data["encryption_key"] = "***REDACTED***"
        if data.get("oidc_client_secret"):
            data["oidc_client_secret"] = "***REDACTED***"
        return data


# ========================================
# Global Settings Instance
# ========================================

_settings: Settings | None = None


def get_settings() -> Settings:
    """Get global settings instance (singleton).

    Returns:
        Settings instance

    Example:
        settings = get_settings()
        print(settings.database_url)
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def set_settings(settings: Settings) -> None:
    """Set global settings instance.

    Args:
        settings: Settings instance to use globally

    Example:
        custom_settings = Settings(environment="prod")
        set_settings(custom_settings)
    """
    global _settings
    _settings = settings


def load_settings_from_file(config_file: Path | str) -> Settings:
    """Load settings from YAML or TOML configuration file.

    Args:
        config_file: Path to configuration file

    Returns:
        Settings instance loaded from file

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config file format is invalid

    Example:
        settings = load_settings_from_file("config/prod.yaml")
        set_settings(settings)
    """
    config_path = Path(config_file)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Determine format from extension
    suffix = config_path.suffix.lower()

    if suffix in [".yaml", ".yml"]:
        import yaml

        with open(config_path) as f:
            config_data = yaml.safe_load(f) or {}
    elif suffix == ".toml":
        import tomllib

        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)
    else:
        raise ValueError(f"Unsupported config file format: {suffix}. Use .yaml, .yml, or .toml")

    # Create settings from loaded data
    return Settings(**config_data)
