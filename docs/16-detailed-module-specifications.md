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
        # Phase 5: Implement device scoping logic based on user.device_scope configuration
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
        # Phase 5: Apply user device scope filtering based on user.device_scope

        return devices

    def _generate_device_id(self) -> str:
        """Generate unique device ID."""
        import uuid
        return f"dev-{uuid.uuid4().hex[:8]}"
```

---

## MCP Tool Modules

### `mcp_tools/system.py`

```python
from fastmcp import FastMCP
from pydantic import BaseModel, Field

from routeros_mcp.domain.devices import DeviceService
from routeros_mcp.domain.routeros_operations.system import SystemOperations
from routeros_mcp.security.auth import get_current_user
from routeros_mcp.security.authz import AuthorizationService
from routeros_mcp.mcp.token_estimation import estimate_tokens

def register_system_tools(mcp: FastMCP):
    """Register all system-related MCP tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        description="Get RouterOS system overview including CPU, memory, uptime, and health metrics"
    )
    async def system_get_overview(
        device_id: str = Field(description="UUID of target RouterOS device")
    ) -> dict:
        """Fetch comprehensive system overview for a RouterOS device.

        Returns:
            Dict with:
            - content: list[dict] with type="text" and formatted overview
            - _meta: metadata including estimated tokens, RouterOS version, uptime
        """
        # Get services
        user = get_current_user()
        device_service = get_device_service()
        system_ops = get_system_operations()
        authz_service = get_authz_service()

        # Get device
        device = await device_service.get_device(device_id)

        # Authorization check
        authz_service.check_tool_access(
            user=user,
            device=device,
            tool_name="system_get_overview",
            tool_tier="fundamental"
        )

        # Execute operation
        overview = await system_ops.get_overview(device)

        # Format response
        response_text = _format_system_overview(overview)
        tokens = estimate_tokens(response_text)

        return {
            "content": [
                {
                    "type": "text",
                    "text": response_text
                }
            ],
            "_meta": {
                "estimated_tokens": tokens,
                "routeros_version": overview.get("routeros_version"),
                "device_uptime_seconds": overview.get("uptime_seconds"),
                "health_status": overview.get("health_status", "unknown")
            }
        }

    @mcp.tool(
        description="Update system identity (hostname) on a RouterOS device"
    )
    async def system_update_identity(
        device_id: str = Field(description="UUID of target device"),
        identity: str = Field(description="New system identity", max_length=64),
        dry_run: bool = Field(default=False, description="Preview changes without applying")
    ) -> dict:
        """Update system identity with audit logging.

        Returns:
            Dict with before/after values and changed flag
        """
        user = get_current_user()
        device_service = get_device_service()
        system_ops = get_system_operations()
        authz_service = get_authz_service()

        device = await device_service.get_device(device_id)

        # Authorization (advanced tier)
        authz_service.check_tool_access(
            user=user,
            device=device,
            tool_name="system_update_identity",
            tool_tier="advanced"
        )

        # Execute operation
        result = await system_ops.update_identity(
            device=device,
            identity=identity,
            dry_run=dry_run
        )

        # Format response
        response_text = (
            f"System identity update {'(dry run)' if dry_run else 'applied'}\n"
            f"Device: {device.name} ({device_id})\n"
            f"Old identity: {result['old_identity']}\n"
            f"New identity: {result['new_identity']}\n"
            f"Changed: {result['changed']}\n"
        )

        return {
            "content": [
                {
                    "type": "text",
                    "text": response_text
                }
            ],
            "_meta": {
                "estimated_tokens": estimate_tokens(response_text),
                "changed": result["changed"],
                "dry_run": dry_run
            }
        }

def _format_system_overview(overview: dict) -> str:
    """Format system overview for display."""
    return f"""
# System Overview

## Device Information
- RouterOS Version: {overview.get('routeros_version', 'Unknown')}
- System Identity: {overview.get('identity', 'Unknown')}
- Board Name: {overview.get('board_name', 'Unknown')}
- Architecture: {overview.get('architecture', 'Unknown')}

