# Implementation Architecture & Module Layout

## Purpose

Describe the concrete implementation architecture for the RouterOS MCP service: runtime stack choices (Python frameworks and libraries), package/module layout, and the key classes/functions and their signatures. This document connects the high-level design to actual code structure.

---

## Runtime stack overview

The implementation is based on:

- **Language & runtime**
  - Python 3.11+ (type hints, `async`/`await` used throughout).

- **Web / API stack**
  - FastAPI for the HTTP API layer (admin UI and optional REST API).  
  - Uvicorn as the ASGI server.

- **MCP integration**
  - A dedicated `MCPServer` component that:
    - Exposes tools over the MCP protocol (e.g., via stdin/stdout or HTTP-based transport).  
    - Uses the same domain services as the HTTP API.  
  - The MCP server is implemented in-process alongside the HTTP API.

- **Configuration & validation**
  - Pydantic (v2) for settings and request/response schemas.

- **RouterOS integration**
  - `httpx` (async) for RouterOS REST clients.  
  - `asyncssh` for SSH/CLI fallback commands.

- **Persistence**
  - PostgreSQL as the primary database.  
  - SQLAlchemy 2.x ORM for models and queries.  
  - Alembic for schema migrations.

- **Background jobs & scheduling**
  - A simple job runner in-process for initial implementation, using:
    - SQL-backed job table (see `Job` in `docs/05-...`).  
    - An async scheduler (e.g., `apscheduler`) to trigger periodic tasks (health checks, metrics).
  - Future versions may replace this with an external queue (Redis/RQ) if needed.

- **Observability**
  - Python `logging` (structured JSON logs) or `structlog`.  
  - `prometheus_client` for metrics.  
  - OpenTelemetry SDK for tracing (with FastAPI/HTTPX instrumentation).

- **Testing & tooling**
  - `pytest`, `pytest-asyncio`, `pytest-cov`.  
  - `mypy` for static type checking.  
  - `ruff` and `black` for linting/formatting.  
  - `tox` to orchestrate tests, linting, type-checking, and coverage runs.  
  - `uv` as the preferred tool for environment and dependency management (see `docs/12-...` for details).

---

## Package and module layout

The main Python package is `routeros_mcp` with the following structure:

- `routeros_mcp/config.py`
  - Pydantic `Settings` class for application configuration (DB URL, OIDC config, etc.).
  - See `docs/17-configuration-specification.md` for complete Settings specification.

- `routeros_mcp/cli.py`
  - Command-line argument parsing for MCP server.
  - Supports config files (YAML/TOML), environment variables, and CLI overrides.
  - See `docs/17-configuration-specification.md` for CLI specification.

- `routeros_mcp/mcp_server.py` (top-level)
  - `MCPServer` implementation and tool registration/discovery using FastMCP SDK.
  - See `docs/14-mcp-protocol-integration-and-transport-design.md` for MCP integration.

- `routeros_mcp/api/`
  - `api/http.py`
    - FastAPI application, HTTP routes (admin API, health, metrics).
  - `api/middleware.py`
    - HTTP middleware for authentication, authorization, logging.
  - `api/dependencies.py`
    - FastAPI dependency injection (session, settings, auth).
  - `api/schemas.py`
    - Pydantic models for external request/response schemas mapped from `docs/04-...`.

- `routeros_mcp/mcp_tools/`
  - `mcp_tools/system.py`, `mcp_tools/interface.py`, etc.
    - MCP tool implementations (fundamental, advanced, professional tiers).
    - See `docs/04-mcp-tools-interface-and-json-schema-specification.md`.

- `routeros_mcp/mcp_resources/`
  - `mcp_resources/device.py`, `mcp_resources/fleet.py`, etc.
    - MCP resource providers for device://, fleet://, plan://, audit:// URIs.
    - See `docs/15-mcp-resources-and-prompts-design.md`.

- `routeros_mcp/mcp_prompts/`
  - `mcp_prompts/workflows.py`, `mcp_prompts/troubleshooting.py`
    - MCP prompt templates for guided workflows.
    - See `docs/15-mcp-resources-and-prompts-design.md`.

- `routeros_mcp/security/`
  - `security/auth.py`  
    - OIDC token validation and user extraction.
  - `security/authz.py`  
    - Authorization decisions based on roles, device scopes, tool tiers, environment, and capability flags.

- `routeros_mcp/domain/`
  - `domain/devices.py`  
    - `DeviceService` for device registry and metadata.  
  - `domain/routeros_operations/`  
    - `system.py`, `interfaces.py`, `ip.py`, `dns.py`, `ntp.py`, etc. (topic-specific operations).  
  - `domain/plans.py`  
    - `PlanService` for plan/apply workflows.  
  - `domain/jobs.py`  
    - `JobService` for job scheduling and execution.  
  - `domain/models.py`  
    - Pydantic domain models (Device, Plan, Job summaries, etc.).

- `routeros_mcp/infra/routeros/`
  - `rest_client.py`  
    - `RouterOSRestClient` with generic and topic-specific methods.  
  - `ssh_client.py`  
    - `RouterOSSshClient` for whitelisted CLI commands.

