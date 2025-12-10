# Copilot Coding Agent Onboarding – RouterOS MCP

> Short version: this repo is currently a **design-first, code-not-yet-bootstrapped** MCP service. Treat the docs as the source of truth, follow the issue/task files, and use the commands below in the order given once the Python project skeleton exists.

---

## 1. What this repository is

- **Purpose**: Design and implement a **Model Context Protocol (MCP) service** that manages MikroTik RouterOS v7 devices (primarily via REST, with tightly-scoped SSH fallbacks) and exposes safe, well-typed tools/resources/prompts to LLM clients and human operators.
- **Current status (master branch)**: As of late 2025 this branch is **almost entirely design documentation**:
  - 20 numbered design docs under `docs/00-19` (~50k lines) describing architecture, security, persistence, MCP integration, testing, etc.
  - Prompt templates and prompt-design docs under `prompts/`.
  - Implementation is intended to be done via GitHub issues driven by Copilot Agent, guided by:
    - `GITHUB-COPILOT-AGENT-INSTRUCTIONS.md`
    - `GITHUB-COPILOT-TASKS.md`
- **Planned implementation stack** (see `docs/11`, `docs/12`, `docs/13`):
  - **Language**: Python 3.11+ (async-first, fully type-annotated)
  - **Frameworks**: FastAPI, FastMCP SDK, SQLAlchemy 2.x, Alembic
  - **Runtime deps**: httpx, asyncssh, structlog, prometheus-client, OpenTelemetry, authlib, cryptography, apscheduler
  - **Tooling**: `uv` (env & deps), pytest (+pytest-asyncio, pytest-cov), coverage, mypy, ruff, black, tox
  - **External systems**: PostgreSQL 14+, RouterOS v7.10+, OIDC provider (for HTTP/SSE transport)
- **Important reality check**: At the time of writing there is **no `pyproject.toml`, no `routeros_mcp/` package, and no `tests/` directory** in this repo. Many commands in the README/docs are **forward-looking** and will fail until Phase 0 tasks (project skeleton + deps) are implemented.

Always start by confirming whether the implementation has begun:

- If you see `pyproject.toml` and a `routeros_mcp/` package, follow the commands below as **live** instructions.
- If not, you are likely working on an early bootstrap task (T1 / Phase 0.1+). You will be the one introducing those files.

---

## 2. Project layout & key files

**Root directory** (today):

- `README.md` – high-level product overview, architecture summary, aspirational quick-start commands.
- `docs/` – authoritative design specs:
  - `00-09` – requirements, architecture, security, RouterOS integration, observability, operations.
  - `10` – testing & validation strategy (TDD, coverage, sandboxing).
  - `11` – implementation architecture & module layout (defines the `routeros_mcp/` tree you should create).
  - `12` – dev environment, dependencies, common commands.
  - `13` – Python coding standards & conventions.
  - `14-19` – MCP integration, resources/prompts, config spec, DB/ORM spec, JSON-RPC error taxonomy.
- `docs/best_practice/` – meta-guidance for MCP projects and coding agents (worth skimming once).
- `prompts/` – YAML MCP prompt templates:
  - `dns_ntp_rollout.yaml`, `troubleshoot_dns_ntp.yaml` plus `README.md` describing prompt format and intent.
- `GITHUB-COPILOT-AGENT-INSTRUCTIONS.md` – how issues for Copilot Agent are structured and what paths it may touch for each task.
- `GITHUB-COPILOT-TASKS.md` – phased implementation plan (Phase 0–2) with detailed, per-task prompts and acceptance criteria.
- `.env` – **added for you** with placeholder values for `MCP_ENV`, `DATABASE_URL`, `ROUTEROS_MCP_ENCRYPTION_KEY`, and OIDC settings. Replace placeholders with real secrets in your own environment; do not commit real credentials.
- `.whitesource` – Mend/WhiteSource dependency scan configuration (no local command to run; driven by GitHub app/CI when present).
- `.gitignore`, `.git/` – standard VCS files.

