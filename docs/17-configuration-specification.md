# Configuration Specification

## Purpose

Define the complete configuration system for the RouterOS MCP service, including default values, environment variables, command-line arguments, and configuration file formats. This ensures deployable defaults with flexible override mechanisms.

---

## Configuration Priority

Configuration values are resolved in the following order (later overrides earlier):

1. **Built-in defaults** (coded in Settings class)
2. **Configuration file** (YAML/TOML)
3. **Environment variables** (prefixed with `ROUTEROS_MCP_`)
4. **Command-line arguments** (highest priority)

---

## Configuration Schema

### Application Settings

| Setting | Type | Default | CLI Arg | Env Var | Description |
|---------|------|---------|---------|---------|-------------|
| `environment` | str | `"lab"` | `--environment` | `ROUTEROS_MCP_ENVIRONMENT` | Environment: lab/staging/prod |
| `debug` | bool | `False` | `--debug` | `ROUTEROS_MCP_DEBUG` | Enable debug mode |
| `log_level` | str | `"INFO"` | `--log-level` | `ROUTEROS_MCP_LOG_LEVEL` | Logging level |
| `log_format` | str | `"json"` | `--log-format` | `ROUTEROS_MCP_LOG_FORMAT` | Log format: json/text |

### MCP Configuration

| Setting | Type | Default | CLI Arg | Env Var | Description |
|---------|------|---------|---------|---------|-------------|
| `mcp_transport` | str | `"stdio"` | `--mcp-transport` | `ROUTEROS_MCP_TRANSPORT` | Transport: stdio/http |
| `mcp_http_host` | str | `"127.0.0.1"` | `--mcp-host` | `ROUTEROS_MCP_HTTP_HOST` | HTTP bind address |
| `mcp_http_port` | int | `8080` | `--mcp-port` | `ROUTEROS_MCP_HTTP_PORT` | HTTP port |
| `mcp_http_base_path` | str | `"/mcp"` | N/A | `ROUTEROS_MCP_HTTP_BASE_PATH` | HTTP base path |

### Database Configuration

| Setting | Type | Default | CLI Arg | Env Var | Description |
|---------|------|---------|---------|---------|-------------|
| `database_url` | str | `"sqlite:///./routeros_mcp.db"` | `--database-url` | `ROUTEROS_MCP_DATABASE_URL` | Database connection URL |
| `database_pool_size` | int | `5` | N/A | `ROUTEROS_MCP_DATABASE_POOL_SIZE` | Connection pool size |
| `database_max_overflow` | int | `10` | N/A | `ROUTEROS_MCP_DATABASE_MAX_OVERFLOW` | Max overflow connections |
| `database_echo` | bool | `False` | N/A | `ROUTEROS_MCP_DATABASE_ECHO` | Echo SQL statements |

**Supported Database URLs:**
- SQLite: `sqlite:///path/to/db.db` (default for development)
- PostgreSQL (asyncpg): `postgresql+asyncpg://user:pass@host/db`
- PostgreSQL (psycopg): `postgresql+psycopg://user:pass@host/db`

### OIDC Authentication (HTTP Transport)

| Setting | Type | Default | CLI Arg | Env Var | Description |
|---------|------|---------|---------|---------|-------------|
| `oidc_enabled` | bool | `False` | `--oidc-enabled` | `ROUTEROS_MCP_OIDC_ENABLED` | Enable OIDC auth |
| `oidc_issuer` | str | `None` | N/A | `ROUTEROS_MCP_OIDC_ISSUER` | OIDC issuer URL |
| `oidc_client_id` | str | `None` | N/A | `ROUTEROS_MCP_OIDC_CLIENT_ID` | OIDC client ID |
| `oidc_client_secret` | str | `None` | N/A | `ROUTEROS_MCP_OIDC_CLIENT_SECRET` | OIDC client secret |
| `oidc_audience` | str | `None` | N/A | `ROUTEROS_MCP_OIDC_AUDIENCE` | Expected token audience |

