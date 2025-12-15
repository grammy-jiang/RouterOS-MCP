---
name: Python Coding Standards
description: Python 3.11+ async-first development with type hints, secure logging, and comprehensive testing (RouterOS MCP)
applyTo: "**/*.py"
---

# Python Coding Standards for RouterOS MCP

## Language & Environment

- **Python 3.11+** only (also compatible with 3.12, 3.13).
- **Type hints required** on all public APIs:
  - Function parameters and return types (no `-> None` omitted)
  - Class attributes (especially Pydantic models and domain entities)
  - Use `|` for unions (Python 3.10+ syntax), not `Union`
  - Avoid `Any`; prefer precise types or `Protocol`
  - Do not add new `# type: ignore` without clear justification in a comment
- **Async-first**: All I/O operations (RouterOS REST/SSH, HTTP/SSE transports, database) must use `async`/`await`.
- **Never block the event loop** with synchronous network, disk, or CPU-intensive operations in async contexts.
- **Line length**: Maximum 100 characters (enforced by black and ruff).
- **Naming conventions** (PEP 8):
  - `snake_case` for functions, methods, and variables
  - `CamelCase` for classes
  - `UPPER_SNAKE_CASE` for constants

## Static Type Checking

- **Run mypy** on new modules; check for errors before committing:
  ```bash
  mypy routeros_mcp tests
  ```
- **mypy configuration** (from pyproject.toml):
  - `disallow_untyped_defs = true` (all functions must have type hints)
  - `disallow_incomplete_defs = true` (no partially typed functions)
  - `warn_unused_ignores = true` (flag unnecessary `# type: ignore`)
  - `strict_equality = true` (strict type checking in comparisons)
- **Context variables for MCP protocol**: Use `contextvars` for correlation ID and session tracking (see design docs for patterns).

## Code Formatting Workflow (in strict order)

1. **isort** – Sort and organize imports

   ```bash
   isort routeros_mcp tests --profile black
   ```

   - Black-compatible profile for consistency
   - Groups: stdlib, third-party, local imports

2. **black** – Format code

   ```bash
   black routeros_mcp tests
   ```

   - Enforces 100-character line length limit
   - Consistent string quotes and formatting

3. **ruff** – Lint and fix remaining issues
   ```bash
   ruff check routeros_mcp tests --fix
   ```
   - Auto-fix common issues first
   - Review remaining warnings manually
   - **Note**: Ruff's "I" (isort) rule should be disabled in pyproject.toml to avoid conflicts with isort

**Full CI check command:**

```bash
pytest tests/unit -q && isort routeros_mcp tests --check-only --profile black && black routeros_mcp tests --check && ruff check routeros_mcp tests
```

## Testing & Quality (Test-Driven Development)

**This project follows Test-Driven Development (TDD)** - write tests before implementation.

### Test Frameworks & Patterns

- **Test runner**: pytest with pytest-asyncio for async code
- **Test style**: Both `unittest.TestCase` (with async helper) and pytest-style functions are supported:

  ```python
  # unittest.TestCase style (preferred for e2e tests)
  import unittest
  import asyncio

  ```

**Structured logging with correlation IDs is mandatory for all operations.**

- **Never log secrets**: No credentials, passwords, API keys, OIDC tokens, encryption keys, or PII in any log.
- **Use structured logging**: Follow patterns in `routeros_mcp/infra/observability/logging.py`:
  - All logs are JSON-structured with consistent fields
  - Use `extra={}` for structured context (never string interpolation for sensitive data)
  - Include correlation IDs for request tracing (via `contextvars`)
- **Correlation ID propagation**: Use context variables (`correlation_id_var`) to propagate IDs through async call stacks:

  ```python
  from routeros_mcp.infra.observability.logging import correlation_id_var

  async def handle_request(request_id: str):
      correlation_id_var.set(request_id)  # Propagates to all logs in this context
      logger.info("Processing request", extra={"device_id": device_id})
  ```

- **Log fields** (consistent naming):
  - `timestamp`, `level`, `component`, `correlation_id`
  - `mcp_method`, `tool_name`, `tool_tier`
  - `user_sub`, `user_role` (when authenticated)
  - `device_id`, `device_environment`
  - `error_code`, `error_message` (for failures)
