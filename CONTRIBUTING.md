# Contributing to RouterOS MCP Service

Thank you for your interest in contributing to the RouterOS MCP Service! This guide will help you set up your development environment and understand our development workflow.

## Prerequisites

- Python 3.11 or later
- Git
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

## Development Environment Setup

### 1. Clone the Repository

```bash
git clone https://github.com/grammy-jiang/RouterOS-MCP.git
cd RouterOS-MCP
```

### 2. Create a Virtual Environment

Using `uv` (recommended):

```bash
uv venv .venv
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

Using standard Python:

```bash
python -m venv .venv
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows
```

### 3. Install Dependencies

Using `uv`:

```bash
uv pip install -e .[dev]
```

Using pip:

```bash
pip install -e .[dev]
```

This installs the package in editable mode with all development dependencies.

## Development Workflow

### Running the CLI

Test the CLI with the example lab configuration:

```bash
routeros-mcp --config config/lab.yaml
```

Or with command-line overrides:

```bash
routeros-mcp --debug --log-level DEBUG
```

See [**Configuration Specification**](docs/17-configuration-specification.md) for all available settings, environment variables, and CLI arguments.

### Running Tests

**Test-Driven Development (TDD) is mandatory** – write tests before implementation, follow red-green-refactor cycle.

Quick feedback (unit tests only, ~6 seconds):

```bash
uv run pytest tests/unit -q
```

Full test suite with coverage (~21 seconds):

```bash
uv run pytest
```

With coverage report (HTML):

```bash
uv run pytest --cov=routeros_mcp --cov-report=html
```

Run specific test file:

```bash
uv run pytest tests/unit/test_config.py
```

Run specific test (verbose):

```bash
uv run pytest -v tests/unit/test_config.py::test_load_config_from_yaml
```

**Coverage Targets:**
- **Overall**: 85%+ (currently 80%+)
- **Core modules** (domain, security, config): 95%+
- **Authorization logic**: 100% (single-line bugs can be catastrophic)

See [**Testing & Validation Strategy**](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md) for TDD workflow, test patterns, and sandbox environment setup.

### Code Quality Checks

#### Type Checking with mypy

```bash
mypy routeros_mcp
```

**Note:** Current baseline has 1100+ errors in untouched code. Focus on new/modified code; gradually improve legacy code.

#### Linting with ruff

Check for issues:

```bash
ruff check routeros_mcp tests
```

Auto-fix safe issues (commit first!):

```bash
ruff check --fix routeros_mcp tests
```

**Note:** Current baseline has ~164 errors; ~85 are auto-fixable. See [**Python Coding Standards**](docs/13-python-coding-standards-and-conventions.md) for style guide.

#### Code Formatting with black

Check formatting:

```bash
black --check routeros_mcp tests
```

Apply formatting:

```bash
black routeros_mcp tests
```

#### Pre-Commit Workflow

Before pushing:

```bash
# Auto-fix + format (review diffs!)
ruff check --fix routeros_mcp tests
black routeros_mcp tests

# Type check new code
mypy routeros_mcp

# Run tests
uv run pytest
```

## Code Standards

### Python Style

- **Line length**: 100 characters max
- **Naming conventions**:
  - `snake_case` for functions, variables, and module names
  - `CamelCase` for classes and exception types
  - `UPPER_SNAKE_CASE` for module-level constants
- **Type hints**: Required for all new functions and methods (use `Optional[]`, `Union[]`, async context managers)
- **Docstrings**: Required for all public modules, classes, and functions (Google style preferred)
- **Imports**: Organize as `builtin` → `stdlib` → `third-party` → `local` (use `isort` config in `pyproject.toml`)

See [**Python Coding Standards & Conventions**](docs/13-python-coding-standards-and-conventions.md) for detailed style guide and examples.

### Testing

- Write tests **before** implementation (TDD: red-green-refactor)
- **Test naming**: `test_<what>_<when>_<expected>` (e.g., `test_device_add_when_invalid_environment_raises_validation_error`)
- **Fixtures**: Use existing fixtures in `tests/unit/conftest.py` (e.g., `initialize_session_manager`, `app`)
- **Mocks**: Prefer existing mocks in `tests/unit/mcp_tools_test_utils.py` before creating new ones
- **Coverage**: Ensure all branches of new code are tested; use `--cov` to measure
- **Organization**: Unit tests for functions, E2E tests for tool workflows

Example test structure:

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_device_registration_when_invalid_environment_raises_error(app):
    \"\"\"Device registration should reject invalid environment values.\"\"\"
    device_service = app.state.device_service
    
    with pytest.raises(ValidationError, match="environment must be"):
        await device_service.register_device(
            name="test",
            management_address="192.168.1.1:443",
            environment="invalid",  # Should fail
            credentials={"username": "admin", "password": "test"}
        )
```

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat` – New feature
- `fix` – Bug fix
- `docs` – Documentation changes (design docs, README, etc.)
- `style` – Code style changes (formatting, no logic change)
- `refactor` – Code refactoring without behavior change
- `test` – Test additions or updates
- `chore` – Maintenance tasks (deps, CI config, etc.)

**Example:**

```
feat(config): add support for TOML configuration files