### RouterOS Integration

| Setting | Type | Default | CLI Arg | Env Var | Description |
|---------|------|---------|---------|---------|-------------|
| `routeros_rest_timeout_seconds` | float | `5.0` | N/A | `ROUTEROS_MCP_ROUTEROS_REST_TIMEOUT` | REST call timeout |
| `routeros_max_concurrent_per_device` | int | `3` | N/A | `ROUTEROS_MCP_ROUTEROS_MAX_CONCURRENT` | Max concurrent calls per device |
| `routeros_retry_attempts` | int | `3` | N/A | `ROUTEROS_MCP_ROUTEROS_RETRY_ATTEMPTS` | Retry attempts for failed calls |
| `routeros_retry_backoff_seconds` | float | `1.0` | N/A | `ROUTEROS_MCP_ROUTEROS_RETRY_BACKOFF` | Exponential backoff base |

### Health Checks & Metrics

| Setting | Type | Default | CLI Arg | Env Var | Description |
|---------|------|---------|---------|---------|-------------|
| `health_check_interval_seconds` | int | `60` | N/A | `ROUTEROS_MCP_HEALTH_CHECK_INTERVAL` | Health check interval |
| `health_check_jitter_seconds` | int | `10` | N/A | `ROUTEROS_MCP_HEALTH_CHECK_JITTER` | Random jitter for health checks |
| `metrics_collection_interval_seconds` | int | `300` | N/A | `ROUTEROS_MCP_METRICS_INTERVAL` | Metrics collection interval |

### Security & Encryption

| Setting | Type | Default | CLI Arg | Env Var | Description |
|---------|------|---------|---------|---------|-------------|
| `encryption_key` | str | **Required** | N/A | `ROUTEROS_MCP_ENCRYPTION_KEY` | Master encryption key (32+ bytes base64) |
| `encryption_algorithm` | str | `"fernet"` | N/A | `ROUTEROS_MCP_ENCRYPTION_ALGORITHM` | Encryption algorithm |

---

## Configuration Implementation

### Settings Class