## System Resources
- CPU: {overview.get('cpu_usage', 'N/A')}%
- Memory: {overview.get('memory_used', 'N/A')} / {overview.get('memory_total', 'N/A')} ({overview.get('memory_usage_percent', 'N/A')}%)
- Uptime: {_format_uptime(overview.get('uptime_seconds', 0))}

## Health Metrics
- Temperature: {overview.get('temperature_celsius', 'N/A')}°C
- Voltage: {overview.get('voltage', 'N/A')}V
- Health Status: {overview.get('health_status', 'Unknown')}
"""

def _format_uptime(seconds: int) -> str:
    """Format uptime seconds to human-readable string."""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    return f"{days}d {hours}h {minutes}m"
```

---

## MCP Resource Modules

### `mcp_resources/device.py`

```python
from fastmcp import FastMCP
import json

from routeros_mcp.domain.devices import DeviceService
from routeros_mcp.domain.health import HealthService
from routeros_mcp.security.auth import get_current_user
from routeros_mcp.mcp.resources import check_resource_access

def register_device_resources(mcp: FastMCP):
    """Register device-scoped resources.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.resource(
        uri="device://{device_id}/overview",
        name="Device System Overview",
        description="Current system metrics and information for a RouterOS device"
    )
    async def device_overview(device_id: str) -> str:
        """Get current system overview for device.

        Returns:
            JSON-formatted system overview
        """
        user = get_current_user()
        await check_resource_access(user, device_id, "overview")

        system_service = get_system_service()
        overview = await system_service.get_overview(device_id)

        return json.dumps(overview, indent=2)

    @mcp.resource(
        uri="device://{device_id}/health",
        name="Device Health Metrics",
        description="Real-time health status and metrics",
        subscribe=True
    )
    async def device_health(device_id: str) -> str:
        """Get current health metrics (subscribable).

        Returns:
            JSON-formatted health metrics
        """
        user = get_current_user()
        await check_resource_access(user, device_id, "health")

        health_service = get_health_service()
        health = await health_service.get_current_health(device_id)

        return json.dumps(health, indent=2)

    @mcp.resource(
        uri="device://{device_id}/config",
        name="RouterOS Configuration",
        description="Current device configuration export",
        mime_type="text/x-routeros-script"
    )
    async def device_config(device_id: str) -> str:
        """Get current RouterOS configuration.

        Returns:
            RouterOS configuration script
        """
        user = get_current_user()
        await check_resource_access(user, device_id, "config")

        snapshot_service = get_snapshot_service()
        config = await snapshot_service.get_current_config(device_id)

        return config
```

---

## MCP Prompt Modules

### `mcp_prompts/workflows.py`

```python
from fastmcp import FastMCP
from typing import Literal

from routeros_mcp.domain.devices import DeviceService

def register_workflow_prompts(mcp: FastMCP):
    """Register workflow-oriented prompts.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.prompt(
        name="dns-ntp-rollout",
        description="Step-by-step guide for rolling out DNS/NTP changes across devices"
    )
    async def dns_ntp_rollout_workflow(
        environment: Literal["lab", "staging", "prod"] = "lab",
        dry_run: bool = True
    ) -> str:
        """DNS/NTP configuration rollout workflow guide.

        Args:
            environment: Target environment for rollout
            dry_run: Whether to recommend dry-run first

        Returns:
            Formatted workflow guide with step-by-step instructions
        """
        device_service = get_device_service()
        devices = await device_service.list_devices(environment=environment)
        device_count = len(devices)

        safety_note = ""
        if environment == "prod":
            safety_note = """
⚠️  PRODUCTION ENVIRONMENT ALERT ⚠️
- Changes require admin role
- Plan/apply workflow is MANDATORY
- Human approval token required
- Devices must have allow_advanced_writes=true
- Post-change monitoring required
"""

        return f"""
# DNS/NTP Rollout Workflow for {environment.upper()}

## Overview
Rolling out DNS/NTP changes to **{device_count} devices** in {environment} environment.

{safety_note}

## Prerequisites
- [ ] User role: {'admin' if environment == 'prod' else 'ops_rw or admin'}
- [ ] Environment: {environment}
- [ ] Backup current DNS/NTP config (recommended)

## Workflow Steps

### 1. List Target Devices
**Tool:** `device.list_devices`

