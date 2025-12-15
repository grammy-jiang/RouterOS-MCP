# Copilot Coding Agent Onboarding (RouterOS-MCP)

## What This Repository Is

**Model Context Protocol (MCP) service** for managing MikroTik RouterOS v7 devices with safe, role-aware tools/resources/prompts.

**Stack:** Python 3.11+ • FastMCP • FastAPI/Starlette • SQLAlchemy 2.x/Alembic • asyncssh/httpx • structlog/OpenTelemetry • APScheduler

**Scale:** ~20 design specs (docs/00-19), extensive Python codebase, 583 tests (564 unit + 19 e2e), 80% coverage target

**Entry point:** `routeros-mcp` CLI → `routeros_mcp.main:main` (stdio MCP server; HTTP/SSE transport planned)

## Project Layout & Architecture

### Root Directory

- `pyproject.toml` - All dependencies, tool configs (pytest/coverage/mypy/ruff/black), scripts
- `README.md` - Project overview, features, documentation index
- `CONTRIBUTING.md` - Development workflow, code standards, commit conventions
- `alembic/` - Database migrations (one migration: 4f1013926767_initial_schema.py)
- `config/lab.yaml` - Development config (SQLite, debug mode, stdio transport)
- `.github/workflows/` - CI pipelines (copilot-agent-ci.yml, copilot-setup-steps.yml)
- `docs/` - 20 comprehensive design documents (00-19 series)
- `tests/` - Unit tests (tests/unit/), e2e tests (tests/e2e/)

### Source Code Structure (`routeros_mcp/`)

- `config.py` - Pydantic Settings with priority: defaults → YAML/TOML → env vars → CLI args
- `cli.py` - Argument parsing, config file loading
- `main.py` - Application startup, logging setup, server initialization
- `domain/` - Business logic layer
  - `models.py` - SQLAlchemy ORM models (Device, Job, Plan, AuditEvent, etc.)
  - `services/` - Core services (device, dns_ntp, firewall, health, interface, ip, routing, system, diagnostics, job, plan)
- `infra/` - Infrastructure layer
  - `db/` - SQLAlchemy session management
  - `observability/` - Logging (structlog), metrics (Prometheus), tracing (OpenTelemetry)
  - `routeros/` - REST client (httpx) and SSH client (asyncssh) for RouterOS devices
- `mcp/` - MCP protocol implementation
  - `server.py` - FastMCP server, tool/resource/prompt registration
  - `protocol/` - JSON-RPC protocol handling
  - `transport/` - stdio and HTTP/SSE transports
- `mcp_tools/` - MCP tool implementations (34 tools: config, device, diagnostics, dns_ntp, firewall_logs, firewall_write, interface, ip, routing, system)
- `mcp_resources/` - MCP resource providers (device, fleet, plan, audit)
- `mcp_prompts/` - Jinja2 prompt templates (8 prompts in prompts/ directory)
- `security/` - Authentication (OIDC) and authorization (role-based)

### Configuration Priority (Validated)

1. Built-in defaults (Settings class)
2. Config file (YAML/TOML via `--config`)
3. Environment variables (prefix: `ROUTEROS_MCP_`)
4. CLI arguments (highest priority)

**Critical:** Lab env uses insecure fallback encryption_key; staging/prod REQUIRE `ROUTEROS_MCP_ENCRYPTION_KEY` env var or fail with warnings.

## Development Setup (Validated 2025-12-15)

### Prerequisites

- **Python 3.11+** (tested with 3.13.1, works with 3.11/3.12)
- Virtual environment recommended: `python -m venv .venv && source .venv/bin/activate`
- Alternative: `uv venv .venv && source .venv/bin/activate` (faster)

### Installation (One-Time)

```bash
python -m pip install -e .[dev]
```

**Verified:** Installs routeros-mcp 0.1.0 in editable mode with all dev dependencies (pytest, mypy, ruff, black, coverage)

### Optional Setup

Create `.env` file with encryption key to silence warnings:

```bash
ROUTEROS_MCP_ENCRYPTION_KEY=your-32-byte-base64-key-here
```

## Build, Test, Run Commands (All Validated)

### Run Tests

**Fast smoke test (unit only):**

```bash
pytest tests/unit -q
```

- **Time:** ~6 seconds (564 tests)
- **Coverage:** Generates htmlcov/ and coverage.xml
- **Output:** Many warnings about lab encryption_key (expected and safe)
- **Use:** Quick validation before commits

**Full test suite:**

```bash
pytest
```

- **Time:** ~21 seconds (583 tests: 564 unit + 19 e2e)
- **Coverage:** 79.89% overall (targets: 85% overall, 95%+ core modules)
- **Use:** Pre-CI validation

**With verbose output:**

```bash
pytest -v
```

**Specific test file:**

```bash
pytest tests/unit/test_config.py
```

### Linting & Formatting

**Check lint issues (will show many errors):**

```bash
ruff check routeros_mcp tests
```

- **Current baseline:** 164 errors (43 blank-line-with-whitespace, 32 trailing-whitespace, 27 raise-without-from, 15 f-string-missing-placeholders, 14 unused-import, 9 unsorted-imports, others)
- **85 are auto-fixable** with `--fix`

**Auto-fix safe issues:**

```bash
ruff check --fix routeros_mcp tests
```

