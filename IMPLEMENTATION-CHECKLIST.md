# Implementation Checklist

Quick reference for implementing the RouterOS MCP service following the design specifications.

## Pre-Implementation

- [ ] Read [docs/00](docs/00-requirements-and-scope-specification.md) - Requirements
- [ ] Read [docs/01](docs/01-overall-system-architecture-and-deployment-topology.md) - Architecture
- [ ] Read [docs/14](docs/14-mcp-protocol-integration-and-transport-design.md) - MCP Integration
- [ ] Read [docs/ANALYSIS.md](docs/ANALYSIS.md) - Design Analysis
- [ ] Review [IMPROVEMENTS-SUMMARY.md](docs/IMPROVEMENTS-SUMMARY.md)

## Phase 0: Service Skeleton & Security Baseline

### Project Setup

- [ ] Create project structure per [docs/16](docs/16-detailed-module-specifications.md)
- [ ] Create `pyproject.toml` with dependencies from [docs/12](docs/12-development-environment-dependencies-and-commands.md)
- [ ] Set up git repository with `.gitignore`
- [ ] Create virtual environment: `uv venv .venv`
- [ ] Install dependencies: `uv pip install -e .[dev]`

### Configuration

- [ ] Implement `config.py` with `pydantic-settings`
- [ ] Create `config/lab.yaml` example
- [ ] Set up environment variable loading
- [ ] Add validation for required settings

### Database

- [ ] Set up PostgreSQL database (local or Docker)
- [ ] Create SQLAlchemy models in `infra/db/models.py`
- [ ] Configure Alembic in `infra/db/migrations/`
- [ ] Create initial migration
- [ ] Test migration: `uv run alembic upgrade head`

### MCP Server

- [ ] Implement `mcp_server.py` with FastMCP
- [ ] Configure logging (stderr for stdio mode)
- [ ] Add transport selection (stdio vs. HTTP)
- [ ] Test server starts: `uv run python -m routeros_mcp.mcp_server`

### Security Layer

- [ ] Implement `security/crypto.py` for credential encryption
- [ ] Implement `security/auth.py` with authlib
- [ ] Implement `security/authz.py` with role checking
- [ ] Add OIDC configuration (mark as optional for Phase 0)

### Domain Services

- [ ] Create domain models in `domain/models.py`
- [ ] Implement `domain/devices.py` - DeviceService
- [ ] Implement `domain/exceptions.py`
- [ ] Add device repository interface

### Basic Tools

- [ ] Create `mcp_tools/system.py`
- [ ] Implement `device.list_devices` tool
- [ ] Implement `device.check_connectivity` tool
- [ ] Add authorization middleware

### Testing

- [ ] Set up pytest configuration
- [ ] Write unit tests for config
- [ ] Write unit tests for domain services
- [ ] Test with MCP Inspector
- [ ] Verify stdio transport works

### Documentation

- [ ] Add docstrings to all modules
- [ ] Create `CONTRIBUTING.md`
- [ ] Update README if needed

## Phase 1: Read-Only Inventory & Health MVP

### RouterOS Integration

- [ ] Implement `infra/routeros/rest_client.py`
- [ ] Implement `infra/routeros/errors.py`
- [ ] Add connection pooling with httpx
- [ ] Add retry logic with backoff
- [ ] Test against real RouterOS device (lab)

### System Tools

- [ ] Implement `system.get_overview` tool
- [ ] Implement `system.get_identity` tool
- [ ] Add RouterOS version detection

### Interface Tools

- [ ] Implement `interface.list_interfaces` tool
- [ ] Implement `interface.get_interface` tool
- [ ] Parse interface statistics

### IP Tools

- [ ] Implement `ip.list_addresses` tool
- [ ] Implement `ip.get_address` tool

### DNS/NTP Tools

- [ ] Implement `dns.get_status` tool
- [ ] Implement `ntp.get_status` tool

### Diagnostics Tools

- [ ] Implement `tool.ping` tool
- [ ] Implement `tool.traceroute` tool
- [ ] Add safety limits (max count, timeout)

### Health Checks

- [ ] Implement `domain/health.py` service
- [ ] Create health check job
- [ ] Set up APScheduler
- [ ] Store health check results

### MCP Resources

- [ ] Implement `mcp_resources/device.py`
- [ ] Add `device://{device_id}/overview` resource
- [ ] Add `device://{device_id}/health` resource
- [ ] Implement `mcp_resources/fleet.py`
- [ ] Add `fleet://devices` resource
- [ ] Add `fleet://health-summary` resource

### MCP Prompts

- [ ] Implement `mcp_prompts/troubleshooting.py`
- [ ] Add `troubleshoot-device` prompt
- [ ] Test prompts in MCP Inspector

### Admin API

- [ ] Create `api/http.py` with FastAPI
- [ ] Add `/admin/devices/register` endpoint
- [ ] Add `/admin/devices/{id}` CRUD endpoints
- [ ] Secure admin API with OAuth

### Testing

- [ ] Unit tests for all tools
- [ ] Integration tests with lab RouterOS
- [ ] MCP Inspector testing
- [ ] Achieve 85%+ coverage

## Phase 2: Low-Risk Single-Device Writes

### Advanced Tools

- [ ] Implement `system.update_identity` tool
- [ ] Implement `interface.update_comment` tool
- [ ] Add dry-run support

### Authorization

- [ ] Enforce advanced tier authorization
- [ ] Check device capability flags
- [ ] Verify environment constraints

### Audit Logging

- [ ] Implement `domain/audit.py` service
- [ ] Log all write operations
- [ ] Log sensitive reads
- [ ] Create audit event database table

