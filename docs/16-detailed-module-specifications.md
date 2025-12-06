# Detailed Module Specifications

## Purpose

Provide detailed class, method, and function specifications for all major modules in the RouterOS MCP service. This document serves as the implementation blueprint with precise signatures, dependencies, and patterns.

---

## Module Organization

```
routeros_mcp/
├── config.py                 # Application configuration (see Doc 17)
├── cli.py                    # CLI argument parsing (see Doc 17)
├── main.py                   # Application entrypoint
├── mcp_server.py             # MCP server initialization (top-level)
├── api/                      # API & MCP layer
│   ├── __init__.py
│   ├── http.py              # FastAPI HTTP application
│   ├── middleware.py        # HTTP middleware
│   └── dependencies.py      # FastAPI dependencies
├── mcp_tools/                # MCP tool implementations
│   ├── __init__.py
│   ├── system.py
│   ├── interface.py
│   ├── ip.py
│   ├── dns.py
│   ├── ntp.py
│   ├── logs.py
│   ├── diagnostics.py
│   └── config_mgmt.py       # Plan/apply tools
├── mcp_resources/            # MCP resource providers
│   ├── __init__.py
│   ├── device.py
│   ├── fleet.py
│   ├── plan.py
│   └── audit.py
├── mcp_prompts/              # MCP prompt templates
│   ├── __init__.py
│   ├── workflows.py
│   └── troubleshooting.py
├── security/                 # Security & authorization
│   ├── __init__.py
│   ├── auth.py              # OIDC authentication
│   ├── authz.py             # Authorization logic
│   └── crypto.py            # Encryption for secrets
├── domain/                   # Domain services
│   ├── __init__.py
│   ├── models.py            # Domain models (Pydantic)
│   ├── exceptions.py        # Domain exceptions
│   ├── devices.py           # Device management
│   ├── health.py            # Health checks
│   ├── plans.py             # Plan/apply orchestration
│   ├── jobs.py              # Job execution
│   └── routeros_operations/
│       ├── __init__.py
│       ├── base.py          # Base operation classes
│       ├── system.py
│       ├── interface.py
│       ├── ip.py
│       ├── dns.py
│       ├── ntp.py
│       ├── logs.py
│       └── diagnostics.py
├── infra/                    # Infrastructure layer
│   ├── __init__.py
│   ├── routeros/
│   │   ├── __init__.py
│   │   ├── rest_client.py   # RouterOS REST client
│   │   ├── ssh_client.py    # SSH client (whitelisted commands)
│   │   ├── errors.py        # RouterOS error mapping
│   │   └── feature_detection.py
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py        # SQLAlchemy ORM models
│   │   ├── session.py       # Database session management
│   │   └── migrations/      # Alembic migrations
│   ├── jobs/
│   │   ├── __init__.py
│   │   ├── scheduler.py     # APScheduler integration
│   │   └── runner.py        # Job execution logic
│   └── observability/
│       ├── __init__.py
│       ├── logging.py       # Structured logging setup
│       ├── metrics.py       # Prometheus metrics
│       └── tracing.py       # OpenTelemetry tracing
└── tests/                    # Test suite
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## Configuration Module

### `config.py`

**Note**: For the complete Settings class specification with all fields, defaults, validators, and CLI integration, see [docs/17-configuration-specification.md](17-configuration-specification.md).

The configuration module provides:

```python
from pydantic_settings import BaseSettings
from typing import Literal, Optional

class Settings(BaseSettings):
    """Application configuration from environment variables, config files, and CLI args.

    Complete specification in docs/17-configuration-specification.md.

    Key features:
    - Supports SQLite (default) and PostgreSQL
    - Environment variables with ROUTEROS_MCP_ prefix
    - Config file support (YAML/TOML)
    - CLI argument override
    - Full validation and reasonable defaults
    """

    # Example key settings (see Doc 17 for complete list)
    environment: Literal["lab", "staging", "prod"] = "lab"
    database_url: str = "sqlite:///./routeros_mcp.db"  # Default SQLite
    mcp_transport: Literal["stdio", "http"] = "stdio"
    log_level: str = "INFO"

    # ... (40+ more settings - see Doc 17)