**Parameters:**
```json
{{
  "environment": "{environment}"
}}
```

### 2. Create Rollout Plan
**Tool:** `config.plan_dns_ntp_rollout`

**Parameters:**
```json
{{
  "device_ids": ["dev-001", "dev-002"],
  "dns_servers": ["8.8.8.8", "8.8.4.4"],
  "ntp_servers": ["time.cloudflare.com"],
  "description": "DNS/NTP update for {environment}"
}}
```

### 3. Review Plan Details
**Resource:** `plan://{{plan_id}}/details`

**Review checklist:**
- [ ] All intended devices included
- [ ] Current vs new values are correct
- [ ] Risk levels acceptable
- [ ] No precondition failures

### 4. Apply Changes
**Tool:** `config.apply_dns_ntp_rollout`

**Parameters:**
```json
{{
  "plan_id": "<plan_id from step 2>",
  "batch_size": 5,
  "pause_between_batches_seconds": 30
}}
```

## Safety Notes
- Always test in **lab** first
- Use **staging** for final validation
- Production requires **admin approval**
- Monitor health checks post-change
"""
```

---

## MCP Registry and Middleware Modules

### `mcp/registry.py`

```python
from typing import Callable, Any, Protocol
from dataclasses import dataclass
from inspect import signature
import json

class ToolHandler(Protocol):
    """Protocol for MCP tool handler functions."""
    async def __call__(self, **kwargs: Any) -> dict[str, Any]: ...

@dataclass
class ToolMetadata:
    """Metadata for a registered MCP tool."""
    name: str
    description: str
    input_schema: dict[str, Any]
    tier: str  # fundamental, advanced, professional
    handler: ToolHandler
    environments: list[str] | None = None
    requires_approval: bool = False

class ToolRegistry:
    """Registry for MCP tools."""

    def __init__(self):
        self._tools: dict[str, ToolMetadata] = {}

    def register(self, metadata: ToolMetadata) -> None:
        """Register a tool.

        Args:
            metadata: Tool metadata including handler and schema
        """
        self._tools[metadata.name] = metadata

    def get(self, name: str) -> ToolMetadata | None:
        """Get tool metadata by name.

        Args:
            name: Tool name

        Returns:
            Tool metadata or None if not found
        """
        return self._tools.get(name)

    def list_all(self) -> list[ToolMetadata]:
        """List all registered tools.

        Returns:
            List of all tool metadata
        """
        return list(self._tools.values())

    def list_by_tier(self, tier: str) -> list[ToolMetadata]:
        """List tools by tier.

        Args:
            tier: Tool tier (fundamental, advanced, professional)

        Returns:
            List of tools in the specified tier
        """
        return [t for t in self._tools.values() if t.tier == tier]

# Global registry
_global_registry: ToolRegistry | None = None

def get_global_tool_registry() -> ToolRegistry:
    """Get global tool registry (singleton).

    Returns:
        Global ToolRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry

def mcp_tool(
    *,
    name: str,
    description: str,
    tier: str = "fundamental",
    environments: list[str] | None = None,
    requires_approval: bool = False
):
    """Decorator for MCP tool registration with automatic schema generation.

    Args:
        name: Tool name (e.g., "system.get_overview")
        description: Human-readable description
        tier: Tool tier (fundamental, advanced, professional)
        environments: Allowed environments (None = all)
        requires_approval: Whether tool requires approval

    Returns:
        Decorated function with automatic registration
    """
    def decorator(func: ToolHandler) -> ToolHandler:
        # Generate schema from function signature
        sig = signature(func)
        input_schema = _generate_schema_from_signature(sig)

        # Register tool
        metadata = ToolMetadata(
            name=name,
            description=description,
            input_schema=input_schema,
            tier=tier,
            handler=func,
            environments=environments,
            requires_approval=requires_approval
        )
        get_global_tool_registry().register(metadata)

        return func

    return decorator

