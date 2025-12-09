# Python Coding Standards & Conventions

## Purpose

Define the Python coding standards and conventions for this repository so that all contributors write consistent, maintainable, and safe code. This document complements the implementation architecture (`docs/11-...`) and development environment docs (`docs/12-...`).

---

## Language, style, and general principles

- Python 3.11+ only.  
- Code should prioritize:
  - Clarity and correctness over cleverness.  
  - Explicit separation of concerns (API, domain, infrastructure).  
  - Security and safety, especially around RouterOS operations.
- Follow PEP 8 naming and layout conventions:
  - `snake_case` for functions, methods, and variables.  
  - `CamelCase` for classes.  
  - `UPPER_SNAKE_CASE` for constants.

---

## Type hints and static typing

- All new code must be fully type-annotated:
  - Function parameters and return types.
  - Class attributes (especially on Pydantic models and domain models).
  - Avoid `Any` unless strictly necessary; prefer precise types or `Protocol`s.
- Use `mypy` for static type checking:
  - Add new modules under type checking.
  - Do not introduce new `# type: ignore` without a clear justification.
- Prefer standard-library typing features (`collections.abc`, `typing`, `typing_extensions`) over ad-hoc or untyped patterns.

### MCP-specific type patterns

- **MCP protocol message types**: Use Pydantic models for all JSON-RPC 2.0 messages:

```python
from pydantic import BaseModel, Field

class JsonRpcRequest(BaseModel):
    """Base JSON-RPC 2.0 request."""
    jsonrpc: str = Field(default="2.0", frozen=True)
    id: int | str | None = None
    method: str
    params: dict[str, Any] | None = None

class InitializeRequest(BaseModel):
    """MCP initialize request params."""
    protocol_version: str = Field(alias="protocolVersion")
    capabilities: dict[str, Any]
    client_info: dict[str, str] = Field(alias="clientInfo")

class ToolsCallRequest(BaseModel):
    """MCP tools/call request params."""
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
```

- **Tool handler signatures**: All MCP tool handlers must follow this signature:

```python
from typing import Protocol

class ToolHandler(Protocol):
    """Protocol for MCP tool handler functions."""
    async def __call__(
        self,
        *,
        # Tool-specific parameters from tool schema
        **kwargs: Any
    ) -> dict[str, Any]:
        """
        Execute tool and return MCP response.

        Returns:
            dict with keys:
            - content: list[dict] with type="text" or type="image"
            - _meta: optional metadata (tokens, RouterOS version, etc.)
        """
        ...
```

- **Context variables**: Use `contextvars` for correlation ID and session tracking:

```python
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)
client_info_var: ContextVar[dict[str, str] | None] = ContextVar("client_info", default=None)
```

- **Generic types for registry patterns**:

```python
from typing import TypeVar, Generic

T = TypeVar("T")

class Registry(Generic[T]):
    """Generic registry for tools, resources, etc."""
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def register(self, name: str, item: T) -> None:
        """Register item by name."""
        self._items[name] = item

    def get(self, name: str) -> T | None:
        """Get item by name."""
        return self._items.get(name)
```

---

## Asynchronous I/O and RouterOS calls

- All RouterOS REST and SSH operations must be **async**:
  - Use `async`/`await` end-to-end from API layer down to infrastructure.
  - Do not block the event loop with synchronous network or disk I/O in async code.
- `httpx`:
  - Use `AsyncClient` with appropriate timeouts and connection pooling.
  - Centralize REST calls in `RouterOSRestClient`; domain code should not construct HTTP requests directly.
- `asyncssh`:
  - Use an async SSH client only via `RouterOSSshClient`, with whitelisted command IDs.
  - Do not run arbitrary shell commands from domain or API layers.

### MCP-specific async patterns

- **MCP transport I/O**: All MCP transport operations (stdio, HTTP/SSE) must be async:

```python
from abc import ABC, abstractmethod

class Transport(ABC):
    """Abstract MCP transport."""

    @abstractmethod
    async def start(self) -> None:
        """Start transport and begin accepting connections."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop transport (complete in-flight requests)."""
        ...

    @abstractmethod
    async def send_message(self, message: dict[str, Any]) -> None:
        """Send JSON-RPC message to client."""
        ...

    @abstractmethod
    async def receive_message(self) -> dict[str, Any]:
        """Receive JSON-RPC message from client (blocks until available)."""
        ...
```