```python
# routeros_mcp/config.py

import os
import sys
from pathlib import Path
from typing import Literal, Optional

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
        extra="ignore"  # Ignore unknown fields
    )

    # ========================================
    # Application Settings
    # ========================================

    environment: Literal["lab", "staging", "prod"] = Field(
        default="lab",
        description="Deployment environment"
    )

    debug: bool = Field(
        default=False,
        description="Enable debug mode with verbose logging"
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="Logging level"
    )

    log_format: Literal["json", "text"] = Field(
        default="json",
        description="Log output format"
    )

    # ========================================
    # MCP Configuration
    # ========================================

    mcp_transport: Literal["stdio", "http"] = Field(
        default="stdio",
        description="MCP transport mode"
    )

    mcp_description: str = Field(
        default="RouterOS MCP Service",
        description="Service description for MCP"
    )

    mcp_http_host: str = Field(
        default="127.0.0.1",
        description="HTTP server bind address (0.0.0.0 for all interfaces)"
    )

    mcp_http_port: int = Field(
        default=8080,
        ge=1,
        le=65535,
        description="HTTP server port"
    )

    mcp_http_base_path: str = Field(
        default="/mcp",
        description="Base path for MCP HTTP endpoints"
    )

    # ========================================
    # Database Configuration
    # ========================================

    database_url: str = Field(
        default="sqlite:///./routeros_mcp.db",
        description="Database connection URL (SQLite or PostgreSQL)"
    )

    database_pool_size: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Database connection pool size"
    )

    database_max_overflow: int = Field(
        default=10,
        ge=0,
        le=100,
        description="Max overflow connections beyond pool size"
    )

    database_echo: bool = Field(
        default=False,
        description="Echo SQL statements to logs (debug only)"
    )

    # ========================================
    # OIDC Authentication (HTTP Transport)
    # ========================================

    oidc_enabled: bool = Field(
        default=False,
        description="Enable OIDC authentication"
    )

    oidc_issuer: Optional[str] = Field(
        default=None,
        description="OIDC issuer URL"
    )

    oidc_client_id: Optional[str] = Field(
        default=None,
        description="OIDC client ID"
    )

    oidc_client_secret: Optional[str] = Field(
        default=None,
        description="OIDC client secret"
    )

    oidc_audience: Optional[str] = Field(
        default=None,
        description="Expected token audience"
    )

    # ========================================
    # RouterOS Integration
    # ========================================

    routeros_rest_timeout_seconds: float = Field(
        default=5.0,
        ge=1.0,
        le=60.0,
        description="REST API call timeout"
    )

    routeros_max_concurrent_per_device: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max concurrent REST calls per device"
    )

    routeros_retry_attempts: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Number of retry attempts for failed calls"
    )

    routeros_retry_backoff_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Exponential backoff base for retries"
    )

    # ========================================
    # Health Checks & Metrics
    # ========================================

    health_check_interval_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description="Health check interval"
    )

    health_check_jitter_seconds: int = Field(
        default=10,
        ge=0,
        le=300,
        description="Random jitter added to health check interval"
    )

    metrics_collection_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Metrics collection interval"
    )

    # ========================================
    # Security & Encryption
    # ========================================

    encryption_key: Optional[str] = Field(
        default=None,
        description="Master encryption key for secrets (base64, 32+ bytes)"
    )

    encryption_algorithm: Literal["fernet"] = Field(
        default="fernet",
        description="Encryption algorithm for secrets"
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
            or v.startswith("sqlite://")
            or v.startswith("postgresql://")
            or v.startswith("postgresql+asyncpg://")
            or v.startswith("postgresql+psycopg://")
        ):
            raise ValueError(
                "database_url must be SQLite (sqlite:///) or PostgreSQL "
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
                raise ValueError(
                    f"OIDC enabled but missing required fields: {', '.join(missing)}"
                )
        return self

    @model_validator(mode="after")
    def validate_http_transport(self) -> "Settings":
        """Validate HTTP transport configuration."""
        if self.mcp_transport == "http":
            # HTTP transport in production should use OIDC
            if self.environment == "prod" and not self.oidc_enabled:
                import warnings
                warnings.warn(
                    "HTTP transport in production without OIDC authentication is not recommended",
                    UserWarning
                )
        return self

    @model_validator(mode="after")
    def validate_encryption_key(self) -> "Settings":
        """Validate encryption key is provided."""
        if self.encryption_key is None:
            # Generate a warning in lab, require in staging/prod
            if self.environment in ["staging", "prod"]:
                raise ValueError(
                    "encryption_key is required for staging/prod environments"
                )
            else:
                import warnings
                warnings.warn(
                    "encryption_key not set, using insecure default for lab only",
                    UserWarning
                )
                # Set insecure default for lab
                self.encryption_key = "INSECURE_LAB_KEY_DO_NOT_USE_IN_PRODUCTION"
        return self

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Ensure log level is uppercase."""
        return v.upper()

    # ========================================
    # Helper Methods
    # ========================================

    @property
    def is_sqlite(self) -> bool:
        """Check if database is SQLite."""
        return self.database_url.startswith("sqlite:")

    @property
    def is_postgresql(self) -> bool:
        """Check if database is PostgreSQL."""
        return self.database_url.startswith("postgresql")

    @property
    def database_driver(self) -> str:
        """Get database driver name."""
        if self.is_sqlite:
            return "sqlite"
        elif "+asyncpg://" in self.database_url:
            return "asyncpg"
        elif "+psycopg://" in self.database_url:
            return "psycopg"
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

_settings: Optional[Settings] = None


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
            config_data = yaml.safe_load(f)
    elif suffix == ".toml":
        import tomli
        with open(config_path, "rb") as f:
            config_data = tomli.load(f)
    else:
        raise ValueError(
            f"Unsupported config file format: {suffix}. "
            "Use .yaml, .yml, or .toml"
        )

    # Create settings from loaded data
    return Settings(**config_data)
```