### Change Detection

- [ ] Implement read-modify-write pattern
- [ ] Return `changed` flag in responses
- [ ] Create snapshots before changes

### Testing

- [ ] Test writes on lab devices
- [ ] Verify audit logs
- [ ] Test dry-run mode
- [ ] Verify rollback capability

## Phase 3: Controlled Network Config Writes

### IP Address Management

- [ ] Implement `ip.add_secondary_address` tool
- [ ] Implement `ip.remove_secondary_address` tool
- [ ] Add management path protection

### Address Lists

- [ ] Implement `ip.add_address_list_entry` tool
- [ ] Implement `ip.remove_address_list_entry` tool
- [ ] Restrict to MCP-owned lists

### Testing

- [ ] Test on lab devices
- [ ] Verify no impact to management path
- [ ] Test rollback scenarios

## Phase 4: Multi-Device & Cross-Topic Workflows

### Plan/Apply Pattern

- [ ] Implement `domain/plans.py` service
- [ ] Create `config.plan_dns_ntp_rollout` tool
- [ ] Create `config.apply_dns_ntp_rollout` tool
- [ ] Add approval token validation

### Job Execution

- [ ] Implement `domain/jobs.py` service
- [ ] Create job execution runner
- [ ] Add staged rollout logic
- [ ] Implement health check validation

### MCP Prompts

- [ ] Add `dns-ntp-rollout` prompt
- [ ] Add step-by-step guidance
- [ ] Include safety notes

### Testing

- [ ] Test plan creation
- [ ] Test approval workflow
- [ ] Test staged rollout
- [ ] Test automatic rollback

## Observability

### Logging

- [ ] Configure structlog
- [ ] Add correlation IDs
- [ ] Add structured fields
- [ ] Test log output

### Metrics

- [ ] Set up Prometheus client
- [ ] Add tool invocation metrics
- [ ] Add RouterOS call metrics
- [ ] Add job execution metrics
- [ ] Create `/metrics` endpoint

### Tracing

- [ ] Set up OpenTelemetry
- [ ] Add trace spans for tools
- [ ] Add trace spans for RouterOS calls
- [ ] Configure exporter

## Production Readiness

### Security

- [ ] Enable OIDC authentication
- [ ] Test OAuth flow
- [ ] Rotate encryption keys
- [ ] Review audit logs

### Deployment

- [ ] Create Dockerfile
- [ ] Set up Cloudflare Tunnel
- [ ] Configure HTTP/SSE transport
- [ ] Test production deployment

### Monitoring

- [ ] Set up alerting
- [ ] Create dashboards
- [ ] Test incident runbooks

### Documentation

- [ ] Update README
- [ ] Create operations runbook
- [ ] Document deployment process

## Quality Gates

### Code Quality

- [ ] All code has type hints
- [ ] Passes `mypy --strict`
- [ ] Passes `ruff check`
- [ ] Passes `black --check`
- [ ] No `# type: ignore` without justification

### Testing

- [ ] Overall coverage ≥ 85%
- [ ] Core modules coverage = 100%
- [ ] All tests pass
- [ ] MCP Inspector validation

### Documentation

- [ ] All public functions have docstrings
- [ ] All modules have module docstrings
- [ ] README is up to date
- [ ] CHANGELOG maintained

### Security

- [ ] No secrets in code
- [ ] No secrets in logs
- [ ] All inputs validated
- [ ] All tools have authorization

## Tools and Commands

### Development

```bash
# Create venv
uv venv .venv && source .venv/bin/activate

# Install deps
uv pip install -e .[dev]

# Run server (stdio)
uv run python -m routeros_mcp.mcp_server --config config/lab.yaml

# Run server (HTTP)
uv run python -m routeros_mcp.mcp_server --config config/prod.yaml

# MCP Inspector
npx @modelcontextprotocol/inspector uv run python -m routeros_mcp.mcp_server --config config/lab.yaml
```

### Testing

```bash
# All tests
uv run pytest

# With coverage
uv run pytest --cov=routeros_mcp --cov-report=html

# Specific test
uv run pytest tests/unit/test_config.py -v

# Using tox
uv run tox
```

### Code Quality

```bash
# Lint
uv run ruff check routeros_mcp

# Format
uv run black routeros_mcp

# Type check
uv run mypy routeros_mcp

# All checks
uv run tox -e lint,type
```

### Database

```bash
# Create migration
uv run alembic revision --autogenerate -m "Description"

# Apply migrations
uv run alembic upgrade head

# Rollback
uv run alembic downgrade -1

# Show current version
uv run alembic current
```

---

## Reference Documentation

| Phase | Key Docs |
|-------|----------|
| Phase 0 | [14](docs/14-mcp-protocol-integration-and-transport-design.md), [16](docs/16-detailed-module-specifications.md), [12](docs/12-development-environment-dependencies-and-commands.md) |
| Phase 1 | [03](docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md), [04](docs/04-mcp-tools-interface-and-json-schema-specification.md), [15](docs/15-mcp-resources-and-prompts-design.md) |
| Phase 2-4 | [05](docs/05-domain-model-persistence-and-task-job-model.md), [07](docs/07-device-control-and-high-risk-operations-safeguards.md) |
| Testing | [10](docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md), [13](docs/13-python-coding-standards-and-conventions.md) |
| Operations | [08](docs/08-observability-logging-metrics-and-diagnostics.md), [09](docs/09-operations-deployment-self-update-and-runbook.md) |

---

**Tip**: Print this checklist and check off items as you complete them. Each phase builds on the previous one - complete testing before moving to the next phase.