- **Concurrent tool call handling**: Use semaphores to limit concurrent tool executions:

```python
import asyncio
from typing import Final

MAX_CONCURRENT_TOOL_CALLS: Final[int] = 10

class ToolExecutor:
    """Executes MCP tool calls with concurrency limits."""

    def __init__(self, max_concurrent: int = MAX_CONCURRENT_TOOL_CALLS) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute tool with concurrency limiting."""
        async with self._semaphore:
            # Tool execution logic here
            ...
```

- **Session lifecycle management**: Use async context managers for session cleanup:

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

@asynccontextmanager
async def client_session(
    session_id: str,
    client_info: dict[str, str]
) -> AsyncIterator[ClientSession]:
    """Manage MCP client session lifecycle."""
    session = ClientSession(session_id=session_id, client_info=client_info)
    await session.initialize()

    try:
        yield session
    finally:
        await session.cleanup()
```

- **Graceful shutdown**: Complete in-flight tool calls before stopping:

```python
class MCPServer:
    """MCP protocol server."""

    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._in_flight_calls: set[asyncio.Task] = set()

    async def stop(self, timeout: float = 30.0) -> None:
        """Gracefully stop server."""
        self._shutdown_event.set()

        # Wait for in-flight calls to complete
        if self._in_flight_calls:
            done, pending = await asyncio.wait(
                self._in_flight_calls,
                timeout=timeout
            )

            # Cancel any calls that didn't complete in time
            for task in pending:
                task.cancel()
```

---

## Error handling and domain exceptions

- Do not swallow exceptions silently:
  - Convert low-level errors into well-defined domain or infrastructure exceptions.
  - Return standardized error codes to MCP tools as defined in `docs/04-...`.
- Define focused exception types where useful (e.g., `DeviceUnreachableError`, `RouterOSAuthError`) and handle them at appropriate boundaries (API/MCP layer).
- Use `try`/`except` blocks around RouterOS calls:
  - Log failures with context (device, endpoint, error).
  - Avoid catching broad `Exception` unless you re-raise or convert to a structured error.

### MCP-specific error handling

- **JSON-RPC 2.0 error codes**: Map Python exceptions to standard JSON-RPC error codes:

```python
class MCPError(Exception):
    """Base MCP protocol error."""
    code: int
    message: str
    data: dict[str, Any] | None = None

class ParseError(MCPError):
    """Invalid JSON (-32700)."""
    code = -32700
    message = "Parse error"

class InvalidRequest(MCPError):
    """Invalid Request object (-32600)."""
    code = -32600
    message = "Invalid Request"

class MethodNotFound(MCPError):
    """Method does not exist (-32601)."""
    code = -32601
    message = "Method not found"

class InvalidParams(MCPError):
    """Invalid method parameter(s) (-32602)."""
    code = -32602
    message = "Invalid params"

class InternalError(MCPError):
    """Internal JSON-RPC error (-32603)."""
    code = -32603
    message = "Internal error"
```

- **Exception mapping function**: Convert domain exceptions to JSON-RPC errors:

```python
from pydantic import ValidationError

def map_exception_to_jsonrpc_error(exc: Exception) -> dict[str, Any]:
    """Map Python exception to JSON-RPC error object."""
    if isinstance(exc, MCPError):
        return {
            "code": exc.code,
            "message": exc.message,
            "data": exc.data
        }
    elif isinstance(exc, ValidationError):
        return {
            "code": -32602,
            "message": "Invalid params",
            "data": {"validation_errors": exc.errors()}
        }
    elif isinstance(exc, DeviceNotFoundError):
        return {
            "code": -32602,
            "message": "Invalid params",
            "data": {"error": f"Device not found: {exc.device_id}"}
        }
    elif isinstance(exc, DeviceUnreachableError):
        return {
            "code": -32603,
            "message": "Internal error",
            "data": {"error": f"Device unreachable: {exc.device_id}"}
        }
    else:
        # Generic internal error for unexpected exceptions
        return {
            "code": -32603,
            "message": "Internal error",
            "data": {"error": str(exc), "type": type(exc).__name__}
        }