---

## Command-Line Interface

### CLI Arguments Parser

```python
# routeros_mcp/cli.py

import argparse
import sys
from pathlib import Path
from typing import Optional

from routeros_mcp.config import Settings, load_settings_from_file, set_settings


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser.

    Returns:
        Configured ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="routeros-mcp",
        description="RouterOS MCP Service - Manage MikroTik RouterOS devices via MCP",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Config file
    parser.add_argument(
        "--config",
        "-c",
        type=Path,
        help="Path to configuration file (YAML or TOML)"
    )

    # Application settings
    parser.add_argument(
        "--environment",
        choices=["lab", "staging", "prod"],
        help="Deployment environment"
    )

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode"
    )

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level"
    )

    parser.add_argument(
        "--log-format",
        choices=["json", "text"],
        help="Log output format"
    )

    # MCP configuration
    parser.add_argument(
        "--mcp-transport",
        choices=["stdio", "http"],
        help="MCP transport mode"
    )

    parser.add_argument(
        "--mcp-host",
        help="HTTP server bind address"
    )

    parser.add_argument(
        "--mcp-port",
        type=int,
        help="HTTP server port"
    )

    # Database
    parser.add_argument(
        "--database-url",
        help="Database connection URL (SQLite or PostgreSQL)"
    )

    # OIDC
    parser.add_argument(
        "--oidc-enabled",
        action="store_true",
        help="Enable OIDC authentication"
    )

    # Version
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="%(prog)s 1.0.0"
    )

    return parser


def load_config_from_cli(args: Optional[list[str]] = None) -> Settings:
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
```

---

## Configuration File Examples

### Lab Configuration (YAML)

```yaml
# config/lab.yaml

# Application
environment: lab
debug: true
log_level: DEBUG
log_format: text

# MCP
mcp_transport: stdio

# Database (SQLite for easy development)
database_url: sqlite:///./data/routeros_mcp_lab.db
database_echo: true

# RouterOS (permissive for lab)
routeros_rest_timeout_seconds: 10.0
routeros_retry_attempts: 2

# Health checks (more frequent for testing)
health_check_interval_seconds: 30
health_check_jitter_seconds: 5

# Security (insecure for lab only - warning will be shown)
# encryption_key will use insecure default for lab
```

### Production Configuration (YAML)

```yaml
# config/prod.yaml

# Application
environment: prod
debug: false
log_level: INFO
log_format: json

# MCP (HTTP with OAuth)
mcp_transport: http
mcp_http_host: 0.0.0.0
mcp_http_port: 8080

# Database (PostgreSQL with asyncpg)
database_url: postgresql+asyncpg://mcp_user:${DB_PASSWORD}@postgres:5432/routeros_mcp_prod
database_pool_size: 10
database_max_overflow: 20

# OIDC Authentication
oidc_enabled: true
oidc_issuer: https://idp.example.com
oidc_client_id: routeros-mcp-prod
oidc_client_secret: ${OIDC_CLIENT_SECRET}
oidc_audience: routeros-mcp

# RouterOS
routeros_rest_timeout_seconds: 5.0
routeros_max_concurrent_per_device: 3
routeros_retry_attempts: 3

# Health checks
health_check_interval_seconds: 60
health_check_jitter_seconds: 10

# Metrics
metrics_collection_interval_seconds: 300

# Security (REQUIRED)
encryption_key: ${ENCRYPTION_KEY}
```

### Container/Docker Configuration (TOML)

