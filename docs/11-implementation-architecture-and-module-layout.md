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
    - Implements JSON-RPC 2.0 protocol for MCP communication.
    - Exposes tools over the MCP protocol via multiple transports (stdio, HTTP/SSE).
    - Uses the same domain services as the HTTP API.
    - Provides automatic tool discovery and registration.
    - Manages client sessions and capability negotiation.
  - **MCP SDK**: FastMCP (official MCP SDK for Python) or custom implementation
    - Handles MCP protocol compliance (initialize, tools/list, tools/call, etc.)
    - Provides decorators for tool registration with automatic JSON Schema generation
    - Manages transport abstraction (stdio/HTTP/SSE)
  - The MCP server is implemented in-process alongside the HTTP API for flexibility.
  - **Transport Modes**:
    - **Stdio transport** (default): JSON-RPC over stdin/stdout for Claude Desktop and similar clients
    - **HTTP/SSE transport**: HTTP with Server-Sent Events for multi-client deployments
    - Transport selection via `MCP_TRANSPORT_MODE` environment variable

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
  - **MCP-specific settings**: `MCP_SERVER_NAME`, `MCP_SERVER_VERSION`, `MCP_TRANSPORT_MODE`, `MCP_ENABLE_TOOLS`, `MCP_ENABLE_RESOURCES`, `MCP_ENABLE_PROMPTS`, `MCP_TOKEN_BUDGET_WARNING_THRESHOLD`
  - See `docs/17-configuration-specification.md` for complete Settings specification.

- `routeros_mcp/cli.py`
  - Command-line argument parsing for MCP server.
  - Supports config files (YAML/TOML), environment variables, and CLI overrides.
  - Startup validation (database connectivity, tool schemas, transport binding).
  - See `docs/17-configuration-specification.md` for CLI specification.

- `routeros_mcp/main.py` (top-level entry point)
  - Application startup: initializes database, MCP server, FastAPI app
  - Transport selection and configuration
  - Graceful shutdown handling (in-flight tool calls, database draining)

- `routeros_mcp/mcp/` (MCP protocol implementation)
  - `mcp/server.py`
    - `MCPServer` core implementation using FastMCP SDK
    - Tool discovery and registration
    - Client session management
    - Capability negotiation
    - See `docs/14-mcp-protocol-integration-and-transport-design.md`

  - `mcp/protocol/`
    - `protocol/jsonrpc.py`
      - JSON-RPC 2.0 message handling (request/response/error formatting)
      - Error code mapping (Python exceptions → JSON-RPC error codes)
    - `protocol/messages.py`
      - MCP protocol message types (InitializeRequest, ToolsListRequest, ToolsCallRequest)
      - Pydantic models for MCP protocol messages

  - `mcp/transport/`
    - `transport/base.py`
      - `Transport` abstract base class
    - `transport/stdio.py`
      - `StdioTransport` implementation (stdin/stdout JSON-RPC)
    - `transport/http.py`
      - `HttpTransport` implementation (HTTP + Server-Sent Events)
    - `transport/factory.py`
      - Transport factory based on configuration

  - `mcp/session/`
    - `session/manager.py`
      - Client session lifecycle (initialize → tools/list → tools/call → close)
      - Capability tracking per session
      - Client info tracking (name, version)
    - `session/state.py`
      - Session state models (initialized, ready, closed)

  - `mcp/registry/`
    - `registry/tools.py`
      - Tool registry with automatic discovery
      - Tool metadata management (name, tier, schema, handler)
      - Tool filtering by tier/subscription
    - `registry/resources.py` (Phase 2)
      - Resource provider registry
      - URI pattern routing
    - `registry/prompts.py` (Phase 2)
      - Prompt template registry

  - `mcp/middleware/`
    - `middleware/auth.py`
      - MCP-level authentication (session-based auth)
    - `middleware/logging.py`
      - Request/response logging with correlation IDs
    - `middleware/metrics.py`
      - MCP protocol metrics collection
    - `middleware/validation.py`
      - Tool argument validation against JSON schemas
    - `middleware/token_budget.py`
      - Token estimation and budget tracking

  - `mcp/errors.py`
    - MCP-specific exception classes
    - Error code constants (JSON-RPC -32700 to -32603)
    - Error formatting utilities

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
from typing import Callable, Awaitable, Any
from pydantic import BaseModel
from routeros_mcp.domain.models import Device
from routeros_mcp.mcp.protocol.messages import (
    InitializeRequest,
    InitializeResponse,
    ToolsListRequest,
    ToolsListResponse,
    ToolsCallRequest,
    ToolsCallResponse
)

# Tool handler signature
ToolHandler = Callable[[dict[str, Any], Device], Awaitable[dict[str, Any]]]

