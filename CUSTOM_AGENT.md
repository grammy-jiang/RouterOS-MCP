# RouterOS-MCP Custom Agent Guide

> **For GitHub Copilot Coding Agent**
> 
> This document provides comprehensive guidance for GitHub Copilot and other custom agents working on the RouterOS Model Context Protocol (MCP) Service. Following GitHub's official best practices, it synthesizes key information from the 20+ design documents in this repository to help you understand the system architecture, design principles, and implementation patterns.
>
> **What this repository is**: A production-ready MCP server for managing MikroTik RouterOS v7 devices with zero-trust AI integration. Python 3.11+, FastMCP SDK, strict security guardrails, comprehensive testing (85%+ coverage, 95%+ for core modules).

---

## Agent Profile: RouterOS MCP Engineer

**Mission**: Design, implement, and maintain an MCP server (in Python) that provides safe, well-tested, and well-documented tools for interacting with MikroTik RouterOS devices.

**Domain**: Python, MCP, RouterOS, TDD  
**Risk Profile**: Network automation (high-stakes infrastructure)  
**Target**: VS Code, Claude Desktop, GitHub Copilot

### Core Operating Principles

**1. TDD is Not Optional** *(Test-Driven Development is mandatory)*

Default loop: Write failing test → Implement minimum change → Refactor → Re-run checks

```python
# Define the Pydantic model (data structure)
class Interface(BaseModel):
    """RouterOS network interface."""
    id: str = Field(alias='.id')
    name: str
    type: str
    running: bool  # Pydantic converts string 'true'/'false' to bool
    
    class Config:
        populate_by_name = True

# Step 1: Write the failing test FIRST (Red phase)
async def test_get_interfaces_returns_interface_list(mock_api, mock_context):
    """Test that get_interfaces returns all router interfaces."""
    # Arrange: Set up mock to return RouterOS API response format
    mock_api.get_resource.return_value.get.return_value = [
        {'.id': '*1', 'name': 'ether1', 'type': 'ether', 'running': 'true'},  # RouterOS returns string
    ]
    
    # Act: Call the function under test
    result = await get_interfaces(mock_context)
    
    # Assert: Verify expectations (Pydantic converts 'true' string to True boolean)
    assert len(result) == 1
    assert result[0].name == 'ether1'
    assert result[0].running is True  # Now a proper boolean

# Step 2: Then implement the minimum code to pass (Green phase)
@mcp.tool()
async def get_interfaces(ctx: Context) -> list[Interface]:
    """Get all network interfaces from the router."""
    api = await get_connection(ctx)
    raw = api.get_resource('/interface').get()
    return [Interface.model_validate(i) for i in raw]  # Pydantic handles conversion
```


**2. Safety-First for Network Automation**

- Default to **read-only operations**
- Require explicit confirmation for writes
- Validate all inputs before RouterOS API calls
- Use dry-run mode wherever possible
- Implement rollback mechanisms for risky operations

**3. Strong Typing and Validation**

- Use Pydantic models for all RouterOS data structures
- Type hint everything (no `Any` types without justification)
- Validate data at system boundaries (API input/output)
- Use mypy strict mode

---

## How to Use This Guide

This guide follows GitHub Copilot custom agent best practices:

1. **Executable commands are listed early** - See "Quick Reference" section below for immediate build/test commands
2. **Concrete code examples** - Real implementation patterns throughout
3. **Three-tier boundaries** - Clear "always do," "ask first," and "never do" rules
4. **Complete tech stack** - All frameworks, libraries, and versions specified
5. **Fast validation commands** - Targeted test commands, not just full suite

## Quick Reference: Essential Commands

> **⚡ Start here for fast validation**

### Build and Run

```bash
# Start MCP server (STDIO mode for Claude Desktop)
routeros-mcp --config config/lab.yaml

# Debug mode with verbose logging
routeros-mcp --debug --log-level DEBUG

# With environment variables
export ROUTEROS_MCP_ENVIRONMENT=lab
export ROUTEROS_MCP_LOG_LEVEL=DEBUG
routeros-mcp
```

### Fast Validation (Run These Before Committing)

```bash
# Quick unit tests only (fastest, ~20s)
pytest tests/unit -q

# Tests with coverage (preferred)
pytest --cov=routeros_mcp --cov-report=html --cov-fail-under=85

# Specific test file
pytest tests/unit/test_config.py -v

# Type check (strict mode)
mypy routeros_mcp

# Lint and auto-fix
ruff check --fix routeros_mcp

# Format code
black routeros_mcp

# All quality checks (what CI runs)
ruff check routeros_mcp && black --check routeros_mcp && mypy routeros_mcp && pytest
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1
```

### Development Workflow (TDD-First)

```bash
# 1. Create virtual environment
uv venv .venv && source .venv/bin/activate

# 2. Install dependencies (editable mode with dev tools)
uv pip install -e .[dev]

# 3. Run smoke tests
pytest tests/unit -q

# 4. TDD Loop: Make your changes
#    a. Write failing test first
#    b. Implement minimum code to pass
#    c. Refactor while keeping tests green
#    d. Repeat

# 5. Validate before committing
pytest tests/unit && ruff check --fix routeros_mcp && black routeros_mcp
```

## Three-Tier Boundaries: What to Do, Ask, or Never Do

### ✅ Always Do (Required for All Changes)