Implement TOML file loading in load_settings_from_file function.
Add comprehensive tests for TOML parsing with nested sections.
Update README with TOML example.

Closes #123
```

## Project Structure

```
RouterOS-MCP/
├── pyproject.toml              # Project metadata, dependencies, tool configs
├── alembic/                    # Database migrations
├── config/                     # Example configurations (lab, production)
│   ├── lab.yaml                # Development environment config (STDIO, SQLite)
│   └── http_lab.yaml           # HTTP/SSE dev config
├── docs/                       # 24+ comprehensive design documents
│   ├── 00-requirements-*.md    # Scope, goals, phased roadmap
│   ├── 01-overall-system-*.md  # High-level architecture
│   ├── 02-security-*.md        # Threat model, OAuth, RBAC
│   ├── 04-mcp-tools-*.md       # Tool catalog and JSON schemas
│   ├── 10-testing-*.md         # TDD strategy, test organization
│   ├── 12-development-*.md     # Setup, dependencies, uv workflow
│   └── ...                      # Full specification suite
├── routeros_mcp/               # Main package
│   ├── config.py              # Pydantic Settings (priority: defaults → YAML → env → CLI)
│   ├── cli.py                 # Argument parsing and config loading
│   ├── main.py                # App startup, MCP server init, transport selection
│   ├── domain/                # Business logic (services by capability area)
│   │   ├── models.py          # SQLAlchemy ORM (Device, Job, Plan, AuditEvent)
│   │   └── services/          # device, system, interface, ip, dns_ntp, firewall, dhcp, bridge, wireless, routing, etc.
│   ├── infra/                 # Infrastructure layer
│   │   ├── db/                # SQLAlchemy session management
│   │   ├── observability/     # Logging (structlog), metrics, tracing
│   │   └── routeros/          # REST client (httpx) and SSH client (asyncssh)
│   ├── mcp/                   # MCP protocol implementation
│   │   ├── server.py          # FastMCP server with tool/resource/prompt registration
│   │   ├── protocol/          # JSON-RPC protocol handling
│   │   └── transport/         # STDIO and HTTP/SSE transport layers
│   ├── mcp_tools/             # 66 MCP tool implementations (by capability area)
│   ├── mcp_resources/         # 12+ MCP resource providers
│   └── mcp_prompts/           # 8 Jinja2 prompt templates
├── tests/
│   ├── unit/                  # 564 unit tests (domain, config, utils)
│   ├── e2e/                   # 19 end-to-end tool workflow tests
│   └── conftest.py            # Shared fixtures
└── README.md                  # User-facing project overview
```

See [**Implementation Architecture & Module Layout**](docs/11-implementation-architecture-and-module-layout.md) for detailed module descriptions and class hierarchies.

## Deployment & Operations

### STDIO (Development)

For local development with Claude Desktop:

```bash
routeros-mcp --config config/lab.yaml
```

### HTTP/SSE (Production)

For remote clients and multi-user deployments:

```bash
routeros-mcp --config config/prod.yaml
```

**Requirements:**
- **Database:** PostgreSQL 14+ (replaces SQLite; allows stateless horizontal scaling)
- **Transport:** HTTPS with TLS 1.3+ (self-signed or public CA certificates)
- **Authentication:** OAuth 2.1/OIDC provider
  - [Azure AD Setup](docs/21-oauth-setup-azure-ad.md)
  - [Okta Setup](docs/22-oauth-setup-okta.md)
  - [Auth0 Setup](docs/23-oauth-setup-auth0.md)
- **Reverse Proxy:** nginx, HAProxy, or Cloudflare Tunnel for load balancing

**Features:**
- Server-Sent Events (SSE) for streaming tool outputs and real-time health updates
- Horizontal scaling with shared PostgreSQL session store
- Cloudflare Tunnel support for outbound-only connectivity
- Per-user device scopes and RBAC (Phase 5)
- Mandatory approval tokens for professional-tier operations

See [**HTTP/SSE Deployment Guide**](docs/20-http-sse-transport-deployment-guide.md), [**Admin CLI Reference**](docs/ADMIN_CLI.md), and [**Operations Runbook**](docs/09-operations-deployment-self-update-and-runbook.md) for detailed setup, command reference, and production monitoring.

## Documentation Standards

All design decisions are documented in the `docs/` directory. When making significant changes:

1. **Review relevant specs** – Check design documents (especially Phase documents and implementation specs) before major changes
2. **Update docs on behavior change** – If implementation changes expected behavior, update related design docs
3. **Add design docs for features** – Major features (new capability area, new tier, new transport) need a design document
4. **Link from code** – Code comments should link to relevant design docs (e.g., "See docs/02-... for authorization model")
5. **Keep examples current** – README, ARCHITECTURE.md, CONTRIBUTING.md examples must reflect actual working commands

## Questions or Issues?

- Check existing issues: https://github.com/grammy-jiang/RouterOS-MCP/issues
- Open a new issue for bugs or feature requests
- Discuss in pull request comments

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
