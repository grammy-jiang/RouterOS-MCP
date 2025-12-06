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

---

## Error handling and domain exceptions

- Do not swallow exceptions silently:
  - Convert low-level errors into well-defined domain or infrastructure exceptions.  
  - Return standardized error codes to MCP tools as defined in `docs/04-...`.
- Define focused exception types where useful (e.g., `DeviceUnreachableError`, `RouterOSAuthError`) and handle them at appropriate boundaries (API/MCP layer).
- Use `try`/`except` blocks around RouterOS calls:
  - Log failures with context (device, endpoint, error).  
  - Avoid catching broad `Exception` unless you re-raise or convert to a structured error.

---

## Logging, metrics, and tracing usage

- Use the central logging utilities defined in `routeros_mcp/infra/observability/logging.py`:
  - Always include standard fields: `correlation_id`, `tool_name`, `user_sub`, `device_id`, etc., where applicable.  
  - Do not log secrets or sensitive token values.
- Use metrics helpers in `routeros_mcp/infra/observability/metrics.py`:
  - Increment counters and record latencies for MCP tools and RouterOS calls as described in `docs/08-...`.
- Use tracing helpers in `routeros_mcp/infra/observability/tracing.py`:
  - Wrap major operations and RouterOS calls in spans with appropriate attributes.

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
