# Mypy Type Checking Restoration Plan

## Current Status

- **Baseline errors**: ~1100 errors across 77 files
- **CI status**: Deferred to `continue-on-error: true` (non-blocking)
- **Reason**: Numerous baseline type issues inherited from initial implementation; gradual cleanup preferred over blocking CI

## Strategy

### Phase 1: Core Module Coverage (Weeks 1–2)
Target the most critical entry points first:

1. **routeros_mcp/config.py** – Configuration and settings validation
   - Type critical since it bootstraps the entire app
   - Estimated fixes: 50–100 errors
   
2. **routeros_mcp/cli.py** – CLI argument parsing and entry point
   - Relatively isolated; low churn
   - Estimated fixes: 30–50 errors
   
3. **routeros_mcp/main.py** – Application startup and server initialization
   - Must-have for MCP protocol correctness
   - Estimated fixes: 40–80 errors

4. **routeros_mcp/security/** – Authentication and authorization
   - High-security impact; worth validating types
   - Estimated fixes: 60–100 errors

**Action**: Target 200–330 errors fixed; scope mypy to these modules in CI once clean.

### Phase 2: Service Layer (Weeks 3–4)
Once core is stable, move to domain services:

1. **routeros_mcp/domain/services/** – Business logic layer
   - Services are heavily used; type validation helps prevent bugs
   - Estimated: 300–400 errors

2. **routeros_mcp/infra/db/** – Database session management
   - SQLAlchemy integration; worth typing well
   - Estimated: 50–100 errors

**Action**: Expand mypy scope to include all of `routeros_mcp/domain/` and `routeros_mcp/infra/`.

### Phase 3: Tools and Resources (Weeks 5–6)
Add type checking to MCP-specific code:

1. **routeros_mcp/mcp_tools/** – Tool implementations (34 tools)
   - High-user-facing; type safety helps
   - Estimated: 200–300 errors

2. **routeros_mcp/mcp_resources/** – Resource providers
   - JSON-RPC interfaces; types document contracts
   - Estimated: 100–150 errors

3. **routeros_mcp/mcp_prompts/** – Jinja2 prompt templates
   - Low priority; can defer
   - Estimated: 50–100 errors

**Action**: Full package `routeros_mcp/` coverage.

### Phase 4: Tests (Weeks 7–8)
Lastly, type-check test code:

- **tests/unit/** – Unit tests (564 tests)
- **tests/smoke/** – Smoke tests (55 tests)
- **tests/e2e/** – End-to-end tests (19 tests)

**Action**: `uv run mypy routeros_mcp tests` passes; restore `continue-on-error: false` in CI.

## Implementation Steps

1. **Weekly audit**: Run `uv run mypy routeros_mcp --report-dir=mypy-report` and prioritize by module error count.
2. **Targeted fixes**: Focus on one module per PR; add type hints incrementally.
3. **CI gating**: Update workflows to scope mypy to completed modules as they achieve 0 errors.
4. **Documentation**: Reference [docs/13-python-coding-standards-and-conventions.md](13-python-coding-standards-and-conventions.md) for type annotation guidelines.

## Quick Reference: Current Mypy Config

```toml
[tool.mypy]
python_version = "3.11"
warn_return_any = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
strict_equality = true
# See pyproject.toml for full config and ignores per module (asyncssh, apscheduler, fastmcp, etc.)
```

## Links

- [Mypy docs](https://mypy.readthedocs.io/)
- Project type standards: [docs/13-python-coding-standards-and-conventions.md](13-python-coding-standards-and-conventions.md)
- CI workflows: [.github/workflows/copilot-agent-ci.yml](.github/workflows/copilot-agent-ci.yml)
