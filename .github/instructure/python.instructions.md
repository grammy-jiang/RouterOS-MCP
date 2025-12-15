---
name: Python Coding Standards
description: Python 3.11+ async-first development with type hints, secure logging, and comprehensive testing
applyTo: "**/*.py"
---

# Python Coding Standards for RouterOS MCP

## Language & Environment

- **Python 3.11+** only; use type hints on all public APIs (no `Any` without justification).
- **Async-first**: All I/O operations (RouterOS REST/SSH, HTTP/SSE transports, database) must use `async`/`await`.
- **Never block the event loop** with synchronous network, disk, or CPU-intensive operations in async contexts.

## Type Hints & Static Analysis

- **Type hints required** on all new code:
  - Function parameters and return types (no `-> None` omitted)
  - Class attributes (especially Pydantic models and domain entities)
  - Use `|` for unions (Python 3.10+ syntax), not `Union`
  - Avoid `Any`; prefer precise types or `Protocol`
  - Do not add new `# type: ignore` without clear justification in a comment
- **Run mypy** on new modules; check for errors before committing.

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

**Full CI check command:**

```bash
pytest tests/unit -q && isort routeros_mcp tests --check-only --profile black && black routeros_mcp tests --check && ruff check routeros_mcp tests
```

## Testing & Quality

- **Add tests for all new logic**, especially domain services and infrastructure integrations.
- **Test frameworks**: pytest + pytest-asyncio for async code.
- **Fast validation**: `pytest tests/unit -q` before finalizing changes.
- **Coverage targets**:
  - Non-core modules: ≥85%
  - Core modules (domain, security, RouterOS clients): ≥95%
  - Keep coverage from regressing; flag reduction as a blocker
- **Test naming**: `test_<function>_when_<condition>_then_<expected>` (e.g., `test_get_dns_when_server_down_raises_timeout`)
- **Fixtures**: Use existing fixtures from `tests/unit/conftest.py` and `tests/unit/mcp_tools_test_utils.py`.

## Logging & Security

- **Never log secrets**: No credentials, passwords, API keys, OIDC tokens, or PII in any log.
- **Use structured logging**: Follow patterns in `routeros_mcp/infra/observability/logging.py`.
- **Include correlation IDs**: All logs should propagate correlation IDs for request tracing.
- **Error messages**: Provide actionable information without leaking sensitive details.
- **Example**:
  ```python
  logger.info("Device health check completed", extra={"device_id": device_id, "status": status})
  ```

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
    service = get_health_service()
    return await service.check_device_health(device_id)
```

### Context Management

- Use `@asynccontextmanager` for session lifecycle.
- Ensure cleanup on error (context managers handle this automatically).

## Error Handling

- **Raise typed exceptions**: Use domain exceptions (e.g., `DeviceNotFoundError`, `RouterOSConnectionError`).
- **No silent failures**: Always log and raise on unexpected conditions.
- **Validation first**: Validate inputs at API/tool boundaries; raise `ValueError` with clear messages.
- **RouterOS errors**: Map RouterOS REST errors to domain exceptions; never expose raw error codes to users.

## Module Organization

**Follow this structure for new modules:**

```
routeros_mcp/
├── domain/services/     ← Business logic (no I/O, except through injected clients)
├── infra/              ← I/O clients (REST, SSH, DB, observability)
├── mcp_tools/          ← MCP tool implementations (API boundary)
├── mcp_resources/      ← MCP resource providers (read-only data)
└── security/           ← Auth, authz, crypto
```

- **No circular imports**: Use dependency injection or type `from __future__ import annotations` if needed.
- **One class/function per concern**: Keep functions focused and testable.

## Documentation

- **Docstrings required** for public functions, classes, and modules.
- **Format**: Use Google-style or NumPy-style docstrings consistently.
- **Example**:
  ```python
  async def update_dns_servers(
      device_id: str,
      servers: list[str]
  ) -> dict[str, Any]:
      """Update DNS servers on a device.

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
