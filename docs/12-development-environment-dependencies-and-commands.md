# Development Environment, Dependencies & Common Commands

## Purpose

Describe the recommended development environment, external dependencies, and common commands for working on the RouterOS MCP service implementation. The preferred tool for managing Python environments and dependencies is [`uv`](https://github.com/astral-sh/uv).

---

## Language and runtime

- Python 3.11+  
- Recommended local setup with `uv`:
  - Install `uv` (see official docs).  
  - Create and activate a virtual environment:

    ```bash
    uv venv .venv
    source .venv/bin/activate  # Unix
    # or .venv\Scripts\activate on Windows
    ```

  - Install dependencies once a `pyproject.toml` exists:

    ```bash
    uv pip install -e .[dev]
    ```

- Alternatively, standard `venv` + `pip` can be used if `uv` is not available.

---

## Python dependencies

### Dependency Selection Philosophy

**Priority: Popular, well-maintained packages with wide community adoption.**

- Prefer high-level, batteries-included solutions over low-level libraries
- Use official/canonical packages where they exist
- Choose packages with active maintenance (recent commits, issue responses)
- Avoid obscure or abandoned packages
- Include fallback options where appropriate

### Core MCP Integration

- **`fastmcp`** (≥0.1.0) – Official Python MCP SDK with zero-boilerplate tool registration
  - Provides automatic schema generation from type hints
  - Handles MCP protocol lifecycle (initialization, discovery, execution)
  - Supports both stdio and HTTP/SSE transports
  - Maintained by Model Context Protocol team
  - Alternative: Could use lower-level `mcp` package, but `fastmcp` is recommended

### Core runtime

- **`fastapi`** (≥0.109.0) – Modern, fast web framework with automatic API docs
  - Industry standard for Python async web APIs
  - Excellent type hint support and validation via Pydantic
  - Built-in OpenAPI/Swagger documentation
  - Extremely popular (74k+ GitHub stars, very active)

- **`uvicorn[standard]`** (≥0.27.0) – Lightning-fast ASGI server
  - Reference implementation for ASGI servers
  - Recommended by FastAPI documentation
  - Includes uvloop and httptools for performance
  - Alternative: `hypercorn` for HTTP/2 support if needed

- **`pydantic`** (≥2.5.0) – Data validation using Python type hints
  - V2 offers significant performance improvements over V1
  - Used by FastAPI, FastMCP, and many other major projects
  - Industry standard for Python data validation
  - Excellent JSON schema generation

- **`httpx`** (≥0.26.0) – Modern async/sync HTTP client
  - Successor to `requests` with async support
  - Excellent connection pooling and timeout handling
  - Well-maintained by Encode (same team as FastAPI)
  - Alternative: `aiohttp` if specific features needed, but httpx preferred for consistency

- **`asyncssh`** (≥2.14.0) – Async SSH client library
  - Pure Python asyncio SSH client/server
  - Well-maintained with regular updates
  - Comprehensive SSH feature support
  - Alternative: `paramiko` (sync only) as fallback, but asyncssh preferred for async/await

### Persistence

- **`sqlalchemy[asyncio]`** (≥2.0.25) – SQL toolkit and ORM
  - Industry standard Python ORM
  - V2 offers modern async support
  - Excellent documentation and community
  - Type stub support for mypy
  - Very actively maintained (SQLAlchemy is the reference ORM)

- **`asyncpg`** (≥0.29.0) – Fast PostgreSQL async driver
  - Fastest PostgreSQL driver for Python
  - Native support for PostgreSQL types and features
  - Preferred over psycopg for async workloads
  - Fallback: `psycopg[binary]` (≥3.1.0) for sync or if asyncpg has issues
    - Note: Use `psycopg` v3+, not old `psycopg2-binary`

- **`alembic`** (≥1.13.0) – Database migration tool
  - Official migration tool for SQLAlchemy
  - Industry standard for schema migrations
  - Excellent autogenerate capabilities
  - Well-maintained by SQLAlchemy team

### Observability

- **`structlog`** (≥24.1.0) – Structured logging for humans
  - Industry standard for structured logging in Python
  - Excellent integration with standard library logging
  - Powerful processors for log enrichment
  - Better than JSON-formatter for structured output
  - Fallback: Standard library `logging` with `python-json-logger` if structlog unavailable

- **`prometheus-client`** (≥0.20.0) – Prometheus metrics client
  - Official Python client for Prometheus
  - Reference implementation maintained by Prometheus team
  - Excellent integration with FastAPI
  - Industry standard for metrics

- **`opentelemetry-api`** (≥1.22.0) – OpenTelemetry API
- **`opentelemetry-sdk`** (≥1.22.0) – OpenTelemetry SDK
- **`opentelemetry-instrumentation-fastapi`** (≥0.43b0) – FastAPI auto-instrumentation
- **`opentelemetry-instrumentation-httpx`** (≥0.43b0) – HTTPX auto-instrumentation
- **`opentelemetry-instrumentation-sqlalchemy`** (≥0.43b0) – SQLAlchemy auto-instrumentation
  - OpenTelemetry is CNCF standard for observability
  - Vendor-neutral tracing and metrics
  - Excellent Python support and auto-instrumentation
  - Wide industry adoption

### Background jobs and scheduling

- **`apscheduler`** (≥3.10.0) – Advanced Python scheduler
  - Industry standard for Python job scheduling
  - Supports cron-like scheduling, interval-based, and date-based triggers
  - Async support built-in
  - Persistent job stores (DB-backed)
  - Alternative: `celery` for distributed task queue (Phase 4+), but APScheduler sufficient for single-instance

### Configuration and secrets

- **`pydantic-settings`** (≥2.1.0) – Settings management using Pydantic
  - Official settings extension for Pydantic v2
  - Automatic environment variable loading
  - Excellent validation and type safety
  - Replaces deprecated `BaseSettings` in pydantic core

- **`python-dotenv`** (≥1.0.0) – Load environment variables from .env files
  - Standard tool for development environment configuration
  - Well-maintained, simple, and reliable
  - Good integration with pydantic-settings

- **`pyyaml`** (≥6.0.1) – YAML parser and emitter
  - Industry standard for YAML parsing
  - Used for YAML configuration file support
  - Required by config.py for load_settings_from_file()
  - Alternative: `ruamel.yaml` for advanced YAML features

- **`tomli`** (≥2.0.1) – TOML parser (Python 3.11+)
  - Standard library in Python 3.11+ (tomllib)
  - Used for TOML configuration file support
  - Required by config.py for load_settings_from_file()
  - Note: Use built-in `tomllib` on Python 3.11+, tomli as backport

### Security and cryptography

- **`cryptography`** (≥41.0.0) – Cryptographic recipes and primitives
  - Industry standard Python cryptography library
  - PyCA (Python Cryptographic Authority) maintained
  - Used by most other security libraries
  - Excellent for encrypting RouterOS credentials at rest

- **`authlib`** (≥1.3.0) – OAuth/OIDC client and server library
  - Most comprehensive OAuth/OIDC library for Python
  - Supports OAuth 2.1, OIDC, JWT
  - Excellent FastAPI integration
  - Well-maintained by Authlib organization
  - Alternative: `python-jose` for JWT only, but Authlib more complete

### Testing and developer tooling

- **`pytest`** (≥8.0.0) – Testing framework
  - Industry standard Python testing framework
  - Extremely popular and well-maintained
  - Rich plugin ecosystem

- **`pytest-asyncio`** (≥0.23.0) – Async test support for pytest
  - Official pytest plugin for async tests
  - Essential for testing async/await code
  - Well-maintained

- **`pytest-cov`** (≥4.1.0) – Coverage plugin for pytest
  - Official pytest coverage plugin
  - Uses `coverage.py` underneath
  - Industry standard for Python coverage

- **`coverage[toml]`** (≥7.4.0) – Code coverage measurement
  - Reference implementation for Python coverage
  - Excellent reporting and configuration
  - Supports pyproject.toml configuration

- **`mypy`** (≥1.8.0) – Static type checker
  - Reference implementation for Python type checking
  - Maintained by Python core developers
  - Industry standard for Python typing
  - Excellent IDE integration

- **`ruff`** (≥0.2.0) – Extremely fast Python linter
  - Modern replacement for flake8, isort, and many other tools
  - 10-100x faster than alternatives
  - Actively developed by Astral (same team as uv)
  - Replacing multiple older tools (flake8, pylint, isort, etc.)
  - Note: Can also format (replacing black), but black still preferred for now

- **`black`** (≥24.1.0) – Uncompromising code formatter
  - Industry standard Python formatter
  - Used by most major Python projects
  - Eliminates formatting debates
  - Note: Ruff formatter is emerging alternative, but black is more established

- **`tox`** (≥4.12.0) – Test automation and standardization
  - Industry standard for test automation
  - Manages multiple test environments
  - Excellent CI/CD integration
  - Supports pyproject.toml configuration

### Development tools

- **`uv`** (≥0.1.0) – Ultra-fast Python package installer and resolver
  - Modern replacement for pip with 10-100x speedup
  - Drop-in pip replacement
  - Maintained by Astral (same team as ruff)
  - Rapidly gaining adoption in Python community
  - Note: Still use pip as fallback if uv unavailable, but uv strongly recommended

- **`ipython`** (≥8.20.0) – Enhanced interactive Python shell
  - Industry standard interactive shell
  - Excellent for debugging and exploration
  - Rich syntax highlighting and autocompletion

### Optional: Enhanced development experience

- **`rich`** (≥13.7.0) – Rich text and formatting in terminal
  - Beautiful terminal output
  - Excellent for CLI tools and logging enhancement
  - Can integrate with structlog for colored output
  - Popular and well-maintained

- **`typer`** (≥0.9.0) – Build CLI applications
  - Modern CLI framework from FastAPI creator
  - If building CLI tools for MCP management
  - Excellent type hint support
  - Alternative: `click` (more established, but typer is more modern)

---

## Suggested project layout

The implementation should follow the module layout described in `docs/11-implementation-architecture-and-module-layout.md` under a top-level package `routeros_mcp/`.

In addition, a `pyproject.toml` or `setup.cfg` should:

- Declare the package `routeros_mcp`.  
- Group dependencies into:
  - `main` (runtime).  
  - `dev` (testing, linting, formatting).

---

## Common development commands

These commands assume:

- A virtual environment is created and activated (preferably using `uv venv`).  
- Dependencies are installed with `uv pip install -e .[dev]` once a proper `pyproject.toml`/`setup.cfg` exists.

### Environment setup (with `uv`)

```bash
uv venv .venv
source .venv/bin/activate  # Unix
uv pip install -e .[dev]
```

### Running the application (development)

Run the FastAPI app with Uvicorn:

```bash
uv run uvicorn routeros_mcp.api.http:create_app --factory --reload
```

This starts the HTTP API for admin and health/metrics endpoints. The MCP server component may be started as:

```bash
uv run python -m routeros_mcp.api.mcp_server
```

### Database migrations

Assuming Alembic is configured:

```bash
uv run alembic upgrade head      # Apply migrations
uv run alembic revision --autogenerate -m "Describe change"  # Create a new migration
```

### Running tests

```bash
uv run pytest
uv run pytest --cov=routeros_mcp
```

Using `tox` to orchestrate environments (once `tox` is configured):

```bash
uv run tox           # run all configured envs
uv run tox -e py     # run unit tests
uv run tox -e lint   # run ruff
uv run tox -e type   # run mypy
uv run tox -e cov    # run tests with coverage
```

CI pipelines should run the coverage-focused environment (for example `tox -e cov`) and enforce the coverage thresholds defined in `docs/13-python-coding-standards-and-conventions.md` (baseline ≥ 85% overall, with selected core modules configured for 100%).

### Static analysis and formatting

```bash
uv run ruff check routeros_mcp
uv run black routeros_mcp
uv run mypy routeros_mcp
```

### Local health checks

After starting the service, you should be able to:

- Hit a health endpoint (to be defined, e.g. `/health`) to validate the app is up.  
- Hit a metrics endpoint (e.g. `/metrics`) to see Prometheus metrics.
