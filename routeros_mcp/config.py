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
from typing import Any, Literal

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
    # SSE Subscription Configuration
    # ========================================

    sse_max_subscriptions_per_device: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum SSE subscriptions per device (prevent DoS)",
    )

    sse_client_timeout_seconds: int = Field(
        default=1800,  # 30 minutes
        ge=0,
        le=7200,
        description="Timeout for inactive SSE clients (0 = no timeout)",
    )

    sse_update_batch_interval_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Debounce interval for batching SSE updates",
    )

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
    # Redis Configuration (Session Store)
    # ========================================

    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description=(
            "Redis connection URL for session storage. "
            "Production/staging MUST use TLS (rediss://) and authentication. "
            "Example production URL: rediss://username:password@redis.example.com:6380/0"
        ),
    )

    redis_pool_size: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Redis connection pool size. Recommended: 10-20 for production",
    )

    redis_timeout_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=60.0,
        description="Redis operation timeout. Recommended: 5-10 seconds for production",
    )

    redis_password: str | None = Field(
        default=None,
        description="Redis authentication password (can also be in redis_url)",
    )

    redis_ssl_cert_file: str | None = Field(
        default=None,
        description="Path to Redis SSL client certificate file for mutual TLS",
    )

    redis_ssl_key_file: str | None = Field(
        default=None,
        description="Path to Redis SSL client key file for mutual TLS",
    )

    redis_ssl_ca_certs: str | None = Field(
        default=None,
        description="Path to Redis SSL CA certificates file for server verification",
    )

    # ========================================
    # OIDC Authentication (HTTP Transport)
    # ========================================

    oidc_enabled: bool = Field(default=False, description="Enable OIDC authentication")

    oidc_provider_url: str | None = Field(
        default=None, description="OIDC provider URL (e.g., https://auth0.example.com)"
    )

    oidc_issuer: str | None = Field(
        default=None,
        description="OIDC issuer URL for Authorization Code flow (e.g., https://auth0.example.com)",
    )

    oidc_client_id: str | None = Field(default=None, description="OIDC client ID")

    oidc_client_secret: str | None = Field(
        default=None, description="OIDC client secret (for service account token validation)"
    )

    oidc_redirect_uri: str | None = Field(
        default=None,
        description="OAuth redirect URI for Authorization Code flow (e.g., http://localhost:8080/api/auth/callback)",
    )

    oidc_scopes: str = Field(
        default="openid profile email",
        description="Space-separated OAuth scopes to request",
    )

    oidc_audience: str | None = Field(default=None, description="Expected token audience")

    oidc_skip_verification: bool = Field(
        default=False, description="Skip JWT signature verification (dev mode only, DANGEROUS)"
    )

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
    # Resource Cache Configuration
    # ========================================

    mcp_resource_cache_enabled: bool = Field(
        default=True, description="Enable in-memory resource caching with TTL"
    )

    mcp_resource_cache_ttl_seconds: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="Time-to-live for cached resource entries in seconds",
    )

    mcp_resource_cache_max_entries: int = Field(
        default=1000,
        ge=10,
        le=10000,
        description="Maximum number of cached entries (LRU eviction when exceeded)",
    )

    mcp_resource_cache_auto_invalidate: bool = Field(
        default=True,
        description="Automatically invalidate cache on device state changes",
    )

    # ========================================
    # Redis Resource Cache Configuration
    # ========================================
    # Note: The resource cache shares the Redis connection configuration
    # (redis_url, redis_pool_size, redis_timeout_seconds) with the session store.
    # Both use the same Redis instance but different key prefixes to avoid conflicts:
    # - Session store keys: "session:*"
    # - Resource cache keys: "resource:*"

    redis_cache_enabled: bool = Field(
        default=True,
        description="Enable Redis-backed resource caching for device data",
    )

    redis_cache_ttl_interfaces: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="TTL for interface data cache in seconds (default: 5 minutes)",
    )

    redis_cache_ttl_ips: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="TTL for IP address data cache in seconds (default: 5 minutes)",
    )

    redis_cache_ttl_routes: int = Field(
        default=300,
        ge=10,
        le=3600,
        description="TTL for routing data cache in seconds (default: 5 minutes)",
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
    # Snapshot Configuration (Phase 2.1)
    # ========================================

    snapshot_capture_enabled: bool = Field(
        default=True,
        description="Enable periodic configuration snapshot capture",
    )

    snapshot_capture_interval_seconds: int = Field(
        default=3600,
        ge=300,
        le=86400,
        description="Interval between snapshot captures (5 min to 24 hours)",
    )

    snapshot_max_size_bytes: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        ge=1024 * 1024,  # 1MB minimum
        le=100 * 1024 * 1024,  # 100MB maximum
        description="Maximum snapshot size (uncompressed)",
    )

    snapshot_retention_count: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Number of snapshots to retain per device (latest N)",
    )

    snapshot_compression_level: int = Field(
        default=6,
        ge=0,
        le=9,
        description="GZIP compression level (0=none, 9=max, 6=balanced)",
    )

    snapshot_use_ssh_fallback: bool = Field(
        default=True,
        description="Fallback to SSH export if REST API export fails",
    )

    # ========================================
    # Notification Configuration (Phase 5 #9)
    # ========================================

    notification_enabled: bool = Field(
        default=False,
        description="Enable email notifications for approval requests and job execution",
    )

    notification_backend: Literal["smtp", "mock"] = Field(
        default="mock",
        description="Notification backend: smtp (production) or mock (development/testing)",
    )

    notification_from_address: str = Field(
        default="routeros-mcp@example.com",
        description="Email address used as sender for notifications",
    )

    notification_smtp_host: str = Field(
        default="localhost",
        description="SMTP server hostname",
    )

    notification_smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
        description="SMTP server port (587 for STARTTLS, 465 for SSL)",
    )

    notification_smtp_use_tls: bool = Field(
        default=True,
        description="Use STARTTLS for SMTP connection",
    )

    notification_smtp_username: str | None = Field(
        default=None,
        description="SMTP authentication username",
    )

    notification_smtp_password: str | None = Field(
        default=None,
        description="SMTP authentication password",
    )

    notification_smtp_timeout: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="SMTP connection timeout in seconds",
    )

    notification_base_url: str | None = Field(
        default=None,
        description="Base URL for web UI links in notification emails (e.g., https://routeros-mcp.example.com)",
    )

    # ========================================
    # Rate Limiting Configuration (Phase 5 #13)
    # ========================================

    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting middleware for tool execution",
    )

    rate_limit_read_only_per_minute: int = Field(
        default=10,
        ge=1,
        le=1000,
        description=(
            "Rate limit for read_only role: requests per minute. "
            "Must be >= 1; only admin role supports unlimited (0) for emergency access."
        ),
    )

    rate_limit_ops_rw_per_minute: int = Field(
        default=5,
        ge=1,
        le=1000,
        description=(
            "Rate limit for ops_rw role: requests per minute. "
            "Must be >= 1; only admin role supports unlimited (0) to prevent unbounded write operations."
        ),
    )

    rate_limit_admin_per_minute: int = Field(
        default=0,
        ge=0,
        le=1000,
        description="Rate limit for admin role: requests per minute (0 = unlimited)",
    )

    rate_limit_approver_per_minute: int = Field(
        default=5,
        ge=1,
        le=1000,
        description=(
            "Rate limit for approver role: requests per minute. "
            "Must be >= 1; only admin role supports unlimited (0) for break-glass emergency access."
        ),
    )

    rate_limit_window_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Time window for rate limiting in seconds",
    )

    rate_limit_use_redis: bool = Field(
        default=True,
        description="Use Redis for distributed rate limiting (required for multi-instance)",
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
            # Support both oidc_issuer (new) and oidc_provider_url (legacy)
            issuer = self.oidc_issuer or self.oidc_provider_url

            required_fields = {
                "oidc_issuer or oidc_provider_url": issuer,
                "oidc_client_id": self.oidc_client_id,
            }
            missing = [k for k, v in required_fields.items() if not v]
            if missing:
                raise ValueError(f"OIDC enabled but missing required fields: {', '.join(missing)}")

            # Validate HTTPS in production/staging
            if (
                issuer
                and self.environment in ["staging", "prod"]
                and not issuer.startswith("https://")
            ):
                raise ValueError(
                    f"oidc_issuer/oidc_provider_url must use HTTPS in {self.environment} environment"
                )

            # Validate redirect_uri format if provided
            if self.oidc_redirect_uri:
                if not self.oidc_redirect_uri.startswith(("http://", "https://")):
                    raise ValueError("oidc_redirect_uri must be a valid HTTP/HTTPS URL")
                # Require HTTPS in production/staging
                if self.environment in [
                    "staging",
                    "prod",
                ] and not self.oidc_redirect_uri.startswith("https://"):
                    raise ValueError(
                        f"oidc_redirect_uri must use HTTPS in {self.environment} environment"
                    )

            # Warn if skip_verification enabled
            if self.oidc_skip_verification and self.environment in ["staging", "prod"]:
                warnings.warn(
                    "oidc_skip_verification=true in staging/prod is DANGEROUS and not recommended",
                    UserWarning,
                    stacklevel=2,
                )

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

    @model_validator(mode="after")
    def validate_redis_security(self) -> "Settings":
        """Validate Redis configuration security for production environments."""
        if self.environment in ["staging", "prod"]:
            # Require TLS for production/staging
            if not self.redis_url.startswith("rediss://"):
                warnings.warn(
                    f"Redis URL in {self.environment} environment should use TLS (rediss://). "
                    "Current configuration may expose session data in transit.",
                    UserWarning,
                    stacklevel=2,
                )

            # Warn if using localhost in production
            if "localhost" in self.redis_url or "127.0.0.1" in self.redis_url:
                warnings.warn(
                    f"Redis URL uses localhost in {self.environment} environment. "
                    "Multi-instance deployments require a shared Redis instance.",
                    UserWarning,
                    stacklevel=2,
                )

        return self

    @model_validator(mode="after")
    def validate_notification_config(self) -> "Settings":
        """Validate notification configuration if enabled."""
        if (
            self.notification_enabled
            and self.notification_backend == "smtp"
            and self.environment in ["staging", "prod"]
            and (not self.notification_smtp_username or not self.notification_smtp_password)
        ):
            warnings.warn(
                f"SMTP authentication credentials not set in {self.environment} environment",
                UserWarning,
                stacklevel=2,
            )
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

    def to_dict(self) -> dict[str, Any]:
        """Convert settings to dictionary, masking secrets."""
        # Pydantic's model_dump() returns a plain dict; annotate for clarity
        data: dict[str, Any] = self.model_dump()
        # Mask sensitive fields
        if data.get("encryption_key"):
            data["encryption_key"] = "***REDACTED***"
        if data.get("oidc_client_secret"):
            data["oidc_client_secret"] = "***REDACTED***"
        if data.get("notification_smtp_password"):
            data["notification_smtp_password"] = "***REDACTED***"
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
    config_data: dict[str, Any] = {}
    suffix = config_path.suffix.lower()

    if suffix in [".yaml", ".yml"]:
        import yaml

        with open(config_path) as f:
            loaded: Any = yaml.safe_load(f)
            config_data = loaded or {}
    elif suffix == ".toml":
        import tomllib

        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)
    else:
        raise ValueError(f"Unsupported config file format: {suffix}. Use .yaml, .yml, or .toml")

    # Create settings from loaded data
    return Settings(**config_data)