**Not present yet (you will likely create these as part of tasks):**

- `pyproject.toml` (or `setup.cfg`) – project/dependency metadata.
- `routeros_mcp/` – main Python package tree described in `docs/11`.
- `tests/` – unit, integration, and E2E tests structured per `docs/10`.
- `.github/workflows/*.yml` – CI workflows. CI expectations are documented in `docs/10` and `docs/12` but workflows themselves haven’t been added.

When adding new structure, keep it consistent with `docs/11`, `docs/16`, and the task you are working on. Avoid inventing new top-level directories unless the docs explicitly allow it.

---

## 3. Environment & commands (what works today vs future state)

### 3.1. Python & tooling

- Verified in this environment:
  - `python3 --version` → Python 3.13.1 (design targets 3.11+, so use 3.11+ features only).
  - `uv --version` → `uv 0.9.10` is installed.
  - `uv venv .venv` from repo root **works** and creates `.venv/`.
- Command that **currently fails** (and why):
  - `uv pip install -e .[dev]` → fails with:
    - `does not appear to be a Python project, as neither pyproject.toml nor setup.py are present` (exit code 2).
  - This is expected until you add `pyproject.toml` (T1/Phase 0.1).

**Always**:

1. Create/refresh a virtualenv at the repo root (once):
   - `uv venv .venv`
2. Activate it before running Python commands (outside of `uv run`):
   - `source .venv/bin/activate` (on Linux/macOS bash).
3. Once `pyproject.toml` exists, **always run**:
   - `uv pip install -e .[dev]`
   - Do this after editing dependencies or pulling a branch that changed `pyproject.toml`.

### 3.2. Build / run commands (expected once code exists)

The following commands are defined in `README.md` and `docs/12`. They are **not runnable yet** but should be implemented and used exactly as written once the skeleton is in place:

- **Run FastAPI admin/health API (dev):**
  - `uv run uvicorn routeros_mcp.api.http:create_app --factory --reload`
- **Run MCP server (stdio, for Claude Desktop / MCP Inspector):**
  - `uv run python -m routeros_mcp.mcp.server`
- **Run MCP server (HTTP/SSE):**
  - `uv run python -m routeros_mcp.mcp.server --transport http --port 8080`
- **Run combined entrypoint (API + MCP, config-driven):**
  - `uv run python -m routeros_mcp.main`
- **Environment variables typically required:**
  - `MCP_ENV` (e.g., `lab|staging|prod`)
  - `DATABASE_URL` (PostgreSQL URL; tests may use SQLite in-memory)
  - `MCP_TRANSPORT_MODE` (`stdio` or `http`)
  - `MCP_HTTP_PORT` (e.g., `8080` for HTTP mode)
  - `ROUTEROS_MCP_ENCRYPTION_KEY` (Fernet key for credential encryption)
  - OIDC-related vars when HTTP auth is enabled: `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_AUDIENCE`.

Treat these as **hard preconditions** for running anything that touches the DB or RouterOS. Prefer loading them from `.env` during local development.

### 3.3. Test, lint, type-check (future state expectations)

Once `pyproject.toml`, `routeros_mcp/`, and `tests/` exist, the standard validation pipeline should be:

- **Unit & integration tests** (pytest):
  - `uv run pytest` (all tests)
  - `uv run pytest --cov=routeros_mcp --cov-report=html` (coverage)
- **Orchestrated via tox** (as recommended):
  - `uv run tox` (all envs)
  - `uv run tox -e py` (unit tests only)
  - `uv run tox -e lint` (ruff)
  - `uv run tox -e type` (mypy)
  - `uv run tox -e cov` (coverage gate; CI should enforce this)
- **Static analysis & formatting**:
  - `uv run ruff check routeros_mcp`
  - `uv run black routeros_mcp`
  - `uv run mypy routeros_mcp`