def _generate_schema_from_signature(sig) -> dict[str, Any]:
    """Generate JSON Schema from function signature.

    Args:
        sig: Function signature from inspect.signature

    Returns:
        JSON Schema dict
    """
    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        # Extract type annotation
        param_type = param.annotation
        if param_type == str:
            properties[param_name] = {"type": "string"}
        elif param_type == int:
            properties[param_name] = {"type": "integer"}
        elif param_type == bool:
            properties[param_name] = {"type": "boolean"}
        else:
            properties[param_name] = {"type": "string"}  # Default

        # Check if required
        if param.default == param.empty:
            required.append(param_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required
    }
```

### `mcp/middleware.py`

```python
from typing import Callable, Any
from datetime import datetime
from contextvars import ContextVar
from uuid import uuid4

from routeros_mcp.mcp.token_estimation import estimate_tokens
from routeros_mcp.mcp.exceptions import TokenBudgetExceededError

# Context variables
correlation_id_var: ContextVar[str] = ContextVar("correlation_id")
session_id_var: ContextVar[str] = ContextVar("session_id")

TOKEN_WARNING_THRESHOLD = 5_000
TOKEN_ERROR_THRESHOLD = 50_000

async def correlation_id_middleware(request: dict, next_handler: Callable) -> Any:
    """Generate and propagate correlation ID.

    Args:
        request: JSON-RPC request
        next_handler: Next handler in chain

    Returns:
        Handler result
    """
    correlation_id = str(uuid4())
    correlation_id_var.set(correlation_id)

    logger.info(
        "MCP request received",
        extra={
            "correlation_id": correlation_id,
            "method": request.get("method"),
            "request_id": request.get("id")
        }
    )

    result = await next_handler(request)
    return result

async def token_budget_middleware(tool_name: str, result: dict) -> dict:
    """Check token budget and warn/error on large responses.

    Args:
        tool_name: Name of tool being executed
        result: Tool result dict

    Returns:
        Result with optional warnings

    Raises:
        TokenBudgetExceededError: If response exceeds error threshold
    """
    estimated_tokens = result.get("_meta", {}).get("estimated_tokens", 0)

    if estimated_tokens > TOKEN_ERROR_THRESHOLD:
        raise TokenBudgetExceededError(
            code=-32000,
            message="Response exceeds token budget",
            data={
                "tool_name": tool_name,
                "estimated_tokens": estimated_tokens,
                "threshold": TOKEN_ERROR_THRESHOLD,
                "suggested_action": "Use pagination or filtering to reduce response size"
            }
        )

    if estimated_tokens > TOKEN_WARNING_THRESHOLD:
        result["_meta"]["token_warning"] = (
            f"Response size ({estimated_tokens} tokens) exceeds recommended limit "
            f"({TOKEN_WARNING_THRESHOLD} tokens). Consider using pagination."
        )

    return result

async def authorization_middleware(
    user: User,
    device: Device,
    tool_name: str,
    tool_tier: str
) -> None:
    """Check authorization before tool execution.

    Args:
        user: Current user
        device: Target device
        tool_name: Tool being executed
        tool_tier: Tool tier

    Raises:
        McpError: If authorization fails
    """
    authz_service = get_authz_service()
    authz_service.check_tool_access(
        user=user,
        device=device,
        tool_name=tool_name,
        tool_tier=tool_tier
    )

async def audit_logging_middleware(
    user: User,
    tool_name: str,
    device_id: str,
    result: dict
) -> None:
    """Log tool invocation for audit trail.

    Args:
        user: Current user
        tool_name: Tool executed
        device_id: Target device
        result: Tool result
    """
    audit_service = get_audit_service()
    await audit_service.log_tool_invocation(
        user_sub=user.sub,
        tool_name=tool_name,
        device_id=device_id,
        success=not result.get("isError", False),
        correlation_id=correlation_id_var.get()
    )
```

---

Due to length constraints, this document provides the essential patterns and specifications. Additional modules follow the same structure with:

- Clear type hints for all parameters and returns
- Pydantic models for data validation
- Protocol classes for dependency injection
- Async/await throughout
- Comprehensive docstrings
- Error handling with domain exceptions

See [docs/11-implementation-architecture-and-module-layout.md](11-implementation-architecture-and-module-layout.md) for complete module list and [docs/14-mcp-protocol-integration-and-transport-design.md](14-mcp-protocol-integration-and-transport-design.md) for MCP-specific implementations.