class MCPServer:
    """MCP protocol server implementation."""

    def __init__(
        self,
        *,
        name: str,
        version: str,
        transport_mode: str,  # "stdio" | "http" | "both"
        settings: Settings,
        session_manager: SessionManager,
        tool_registry: ToolRegistry
    ) -> None:
        """Initialize MCP server with transport and registries."""
        ...

    async def start(self) -> None:
        """Start MCP server and begin accepting requests."""
        ...

    async def stop(self) -> None:
        """Gracefully stop server (complete in-flight requests)."""
        ...

    # MCP Protocol Methods
    async def handle_initialize(
        self,
        request: InitializeRequest
    ) -> InitializeResponse:
        """Handle initialize request (capability negotiation)."""
        ...

    async def handle_tools_list(
        self,
        request: ToolsListRequest
    ) -> ToolsListResponse:
        """Return list of available tools for client."""
        ...

    async def handle_tools_call(
        self,
        request: ToolsCallRequest
    ) -> ToolsCallResponse:
        """Execute tool and return result."""
        ...

    # Tool Registration
    def register_tool(
        self,
        *,
        name: str,
        description: str,
        handler: ToolHandler,
        input_schema: dict[str, Any],
        tier: str,  # "free" | "basic" | "professional"
        environments: list[str] | None = None,
        requires_approval: bool = False
    ) -> None:
        """Register tool with metadata."""
        ...

class ToolRegistry:
    """Registry for MCP tools with automatic discovery."""

    def __init__(self) -> None:
        self.tools: dict[str, ToolMetadata] = {}

    def register(self, tool_metadata: ToolMetadata) -> None:
        """Register a tool with metadata."""
        ...

    def discover_tools(self, package: str = "routeros_mcp.mcp_tools") -> None:
        """Automatically discover and register tools from package."""
        ...

    def get_tools_for_tier(self, tier: str) -> list[ToolMetadata]:
        """Get all tools available for given tier."""
        ...

    def get_tool(self, name: str) -> ToolMetadata:
        """Get tool metadata by name."""
        ...

class ToolMetadata(BaseModel):
    """Metadata for an MCP tool."""
    name: str
    description: str
    input_schema: dict[str, Any]
    tier: str
    handler: ToolHandler
    environments: list[str] | None = None
    requires_approval: bool = False
    estimated_tokens: int = 0

# Tool decorator for automatic registration
def mcp_tool(
    *,
    name: str,
    description: str,
    tier: str = "free",
    environments: list[str] | None = None,
    requires_approval: bool = False
):
    """Decorator for MCP tool registration with automatic schema generation."""
    def decorator(func: ToolHandler) -> ToolHandler:
        # Extract input schema from function signature and Pydantic models
        input_schema = generate_schema_from_signature(func)

        # Register tool
        tool_metadata = ToolMetadata(
            name=name,
            description=description,
            input_schema=input_schema,
            tier=tier,
            handler=func,
            environments=environments,
            requires_approval=requires_approval
        )
        get_global_tool_registry().register(tool_metadata)

        return func
    return decorator

# Example tool implementation using decorator
@mcp_tool(
    name="system.get_overview",
    description="Get RouterOS system overview and health metrics",
    tier="free"
)
async def get_system_overview(
    device_id: str,
    *,
    device: Device
) -> dict[str, Any]:
    """Get system overview for device."""
    # Implementation uses domain services
    system_service = get_system_service()
    overview = await system_service.get_overview(device_id)

    return {
        "content": [
            {
                "type": "text",
                "text": format_system_overview(overview)
            }
        ],
        "_meta": {
            "routeros_version": overview["routeros_version"],
            "cpu": overview["cpu"],
            "memory": overview["memory"],
            "estimated_tokens": estimate_tokens(overview)
        }
    }
```

**MCP Protocol Message Types:**

```python
from pydantic import BaseModel

class InitializeRequest(BaseModel):
    """MCP initialize request."""
    protocol_version: str
    capabilities: dict[str, Any]
    client_info: dict[str, str]

class InitializeResponse(BaseModel):
    """MCP initialize response."""
    protocol_version: str
    capabilities: dict[str, Any]
    server_info: dict[str, str]

class ToolsListRequest(BaseModel):
    """MCP tools/list request."""
    pass  # No params

class ToolsListResponse(BaseModel):
    """MCP tools/list response."""
    tools: list[dict[str, Any]]  # List of tool schemas

class ToolsCallRequest(BaseModel):
    """MCP tools/call request."""
    name: str
    arguments: dict[str, Any]

class ToolsCallResponse(BaseModel):
    """MCP tools/call response."""
    content: list[dict[str, Any]]  # MCP content blocks
    is_error: bool = False
    _meta: dict[str, Any] | None = None