- **Warning:** This modifies files! Commit or stash changes first
- **Post-fix:** Still expect ~79 unfixable errors (need manual review)

**Check formatting:**

```bash
black --check routeros_mcp tests
```

- **Current state:** Would reformat ~50 files (not enforced in baseline)

**Apply formatting:**

```bash
black routeros_mcp tests
```

**Type checking:**

```bash
mypy routeros_mcp tests
```

- **Current baseline:** 1100 errors in 77 files (no-untyped-def, unused-ignore, etc.)
- **Not blocking:** Improve gradually, focus on new/modified code

### Run Application

**Stdio mode (default, for Claude Desktop):**

```bash
routeros-mcp --config config/lab.yaml
```

- **Protocol:** JSON-RPC over stdin/stdout
- **Logs:** Go to stderr (stdout reserved for protocol)
- **Use:** Local development, MCP Inspector testing

**Debug mode:**

```bash
routeros-mcp --config config/lab.yaml --debug --log-level DEBUG
```

**Show help:**

```bash
routeros-mcp --help
```

### Database Migrations

**Apply migrations (when needed):**

```bash
alembic upgrade head
```

- **Not required** for unit tests (use in-memory SQLite)
- **Required** for integration/e2e tests or running the server

## CI Pipeline (GitHub Actions)

### Workflows

- `.github/workflows/copilot-agent-ci.yml` - Main CI pipeline

  - Triggers: Push to main, all PRs
  - Jobs: `lint-and-typecheck`, `tests`
  - Both depend on: `copilot-setup-steps` (pre-warm)

- `.github/workflows/copilot-setup-steps.yml` - Reusable workflow
  - Runs: `pytest tests/unit -q` (smoke test)
  - Timeout: 45 minutes
  - Python: 3.11 (pinned)

### CI Requirements (What Must Pass)

**lint-and-typecheck job:**

1. `ruff check routeros_mcp tests` (must pass or fail)
2. `black --check routeros_mcp tests` (must pass or fail)
3. `mypy routeros_mcp tests` (must pass or fail)

**tests job:**

1. `pytest` (all tests must pass)

**Current Reality:** CI WILL FAIL on lint/type checks with baseline code (164 ruff errors, 1100 mypy errors, 50 files unformatted)

### Making CI Pass

- **For ruff:** Fix errors in files you touch OR run `ruff check --fix routeros_mcp tests` before commit
- **For black:** Run `black routeros_mcp tests` before commit
- **For mypy:** Add type hints to new code; ignore baseline errors in untouched files
- **For tests:** Ensure new code has tests and all tests pass locally

## Code Standards & Best Practices

### Python Style

- **Line length:** 100 characters max
- **Naming:** snake_case (functions/vars), CamelCase (classes), UPPER_SNAKE_CASE (constants)
- **Type hints:** Required for all new functions/methods
- **Docstrings:** Required for public modules/classes/functions

### Testing Requirements

- **Coverage targets:** 85%+ overall, 95%+ core modules (domain, security, config)
- **Test naming:** `test_<what>_<when>_<expected>` (e.g., `test_get_device_when_not_found_raises_not_found`)
- **Fixtures:** Use existing in `tests/unit/mcp_tools_test_utils.py`, `tests/unit/conftest.py`
- **Mocks:** Prefer existing mocks/stubs before creating new ones

### Commit Messages

Follow conventional commits:

```
<type>(<scope>): <subject>

<body>

<footer>
```

Types: feat, fix, docs, style, refactor, test, chore

### Domain-Driven Design

- **Never call RouterOS clients directly** - Use domain services in `routeros_mcp/domain/services/`
- **Service hierarchy:** MCP tools → domain services → infra (REST/SSH clients)
- **Observability:** Use helpers in `routeros_mcp/infra/observability/` for logging/metrics/tracing

## Common Pitfalls & Workarounds

### Encryption Key Warnings

**Problem:** Many warnings about insecure encryption_key in lab mode
**Solution:** Expected behavior; safe to ignore OR set `ROUTEROS_MCP_ENCRYPTION_KEY` env var

### Stdout vs Stderr Logging

**Problem:** Logs appear on stdout, breaking MCP protocol
**Solution:** Stdio transport forces logging to stderr (handled in `main.py:setup_logging`)

### Test Failures with "initialize_session_manager"

**Problem:** Some tests need session manager initialized
**Solution:** Use `initialize_session_manager` fixture from `tests/unit/conftest.py`

### Ruff Auto-Fix Breaks Tests

**Problem:** `ruff check --fix` might introduce unwanted changes
**Solution:** Always commit/stash before running `--fix`; review diffs carefully

## Key Design Documents (Read These First)

1. `docs/11-implementation-architecture-and-module-layout.md` - Architecture, module structure
2. `docs/17-configuration-specification.md` - Config system, env vars, defaults
3. `docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md` - Testing strategy
4. `docs/04-mcp-tools-interface-and-json-schema-specification.md` - Tool contracts, schemas
5. (Legacy Copilot task file removed)

## Trust These Instructions First

This file is validated with actual command execution (2025-12-15). If instructions seem incomplete or contradictory:

1. Re-read this section carefully
2. Check referenced design docs
3. Only then use search/grep tools

**DO NOT** waste time exploring if the answer is here. These instructions save you 10-15 minutes per task.
