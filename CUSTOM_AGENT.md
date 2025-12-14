# RouterOS-MCP Custom Agent Guide

## Overview

This document provides comprehensive guidance for custom agents working on the RouterOS Model Context Protocol (MCP) Service. It synthesizes key information from the 20+ design documents in this repository to help you understand the system architecture, design principles, and implementation patterns.

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
    
    # 4. Write audit event
    await audit_service.log_event(
        tool_name="system/get-overview",
        device_id=args.device_id,
        result=result,
        sensitive=False
    )
    
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
from routeros_mcp.mcp.errors import (
    DeviceNotFoundError,
    DeviceUnreachableError,
    UnauthorizedError
)

try:
    result = await device_service.execute_operation(device_id, operation)
except DeviceNotFoundError as e:
    # JSON-RPC error code -32602 (Invalid params)
    raise MCPError(
        code=-32602,
        message="Invalid device_id",
        data={
            "mcp_error_code": "DEVICE_NOT_FOUND",
            "device_id": device_id,
            "suggestion": "Use device/list-devices to see available devices"
        }
    )
except DeviceUnreachableError as e:
    # JSON-RPC error code -32000 (Server error)
    raise MCPError(
        code=-32000,
        message="Device unreachable",
        data={
            "mcp_error_code": "DEVICE_UNREACHABLE",
            "device_id": device_id,
            "management_address": e.management_address,
            "suggestion": "Check network connectivity and device status"
        }
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

## Common Pitfalls to Avoid

1. **NEVER write to stdout in STDIO mode** - This corrupts JSON-RPC messages. Use stderr for all logs.

2. **NEVER bypass server-side validation** - All safety controls must be enforced server-side, even for "trusted" clients.

3. **NEVER log secrets** - RouterOS credentials, OIDC client secrets, approval tokens must never appear in logs (even in debug mode).

4. **NEVER ignore environment/capability flags** - Even admin users respect `environment` tags and device `allow_*` flags.

5. **NEVER make unbounded RouterOS calls** - Always use timeouts, retries, and per-device rate limiting.

6. **NEVER skip audit logging** - All writes and sensitive reads must be logged with correlation IDs.

7. **NEVER assume well-behaved clients** - Validate all tool arguments against JSON schemas.

8. **NEVER use blocking I/O** - All RouterOS calls, DB operations, HTTP requests must use async/await.

## Quick Reference

### Run MCP Server (STDIO)

```bash
# With lab config
routeros-mcp --config config/lab.yaml

# With environment variables
export ROUTEROS_MCP_ENVIRONMENT=lab
export ROUTEROS_MCP_LOG_LEVEL=DEBUG
routeros-mcp

# With debug mode
routeros-mcp --debug --log-level DEBUG
```

### Run Tests

```bash
# All tests with coverage
pytest --cov=routeros_mcp --cov-report=html

# Unit tests only
pytest tests/unit -v

# Specific test file
pytest tests/unit/test_config.py -v

# With coverage threshold enforcement
pytest --cov=routeros_mcp --cov-fail-under=85
```

### Code Quality

```bash
# Lint
ruff check routeros_mcp

# Auto-fix linting issues
ruff check --fix routeros_mcp

# Format
black routeros_mcp

# Type check
mypy routeros_mcp

# All checks
ruff check routeros_mcp && black --check routeros_mcp && mypy routeros_mcp && pytest
```

### Database Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "Add device capability flags"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1

# Show current revision
alembic current
```

## Additional Resources

- **MCP Specification**: https://spec.modelcontextprotocol.io/ (Official MCP protocol specification)
- **FastMCP SDK**: https://github.com/jlowin/fastmcp (Python MCP SDK)
- **RouterOS v7 REST API**: https://help.mikrotik.com/docs/display/ROS/REST+API (Official MikroTik documentation)
- **Design Documents**: [`docs/`](docs/) directory (20+ documents)
- **Contributing Guide**: [CONTRIBUTING.md](CONTRIBUTING.md)
- **Implementation Tasks**: [GITHUB-COPILOT-TASKS.md](GITHUB-COPILOT-TASKS.md)

## Summary

This custom agent guide synthesizes the comprehensive design documentation into actionable guidance. The RouterOS-MCP service is a well-designed, security-first MCP implementation with clear phase boundaries, strong testing requirements, and production-ready architecture.

**Key Takeaways for Custom Agents**:

1. **Security is non-negotiable**: All clients are untrusted, all safety is server-side
2. **Phase-based implementation**: Follow the 0-5 phase roadmap for risk management
3. **Test-driven development**: 85%+ coverage (95%+ for core modules)
4. **MCP best practices**: Intent-based tools, token budgets, error recovery
5. **Zero compromises on quality**: Type hints, async/await, linting, formatting

For questions or clarifications, refer to the specific design document or open a GitHub issue.