```

**MCP Transport Implementations:**

```python
from abc import ABC, abstractmethod

class Transport(ABC):
    """Abstract base class for MCP transports."""

    @abstractmethod
    async def start(self) -> None:
        """Start transport."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop transport."""
        ...

    @abstractmethod
    async def send_message(self, message: dict[str, Any]) -> None:
        """Send JSON-RPC message to client."""
        ...

    @abstractmethod
    async def receive_message(self) -> dict[str, Any]:
        """Receive JSON-RPC message from client."""
        ...

class StdioTransport(Transport):
    """Stdio transport for MCP (JSON-RPC over stdin/stdout)."""

    def __init__(self) -> None:
        self.stdin = asyncio.get_event_loop().stdin
        self.stdout = asyncio.get_event_loop().stdout

    async def send_message(self, message: dict[str, Any]) -> None:
        """Send JSON-RPC message to stdout."""
        json_str = json.dumps(message)
        self.stdout.write(f"{json_str}\n")
        await self.stdout.drain()

    async def receive_message(self) -> dict[str, Any]:
        """Receive JSON-RPC message from stdin."""
        line = await self.stdin.readline()
        return json.loads(line)

class HttpTransport(Transport):
    """HTTP/SSE transport for MCP."""

    def __init__(self, app: FastAPI, base_path: str = "/mcp") -> None:
        self.app = app
        self.base_path = base_path
        self.sessions: dict[str, ClientSession] = {}

    async def send_message(self, session_id: str, message: dict[str, Any]) -> None:
        """Send message via Server-Sent Events."""
        session = self.sessions[session_id]
        await session.send_event(data=json.dumps(message))

    async def receive_message(self, session_id: str) -> dict[str, Any]:
        """Receive message via HTTP POST."""
        # HTTP transport receives via POST to /mcp/message
        # This is handled by FastAPI route
        ...
```

**MCP Session Management:**

```python
from enum import Enum

class SessionState(str, Enum):
    """MCP client session states."""
    UNINITIALIZED = "uninitialized"
    INITIALIZED = "initialized"
    READY = "ready"
    CLOSED = "closed"

class ClientSession(BaseModel):
    """MCP client session."""
    session_id: str
    client_info: dict[str, str]
    capabilities: dict[str, Any]
    state: SessionState
    created_at: datetime
    last_activity_at: datetime

class SessionManager:
    """Manages MCP client sessions."""

    def __init__(self) -> None:
        self.sessions: dict[str, ClientSession] = {}

    async def create_session(
        self,
        client_info: dict[str, str],
        capabilities: dict[str, Any]
    ) -> ClientSession:
        """Create new client session."""
        session_id = str(uuid.uuid4())
        session = ClientSession(
            session_id=session_id,
            client_info=client_info,
            capabilities=capabilities,
            state=SessionState.INITIALIZED,
            created_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow()
        )
        self.sessions[session_id] = session
        return session

    async def get_session(self, session_id: str) -> ClientSession:
        """Get session by ID."""
        return self.sessions[session_id]

    async def close_session(self, session_id: str) -> None:
        """Close and remove session."""
        if session_id in self.sessions:
            self.sessions[session_id].state = SessionState.CLOSED
            del self.sessions[session_id]
```

**Token Estimation Utilities:**

```python
class TokenEstimator:
    """Estimate token count for tool responses."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count using simple heuristic."""
        # Simple approximation: ~4 chars per token
        return len(text) // 4

    @staticmethod
    def estimate_tokens_for_response(response: dict[str, Any]) -> int:
        """Estimate tokens for MCP tool response."""
        content = response.get("content", [])
        total_chars = 0

        for block in content:
            if block.get("type") == "text":
                total_chars += len(block.get("text", ""))
            elif block.get("type") == "resource":
                # Resource blocks typically smaller
                total_chars += 100

        return total_chars // 4

    @staticmethod
    def check_token_budget(
        response: dict[str, Any],
        warning_threshold: int = 5000,
        error_threshold: int = 50000
    ) -> tuple[int, str]:
        """Check token budget and return (tokens, status)."""
        tokens = TokenEstimator.estimate_tokens_for_response(response)

        if tokens > error_threshold:
            return tokens, "error"
        elif tokens > warning_threshold:
            return tokens, "warning"
        else:
            return tokens, "ok"
```

**Error Mapping:**

```python
class MCPError(Exception):
    """Base MCP error."""
    code: int
    message: str

class ParseError(MCPError):
    """Invalid JSON was received by the server (-32700)."""
    code = -32700

class InvalidRequest(MCPError):
    """The JSON sent is not a valid Request object (-32600)."""
    code = -32600

class MethodNotFound(MCPError):
    """The method does not exist / is not available (-32601)."""
    code = -32601