From `docs/10` and `docs/13`:

- Target **≥ 85% overall coverage**, with **100%** for designated core modules.
- TDD is required: write failing tests first, then minimal implementation, then refactor.

As of the current repo state, these commands will fail because there is no `tests/` folder and no deps configured. When you introduce them, wire the commands exactly as above and add CI workflows that run at least `tox -e cov lint type` on every PR.

### 3.4. MCP-specific validation (future state)

When MCP server code exists, additional high-value checks (from `docs/12`):

- Validate tool schemas:
  - `uv run python -m routeros_mcp.mcp.validate_tools`
- Generate tool catalog JSON:
  - `uv run python -m routeros_mcp.mcp.generate_catalog --output dist/mcp-tools.json`
- Test protocol/E2E behaviour:
  - `uv run pytest tests/e2e/test_mcp_protocol.py -v`
  - `npm install -g @modelcontextprotocol/inspector` then
  - `mcp-inspector "uv run python -m routeros_mcp.mcp.server"`

These commands are design commitments; implement them as you build the MCP layer.

---

## 4. CI, validation, and safety expectations

- There is **no `.github/workflows/` directory yet**. When adding CI, align with `docs/10` and `docs/12`:
  - Install deps via `uv pip install -e .[dev]`.
  - Run `uv run tox -e lint,type,py,cov`.
  - Fail the build if coverage or type-checking thresholds are not met.
- Security & safety:
  - All clients (including LLMs) are treated as untrusted. Enforce server-side checks for roles, device capabilities, and environment (`lab` vs `prod`).
  - Never log plaintext passwords, API keys, or RouterOS credentials. Use `ROUTEROS_MCP_ENCRYPTION_KEY` for encryption at rest.
  - For RouterOS operations, prefer mocks/fakes in tests and lab devices for E2E; **never** hardcode lab credentials into the repo.

---

## 5. How to work efficiently as a coding agent

1. **Start with the task file, not a random search**

   - For any new issue, read the relevant section of `GITHUB-COPILOT-TASKS.md` or `GITHUB-COPILOT-AGENT-INSTRUCTIONS.md` first.
   - These files specify allowed paths, acceptance criteria, and which design docs to consult.

2. **Use the design docs as authoritative specs**

   - For architecture and layout: `docs/11`, `docs/16`.
   - For config and env vars: `docs/17`, `docs/12`.
   - For DB/ORM: `docs/05`, `docs/18`.
   - For MCP protocol: `docs/04`, `docs/14`, `docs/19`.
   - For coding style, tests, and TDD: `docs/10`, `docs/13`.

3. **Trust this instructions file before exploring**

   - Assume the commands and layouts described here are correct.
   - Only reach for `grep`, `find`, or wide code search when:
     - You are wiring into existing Python modules that are not yet documented here, or
     - You discover a concrete mismatch between this file and reality (e.g., a command or path has been renamed).

4. **Validation workflow for any non-trivial change (once code exists)**

   - Ensure `.venv` exists and dependencies are installed.
   - Run the narrowest tests first (e.g., `pytest tests/unit/...`), then broader suites.
   - Run ruff, mypy, and black as part of your change before opening a PR.
   - For MCP-related changes, run protocol/E2E tests and, where feasible, validate with MCP Inspector in addition to unit tests.

5. **Be environment- and risk-aware**
   - Respect environment semantics (`MCP_ENV` lab/staging/prod) and tool tiers (fundamental/advanced/professional).
   - When writing or modifying tools that perform RouterOS writes, follow the safeguards from `docs/07` and ensure tests cover failure modes (timeouts, unreachable devices, auth errors).

If you follow this file plus the task-specific instructions, you should very rarely need exploratory shell commands or ad-hoc searches. Treat discrepancies you find as bugs either in your branch or in this file and document them clearly in your PR description.