```

- **Tool handler error pattern**: Wrap tool execution in try/except:

```python
async def execute_tool_call(
    tool_name: str,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute MCP tool call and return JSON-RPC response."""
    try:
        # Get tool handler
        handler = tool_registry.get(tool_name)
        if not handler:
            raise MethodNotFound(f"Tool not found: {tool_name}")

        # Validate arguments against schema
        validate_tool_arguments(tool_name, arguments)

        # Execute tool
        result = await handler(**arguments)

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result
        }

    except MCPError as e:
        # MCP protocol errors pass through
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {
                "code": e.code,
                "message": e.message,
                "data": e.data
            }
        }

    except Exception as e:
        # Convert unexpected errors to JSON-RPC format
        error_obj = map_exception_to_jsonrpc_error(e)
        logger.exception(
            "Tool execution failed",
            extra={
                "tool_name": tool_name,
                "arguments": arguments,
                "error_code": error_obj["code"]
            }
        )
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error_obj
        }
```

---

## Logging, metrics, and tracing usage

- Use the central logging utilities defined in `routeros_mcp/infra/observability/logging.py`:
  - Always include standard fields: `correlation_id`, `tool_name`, `user_sub`, `device_id`, etc., where applicable.
  - Do not log secrets or sensitive token values.
- Use metrics helpers in `routeros_mcp/infra/observability/metrics.py`:
  - Increment counters and record latencies for MCP tools and RouterOS calls as described in `docs/08-...`.
- Use tracing helpers in `routeros_mcp/infra/observability/tracing.py`:
  - Wrap major operations and RouterOS calls in spans with appropriate attributes.

### MCP-specific observability patterns

- **JSON-RPC message logging**: Log all protocol messages with configurable verbosity:

```python
import logging

logger = logging.getLogger(__name__)

def log_jsonrpc_message(
    direction: str,  # "inbound" or "outbound"
    message: dict[str, Any],
    *,
    session_id: str | None = None
) -> None:
    """Log JSON-RPC message (if enabled via MCP_LOG_JSONRPC env var)."""
    if not settings.MCP_LOG_JSONRPC:
        return

    logger.debug(
        f"JSON-RPC {direction}",
        extra={
            "direction": direction,
            "method": message.get("method"),
            "request_id": message.get("id"),
            "session_id": session_id,
            "message": message  # Full message for debugging
        }
    )
```

- **Tool execution logging**: Always log tool calls with structured context:

```python
async def log_tool_execution(
    tool_name: str,
    arguments: dict[str, Any],
    result: dict[str, Any] | None = None,
    error: Exception | None = None,
    duration_ms: float | None = None
) -> None:
    """Log MCP tool execution with full context."""
    log_data = {
        "tool_name": tool_name,
        "correlation_id": correlation_id_var.get(),
        "session_id": session_id_var.get(),
        "client_info": client_info_var.get(),
        "arguments": redact_sensitive_fields(arguments),
        "duration_ms": duration_ms
    }

    if error:
        logger.error(
            f"Tool execution failed: {tool_name}",
            extra=log_data | {"error": str(error), "error_type": type(error).__name__}
        )
    else:
        # Log estimated token count
        estimated_tokens = result.get("_meta", {}).get("estimated_tokens", 0)
        logger.info(
            f"Tool execution completed: {tool_name}",
            extra=log_data | {"estimated_tokens": estimated_tokens}
        )
```

- **Session lifecycle logging**: Track MCP session lifecycle events:

```python
class ClientSession:
    """MCP client session."""

    async def initialize(self) -> None:
        """Initialize session."""
        logger.info(
            "MCP session initialized",
            extra={
                "session_id": self.session_id,
                "client_info": self.client_info,
                "protocol_version": self.protocol_version,
                "capabilities": self.capabilities
            }
        )

    async def cleanup(self) -> None:
        """Clean up session."""
        logger.info(
            "MCP session closed",
            extra={
                "session_id": self.session_id,
                "total_tool_calls": self.stats.total_calls,
                "total_tokens": self.stats.total_tokens,
                "duration_seconds": self.stats.duration_seconds
            }
        )
```

- **Metrics for MCP tools**: Use consistent metric naming:

```python
from prometheus_client import Counter, Histogram

# Tool call metrics
mcp_tool_calls_total = Counter(
    "mcp_tool_calls_total",
    "Total MCP tool calls",
    ["tool_name", "status"]  # status: success, error, rate_limited
)

mcp_tool_call_duration_seconds = Histogram(
    "mcp_tool_call_duration_seconds",
    "MCP tool call duration",
    ["tool_name"]
)

mcp_tool_tokens_total = Counter(
    "mcp_tool_tokens_total",
    "Total tokens returned by MCP tools",
    ["tool_name"]
)

# Usage in tool execution
async def execute_tool_with_metrics(
    tool_name: str,
    arguments: dict[str, Any]
) -> dict[str, Any]:
    """Execute tool with metrics."""
    start_time = time.time()

    try:
        result = await execute_tool(tool_name, arguments)

        # Record success metrics
        mcp_tool_calls_total.labels(tool_name=tool_name, status="success").inc()
        tokens = result.get("_meta", {}).get("estimated_tokens", 0)
        mcp_tool_tokens_total.labels(tool_name=tool_name).inc(tokens)

        return result

    except RateLimitExceededError:
        mcp_tool_calls_total.labels(tool_name=tool_name, status="rate_limited").inc()
        raise

    except Exception:
        mcp_tool_calls_total.labels(tool_name=tool_name, status="error").inc()
        raise

    finally:
        duration = time.time() - start_time
        mcp_tool_call_duration_seconds.labels(tool_name=tool_name).observe(duration)
```

---

## Configuration and settings

- Use the Pydantic `Settings` class (`routeros_mcp/config.py`) for configuration:
  - Do not read environment variables directly outside of `Settings`.  
  - Avoid hard-coding environment-specific values.
- Configuration must be:
  - Loaded once at startup.  
  - Injected into components that need it (e.g., REST client timeouts, DB URLs).

---

## Module and package structure

- Follow the module layout defined in `docs/11-implementation-architecture-and-module-layout.md`:
  - Keep API-facing code in `routeros_mcp/api`.
  - Keep domain logic in `routeros_mcp/domain`.
  - Keep infrastructure concerns (DB, RouterOS clients, jobs, observability) in `routeros_mcp/infra`.
- Avoid circular dependencies between:
  - API and domain.
  - Domain and infrastructure.

### MCP module organization

- **MCP protocol code**: Organize MCP-specific code under `routeros_mcp/mcp/`:

```
routeros_mcp/mcp/
├── __init__.py              # Public API exports
├── server.py                # MCPServer main class
├── protocol/
│   ├── __init__.py
│   ├── messages.py          # JSON-RPC message models
│   ├── errors.py            # MCPError hierarchy
│   └── validation.py        # Request/response validation
├── transport/
│   ├── __init__.py
│   ├── base.py              # Transport ABC
│   ├── stdio.py             # StdioTransport
│   └── http.py              # HttpTransport (SSE)
├── session/
│   ├── __init__.py
│   ├── manager.py           # SessionManager
│   └── state.py             # ClientSession
├── registry/
│   ├── __init__.py
│   ├── tools.py             # ToolRegistry
│   └── decorators.py        # @mcp_tool decorator
└── middleware/
    ├── __init__.py
    ├── auth.py              # Authentication middleware
    ├── validation.py        # Request validation middleware
    ├── metrics.py           # Metrics middleware
    └── token_budget.py      # Token budget estimation
```

- **Tool implementations**: Keep MCP tool handlers separate from domain services:

```
routeros_mcp/mcp_tools/
├── __init__.py
├── system.py                # system.* tools
├── interfaces.py            # interface.* tools
├── ip_addresses.py          # ip.address.* tools
├── firewall.py              # firewall.* tools
└── diagnostics.py           # diagnostics.* tools
```

- **Import patterns for MCP code**:

```python
# Good: Import from mcp package
from routeros_mcp.mcp.registry import ToolRegistry, mcp_tool
from routeros_mcp.mcp.protocol import JsonRpcRequest, MCPError
from routeros_mcp.mcp.transport import StdioTransport

# Good: MCP tools import domain services
from routeros_mcp.domain.devices import DeviceService
from routeros_mcp.domain.interfaces import InterfaceService

# Bad: Don't import tool handlers in domain code
# Domain services should not know about MCP tools
```

---

## Testing strategy and conventions

**For comprehensive TDD methodology, test-driven development workflow, Red-Green-Refactor cycle, and detailed testing strategies, see [docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md](10-testing-validation-and-sandbox-strategy-and-safety-nets.md).**

- Use `pytest` for all tests:
  - Place tests in a top-level `tests/` directory mirroring the package structure.
  - Name test files `test_*.py` and test functions `test_*`.
- For async code, use `pytest-asyncio` or similar fixtures:

```python
import pytest

@pytest.mark.asyncio
async def test_example_async_behavior() -> None:
    ...
```

- Write unit tests for:
  - Domain logic (plan generation, validation, authorization decisions).  
  - RouterOS integration mapping (using mocks to avoid live devices).
- Use integration and device-lab tests for:
  - End-to-end flows involving actual RouterOS devices in the `lab` environment.

- Strive for a test-driven development style:
  - When adding or changing behavior, add or update tests first or in parallel with implementation changes.  
  - Tests should cover both normal return values and all documented error/exception scenarios for functions and methods.  
  - Common end-to-end usage patterns (e.g., typical MCP tool calling sequences) should be represented in integration tests.

---

## Tox, coverage, linting, and formatting

- Use `tox` to standardize local and CI runs:
  - Recommended envs (to be defined in `tox.ini` / `pyproject.toml`):
    - `py` (tests).  
    - `lint` (ruff).  
    - `type` (mypy).  
    - `cov` (pytest with coverage).
- Coverage:
  - Use `pytest-cov` (or `pytest --cov`) to enforce coverage thresholds in local runs and CI.  
  - Maintain an overall test coverage of at least **85%** across the codebase (configurable, but this is the default baseline for 1.x).  
  - Critical/core modules (e.g., domain logic, security, RouterOS integration, plan/apply orchestration) are expected to reach **100%** coverage on reachable code paths; changes that reduce coverage in these areas should be treated as regressions.  
  - Focus coverage improvements on domain, security, and RouterOS integration code when prioritizing gaps.
- Linting and formatting:
  - `ruff` is the primary linter; fix or justify any new lint warnings.  
  - Use `black` as the formatter (or ruff’s formatter if explicitly configured).  
  - Run both locally (or via `tox`) before committing.

---

## Dependency management and imports

- Keep dependencies minimal and justified:
  - Prefer standard library modules where reasonable.  
  - Add new third-party dependencies only when they provide clear value.
- Import style:
  - Absolute imports within the package (e.g., `from routeros_mcp.domain.devices import DeviceService`).  
  - Group imports: stdlib, third-party, then local, separated by blank lines.
- Avoid:
  - Wildcard imports (`from module import *`).  
  - Heavy logic in `__init__.py` files.

---

## Security-focused practices

- Treat all external input as untrusted:
  - Validate parameters in API and MCP layers using Pydantic models.  
  - Enforce authorization checks before calling domain services or RouterOS clients.
- Never:
  - Log secrets, passwords, tokens, or full configs.  
  - Build RouterOS CLI commands from raw user input; always use templated command IDs and validated parameters.
- Ensure all write operations:
  - Respect environment tags and device capability flags.  
  - Report `changed` vs `unchanged` accurately.  
  - Integrate with the plan/apply + approval model where required.

---

## Mocking and test data

- Only test code (under `tests/`) may contain mock data, fake responses, or stub implementations.
- Production code must not contain built-in mock/demo modes, fake RouterOS responses, or hard-coded test data.
- Use dependency injection and clear interfaces so that tests can substitute mocked RouterOS clients or other dependencies without introducing mock behavior into the main codebase.

### MCP-specific testing patterns

- **Tool handler testing**: Test tool handlers in isolation using mocks:

```python
import pytest
from unittest.mock import AsyncMock, Mock

@pytest.mark.asyncio
async def test_system_get_overview_tool():
    """Test system.get_overview tool handler."""
    # Mock device service
    mock_device_service = Mock()
    mock_device_service.get_overview = AsyncMock(return_value={
        "routeros_version": "7.16",
        "cpu": {"load": "5%"},
        "memory": {"used": "45%"}
    })

    # Import and call tool handler with mocked dependencies
    from routeros_mcp.mcp_tools.system import get_system_overview

    result = await get_system_overview(
        device_id="test-device-123",
        device=mock_device  # Injected mock
    )

    # Verify response format
    assert "content" in result
    assert result["content"][0]["type"] == "text"
    assert "_meta" in result
    assert "estimated_tokens" in result["_meta"]
```

- **MCP protocol testing**: Test JSON-RPC message handling:

```python
@pytest.mark.asyncio
async def test_tools_list_request():
    """Test MCP tools/list request handling."""
    server = MCPServer(...)

    request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {}
    }

    response = await server.handle_request(request)

    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 1
    assert "result" in response
    assert "tools" in response["result"]
    assert len(response["result"]["tools"]) > 0
```

- **Transport testing**: Test stdio and HTTP transports with mocked I/O:

```python
@pytest.mark.asyncio
async def test_stdio_transport_send_receive():
    """Test StdioTransport message send/receive."""
    # Mock stdin/stdout
    mock_reader = AsyncMock()
    mock_writer = AsyncMock()

    transport = StdioTransport(reader=mock_reader, writer=mock_writer)

    # Test send
    message = {"jsonrpc": "2.0", "method": "test"}
    await transport.send_message(message)

    # Verify JSON was written to stdout
    written_data = mock_writer.write.call_args[0][0]
    assert b'"jsonrpc"' in written_data
    assert b'"method": "test"' in written_data

    # Test receive
    mock_reader.readline = AsyncMock(
        return_value=b'{"jsonrpc":"2.0","id":1}\n'
    )
    received = await transport.receive_message()

    assert received["jsonrpc"] == "2.0"
    assert received["id"] == 1
```

- **Session lifecycle testing**: Test session initialization and cleanup:

```python
@pytest.mark.asyncio
async def test_session_lifecycle():
    """Test MCP session lifecycle."""
    session_manager = SessionManager()

    # Test initialization
    session = await session_manager.create_session(
        client_info={"name": "test-client", "version": "1.0.0"}
    )

    assert session.session_id is not None
    assert session.state == "initialized"

    # Test cleanup
    await session_manager.close_session(session.session_id)

    # Verify session is removed
    with pytest.raises(SessionNotFoundError):
        session_manager.get_session(session.session_id)
```

- **Error mapping testing**: Test exception to JSON-RPC error conversion:

```python
@pytest.mark.parametrize(
    "exception,expected_code,expected_message",
    [
        (ParseError("Invalid JSON"), -32700, "Parse error"),
        (MethodNotFound("Unknown method"), -32601, "Method not found"),
        (ValidationError(...), -32602, "Invalid params"),
        (DeviceNotFoundError("dev-1"), -32602, "Invalid params"),
        (Exception("Unexpected"), -32603, "Internal error"),
    ]
)
def test_exception_to_jsonrpc_error(exception, expected_code, expected_message):
    """Test exception mapping to JSON-RPC errors."""
    error_obj = map_exception_to_jsonrpc_error(exception)

    assert error_obj["code"] == expected_code
    assert expected_message in error_obj["message"]
```

---

## Tool decorator and automatic schema generation

- **@mcp_tool decorator pattern**: Use decorator for automatic tool registration:

```python
from routeros_mcp.mcp.registry import mcp_tool

@mcp_tool(
    name="system.get_overview",
    description="Get RouterOS system overview and health metrics",
    tier="free"
)
async def get_system_overview(
    device_id: str,
    *,
    device: Device  # Injected by MCP framework
) -> dict[str, Any]:
    """
    Get system overview for device.

    Args:
        device_id: UUID of target device

    Returns:
        MCP tool response with content and _meta
    """
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
            "estimated_tokens": estimate_tokens(overview)
        }
    }
```

- **Schema generation from Pydantic**: Use Pydantic models for automatic JSON Schema:

```python
from pydantic import BaseModel, Field

class GetOverviewArgs(BaseModel):
    """Arguments for system.get_overview tool."""
    device_id: str = Field(
        description="UUID of target RouterOS device",
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )

@mcp_tool(
    name="system.get_overview",
    description="Get RouterOS system overview",
    tier="free",
    input_schema=GetOverviewArgs  # Automatically converted to JSON Schema
)
async def get_system_overview(args: GetOverviewArgs) -> dict[str, Any]:
    """Get system overview."""
    ...
```

- **Tool handler return format**: All tool handlers must return this structure:

```python
{
    "content": [
        {
            "type": "text",  # or "image"
            "text": "Human-readable output..."  # or "data": "base64..."
        }
    ],
    "_meta": {  # Optional metadata
        "estimated_tokens": 1250,
        "routeros_version": "7.16",
        "device_uptime": "15d 3h 45m"
    },
    "isError": False  # Optional, defaults to False
}
```
