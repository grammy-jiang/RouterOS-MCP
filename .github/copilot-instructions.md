# Copilot Coding Agent Onboarding (RouterOS-MCP)

## What this repo is

- Model Context Protocol (MCP) service to manage MikroTik RouterOS v7 devices with safe, role-aware tools/resources/prompts. Python 3.11+ stack using FastMCP, FastAPI/Starlette, SQLAlchemy/Alembic, asyncssh/httpx, structlog/OpenTelemetry, APScheduler.
- Repo is documentation-heavy (docs/00–19 ~20 design specs), with a sizable Python codebase plus extensive tests (unit/e2e) under `tests/`. Entry script is `routeros-mcp` -> `routeros_mcp.main:main` (stdio MCP server today; HTTP/SSE planned).

## Layout quick map

- Root: `pyproject.toml` (dependencies + tool configs for pytest/coverage/mypy/ruff/black), `README.md`, `CONTRIBUTING.md`, `PHASE1_IMPLEMENTATION_OVERVIEW.md`, `GITHUB-COPILOT-TASKS.md`, `GITHUB-COPILOT-AGENT-INSTRUCTIONS.md`, `alembic/` (env + versions), `config/` (sample `lab.yaml`), `.github/workflows/` (CI), `docs/` (design), `tests/` (unit/e2e), `routeros_mcp/` (source).
- Source highlights: `routeros_mcp/config.py` (pydantic settings), `cli.py` (arg parsing), `main.py` (startup), `domain/` (services), `infra/` (db, observability, routeros clients), `mcp/` (server, protocol, transports), `mcp_tools/`, `mcp_resources/`, `mcp_prompts/`, `security/`.
- Config priority: defaults < config file (YAML/TOML) < env vars (prefix `ROUTEROS_MCP_`) < CLI args. Lab env autogenerates an insecure encryption key; staging/prod require `encryption_key` (set `ROUTEROS_MCP_ENCRYPTION_KEY`). HTTP transport in prod without OIDC raises warnings.

## Setup (validated)

- Python 3.11 recommended; works with pyenv/uv or system Python. Virtualenv advised (`uv venv .venv && source .venv/bin/activate`).
- Install deps once: `python -m pip install -e .[dev]` (validated 2025-12-11 on Linux).
- Optional: `.env` with `ROUTEROS_MCP_ENCRYPTION_KEY` to avoid warnings when using staging/prod.

## Run & validate

- Smoke tests (fast, ran 2025-12-11 on Linux, py3.13): `pytest tests/unit -q` → **pass** in ~20s with many warnings about lab encryption_key fallback; coverage HTML/XML generated.
- Full tests: `pytest` (CI runs this; expect longer). Coverage configured in `pyproject.toml`.
- CLI: `routeros-mcp --config config/lab.yaml` runs stdio MCP server (stdout reserved for protocol; logs on stderr). Use `--debug/--log-level DEBUG` for verbose output.
- Lint/type: CI runs `ruff check routeros_mcp tests`, `black --check routeros_mcp tests`, `mypy routeros_mcp tests`. Current baseline **fails ruff** (70 errors: unsorted imports, trailing whitespace, unused imports, missing helper `initialize_session_manager`, etc.). Plan to fix lint issues in touched areas or run with `--fix` where safe before submitting; otherwise expect CI failure.
- DB migrations: Alembic configured; `uv run alembic upgrade head` when DB is needed (not required for unit smoke).

## CI expectations

- `.github/workflows/copilot-agent-ci.yml`: on PR/push → job `lint-and-typecheck` (Python 3.11, pip editable install, ruff, black --check, mypy) and job `tests` (pytest). Both depend on `copilot-setup-steps` reusable workflow.
- `.github/workflows/copilot-setup-steps.yml`: pre-warm step runs `pytest tests/unit -q`.
- Assume CI requires clean lint/type/test unless noted; address ruff issues to avoid red pipelines.

## Tips to work efficiently

- Start from relevant design docs: `docs/11-implementation-architecture-and-module-layout.md` (structure), `docs/17-configuration-specification.md` (settings), `docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md` (testing goals). Tasks curated in `GITHUB-COPILOT-TASKS.md` and `GITHUB-COPILOT-AGENT-INSTRUCTIONS.md`.
- For settings-sensitive tests, set `ROUTEROS_MCP_ENCRYPTION_KEY` when using `environment=staging/prod`; default lab uses insecure key and emits warnings.
- Logging: stdio transport must keep stdout protocol-clean; log to stderr.
- Tests/fixtures live under `tests/unit`; many mocks/stubs are available (e.g., `tests/unit/mcp_tools_test_utils.py`). Use these before writing new ones.
- Observability utilities in `routeros_mcp/infra/observability/`; RouterOS REST/SSH clients in `routeros_mcp/infra/routeros/`; domain services under `routeros_mcp/domain/services/` provide abstractions—prefer calling services over direct client use.
- Trust this file first; only search further if instructions are missing or contradictory.