- **Error messages**: Provide actionable information without leaking sensitive details (no stack traces with credentials, no raw RouterOS error messages exposing topology).ytest-asyncio style (valid for unit/integration tests)
  import pytest

  @pytest.mark.asyncio
  async def test_get_device_when_not_found_raises_error():
  with pytest.raises(DeviceNotFoundError):
  await device_service.get_device("invalid-id")

  ```

  ```

### Testing Commands

- **Fast validation**: `pytest tests/unit -q` (unit tests only, ~6 seconds)
- **Full test suite**: `pytest` (all tests: unit + e2e, ~21 seconds)
- **With coverage**: `pytest --cov=routeros_mcp --cov-report=term-missing`

### Coverage Targets (Enforced)

- **Overall coverage**: ≥85% (baseline for all modules)
- **Core modules**: ≥95% (domain, security, RouterOS clients)
- **Keep coverage from regressing** - flag any reduction as a blocker
- **Coverage configuration**: See `[tool.coverage.*]` in pyproject.toml

### Test Naming & Organization

- **Test naming pattern**: `test_<function>_<scenario>_<expected_result>`
  - Example: `test_get_dns_when_device_unreachable_raises_timeout_error`
- **Test directory structure**:
  ```
  tests/
  ├── unit/              # Pure logic, mocked I/O
  ├── integration/       # Multiple components together
  ├── e2e/               # Full stack (MCP tools → services → mocked infra)
  ├── fixtures/          # Shared test data
  └── conftest.py        # Pytest configuration
  ```
- **Fixtures**: Use existing fixtures from `tests/unit/conftest.py` and `tests/unit/mcp_tools_test_utils.py`

### TDD Workflow (Red-Green-Refactor)

1. **RED**: Write a failing test that defines expected behavior
2. **GREEN**: Write minimal code to make the test pass
3. **REFACTOR**: Improve code quality while keeping tests green
4. **REPEAT**: Move to next feature

### Critical Testing Requirements

- **No information loss**: RouterOS parsers must capture ALL fields from device output (see design doc 13 for parsing requirements)
- **Test with real device output**: Use actual RouterOS output in test mocks, not simplified data
- **Handle multi-line values**: Test continuation line parsing for SSH output
- **Test all error paths**: Verify exception handling, validation errors, and edge cases

## Logging & Security

- **Never log secrets**: No credentials, passwords, API keys, OIDC tokens, or PII in any log.
- **Use structured logging**: Follow patterns in `routeros_mcp/infra/observability/logging.py`.
- **Include correlation IDs**: All logs should propagate correlation IDs for request tracing.
- **Error messages**: Provide actionable information without leaking sensitive details.
- **Example**:
  ```python
  logger.info("Device health check completexplicit approval; prefer stdlib and existing libraries.
  ```
- **Check pyproject.toml** before proposing additions: evaluate cost/benefit, maintenance burden, security posture, and license compatibility.
- **Existing approved dependencies** (prefer these):
  - **Core**: fastmcp, fastapi, uvicorn, pydantic, pydantic-settings
  - **I/O**: httpx (async HTTP), asyncssh (SSH), asyncpg/aiosqlite (database)
  - **Data**: sqlalchemy[asyncio], alembic
  - **Observability**: structlog, prometheus-client, opentelemetry-\*
  - **Security**: cryptography, authlib, python-jose
  - **Utilities**: python-dotenv, apscheduler, jinja2, pyyaml, tomli
- **Import organization** (enforced by isort with black profile):
  1. Standard library imports
  2. Third-party imports
  3. Local imports (routeros_mcp.\*)
- **No circular imports**: Use `from __future__ import annotations` for forward references if needed
- **Ruff import sorting**: The "I" rule in ruff should be disabled in `[tool.ruff.lint]` select to avoid conflicts with isort

## RouterOS Integration

- **Use existing clients/services**: Never construct raw REST/SSH calls in domain or API layers.
  - `RouterOSRestClient` (in `routeros_mcp/infra/routeros/rest_client.py`) for REST operations
  - `RouterOSSshClient` (in `routeros_mcp/infra/routeros/ssh_client.py`) for SSH fallbacks (whitelisted commands only)
