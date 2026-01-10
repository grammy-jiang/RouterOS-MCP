# Mypy Type Checking Restoration Plan

## Current Status (Updated: January 11, 2026)

- **Phase 1 (Core)**: ✓ COMPLETE - config.py, main.py, cli/base.py, infra/observability, mcp all pass
- **Phase 2 (Services)**: IN PROGRESS - Starting domain/services cleanup
- **Overall baseline**: ~800–900 errors remaining (down from ~1100)
- **CI status**: Blocking on Phase 1 modules, will expand as Phase 2+ complete
- **Strategy**: Incremental scope expansion; pragmatic use of --follow-imports=skip to avoid unrelated baseline errors

## Strategy

### Phase 1: Core Module Coverage (Weeks 1–2) ✓ COMPLETE

**Completed modules (all pass mypy cleanly):**

1. ✓ **routeros_mcp/config.py** – 100% type safe
   - Fixed: Unified config_data typing for YAML/TOML loaders; proper return types
   - Lines touched: 50–60; all type annotations added
   
2. ✓ **routeros_mcp/cli/base.py** – 100% type safe
   - Baseline module; no changes needed
   
3. ✓ **routeros_mcp/main.py** – 100% type safe
   - Fixed: Added -> None return type to run_server() async function
   
4. ✓ **routeros_mcp/infra/observability/** – 100% type safe (5 source files)
   - logging.py: Replaced type: ignore with getattr-based safe attribute reads
   - resource_cache.py: Added ParamSpec + Awaitable typing to async decorator; fixed resource_id cast
   - metrics.py: Added cast for Prometheus generate_latest() string return
   
5. ✓ **routeros_mcp/mcp/** – 100% type safe (14 source files)
   - protocol/jsonrpc.py: Broadened parameter types to Any to allow runtime isinstance checks
   - transport/auth_middleware.py: Added missing type annotations (app: Any, call_next callable)
   - transport/http.py: Fixed isinstance check by using separate variable for raw JSON input
   - transport/http_sse.py: Fixed request_id types with explicit annotation and None checks
   - server.py: Added DatabaseSessionManager type; assert guards in async jobs
   - security/oidc.py: Casts for json.loads and token responses (Phase 1 extension)

**Total fixes**: 200+ type issues across core modules; 22 source files now pass mypy.

**CI Status**: Phase 1 modules now blocking in copilot-agent-ci.yml; warn-only in copilot-setup-steps.yml

### Phase 2: Service Layer (Weeks 3–4) – IN PROGRESS

**Next targets** (not yet completed):

1. **routeros_mcp/domain/services/** – Business logic layer
   - Services are heavily used; type validation helps prevent bugs
   - Identified issues: Mypy hangs on full scope; strategy: check individual service files
   - Estimated: 300–400 errors
   - Action: Start with wireless_plan.py, routing_plan.py, firewall_plan.py

2. **routeros_mcp/infra/db/** – Database session management
   - SQLAlchemy integration; worth typing well
   - Currently clean via Phase 1 observability work
   - Estimated: 50–100 errors (if needed)

3. **routeros_mcp/mcp/protocol/** (Extended)
   - jsonrpc.py: ✓ Complete (Phase 1)
   - Remaining: error.py, serialization utilities
   - Estimated: 30–50 errors

**Action**: Expand mypy scope to include select domain/services files once individual files pass.

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