class InvalidParams(MCPError):
    """Invalid method parameter(s) (-32602)."""
    code = -32602

class InternalError(MCPError):
    """Internal JSON-RPC error (-32603)."""
    code = -32603

def map_exception_to_mcp_error(exc: Exception) -> dict[str, Any]:
    """Map Python exception to MCP JSON-RPC error."""
    if isinstance(exc, MCPError):
        return {
            "code": exc.code,
            "message": exc.message
        }
    elif isinstance(exc, ValidationError):
        return {
            "code": -32602,
            "message": f"Invalid params: {str(exc)}"
        }
    elif isinstance(exc, DeviceNotFoundError):
        return {
            "code": -32602,
            "message": f"Device not found: {str(exc)}"
        }
    elif isinstance(exc, AuthorizationError):
        return {
            "code": -32000,  # Custom error code
            "message": f"Authorization failed: {str(exc)}"
        }
    else:
        return {
            "code": -32603,
            "message": f"Internal error: {str(exc)}"
        }
```

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

## Summary

This document defines the complete implementation architecture for the RouterOS MCP service with comprehensive MCP protocol integration:

**Core Technology Stack:**
- **Python 3.11+** with async/await throughout
- **FastMCP SDK** or custom MCP protocol implementation
- **FastAPI** for HTTP/admin APIs with Uvicorn ASGI server
- **SQLAlchemy 2.x** + PostgreSQL for persistence
- **Pydantic v2** for validation and settings
- **httpx** (async) for RouterOS REST, **asyncssh** for SSH fallback
- **Prometheus + OpenTelemetry** for observability

**MCP Protocol Implementation:**
- **JSON-RPC 2.0** message handling with proper error codes
- **Multiple transports**: stdio (stdin/stdout) and HTTP/SSE
- **Session management**: client initialization, capability negotiation, state tracking
- **Tool registry**: automatic discovery, tier filtering, schema generation
- **Token estimation**: automatic token counting with budget warnings
- **Error mapping**: Python exceptions → JSON-RPC error codes

**Module Organization:**
- `routeros_mcp/mcp/` - Complete MCP protocol implementation
  - `protocol/` - JSON-RPC messages and error handling
  - `transport/` - Stdio and HTTP/SSE transport implementations
  - `session/` - Client session lifecycle management
  - `registry/` - Tool/resource/prompt registration
  - `middleware/` - Auth, logging, metrics, validation, token budgets
- `routeros_mcp/mcp_tools/` - Tool implementations with @mcp_tool decorator
- `routeros_mcp/mcp_resources/` - Resource providers (Phase 2)
- `routeros_mcp/mcp_prompts/` - Prompt templates (Phase 2)
- `routeros_mcp/domain/` - Business logic (device, plans, jobs, operations)
- `routeros_mcp/infra/` - Infrastructure (RouterOS clients, database, jobs, observability)
- `routeros_mcp/security/` - Authentication (OIDC) and authorization (RBAC)
- `routeros_mcp/api/` - FastAPI HTTP/admin APIs

**Key Design Patterns:**
- **Decorator-based tool registration**: @mcp_tool with automatic schema generation
- **Transport abstraction**: Abstract Transport base class with stdio/HTTP implementations
- **Session-based state**: ClientSession tracks capabilities and lifecycle
- **Middleware pipeline**: Auth → Validation → Metrics → Logging → Token Budget
- **Error handling**: Centralized exception → MCP error mapping
- **Token estimation**: Automatic estimation with warning/error thresholds

**Operational Features:**
- **Graceful shutdown**: Complete in-flight tool calls before stopping
- **Startup validation**: Database, tool schemas, transport binding, device connectivity
- **Health endpoints**: `/health` for load balancer probes
- **Metrics endpoint**: `/metrics` for Prometheus scraping
- **Multiple transports**: Run stdio + HTTP simultaneously for flexibility

**Cross-references:**
- See [Doc 04 (MCP Tools)](04-mcp-tools-interface-and-json-schema-specification.md) for tool JSON schemas
- See [Doc 14 (MCP Protocol Integration)](14-mcp-protocol-integration-and-transport-design.md) for transport details
- See [Doc 15 (MCP Resources and Prompts)](15-mcp-resources-and-prompts-design.md) for Phase 2 features
- See [Doc 16 (Detailed Module Specifications)](16-detailed-module-specifications.md) for complete implementation details
- See [Doc 17 (Configuration Specification)](17-configuration-specification.md) for all configuration options
- See [Doc 10 (Testing)](10-testing-validation-and-sandbox-strategy-and-safety-nets.md) for MCP testing patterns

---

## Related Documentation

For complete implementation specifications of all modules with detailed class/method signatures and implementation patterns, see [docs/16-detailed-module-specifications.md](16-detailed-module-specifications.md).