- **TDD: Write tests FIRST**: Write failing test → implement minimum code → refactor → repeat (see [Agent Workflow Step 2](#step-2-making-changes-strict-tdd-workflow) for details)
- **Run tests before committing**: `pytest tests/unit -q` minimum, full suite preferred
- **Use type hints**: All function signatures must have complete type annotations (avoid `Any` except when interfacing with untyped third-party libraries or dynamic RouterOS API responses)
- **Follow async/await**: All I/O operations (DB, RouterOS REST, HTTP) must be async
- **Write docstrings**: All public functions require docstrings with Args and Returns sections
- **Update tests**: Add tests for new code, update tests for modified code
- **Run formatters**: `ruff check --fix routeros_mcp && black routeros_mcp` before every commit
- **Respect security model**: All clients are untrusted, all safety enforced server-side
- **Log to stderr in STDIO mode**: Never write to stdout (corrupts JSON-RPC protocol)
- **Check design docs**: Link to relevant design doc when implementing from specifications

### ⚠️ Ask First (Requires Discussion/Approval)

- **Adding new dependencies**: Must check `gh-advisory-database` for vulnerabilities
- **Modifying database schema**: Requires Alembic migration and backward compatibility check
- **Changing MCP tool signatures**: Breaking changes require version bump and deprecation notice
- **Adding high-risk RouterOS endpoints**: Professional-tier tools require plan/apply + approval
- **Modifying security/auth logic**: Zero-trust model must be preserved
- **Changing environment/capability flags**: Could affect production safety guardrails
- **Large refactorings**: Split into multiple PRs with incremental validation

### 🚫 Never Do (Hard Boundaries)

- **Write to stdout in STDIO mode**: Corrupts MCP JSON-RPC protocol (use stderr for logs)
- **Bypass server-side validation**: All safety controls must be server-side, never client-side
- **Log secrets**: RouterOS credentials, OIDC tokens, approval tokens must never appear in logs
- **Remove existing tests**: Tests can only be updated or extended, never deleted
- **Ignore coverage requirements**: 85% minimum (non-core), 95% minimum (core modules)
- **Use blocking I/O**: All RouterOS calls, DB operations, HTTP must use async/await
- **Skip audit logging**: All writes and sensitive reads must be logged
- **Modify production configs**: Configuration changes go through proper channels only
- **Weaken security boundaries**: Environment tags, capability flags always enforced

## Project Summary

**RouterOS-MCP** is a production-ready MCP service for managing MikroTik RouterOS v7 devices with strong security guardrails, comprehensive audit logging, and AI-friendly tool interfaces. The service exposes safe, well-typed, auditable operations to AI tools (e.g., Claude Desktop, ChatGPT, VS Code Copilot) and human operators.

### Key Characteristics

- **Protocol**: Model Context Protocol (MCP) Specification 2024-11-05
- **Language**: Python 3.11+ with full type hints and async/await
- **Architecture**: 3-layer design (API → Domain → Infrastructure)
- **Security**: Zero-trust for all clients, server-side enforcement only
- **Deployment**: Single-tenant per instance, with environment separation (lab/staging/prod)
- **Database**: PostgreSQL (production) or SQLite (development)
- **Transports**: STDIO (local/development) and HTTP/SSE (remote/production)

## Core Design Principles

### 1. Security First (Zero Trust for AI)

All clients, including AI assistants, are treated as **untrusted**:

- **Server-side enforcement**: All safety controls (authorization, environment checks, capability flags, approval tokens) enforced on the MCP server
- **Client-side prompts are untrusted**: AI instructions provide zero security guarantees
- **Every tool invocation validated**: As if it came from an adversary
- **No bypasses**: Even admin users respect environment tags and device capability flags

**Critical**: MCP exposes RouterOS management to AI systems. Unlike human operators, LLMs cannot be trusted to "read carefully" or "use best judgment." All safety must be cryptographically and programmatically enforced.

### 2. Minimal Risk, Maximum Safety

- **Read-only by default**: 23 fundamental tools provide safe diagnostics and visibility
- **Incremental write capabilities**: Only after validation in lab/staging environments
- **Plan/Apply workflows**: High-risk operations require immutable plans + human approval tokens
- **Automatic rollback**: Post-change verification with automatic rollback on failure
- **Blast radius controls**: Multi-device operations execute sequentially, halt on first failure

### 3. MCP Best Practices Integration

This design follows official MCP best practices from Anthropic:

- **FastMCP SDK**: Zero-boilerplate tool registration with automatic schema generation
- **Intent-based descriptions**: All 46 tools include "Use when" guidance for optimal LLM selection
- **Resource metadata**: Token estimation, size hints, `safe_for_context` flags
- **Transport safety**: STDIO (stderr only for logs) and HTTP/SSE with OAuth
- **Error recovery**: Actionable error messages with recovery strategies
- **Versioning**: Semantic versioning with capability negotiation
- **Observability**: Request correlation, token budget tracking, tool-level metrics

### 4. Phase-Based Implementation

Implementation is organized into 6 phases (0-5) to manage risk and complexity:

- **Phase 0**: Service skeleton + security baseline (no writes)
- **Phase 1**: Read-only inventory + health MVP (23 fundamental tools)
- **Phase 2**: Low-risk single-device writes (9 advanced tools)
- **Phase 3**: Controlled network config writes
- **Phase 4**: Multi-device workflows (14 professional tools)
- **Phase 5**: Expert-only high-risk workflows (optional, disabled by default)

## Architecture Overview

### 3-Layer Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     API & MCP LAYER                          │
│  - MCP Protocol (STDIO/HTTP/SSE)                             │
│  - HTTP API (Admin/UI)                                       │
│  - Auth Handler (OIDC Token)                                 │
│  - Tools/Resources/Prompts                                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                 DOMAIN & SERVICE LAYER                       │
│  - Device Registry                                           │
│  - RouterOS Operations (DNS/NTP/System/Interface)            │
│  - Plan/Job Orchestration                                    │
│  - Audit & Policy Service                                    │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                  INFRASTRUCTURE LAYER                        │
│  - RouterOS REST/SSH Clients                                 │
│  - Persistence (Database)                                    │
│  - Background Jobs (APScheduler)                             │
│  - Observability Stack (Logging/Metrics/Tracing)             │
└─────────────────────────────────────────────────────────────┘
```

### Module Layout

Key directories in `routeros_mcp/`:

- **`config.py`**: Pydantic settings (DB URL, OIDC config, MCP transport mode)
- **`cli.py`**: Command-line argument parsing and startup validation
- **`main.py`**: Application entry point (DB init, MCP server, FastAPI app)
- **`mcp/`**: MCP protocol implementation
  - `server.py`: MCPServer core using FastMCP SDK
  - `protocol/`: JSON-RPC 2.0 message handling
  - `transport/`: STDIO and HTTP/SSE transports
  - `session/`: Client session management
  - `registry/`: Tool/resource/prompt registries
  - `middleware/`: Auth, logging, metrics, validation
- **`api/`**: FastAPI HTTP API (admin endpoints, health, metrics)
- **`mcp_tools/`**: Tool implementations (fundamental/advanced/professional tiers)
- **`mcp_resources/`**: Resource providers (device://, fleet://, plan://, audit://)
- **`mcp_prompts/`**: Prompt templates (workflows, troubleshooting)
- **`security/`**: Authentication (OIDC) and authorization (RBAC, device scopes)
- **`domain/`**: Business logic and orchestration
  - `devices.py`: DeviceService
  - `routeros_operations/`: Topic-specific operations (system, interface, dns, ntp, etc.)
  - `plans.py`: PlanService (plan/apply workflows)
  - `jobs.py`: JobService (background tasks)
- **`infra/`**: Infrastructure layer
  - `routeros/`: REST and SSH clients
  - `db/`: SQLAlchemy models, migrations, session management
  - `observability/`: Logging, metrics, tracing

## MCP Integration Details

### Tool Taxonomy (46 Tools Total)

**Fundamental Tier (23 tools)** - Read-only, safe for all users:
- Device management: `device/list-devices`, `device/get-health-data`
- System info: `system/get-overview`, `system/get-clock`, `system/get-resource-usage`
- Interfaces: `interface/list-interfaces`, `interface/get-details`
- IP/DNS/NTP: `ip/list-addresses`, `dns/get-status`, `ntp/get-status`
- Routing: `routing/get-summary`, `routing/list-routes`
- Firewall: `firewall/list-filter-rules`, `firewall/list-address-lists`
- Logs: `logs/get-recent`, `logs/get-system-log`
- Diagnostics: `tool/ping`, `tool/traceroute`
- Fleet: `fleet/get-summary`, `fleet/get-health-overview`
- Audit: `audit/get-events`

**Advanced Tier (9 tools)** - Single-device, low-risk writes:
- System: `system/set-identity`, `interface/update-comment`
- DNS/NTP: `dns/update-servers`, `dns/flush-cache`, `ntp/update-servers`, `ntp/sync-clock`
- Config: `device/get-config-snapshot`, `snapshot/get-content`, `snapshot/compare`

**Professional Tier (14 tools)** - Multi-device, high-risk workflows:
- Planning: `config/plan-dns-ntp-rollout`, `plan/get-details`, `plan/list-plans`
- Execution: `config/apply-dns-ntp-rollout`, `config/rollback-plan`
- Address lists: `addresslist/plan-sync`, `addresslist/apply-sync`
- Fleet: `fleet/plan-config-rollout`, `fleet/apply-config-rollout`
- Approval: `approval/generate-token` (admin only)

**Phase-1 Fallback Tools (6 tools)** - For tools-only clients:
- Provide equivalent functionality to resources for ChatGPT, Mistral, etc.
- Each includes `resource_uri` hint for migration to Phase 2

### Resource URIs (12 URIs - Phase 2)

Provide read-only contextual data:

- **Device resources**: `device://{device_id}/overview`, `device://{device_id}/config`, `device://{device_id}/health`
- **Fleet resources**: `fleet://health-summary`, `fleet://devices/{environment}`
- **Plan resources**: `plan://{plan_id}/details`, `plan://{plan_id}/execution-log`
- **Audit resources**: `audit://events/recent`, `audit://events/by-device/{device_id}`

### Prompts (8 Prompts - Phase 2)

Guided workflow templates:

- **Troubleshooting**: `troubleshoot_dns_ntp`, `troubleshoot_device`
- **Workflows**: `dns_ntp_rollout`, `fleet_health_review`, `address_list_sync`
- **Onboarding**: `device_onboarding`
- **Security**: `security_audit`, `comprehensive_device_review`

### Transport Modes

**STDIO (Phase 0-1)**:
- Default for local development and Claude Desktop integration
- stdin/stdout for MCP protocol, stderr for all logging
- **Critical**: Never write to stdout (corrupts JSON-RPC messages)
- OS-level access control (filesystem permissions, process isolation)

**HTTP/SSE (Phase 4)**:
- For remote/enterprise deployments
- OAuth 2.1 / OIDC authentication
- Cloudflare Tunnel integration
- Horizontal scaling with load balancers

## Security Model

### Phase 1: Single-User OS-Level Security

- **Authentication**: OS user authentication (process-level isolation)
- **Authorization**: Implicit admin role (full tool access)
- **Database**: SQLite protected by filesystem permissions (0600)
- **No network exposure**: STDIO transport only
- **Multi-user on same machine**: Separate processes and databases per OS user

### Phase 4: Multi-User OAuth/OIDC

- **Authentication**: OIDC token validation (signature, issuer, audience, expiry)
- **Role mapping**: OIDC groups → internal roles (read_only, ops_rw, admin)
- **Device scopes**: Per-user device access restrictions
- **Approval tokens**: Short-lived (5-minute TTL) for professional tools
- **Audit logging**: All writes and sensitive reads with correlation IDs

### Tool Tier Authorization

| Tier | Phase 1 (STDIO) | Phase 4 (HTTP) | Device Flags Required |
|------|-----------------|----------------|----------------------|
| Fundamental | All users (implicit admin) | `read_only`, `ops_rw`, `admin` | None |
| Advanced | All users (implicit admin) | `ops_rw`, `admin` | `allow_advanced_writes=true` |
| Professional | All users (implicit admin) | `admin` only | `allow_professional_workflows=true` |

### Environment & Capability Enforcement

- **Environment tags**: `lab`, `staging`, `prod` (immutable after registration)
- **Capability flags**:
  - `allow_advanced_writes`: Enable advanced-tier tools (default: false)
  - `allow_professional_workflows`: Enable professional-tier tools (default: false)
- **Blast radius controls**:
  - Multi-device operations execute sequentially
  - Halt on first device failure
  - Maximum batch size enforced (e.g., 50 devices per plan)

## RouterOS Integration

### REST API Endpoints (41 Endpoints)

**Read-only endpoints (25)**:
- System:
  - `/rest/system/resource`
  - `/rest/system/health`
  - `/rest/system/identity`
  - `/rest/system/clock`
  - `/rest/system/routerboard`
  - `/rest/system/package`
- Interface:
  - `/rest/interface`
  - `/rest/interface/ethernet`
  - `/rest/interface/vlan`
  - `/rest/interface/wireless`
- IP:
  - `/rest/ip/address`
  - `/rest/ip/arp`
  - `/rest/ip/firewall/address-list`
  - `/rest/ip/route`
  - `/rest/ip/dns`
  - `/rest/ip/dhcp-server`
  - `/rest/ip/dhcp-server/lease`
- NTP:
  - `/rest/system/ntp/client`
  - `/rest/system/ntp/server`
- Firewall:
  - `/rest/ip/firewall/filter`
  - `/rest/ip/firewall/nat`
- Logs:
  - `/rest/log`
- Wireless:
  - `/rest/interface/wireless/registration-table`

**Advanced write endpoints (10)**:
- System:
  - `POST /rest/system/identity`
  - `PATCH /rest/interface/{id}`
- DNS/NTP:
  - `POST /rest/ip/dns`
  - `POST /rest/system/ntp/client`
- Interface:
  - `POST /rest/ip/address`

**High-risk endpoints (6)**:
- Firewall:
  - `POST /rest/ip/firewall/filter`
  - `DELETE /rest/ip/firewall/filter/{id}`
- Routing:
  - `POST /rest/ip/route`
  - `DELETE /rest/ip/route/{id}`
- **Note**: High-risk endpoints are professional-tier only, require plan/apply + approval tokens

### SSH Fallback

- Used **only** where REST API is insufficient
- Whitelisted commands only (no arbitrary CLI execution)
- All SSH commands and results captured in audit logs
- Example: `/system identity print` (if REST unavailable)

## Development Guidelines

### Python Coding Standards

Follow `docs/13-python-coding-standards-and-conventions.md`:

- **Type hints**: All functions and classes fully typed
- **Async/await**: Used throughout (RouterOS calls, DB operations, HTTP requests)
- **Linting**: `ruff check routeros_mcp` (must pass)
- **Formatting**: `black routeros_mcp` (100-char line length)
- **Type checking**: `mypy routeros_mcp` (strict mode)
- **Naming**:
  - `snake_case`: Functions, variables, modules
  - `CamelCase`: Classes
  - `UPPER_SNAKE_CASE`: Constants

### Testing Requirements

Follow `docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md`:

- **Coverage targets**:
  - Core modules (domain, security, config): **95%+ coverage (aim for 100%)**
  - Other modules: **85%+ coverage**
  - All return and exception branches tested
- **Test layers**:
  - Unit tests: `tests/unit/` (mock RouterOS responses)
  - Integration tests: `tests/integration/` (real DB, mock RouterOS)
  - E2E tests: `tests/e2e/` (real RouterOS lab devices)
- **LLM-in-the-loop testing**: Automated tests with real LLM clients invoking tools
  - Tool selection accuracy: **90%+ target**
  - Parameter inference: **85%+ target**
- **Testing stack**: pytest, pytest-asyncio, pytest-cov

### Configuration Precedence

Configuration is loaded in priority order (highest to lowest):

1. **Command-line arguments** (e.g., `--debug`, `--log-level DEBUG`)
2. **Environment variables** (prefix: `ROUTEROS_MCP_`)
3. **Configuration file** (YAML or TOML via `--config`)
4. **Built-in defaults** (sensible defaults for development)

Example environment variables:
```bash
export ROUTEROS_MCP_ENVIRONMENT=lab
export ROUTEROS_MCP_LOG_LEVEL=DEBUG
export ROUTEROS_MCP_DATABASE_URL="postgresql://user:pass@localhost/routeros_mcp"
export ROUTEROS_MCP_MCP_TRANSPORT=stdio
export ROUTEROS_MCP_ENCRYPTION_KEY="<base64-encoded-32-byte-key>"
```

### Observability

- **Logging**: Structured JSON logs with correlation IDs (use `structlog`)
- **Metrics**: Prometheus metrics via `prometheus_client`
  - `mcp_tool_calls_total{tool_name, status}`
  - `mcp_tool_duration_seconds{tool_name}`
  - `routeros_rest_calls_total{device_id, endpoint, status}`
- **Tracing**: OpenTelemetry SDK (FastAPI/HTTPX instrumentation)
- **Correlation IDs**: Every tool invocation links MCP request → domain logic → RouterOS calls → audit log

## Task Scope and Issue Structure

### Right-Sizing Tasks for Agent Sessions

GitHub Copilot coding agent runs in **finite, autonomous sessions** (tens of minutes, not hours). Design tasks that:

- **One logical change per task**: Implement a feature flag, refactor a module, add tests for a surface area
- **Reviewable in 15-30 minutes**: Changes should be small enough for human review in one sitting
- **Touch a well-defined slice**: One service, module, or tool category (not "refactor everything")
- **Split naturally**: If a feature requires multiple PRs, create multiple issues

✅ **Good agent tasks:**
- Implement `dns/get-status` tool following tool pattern in `docs/04`
- Add unit tests for `DeviceService.register_device()` method
- Refactor `routeros_mcp/infra/routeros/rest_client.py` to use connection pooling
- Update README.md with Phase 1 status and tool count

❌ **Bad agent tasks:**
- "Modernize the whole codebase"
- "Improve performance everywhere"
- "Implement all Phase 2 tools"
- "Fix all bugs"

### Standard Issue Template for Agents

When creating issues for agents, use this structure:

```markdown
## Problem / 问题
[Brief description of what's broken or what's needed - 1-2 sentences]

## Context / 背景
[Business/technical context - why this matters, usage patterns, constraints]
- This [tool/module/endpoint] is [used for X / called Y times per day / critical for Z]
- [Any historical context, previous attempts, or related issues]

## Acceptance Criteria / 验收标准
- [ ] [Specific, measurable outcome 1]
- [ ] [Specific, measurable outcome 2]
- [ ] Tests added/updated with coverage ≥ [85% or 95%]
- [ ] Documentation updated in [specific file]
- [ ] [Specific test scenario] passes

## Files to Modify / 需要修改的文件
- `routeros_mcp/[module]/[file].py` - [What to change]
- `tests/unit/test_[file].py` - [What tests to add]
- `docs/[doc].md` - [What to document]

## Do Not Change / 禁止修改
- Authentication/authorization middleware
- Database schema (requires Alembic migration)
- Existing test coverage (can extend, not remove)
- [Any other no-touch areas]

## How to Build & Test / 构建与测试
```bash
# Validate changes
pytest tests/unit/test_[specific].py -v
ruff check --fix routeros_mcp/[module]/
mypy routeros_mcp/[module]/

# Verify specific behavior
[Specific command or curl/API call that demonstrates success]
```

## Design References / 设计参考
- Design doc: [docs/XX-relevant-design.md](docs/XX-relevant-design.md)
- Related issue: #123
- Pattern to follow: [point to existing code example]

## Known Edge Cases / 已知边界情况
- [Edge case 1 to handle]
- [Edge case 2 to test]
- [Historical bug to avoid re-introducing]
```

### Example: Well-Scoped Agent Issue

```markdown
## Problem
The `device/list-devices` tool returns 500 error when database has devices with null `routeros_version` field.

## Context
- This is a fundamental-tier tool used by all MCP clients for device discovery
- Called ~50 times per user session
- Some lab devices registered before version tracking was added (v0.2.0) have null version field

## Acceptance Criteria
- [ ] `device/list-devices` returns 200 with version="unknown" for devices with null version
- [ ] Add unit tests covering null version edge case
- [ ] Add integration test with mixed version/null version devices
- [ ] Tool response schema documented in docs/04-mcp-tools-interface-and-json-schema-specification.md
- [ ] Test case: `pytest tests/unit/test_device_tools.py::test_list_devices_null_version -v` passes

## Files to Modify
- `routeros_mcp/mcp_tools/device.py` - Add null check in `list_devices()` handler
- `routeros_mcp/domain/devices.py` - Update `DeviceService.list_devices()` to handle null version
- `tests/unit/test_device_tools.py` - Add test case for null version
- `tests/unit/test_device_service.py` - Add test case for service layer
- `docs/04-mcp-tools-interface-and-json-schema-specification.md` - Update response schema

## Do Not Change
- Device registration logic (separate issue)
- Database schema (version field must remain nullable for backward compat)
- Other device tools (list-devices only)

## How to Build & Test
```bash
# Quick validation
pytest tests/unit/test_device_tools.py -v
pytest tests/unit/test_device_service.py -v

# Verify tool works via MCP
# (requires MCP Inspector or manual test with Claude Desktop)
```

## Design References
- Tool specification: [docs/04-mcp-tools-interface-and-json-schema-specification.md#devicelist-devices](docs/04-mcp-tools-interface-and-json-schema-specification.md)
- Device model: [docs/18-database-schema-and-orm-specification.md](docs/18-database-schema-and-orm-specification.md)
- Pattern to follow: See `system/get-overview` tool in `routeros_mcp/mcp_tools/system.py`

## Known Edge Cases
- Null version field (main issue)
- Empty device list should return empty array, not error
- Device with disabled status should still be listed
```

## Key Design Documents

> **Note**: All document paths are relative to the repository root. View this file from the repository root directory, or use the GitHub web interface for clickable links.

Essential reading for custom agents (in suggested order):

1. **[00-requirements-and-scope-specification.md](docs/00-requirements-and-scope-specification.md)**
   - Problem statement, use cases, success criteria
   - Tool count targets by phase and tier
   - Workflow examples (DNS/NTP rollout, troubleshooting)

2. **[01-overall-system-architecture-and-deployment-topology.md](docs/01-overall-system-architecture-and-deployment-topology.md)**
   - High-level architecture, components, deployment topology
   - Phased architecture evolution (Phase 1-4)
   - Security zones & trust boundaries

3. **[14-mcp-protocol-integration-and-transport-design.md](docs/14-mcp-protocol-integration-and-transport-design.md)**
   - FastMCP SDK integration
   - Transport modes (STDIO vs HTTP/SSE)
   - Protocol lifecycle (initialize → tools/call → shutdown)

4. **[04-mcp-tools-interface-and-json-schema-specification.md](docs/04-mcp-tools-interface-and-json-schema-specification.md)**
   - Complete tool catalog with JSON-RPC schemas
   - Intent-based tool descriptions
   - Tool tier definitions

5. **[11-implementation-architecture-and-module-layout.md](docs/11-implementation-architecture-and-module-layout.md)**
   - Runtime stack (Python 3.11+, FastAPI, SQLAlchemy, httpx, asyncssh)
   - Package/module layout
   - Key classes and signatures

6. **[02-security-oauth-integration-and-access-control.md](docs/02-security-oauth-integration-and-access-control.md)**
   - Threat model and trust boundaries
   - Phase 1 OS-level security vs Phase 4 OAuth/OIDC
   - Authorization model (roles, device scopes, capability flags)

7. **[13-python-coding-standards-and-conventions.md](docs/13-python-coding-standards-and-conventions.md)**
   - Type hints, async/await patterns
   - Testing conventions
   - Linting/formatting rules

8. **[10-testing-validation-and-sandbox-strategy-and-safety-nets.md](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md)**
   - TDD methodology
   - Coverage targets (85% non-core, 95%+ core)
   - LLM-in-the-loop testing

## Common Patterns

### Tool Implementation Pattern

```python
from pydantic import BaseModel

# Assume mcp is a FastMCP instance created at module level:
# from fastmcp import FastMCP
# mcp = FastMCP("RouterOS-MCP")

class GetOverviewArgs(BaseModel):
    device_id: str

@mcp.tool()
async def system_get_overview(args: GetOverviewArgs) -> str:
    """Get comprehensive system overview for a RouterOS device.
    
    Use when:
    - User asks "show me system info for device X"
    - Need CPU, memory, uptime, RouterOS version
    - Starting device diagnostics workflow
    
    Returns: System overview with version, uptime, resources, health.
    """
    # 1. Validate device exists and is accessible
    device = await device_service.get_device(args.device_id)
    
    # 2. Check authorization (environment, capability flags)
    await authz_service.check_tool_access(
        tool_name="system/get-overview",
        tier="fundamental",
        device=device
    )
    
    # 3. Call RouterOS via REST client
    result = await routeros_client.get_system_resource(device)
    
    # 4. Audit logging is handled automatically at the observability layer (not directly in tool implementations)
    
    # 5. Return formatted result
    return json.dumps(result, indent=2)
```

### Resource Provider Pattern

```python
@mcp.resource("device://{device_id}/health")
async def device_health(device_id: str) -> str:
    """Real-time health metrics for a RouterOS device.
    
    Provides: CPU usage, memory usage, temperature, voltage, uptime.
    Updated: Every 60 seconds by background job.
    Safe for context: Yes (< 5KB response).
    """
    # Read from cache (updated by background job)
    health_data = await cache_service.get_device_health(device_id)
    
    return json.dumps({
        "device_id": device_id,
        "timestamp": health_data.timestamp.isoformat(),
        "cpu_usage_percent": health_data.cpu_usage,
        "memory_usage_percent": health_data.memory_usage,
        "temperature_celsius": health_data.temperature,
        "voltage": health_data.voltage,
        "uptime_seconds": health_data.uptime
    })
```

### Error Handling Pattern

```python
from routeros_mcp.mcp.errors import MCPError, map_exception_to_error
from routeros_mcp.mcp_tools.util import format_tool_result

try:
    result = await device_service.execute_operation(device_id, operation)
except Exception as exc:
    # Map the exception to an MCPError (if possible)
    mcp_error = map_exception_to_error(exc)
    return format_tool_result(
        is_error=True,
        error=mcp_error,
        suggestion="Check device ID and network connectivity, or use device/list-devices."
    )
```

## Phase 1 Current Status

**Completed**:
- ✅ Project setup (Python 3.11+, pyproject.toml, dependencies)
- ✅ Configuration management (Pydantic settings, CLI args, env vars)
- ✅ Database schema (SQLAlchemy models, Alembic migrations)
- ✅ MCP server skeleton (FastMCP integration, STDIO transport)
- ✅ Security baseline (encryption for credentials, audit event models)

**In Progress** (as of implementation):
- ⚙️ RouterOS REST client implementation
- ⚙️ Fundamental tools (device, system, interface, dns, ntp, logs, tool)
- ⚙️ Background jobs (health checks, metrics collection)
- ⚙️ Admin HTTP API (device onboarding, plan review)

**Not Started**:
- ❌ Advanced tools (Phase 2)
- ❌ Professional tools (Phase 4)
- ❌ Resources and prompts (Phase 2)
- ❌ HTTP/SSE transport (Phase 4)
- ❌ OAuth/OIDC integration (Phase 4)

## Common Pitfalls to Avoid (Anti-Patterns)

### Critical "Never Do" Items

1. **NEVER write to stdout in STDIO mode**
   - This corrupts JSON-RPC messages. Use stderr for all logs.
   - In STDIO mode, stdout is reserved exclusively for MCP protocol messages
   - All `print()` statements, debug output, and logs must go to stderr

2. **NEVER bypass server-side validation**
   - All safety controls must be enforced server-side, even for "trusted" clients
   - Zero-trust model: LLMs cannot be trusted to "read carefully" or "use best judgment"
   - Client-side prompts provide zero security guarantees

3. **NEVER log secrets**
   - RouterOS credentials, OIDC client secrets, approval tokens must never appear in logs (even in debug mode)
   - Mask passwords and API keys in returned configurations
   - Use structured logging with secret filtering

4. **NEVER ignore environment/capability flags**
   - Even admin users respect `environment` tags and device `allow_*` flags
   - Environment tags (`lab`/`staging`/`prod`) are immutable after registration
   - Capability flags control which tools are allowed per device

5. **NEVER make unbounded RouterOS calls**
   - Always use timeouts, retries, and per-device rate limiting
   - Default: at most 2-3 concurrent REST calls per device
   - Implement circuit breakers for misbehaving devices

6. **NEVER skip audit logging**
   - All writes and sensitive reads must be logged with correlation IDs
   - Audit log writes are non-blocking but failures trigger alerts
   - Correlation IDs link MCP request → domain logic → RouterOS calls → audit log

7. **NEVER assume well-behaved clients**
   - Validate all tool arguments against JSON schemas
   - Enforce maximum batch sizes (e.g., 50 devices per plan)
   - Sanitize and validate all user input

8. **NEVER use blocking I/O**
   - All RouterOS calls, DB operations, HTTP requests must use async/await
   - Use `httpx` (async) for REST, `asyncssh` for SSH, SQLAlchemy async sessions for DB
   - Blocking I/O kills concurrent performance in async runtime

### Agent-Specific Anti-Patterns

9. **Don't create massive, ambiguous tasks**
   - ❌ "Refactor the whole service so it's cleaner"
   - ❌ "Fix all performance issues in this repo"
   - ✅ "Refactor `RouterOSRestClient` to use connection pooling"
   - ✅ "Add unit tests for `DeviceService.register_device()`"

10. **Don't skip environment setup**
    - Agent time is limited; re-installing dependencies wastes precious minutes
    - Use `.github/workflows/copilot-setup-steps.yml` for pre-warming
    - Cache Python packages, system tools, and dependencies

11. **Don't write vague acceptance criteria**
    - ❌ "Add tests" → produces inconsistent results
    - ✅ "Add pytest unit tests in tests/unit/test_device.py with ≥95% coverage for DeviceService.register_device()"
    - ✅ "Tool must return 200 for test device ID `test-device-001`"

12. **Don't ignore existing patterns**
    - Before implementing new code, look for similar patterns in the codebase
    - Follow existing patterns for tool implementation, error handling, testing
    - Reference design docs for architectural decisions

13. **Don't remove tests to "fix" failures**
    - Tests can be updated or extended, never deleted
    - If a test fails, fix the code or update the test assertion (with justification)
    - Removing tests weakens quality and masks regressions

14. **Don't weaken quality gates for automation**
    - Agent PRs must pass same CI checks as human-authored code
    - No lowering coverage thresholds, skipping type checks, or disabling linters
    - Agent code should be production-ready, not "good enough for a bot"

## Agent Workflow: From Issue to Merged PR (TDD-First)

### Step 1: Understanding the Task (Before Writing Any Code)

1. **Read the issue carefully** - Understand problem, context, acceptance criteria
2. **Review referenced design docs** - Understand architectural decisions and constraints
3. **Check existing patterns** - Look for similar implementations to follow
4. **Write a numbered plan** - List changes you'll make and assumptions you're making
5. **Validate plan** - Ensure plan aligns with acceptance criteria and boundaries

### Step 2: Making Changes (Strict TDD Workflow)

**Critical: Tests must be written BEFORE implementation code. No exceptions.**

1. **Write failing test first** (Red phase)
   - Define expected behavior in test
   - Use Arrange-Act-Assert pattern
   - Test should fail because feature doesn't exist yet
   - Example: `pytest tests/unit/test_device_tools.py::test_list_devices_null_version -v` → FAIL

2. **Implement minimal code** (Green phase)
   - Write just enough code to make the test pass
   - No extra features, no premature optimization
   - Focus on making the red test turn green
   - Example: Add null check in `list_devices()` method

3. **Run targeted tests** (Verify Green)
   - `pytest tests/unit/test_[specific].py -v` for quick feedback
   - Test should now pass
   - If fails, debug and fix (don't skip to next step)

4. **Refactor if needed** (Refactor phase)
   - Improve code structure while keeping tests green
   - Extract methods, rename variables, improve readability
   - Run tests after each refactor to ensure green state
   - Only refactor when tests are passing

5. **Add documentation**
   - Update docstrings with type hints and examples
   - Update design docs if architectural changes
   - Update README if user-facing changes

6. **Repeat TDD loop**
   - For each new behavior, start at step 1 (write failing test)
   - Build features incrementally with test coverage at every step

### Step 3: Validation (Before Opening PR)

1. **Run full test suite** - `pytest --cov=routeros_mcp --cov-fail-under=85`
2. **Check coverage** - Ensure ≥85% overall, ≥95% for core modules
3. **Run type checker** - `mypy routeros_mcp` must pass with no errors
4. **Run linter** - `ruff check --fix routeros_mcp` to auto-fix issues
5. **Format code** - `black routeros_mcp` for consistent style
6. **Manual smoke test** - If applicable, test the tool/feature manually

### Step 4: Opening PR

1. **Review changed files** - Ensure only intended files modified
2. **Write clear PR description** - Reference issue, list changes, note any trade-offs
3. **Self-review code** - Read diff as if you're the reviewer
4. **Check CI status** - Ensure all checks pass before requesting review
5. **Tag reviewers** - Use CODEOWNERS or mention specific reviewers

### Step 5: Addressing Review Feedback

1. **Batch feedback** - If multiple comments, address them together in one update
2. **Test fixes** - Run tests after each change to avoid breaking things
3. **Explain trade-offs** - If you disagree with feedback, explain reasoning
4. **Request re-review** - After addressing feedback, ask for another look

## Additional Resources

- **MCP Specification**: https://spec.modelcontextprotocol.io/ (Official MCP protocol specification)
- **FastMCP SDK**: https://github.com/jlowin/fastmcp (Python MCP SDK)
- **RouterOS v7 REST API**: https://help.mikrotik.com/docs/display/ROS/REST+API (Official MikroTik documentation)
- **GitHub Copilot Best Practices**: [docs/best_practice/github-copilot-coding-agent-best-practices.md](docs/best_practice/github-copilot-coding-agent-best-practices.md)
- **MCP Best Practices**: [docs/best_practice/mcp_best_practices_merged.md](docs/best_practice/mcp_best_practices_merged.md)
- **Design Documents**: [`docs/`](docs/) directory (20+ documents)
- **Contributing Guide**: [CONTRIBUTING.md](CONTRIBUTING.md)

## Summary

This custom agent guide follows **GitHub Copilot custom agent best practices** and synthesizes the comprehensive design documentation into actionable guidance. The RouterOS-MCP service is a well-designed, security-first MCP implementation with clear phase boundaries, strong testing requirements, and production-ready architecture.

**Key Takeaways for GitHub Copilot and Custom Agents**:

1. **TDD is not optional**: Write failing test FIRST, then implement minimum code, then refactor. No code without tests.
2. **Safety-first for network automation**: Default to read-only, validate all inputs, use dry-run mode, implement rollbacks
3. **Strong typing required**: Pydantic models for all RouterOS data, type hints everywhere, mypy strict mode
4. **Start with executable commands**: Quick reference at top with build/test commands for immediate validation
5. **Security is non-negotiable**: All clients are untrusted, all safety is server-side, zero-trust model
6. **Right-size tasks**: One logical change per session, reviewable in 15-30 minutes, no "refactor everything" tasks
7. **Follow three-tier boundaries**: Clear "always do," "ask first," and "never do" rules
8. **Test coverage requirements**: 85%+ overall, 95%+ for core modules, never remove tests
9. **Use concrete patterns**: Real code examples throughout, not just descriptions
10. **Quality gates apply to all**: Agent PRs must pass same CI checks as human-authored code

**TDD Loop (Non-Negotiable)**:
```
1. Write failing test (Red)
2. Implement minimum code to pass (Green)
3. Refactor while keeping tests green (Refactor)
4. Repeat for next behavior
```

**Safety-First Network Automation**:
- Read-only by default (fundamental tier)
- Explicit confirmation for writes (advanced tier)
- Plan/apply with approval for high-risk (professional tier)
- Validate inputs, use dry-run, implement rollbacks
- Never trust client-side validation

**For Best Results**:
- Reference the standard issue template when creating tasks
- Review relevant design docs before starting work
- Follow existing patterns in the codebase
- Run fast validation commands frequently: `pytest tests/unit -q && ruff check --fix routeros_mcp`
- **Write tests before implementation** (TDD workflow)
- Never bypass server-side validation or weaken security boundaries

For questions or clarifications, refer to the specific design document or open a GitHub issue.