```toml
# config/docker.toml

# Application
environment = "staging"
log_level = "INFO"
log_format = "json"

# MCP
mcp_transport = "http"
mcp_http_host = "0.0.0.0"
mcp_http_port = 8080

# Database (PostgreSQL via Docker network)
database_url = "postgresql+asyncpg://postgres:postgres@db:5432/routeros_mcp"
database_pool_size = 5

# OIDC
oidc_enabled = false  # Enable in production

# RouterOS defaults are fine

# Health checks
health_check_interval_seconds = 60
```

---

## Usage Examples

### Loading Configuration

```python
# Example 1: Load from environment variables only
from routeros_mcp.config import get_settings

settings = get_settings()
print(f"Environment: {settings.environment}")
print(f"Database: {settings.database_url}")

# Example 2: Load from config file
from routeros_mcp.config import load_settings_from_file, set_settings

settings = load_settings_from_file("config/prod.yaml")
set_settings(settings)

# Example 3: Load from CLI (recommended for main entrypoint)
from routeros_mcp.cli import load_config_from_cli

settings = load_config_from_cli()
set_settings(settings)

# Example 4: Programmatic configuration
from routeros_mcp.config import Settings

settings = Settings(
    environment="prod",
    database_url="postgresql+asyncpg://user:pass@localhost/db",
    oidc_enabled=True
)
```

### Environment Variables

```bash
# Set via environment
export ROUTEROS_MCP_ENVIRONMENT=prod
export ROUTEROS_MCP_DATABASE_URL=postgresql+asyncpg://user:pass@localhost/db
export ROUTEROS_MCP_ENCRYPTION_KEY=your-base64-encoded-key
export ROUTEROS_MCP_OIDC_ENABLED=true
export ROUTEROS_MCP_OIDC_CLIENT_SECRET=your-secret

# Run server
python -m routeros_mcp.mcp_server
```

### Command-Line Arguments

```bash
# Override specific settings
python -m routeros_mcp.mcp_server \
    --config config/prod.yaml \
    --environment prod \
    --log-level DEBUG \
    --mcp-transport http \
    --mcp-port 9090

# Simple stdio mode
python -m routeros_mcp.mcp_server --debug

# Full production mode
python -m routeros_mcp.mcp_server \
    --config config/prod.yaml \
    --mcp-transport http \
    --oidc-enabled \
    --database-url postgresql+asyncpg://user:pass@db/routeros_mcp
```

---

## Security Considerations

### Encryption Key Management

The `encryption_key` must be:

1. **Generated securely**:
   ```python
   from cryptography.fernet import Fernet
   key = Fernet.generate_key()
   print(key.decode())  # Save this securely
   ```

2. **Stored securely**:
   - Use environment variables in production
   - Never commit to version control
   - Rotate periodically

3. **Format**: Base64-encoded, 32+ bytes for Fernet

### Secrets in Configuration Files

- Use environment variable interpolation: `${VAR_NAME}`
- Never commit files with actual secrets
- Use `.env` files locally (gitignored)
- Use secret managers in production (AWS Secrets Manager, HashiCorp Vault, etc.)

---

## Validation and Defaults Summary

| Setting | Required | Default | Validation |
|---------|----------|---------|------------|
| `environment` | No | `"lab"` | Enum: lab/staging/prod |
| `database_url` | No | SQLite | Format: sqlite:/// or postgresql:// |
| `encryption_key` | Yes (staging/prod) | Insecure lab default | Base64, 32+ bytes |
| `mcp_http_port` | No | `8080` | Range: 1-65535 |
| `oidc_enabled` | No | `False` | If true, requires oidc_* fields |

All defaults are production-safe except `encryption_key` in lab mode.

---

This configuration system provides:

✅ **Sensible defaults** for quick development start
✅ **Environment variables** for container deployments
✅ **CLI arguments** for operational flexibility
✅ **Config files** for complex deployments
✅ **Validation** to catch misconfigurations early
✅ **Security warnings** for insecure configurations
✅ **SQLite and PostgreSQL** support out of the box