- **Service-driven design**: Call domain services (`routeros_mcp/domain/services/`) from API/tool layers.
- **Read-modify-write pattern**: Always fetch current state before writes to minimize risk of overwrites.
- **SSH is read-only and fallback-only**: No write operations via SSH; SSH commands must be in the whitelist.

## Dependencies & Imports

- **No new runtime dependencies** without approval; prefer stdlib and existing libraries.
- **Check pyproject.toml** before adding: cost/benefit, maintenance, security, license.
- **Prefer asyncio, httpx, asyncssh, SQLAlchemy, Pydantic** (already in the project).

## Authorization & Security

- **Preserve existing authz checks**: Never weaken guardrails for high-risk tools or operations.
- **Enforce tiers**: Respect `read_only`, `ops_rw`, `admin` role enforcement.
- **Environment tags**: Honor `lab`/`staging`/`prod` restrictions on write operations.
- **Approval tokens**: High-risk tools require short-lived (5-min TTL) human-generated approval tokens.
- **Audit all writes**: Every write operation must create an `AuditEvent` entry with user, device, tool name, params, and result.

## Async I/O Patterns

### MCP Transport Operations

```python
class Transport(ABC):
    @abstractmethod
    async def start(self) -> None:
        """Start transport and accept connections."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop (complete in-flight requests)."""
        ...
```

### RouterOS Calls

```python
async def get_device_health(device_id: str) -> dict[str, Any]:
    """Fetch device health. Always use services, never raw REST."""
    service = get_health_service(), `DeviceUnreachableError`).
- **No silent failures**: Always log and raise on unexpected conditions; never catch broad `Exception` without re-raising or converting to structured error.
- **Validation first**: Validate inputs at API/tool boundaries; raise `ValueError` or Pydantic `ValidationError` with clear, actionable messages.
- **MCP error mapping**: Convert Python exceptions to JSON-RPC 2.0 error codes:
  - Parse errors → -32700
  - Invalid request → -32600
  - Method not found → -32601
  - Invalid params → -32602
  - Internal error → -32603
  - Custom errors → -32000 to -32099 range
- **RouterOS errors**: Map RouterOS REST/SSH errors to domain exceptions; never expose raw RouterOS error codes or messages to MCP clients (sanitize and provide actionable guidance)
### Context Management

- Use `@asynccontextmanager` for session lifecycle.
- Ensure cleanup on error (context managers handle this automatically).

## Error Handling & Architecture

**Follow layered architecture (docs/11 for full details):**

```

routeros_mcp/
├── domain/
│ ├── models.py ← SQLAlchemy ORM models (Device, Job, Plan, AuditEvent)
│ └── services/ ← Business logic (no direct I/O; use injected clients)
│ ├── device.py, health.py, dns_ntp.py, firewall.py
│ ├── interface.py, ip.py, routing.py, system.py
│ └── diagnostics.py, job.py, plan.py
├── infra/
│ ├── db/ ← SQLAlchemy session management, repositories
│ ├── routeros/ ← RouterOS REST/SSH clients (async, whitelisted)
│ └── observability/ ← Logging, metrics, tracing (structlog, Prometheus, OTEL)
├── mcp/
│ ├── server.py ← FastMCP server, tool/resource/prompt registration
│ ├── protocol/ ← JSON-RPC 2.0 protocol handling
│ └── transport/ ← stdio, HTTP/SSE transports
├── mcp_tools/ ← MCP tool implementations (34 tools organized by domain)
├── mcp_resources/ ← MCP resource providers (device, fleet, plan, audit)
├── mcp_prompts/ ← Jinja2 prompt templates (8 prompts)
├── security/ ← Auth (OIDC), authz (role-based), encryption
├── config.py ← Pydantic Settings (YAML/TOML/env/CLI config)
├── cli.py ← Argument parsing, config loading
└── main.py ← Application startup, logging setup

```

**Design principles:**

- **Domain-Driven Design**: MCP tools → domain services → infra clients (never skip layers)
- **Dependency injection**: Services receive clients via constructor; avoid global state
- **One concern per module**: Keep functions focused and testable
- **No circular imports**: Use `from __future__ import annotations` for forward references if needed
├── mcp_tools/          ← MCP tool implementations (API boundary)
├── mcp_resources/      ← MCP resource providers (read-only data)
└── security/           ← Auth, authz, crypto
```