- `routeros_mcp/infra/db/`
  - `models.py`  
    - SQLAlchemy ORM models matching entities from `docs/05-...`.  
  - `session.py`  
    - Session/engine management.

- `routeros_mcp/infra/jobs/`
  - `scheduler.py`  
    - Background scheduler integration.  
  - `runner.py`  
    - Job execution loop (health checks, metrics collection, apply-plan jobs).

- `routeros_mcp/infra/observability/`
  - `logging.py`  
    - Logging configuration and helper to attach standard fields.  
  - `metrics.py`  
    - Prometheus metric registration helpers.  
  - `tracing.py`  
    - OpenTelemetry setup.

---

## Core classes and function signatures

This section lists key classes and functions with indicative signatures (simplified for clarity).

### Configuration

```python
from pydantic import BaseSettings, AnyUrl

class Settings(BaseSettings):
    environment: str  # "lab" | "staging" | "prod"
    database_url: AnyUrl
    oidc_issuer: str
    oidc_client_id: str
    oidc_client_secret: str
    routeros_rest_timeout_seconds: float = 5.0
    routeros_max_concurrent_requests_per_device: int = 3

    class Config:
        env_prefix = "ROUTEROS_MCP_"
```

### Security and authorization

```python
from typing import Sequence
from routeros_mcp.domain.models import User, Device

class AuthService:
    async def authenticate_bearer_token(self, token: str) -> User: ...

class AuthorizationService:
    def check_tool_access(
        self,
        user: User,
        device: Device,
        tool_name: str,
        tool_tier: str,  # "fundamental" | "advanced" | "professional"
    ) -> None:
        """Raise an authorization error if access is not allowed."""
```

### RouterOS clients

```python
from typing import Any, Mapping

class RouterOSRestClient:
    async def get(
        self,
        device: Device,
        path: str,
        params: Mapping[str, Any] | None = None,
    ) -> Any: ...

    async def post(
        self,
        device: Device,
        path: str,
        json: Mapping[str, Any] | None = None,
    ) -> Any: ...

    async def patch(
        self,
        device: Device,
        path: str,
        json: Mapping[str, Any] | None = None,
    ) -> Any: ...

    async def delete(self, device: Device, path: str) -> None: ...

class RouterOSSshClient:
    async def run_command(
        self,
        device: Device,
        command_id: str,
        *,
        params: Mapping[str, Any] | None = None,
        timeout_seconds: float = 10.0,
    ) -> str:
        """Executes a whitelisted command template identified by command_id."""
```

### Domain services

```python
from routeros_mcp.domain.models import DeviceCreate, DeviceUpdate, Plan, Job, HealthSummary

class DeviceService:
    async def register_device(self, payload: DeviceCreate) -> Device: ...
    async def update_device(self, device_id: str, payload: DeviceUpdate) -> Device: ...
    async def list_devices(self) -> list[Device]: ...
    async def get_device(self, device_id: str) -> Device: ...

class HealthService:
    async def run_health_check(self, device_id: str) -> HealthSummary: ...

class PlanService:
    async def create_dns_ntp_rollout_plan(
        self,
        device_ids: list[str],
        dns_servers: list[str],
        ntp_servers: list[str],
        description: str | None = None,
    ) -> Plan: ...

    async def apply_plan(self, plan_id: str, approval_token: str) -> Job: ...

class JobService:
    async def schedule_health_checks(self) -> None: ...
    async def run_due_jobs(self) -> None: ...
```

### MCP server and tool registration

```python
from typing import Callable, Awaitable
from routeros_mcp.domain.models import ToolRequest, ToolResponse

ToolHandler = Callable[[ToolRequest], Awaitable[ToolResponse]]

class MCPServer:
    def __init__(self) -> None: ...

    def register_tool(
        self,
        name: str,
        handler: ToolHandler,
        *,
        tier: str,
        required_role: str,
        environments: list[str],
        requires_approval: bool = False,
    ) -> None:
        ...

    async def handle_request(self, request: ToolRequest) -> ToolResponse: ...
```

`ToolRequest` and `ToolResponse` are Pydantic models that wrap the generic envelope described in `docs/04-...` (tool name, params, success/error, result).

### FastAPI HTTP entrypoint

```python
from fastapi import FastAPI

def create_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    # mount routes: health, metrics, admin APIs, MCP bridge if needed
    return app
```

---

## Topic-specific operation modules

Each topic has a domain service responsible for orchestrating RouterOS calls and enforcing guardrails. For example:

```python
class SystemService:
    async def get_overview(self, device_id: str) -> dict:
        """Implements system.get_overview as per docs/04 schema."""

class InterfaceService:
    async def list_interfaces(self, device_id: str) -> list[dict]: ...
    async def update_comment(
        self,
        device_id: str,
        interface_name: str,
        comment: str,
    ) -> dict: ...
```

Each MCP tool is implemented by a thin wrapper that:

1. Authenticates and authorizes the user.
2. Loads the `Device` and environment/capability flags.
3. Calls the appropriate domain service method.
4. Maps the result into the JSON schema defined in `docs/04-...`.

---

## Related Documentation

For complete implementation specifications of all modules with detailed class/method signatures and implementation patterns, see [docs/16-detailed-module-specifications.md](16-detailed-module-specifications.md).