# Global settings management
def get_settings() -> Settings:
    """Get global settings instance (singleton)."""
    ...

def set_settings(settings: Settings) -> None:
    """Set global settings instance."""
    ...

def load_settings_from_file(config_file: Path | str) -> Settings:
    """Load settings from YAML or TOML configuration file."""
    ...
```

### `cli.py`

**Note**: For complete CLI specification, see [docs/17-configuration-specification.md](17-configuration-specification.md#command-line-interface).

Command-line argument parsing for the MCP server:

```python
import argparse
from pathlib import Path
from typing import Optional

def create_argument_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser.

    Supports arguments for:
    - --config: Path to config file
    - --environment: lab/staging/prod
    - --database-url: Database connection
    - --mcp-transport: stdio/http
    - ... (see Doc 17 for full list)
    """
    ...

def load_config_from_cli(args: Optional[list[str]] = None) -> Settings:
    """Load configuration from CLI arguments and environment.

    Priority (later overrides earlier):
    1. Built-in defaults
    2. Config file (if --config specified)
    3. Environment variables
    4. CLI arguments
    """
    ...
```

---

## MCP Server Module

### `mcp_server.py`

```python
import sys
import logging
from fastmcp import FastMCP

from routeros_mcp.config import get_settings
from routeros_mcp.mcp_tools import register_all_tools
from routeros_mcp.mcp_resources import register_all_resources
from routeros_mcp.mcp_prompts import register_all_prompts
from routeros_mcp.infra.observability.logging import configure_logging

def create_mcp_server() -> FastMCP:
    """Create and configure MCP server instance.

    Returns:
        Configured FastMCP server with all tools, resources, prompts registered
    """
    settings = get_settings()

    # Configure logging based on transport
    configure_logging(
        level=settings.log_level,
        use_stderr=(settings.mcp_transport == "stdio")
    )

    # Create MCP server
    mcp = FastMCP(
        name="routeros-mcp",
        version="1.0.0",
        description=settings.mcp_description
    )

    # Register all MCP primitives
    register_all_tools(mcp)
    register_all_resources(mcp)
    register_all_prompts(mcp)

    logging.info(
        "MCP server created",
        extra={
            "transport": settings.mcp_transport,
            "environment": settings.environment
        }
    )

    return mcp

def main():
    """Main entrypoint for MCP server."""
    settings = get_settings()
    mcp = create_mcp_server()

    # Run with appropriate transport
    if settings.mcp_transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="sse",
            host=settings.mcp_http_host,
            port=settings.mcp_http_port
        )

if __name__ == "__main__":
    main()
```

---

## Security Modules

### `security/auth.py`

```python
from typing import Protocol
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import jwt
from fastmcp import get_context

from routeros_mcp.config import get_settings
from routeros_mcp.domain.models import User

class AuthenticationError(Exception):
    """Authentication failed."""
    pass

class AuthService:
    """OIDC authentication service."""

    def __init__(self):
        self.settings = get_settings()
        if self.settings.oidc_enabled:
            self._client = AsyncOAuth2Client(
                client_id=self.settings.oidc_client_id,
                client_secret=self.settings.oidc_client_secret
            )

    async def authenticate_bearer_token(self, token: str) -> User:
        """Authenticate and extract user from bearer token.

        Args:
            token: JWT or opaque access token

        Returns:
            User object with identity and roles

        Raises:
            AuthenticationError: If token invalid or expired
        """
        settings = self.settings

        # Verify token with OIDC provider
        try:
            claims = jwt.decode(
                token,
                key=None,  # Will fetch from OIDC discovery
                claims_options={
                    "iss": {"value": settings.oidc_issuer},
                    "aud": {"value": settings.oidc_audience}
                }
            )
        except Exception as e:
            raise AuthenticationError(f"Token validation failed: {e}")

        # Extract user info
        user = User(
            sub=claims["sub"],
            email=claims.get("email"),
            groups=claims.get("groups", []),
            role=self._map_role(claims.get("groups", []))
        )

        return user

    def _map_role(self, groups: list[str]) -> str:
        """Map OIDC groups to internal role.

        Args:
            groups: List of group claims from token

        Returns:
            Internal role: read_only, ops_rw, or admin
        """
        # Example mapping (configure via settings)
        if "mcp-admin" in groups:
            return "admin"
        elif "mcp-ops" in groups:
            return "ops_rw"
        else:
            return "read_only"

def get_current_user() -> User:
    """Get current user from MCP context (for tool handlers).

    Returns:
        Current authenticated user

    Raises:
        AuthenticationError: If no user in context
    """
    context = get_context()
    user = context.get("user")
    if not user:
        raise AuthenticationError("No user in context")
    return user
```

### `security/authz.py`

```python
from fastmcp.exceptions import McpError

from routeros_mcp.domain.models import User, Device
from routeros_mcp.domain.exceptions import AuthorizationError

class AuthorizationService:
    """Authorization and access control service."""

    def check_tool_access(
        self,
        user: User,
        device: Device,
        tool_name: str,
        tool_tier: str
    ) -> None:
        """Check if user can invoke tool on device.

        Args:
            user: Current user
            device: Target device
            tool_name: Tool being invoked
            tool_tier: fundamental/advanced/professional

        Raises:
            McpError: If access denied
        """
        # Check role vs. tier
        if tool_tier == "fundamental":
            # All roles allowed
            pass
        elif tool_tier == "advanced":
            if user.role not in ["ops_rw", "admin"]:
                raise McpError(
                    code=-32002,
                    message="Forbidden: advanced tier requires ops_rw or admin role"
                )
        elif tool_tier == "professional":
            if user.role != "admin":
                raise McpError(
                    code=-32002,
                    message="Forbidden: professional tier requires admin role"
                )

        # Check device scope
        if not self.device_in_scope(user, device):
            raise McpError(
                code=-32002,
                message="Forbidden: device out of scope",
                data={"device_id": device.id}
            )

        # Check device capability flags
        if tool_tier == "advanced" and not device.allow_advanced_writes:
            raise McpError(
                code=-32002,
                message="Forbidden: device does not allow advanced writes",
                data={"device_id": device.id}
            )

        if tool_tier == "professional" and not device.allow_professional_workflows:
            raise McpError(
                code=-32002,
                message="Forbidden: device does not allow professional workflows",
                data={"device_id": device.id}
            )

    def device_in_scope(self, user: User, device: Device) -> bool:
        """Check if device is in user's scope.

        Args:
            user: Current user
            device: Device to check

        Returns:
            True if device accessible to user
        """
        # Phase 1: All users can access all devices (single-user deployment)
        # Phase 4: Implement device scoping logic based on user.device_scope configuration
        return True
```

---

## Domain Models

### `domain/models.py`

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

class User(BaseModel):
    """User identity from OIDC token."""
    sub: str
    email: str | None = None
    groups: list[str] = Field(default_factory=list)
    role: Literal["read_only", "ops_rw", "admin"]
    device_scope: list[str] | None = None  # List of device IDs or patterns

class Device(BaseModel):
    """RouterOS device entity."""
    id: str
    name: str
    management_address: str  # host:port
    environment: Literal["lab", "staging", "prod"]
    status: Literal["healthy", "degraded", "unreachable"] = "healthy"
    tags: dict[str, str] = Field(default_factory=dict)

    # Capability flags
    allow_advanced_writes: bool = False
    allow_professional_workflows: bool = False

    # RouterOS metadata
    routeros_version: str | None = None
    system_identity: str | None = None
    hardware_model: str | None = None
    serial_number: str | None = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    last_seen_at: datetime | None = None

class HealthSummary(BaseModel):
    """Device health check result."""
    device_id: str
    status: Literal["healthy", "warning", "critical"]
    timestamp: datetime

    cpu_usage_percent: float | None = None
    memory_used_bytes: int | None = None
    memory_total_bytes: int | None = None
    temperature_celsius: float | None = None
    uptime_seconds: int | None = None

    error: str | None = None

class Plan(BaseModel):
    """Multi-device configuration change plan."""
    id: str
    created_at: datetime
    created_by: str  # user sub
    tool_name: str
    status: Literal["draft", "approved", "applied", "cancelled"]
    device_ids: list[str]
    summary: str
    changes: dict  # Tool-specific change details

class Job(BaseModel):
    """Executable job (often tied to a plan)."""
    id: str
    plan_id: str | None = None
    type: str  # APPLY_PLAN, HEALTH_CHECK, etc.
    status: Literal["pending", "running", "success", "failed", "cancelled"]
    device_ids: list[str] = Field(default_factory=list)
    attempts: int = 0
    max_attempts: int = 3
    next_run_at: datetime | None = None
    result_summary: str | None = None
```

---

## Domain Services (Example)

### `domain/devices.py`

```python
from typing import Protocol
from datetime import datetime

from routeros_mcp.domain.models import Device, User
from routeros_mcp.domain.exceptions import DeviceNotFoundError
from routeros_mcp.infra.db.models import DeviceModel
from routeros_mcp.infra.db.session import AsyncSession

class DeviceRepository(Protocol):
    """Device persistence interface."""

    async def create(self, device: Device) -> Device: ...
    async def get_by_id(self, device_id: str) -> Device | None: ...
    async def list_all(self, environment: str | None = None) -> list[Device]: ...
    async def update(self, device: Device) -> Device: ...
    async def delete(self, device_id: str) -> None: ...

class DeviceService:
    """Device management service."""

    def __init__(self, repository: DeviceRepository):
        self.repository = repository

    async def register_device(
        self,
        name: str,
        management_address: str,
        environment: str,
        tags: dict[str, str] | None = None,
        allow_advanced_writes: bool = False
    ) -> Device:
        """Register a new RouterOS device.

        Args:
            name: Human-friendly device name
            management_address: host:port for REST API
            environment: lab/staging/prod
            tags: Optional metadata tags
            allow_advanced_writes: Enable advanced write tools

        Returns:
            Created device

        Raises:
            ValueError: If validation fails
        """
        # Create device entity
        device = Device(
            id=self._generate_device_id(),
            name=name,
            management_address=management_address,
            environment=environment,
            tags=tags or {},
            allow_advanced_writes=allow_advanced_writes,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Persist
        return await self.repository.create(device)

    async def get_device(self, device_id: str) -> Device:
        """Get device by ID.

        Args:
            device_id: Device identifier

        Returns:
            Device entity

        Raises:
            DeviceNotFoundError: If device not found
        """
        device = await self.repository.get_by_id(device_id)
        if not device:
            raise DeviceNotFoundError(f"Device {device_id} not found")
        return device

    async def list_devices(
        self,
        user: User | None = None,
        environment: str | None = None,
        status: str | None = None,
        tag: str | None = None
    ) -> list[Device]:
        """List devices with filtering.

        Args:
            user: Current user (for scope filtering)
            environment: Filter by environment
            status: Filter by health status
            tag: Filter by tag key

        Returns:
            List of devices
        """
        devices = await self.repository.list_all(environment=environment)

        # Apply filters
        if status:
            devices = [d for d in devices if d.status == status]
        if tag:
            devices = [d for d in devices if tag in d.tags]

        # Phase 1: No user device scope filtering (single-user deployment)
        # Phase 4: Apply user device scope filtering based on user.device_scope

        return devices

    def _generate_device_id(self) -> str:
        """Generate unique device ID."""
        import uuid
        return f"dev-{uuid.uuid4().hex[:8]}"
```

---

Due to length constraints, this document provides the essential patterns and specifications. Additional modules follow the same structure with:

- Clear type hints for all parameters and returns
- Pydantic models for data validation
- Protocol classes for dependency injection
- Async/await throughout
- Comprehensive docstrings
- Error handling with domain exceptions

See `docs/11-implementation-architecture-and-module-layout.md` for complete module list and `docs/14-mcp-protocol-integration-and-transport-design.md` for MCP-specific implementations.