- **No circular imports**: Use dependency injection or type `from __future__ import annotations` if needed.
- \*RouterOS Data Parsing (Critical Requirement)

**PRINCIPLE: Complete Data Fidelity - No Information Loss**

All RouterOS parsers (REST and SSH) **must capture and return ALL fields** provided by RouterOS.

### Parsing Requirements

1. **Parse ALL fields**: Every field returned by RouterOS (REST API or SSH CLI) must be captured
2. **Handle multi-line values**: SSH output often uses continuation lines (indented, no colon) for multi-line field values - parsers must accumulate these correctly
3. **Support field variations**: Different RouterOS versions may include/exclude optional fields - handle gracefully
4. **Parse value formats**: Handle RouterOS-specific formats:
   - Size suffixes: `4096KiB`, `2048KB` → extract numeric value
   - Duration formats: `1w`, `5s`, `2d` → preserve or convert
   - Boolean values: `yes`/`no`, `true`/`false` → Python `bool`
   - Empty values: Empty strings → `None` or empty list
5. **Test with actual device output**: Test cases must use real RouterOS output examples, not simplified mocks

### Implementation Pattern

```python
async def _get_resource_via_ssh(self, device_id: str) -> dict[str, Any]:
    """Fetch resource via SSH. MUST return ALL fields - no information loss."""
    ssh_client = await self.device_service.get_ssh_client(device_id)
    output = await ssh_client.execute("/some/command/print")

    result: dict[str, Any] = {}  # Initialize with all possible fields
    current_key: str | None = None

    for line in output.strip().split("\n"):
        # Handle continuation lines (multi-line values)
        if line[0].isspace() and ":" not in line and current_key:
            value = line.strip()
            # Append to current field
            continue

        # Parse key: value lines
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            current_key = key

            # Parse ALL keys returned by RouterOS (never skip fields)
            if key == "some-field":
                result["some_field"] = value
            # ... continue for ALL fields

    return result
```

## Code Review Checklist

Before committing, verify:

- [ ] **Type hints**: All functions/methods fully type-hinted (params + returns)
- [ ] **No unsafe type ignores**: No new `# type: ignore` without comment justification
- [ ] **Async I/O**: All I/O is async (no `requests`, `paramiko`, blocking calls)
- [ ] **No secret leaks**: No secrets in logs, exception messages, or error responses
- [ ] **Tests added**: Tests added/extended for new logic; coverage not reduced
- [ ] **Service-driven RouterOS access**: No raw REST/SSH calls in domain/tool layers
- [ ] **Formatting applied**: isort → black → ruff workflow completed
- [ ] **No unapproved dependencies**: No new runtime dependencies without approval
- [ ] **Auth/authz preserved**: Existing authorization checks not weakened
- [ ] **Docstrings present**: Public APIs have Google-style or NumPy-style docstrings
- [ ] **Complete data parsing**: RouterOS parsers capture ALL fields (no information loss)
- [ ] **Correlation IDs**: Logs propagate correlation IDs via context variables
- [ ] **TDD workflow**: Tests written before implementation (Red-Green-Refactor)
      Args:
      device_id: Device identifier
      servers: List of DNS server IPs (e.g., ["8.8.8.8", "1.1.1.1"])

      Returns:
          dict with "success": bool and optional "error": str

      Raises:
          DeviceNotFoundError: If device not found
          RouterOSConnectionError: If REST API unreachable
      """

  ```

  ```

## Code Review Checklist

Before committing, verify:

- [ ] All functions/methods are fully type-hinted
- [ ] No new `# type: ignore` without comment justification
- [ ] All I/O is async (no `requests`, `paramiko`, blocking calls in async code)
- [ ] No secrets logged (check logger calls and exception messages)
- [ ] Tests added/extended; coverage not reduced
- [ ] RouterOS access via services, not raw REST/SSH calls
- [ ] Formatting workflow applied (isort → black → ruff)
- [ ] No new runtime dependencies without approval
- [ ] Auth/approval checks preserved (not weakened)
- [ ] Docstrings on public APIs
