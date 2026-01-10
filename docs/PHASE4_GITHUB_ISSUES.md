# Phase 4 GitHub Issues - Multi-Device Coordination & Diagnostics

**Generated**: 2026-01-05
**Reference**: [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md)

This document contains GitHub issues for Phase 4 implementation, organized by sprint and priority. Each issue follows GitHub Copilot agent best practices for optimal autonomous execution.

---

## Sprint 1-2: HTTP/SSE Foundation (80-120 hours)

### Issue #1: Add sse-starlette dependency to project

**Priority**: P0 (Critical - blocks HTTP/SSE transport)
**Estimated effort**: 15-20 minutes
**Labels**: `phase-4`, `infrastructure`, `good-first-agent-task`

#### Context
The HTTP/SSE transport implementation requires the `sse-starlette` library for Server-Sent Events support, but it's currently missing from dependencies. This blocks completion of 11 skipped E2E tests.

#### Change Request
Add `sse-starlette` to the project dependencies with proper version constraints.

#### Acceptance Criteria
- [ ] `sse-starlette>=1.8.0,<2.0.0` added to `pyproject.toml` under `dependencies`
- [ ] Run `uv pip install -e ".[dev]"` successfully installs the new dependency
- [ ] No dependency conflicts reported by `uv`
- [ ] `uv.lock` file is updated

#### Files to Modify
- `pyproject.toml` - Add `sse-starlette` to dependencies list

#### Do Not Change
- Existing dependencies or version constraints
- Dev dependencies section
- Optional dependencies

#### How to Build & Test
```bash
# Install dependencies
uv pip install -e ".[dev]"

# Verify sse-starlette is installed
python -c "import sse_starlette; print(sse_starlette.__version__)"

# Run existing tests to ensure no breakage
uv run pytest tests/smoke -q --maxfail=1
```

#### Reference Documentation
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#11-http-server-implementation) - Section 1.1
- [pyproject.toml](../pyproject.toml) - Current dependencies

---

### Issue #2: Complete HTTPSSETransport._process_mcp_request() integration with FastMCP

**Priority**: P0 (Critical - core HTTP transport)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `http-transport`, `high-priority`

#### Context
The HTTP/SSE transport scaffold exists in `routeros_mcp/mcp/transport/http_sse.py`, but `_process_mcp_request()` is not fully wired to integrate with FastMCP. This method must accept JSON-RPC requests from HTTP POST, route to appropriate MCP tools, and return JSON-RPC responses.

Current status: Method stub exists but lacks implementation. This blocks 7 skipped HTTP E2E tests.

#### Change Request
Complete the `_process_mcp_request()` method to:
1. Parse incoming JSON-RPC request
2. Route to FastMCP tool via `self.mcp` instance
3. Handle tool execution
4. Return proper JSON-RPC response or error

#### Acceptance Criteria
- [ ] `_process_mcp_request()` accepts `Request` object and returns JSON-RPC response
- [ ] Method validates JSON-RPC format (id, method, params)
- [ ] Method routes to FastMCP tool using existing `self.mcp` instance
- [ ] Successful tool execution returns JSON-RPC 2.0 result
- [ ] Tool errors return proper JSON-RPC error responses
- [ ] Add unit tests for request parsing, tool routing, and error handling
- [ ] Run `pytest tests/unit/mcp/transport/test_http_sse.py -v` passes all tests

#### Files to Modify
- `routeros_mcp/mcp/transport/http_sse.py` - Complete `_process_mcp_request()` method
- `tests/unit/mcp/transport/test_http_sse.py` - Add unit tests for new functionality

#### Do Not Change
- FastMCP SDK integration in `mcp/server.py`
- JSON-RPC protocol helpers in `mcp/protocol/jsonrpc.py` (use these, don't rewrite)
- Existing HTTP endpoints structure

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/mcp/transport/test_http_sse.py -v

# Run integration test (will still skip some E2E until full wiring)
uv run pytest tests/e2e/test_http_transport_clients.py -v

# Verify JSON-RPC handling
python -m routeros_mcp.mcp.transport.http_sse  # If has __main__
```

#### Known Edge Cases
- Invalid JSON in request body should return JSON-RPC parse error (-32700)
- Missing method field should return invalid request error (-32600)
- Unknown tool name should return method not found error (-32601)
- Tool execution exceptions should be caught and returned as JSON-RPC errors

#### Reference Documentation
- [docs/14](../docs/14-mcp-protocol-integration-and-transport-design.md) - MCP protocol design
- [docs/19](../docs/19-json-rpc-error-codes-and-mcp-protocol-specification.md) - JSON-RPC error codes
- `routeros_mcp/mcp/protocol/jsonrpc.py` - Existing JSON-RPC helpers

---

### Issue #3: Wire HTTP mode in mcp/server.py to start HTTPSSETransport

**Priority**: P0 (Critical - enables HTTP mode)
**Estimated effort**: 1-2 hours
**Labels**: `phase-4`, `http-transport`, `high-priority`

#### Context
Currently, `mcp/server.py` only supports STDIO transport. Phase 4 adds HTTP/SSE transport support, but the server doesn't check `settings.mcp_transport` and start the appropriate transport.

When `settings.mcp_transport == "http"`, the server should start `HTTPSSETransport` instead of STDIO.

#### Change Request
Modify `mcp/server.py` to:
1. Check `settings.mcp_transport` value
2. If `"http"`, start `HTTPSSETransport` with configured host/port
3. If `"stdio"` (default), continue using existing STDIO transport
4. Log which transport is being used

#### Acceptance Criteria
- [ ] `create_mcp_server()` checks `settings.mcp_transport`
- [ ] HTTP transport starts when `mcp_transport="http"` in config
- [ ] STDIO transport continues to work when `mcp_transport="stdio"`
- [ ] Server logs clearly indicate which transport is active
- [ ] HTTP server listens on configured `mcp_http_host` and `mcp_http_port`
- [ ] Add integration test that starts server in HTTP mode
- [ ] Run `pytest tests/unit/test_mcp_server_transport.py -v` passes

#### Files to Modify
- `routeros_mcp/mcp/server.py` - Add transport selection logic in `create_mcp_server()`
- `tests/unit/test_mcp_server_transport.py` - Add test for HTTP mode selection

#### Do Not Change
- Existing STDIO transport logic
- FastMCP SDK integration
- Tool registration logic

#### How to Build & Test
```bash
# Test HTTP mode locally
# Create test config
cat > config/test_http.yaml <<EOF
mcp_transport: http
mcp_http_host: 127.0.0.1
mcp_http_port: 8080
environment: lab
EOF

# Start server (in background)
uv run routeros-mcp --config config/test_http.yaml &
SERVER_PID=$!

# Verify HTTP endpoint responds
sleep 5
curl -X POST http://127.0.0.1:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "method": "echo", "params": {"message": "test"}, "id": 1}'

# Cleanup
kill $SERVER_PID

# Run unit tests
uv run pytest tests/unit/test_mcp_server_transport.py -v
```

#### Reference Documentation
- [docs/14](../docs/14-mcp-protocol-integration-and-transport-design.md) - Transport design
- [docs/17](../docs/17-configuration-specification.md) - Settings configuration
- Existing `routeros_mcp/mcp/server.py` for STDIO transport reference

---

### Issue #4: Implement OAuth/OIDC middleware for bearer token validation

**Priority**: P0 (Critical - HTTP security)
**Estimated effort**: 3-4 hours
**Labels**: `phase-4`, `security`, `http-transport`

#### Context
Phase 4 HTTP transport requires authentication. For Phase 4, we use a single service account with bearer token validation (per-user OAuth 2.1 is Phase 5).

The middleware must:
- Extract `Authorization: Bearer <token>` header
- Validate token with OIDC provider (introspection endpoint)
- Cache validated tokens (5-minute TTL)
- Return 401 Unauthorized on invalid tokens

#### Change Request
Enhance `routeros_mcp/mcp/transport/auth_middleware.py` to add bearer token validation:
1. Extract bearer token from Authorization header
2. Validate with OIDC provider introspection endpoint
3. Cache validated tokens in memory (5-min TTL)
4. Return 401 with clear error on validation failure

#### Acceptance Criteria
- [ ] Middleware extracts `Authorization: Bearer <token>` header
- [ ] Token validation calls OIDC introspection endpoint
- [ ] Validated tokens are cached (5-minute TTL, in-memory)
- [ ] Invalid tokens return 401 with JSON error: `{"error": "unauthorized", "message": "Invalid token"}`
- [ ] Missing Authorization header returns 401 with clear message
- [ ] Add settings for OIDC configuration (provider URL, client ID, client secret)
- [ ] Add unit tests for token validation, caching, and error cases
- [ ] Run `pytest tests/unit/mcp/transport/test_auth_middleware.py -v` passes

#### Files to Modify
- `routeros_mcp/mcp/transport/auth_middleware.py` - Add token validation logic
- `routeros_mcp/config.py` - Add OIDC service account settings
- `tests/unit/mcp/transport/test_auth_middleware.py` - Add comprehensive tests

#### Do Not Change
- Existing authorization logic
- User session handling (Phase 5 feature)
- Role-based access control (Phase 5 feature)

#### How to Build & Test
```bash
# Run unit tests with mocked OIDC provider
uv run pytest tests/unit/mcp/transport/test_auth_middleware.py -v

# Manual test with mock OIDC server (optional)
# See tests/e2e/test_oidc_flow.py for example mock setup

# Verify settings validation
python -c "from routeros_mcp.config import Settings; s = Settings(oidc_enabled=True); print(s.oidc_provider_url)"
```

#### Known Edge Cases
- Network timeout to OIDC provider should fail open or closed? (Fail closed: return 401)
- Expired tokens in cache should be evicted automatically
- Concurrent token validation requests should not duplicate OIDC calls

#### Reference Documentation
- [docs/02](../docs/02-security-oauth-integration-and-access-control.md) - Security model
- [docs/21-24](../docs/21-oauth-setup-azure-ad.md) - OAuth setup guides
- Existing `routeros_mcp/security/oidc.py` for OIDC client logic

---

### Issue #5: Implement SSE resource subscription endpoint

**Priority**: P1 (High - enables real-time monitoring)
**Estimated effort**: 3-4 hours
**Labels**: `phase-4`, `sse`, `resources`

#### Context
MCP resources should support subscriptions for real-time updates. Phase 4 adds SSE (Server-Sent Events) subscriptions for `device://{device_id}/health` resources.

Currently, `routeros_mcp/mcp/transport/sse_manager.py` has subscription scaffolding but `subscribe()` is incomplete.

#### Change Request
Complete `SSEManager.subscribe()` to:
1. Validate resource URI is subscribable (device health only in Phase 4)
2. Register subscription with connection ID
3. Start periodic updates (every 30 seconds) from health check database
4. Send SSE events to subscribed clients
5. Clean up on connection drop

#### Acceptance Criteria
- [ ] `SSEManager.subscribe(uri)` validates URI format and subscribability
- [ ] Only `device://{device_id}/health` URIs are subscribable in Phase 4
- [ ] Subscription sends SSE events every 30 seconds with current health data
- [ ] SSE events use format: `event: health\ndata: {JSON}\n\n`
- [ ] Connection drop removes subscription and stops updates
- [ ] Add unit tests for subscription lifecycle
- [ ] Run `pytest tests/unit/mcp/transport/test_sse_manager.py -v` passes
- [ ] Fix 4 skipped SSE metrics tests

#### Files to Modify
- `routeros_mcp/mcp/transport/sse_manager.py` - Complete `subscribe()` method
- `routeros_mcp/mcp_resources/device.py` - Mark health resource as `subscribable=True`
- `tests/unit/mcp/transport/test_sse_manager.py` - Add subscription tests

#### Do Not Change
- SSE event format (use existing `sse_events.py` helpers)
- Health check collection logic
- Database schema

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/mcp/transport/test_sse_manager.py -v

# Run SSE subscription E2E test
uv run pytest tests/e2e/test_sse_subscriptions.py -v

# Manual SSE test (requires running HTTP server)
curl -N http://localhost:8080/sse/subscribe \
  -H "Accept: text/event-stream" \
  -d '{"uri": "device://dev-001/health"}'
```

#### Known Edge Cases
- Device health not found should return error event, not crash subscription
- Multiple subscriptions to same resource should share underlying query
- Subscription cleanup must not leave zombie background tasks

#### Reference Documentation
- [docs/14](../docs/14-mcp-protocol-integration-and-transport-design.md#sse-subscriptions) - SSE design
- [docs/15](../docs/15-mcp-resources-and-prompts-design.md) - Resource design
- Existing SSE event tests in `tests/e2e/test_sse_subscriptions.py`

---

### Issue #6: Add SSE connection and subscription metrics to Prometheus

**Priority**: P2 (Medium - observability)
**Estimated effort**: 1-2 hours
**Labels**: `phase-4`, `metrics`, `observability`

#### Context
Phase 4 adds SSE subscriptions but lacks metrics for monitoring connection health and subscription activity. This blocks 4 skipped SSE metrics tests.

We need Prometheus metrics for:
- Active SSE connections
- Active subscriptions per resource type
- Events sent per subscription
- Subscription errors/timeouts

#### Change Request
Add SSE metrics to `routeros_mcp/infra/observability/metrics.py` and instrument `SSEManager`:
1. Counter: `sse_events_sent_total` (labels: resource_type, device_id)
2. Gauge: `sse_active_connections`
3. Gauge: `sse_active_subscriptions` (labels: resource_uri)
4. Counter: `sse_subscription_errors_total` (labels: error_type)

#### Acceptance Criteria
- [ ] 4 new Prometheus metrics defined in `metrics.py`
- [ ] `SSEManager` increments metrics on connection/subscription events
- [ ] Metrics are exposed via existing `/metrics` endpoint
- [ ] Add unit tests verifying metrics are incremented
- [ ] Run `pytest tests/unit/mcp/transport/test_sse_manager_metrics.py -v` passes (currently 5 skipped)

#### Files to Modify
- `routeros_mcp/infra/observability/metrics.py` - Add SSE metrics definitions
- `routeros_mcp/mcp/transport/sse_manager.py` - Instrument with metrics
- `tests/unit/mcp/transport/test_sse_manager_metrics.py` - Unskip and fix tests

#### Do Not Change
- Existing Prometheus metrics
- Metrics export endpoint
- SSE core functionality

#### How to Build & Test
```bash
# Run metrics tests
uv run pytest tests/unit/mcp/transport/test_sse_manager_metrics.py -v

# Verify metrics exposed
curl http://localhost:8080/metrics | grep sse_

# Example output:
# sse_events_sent_total{device_id="dev-001",resource_type="health"} 42
# sse_active_connections 3
```

#### Reference Documentation
- [docs/08](../docs/08-observability-logging-metrics-and-diagnostics.md) - Observability design
- Existing metrics in `routeros_mcp/infra/observability/metrics.py`

---

## Sprint 3-4: Diagnostics & Streaming (68-100 hours)

### Issue #7: Implement JSON-RPC streaming protocol support

**Priority**: P0 (Critical - enables diagnostics streaming)
**Estimated effort**: 4-5 hours
**Labels**: `phase-4`, `json-rpc`, `diagnostics`

#### Context
Diagnostics tools (ping, traceroute, bandwidth-test) are long-running operations that need to stream progress updates. Standard JSON-RPC returns a single response, but we need multiple progress messages followed by a final result.

Phase 4 adds `stream_progress=true` parameter support to JSON-RPC protocol.

#### Change Request
Extend `routeros_mcp/mcp/protocol/jsonrpc.py` to support streaming:
1. Accept optional `stream_progress` parameter in requests
2. Allow tools to yield progress messages
3. Send progress as SSE events (if HTTP transport)
4. Send final result with `result` field
5. Document streaming protocol in code comments

#### Acceptance Criteria
- [ ] JSON-RPC request can include `"stream_progress": true` parameter
- [ ] Tools can yield progress dictionaries: `{"type": "progress", "message": "...", "percent": 50}`
- [ ] HTTP transport sends progress as SSE events: `event: progress\ndata: {...}\n\n`
- [ ] Final result sent as SSE event: `event: result\ndata: {"result": {...}}\n\n`
- [ ] STDIO transport collects progress and returns final result only (no streaming)
- [ ] Add unit tests for streaming request handling
- [ ] Run `pytest tests/unit/test_jsonrpc_protocol.py -v` passes

#### Files to Modify
- `routeros_mcp/mcp/protocol/jsonrpc.py` - Add streaming support
- `routeros_mcp/mcp/transport/http_sse.py` - Wire streaming to SSE
- `tests/unit/test_jsonrpc_protocol.py` - Add streaming tests

#### Do Not Change
- Existing non-streaming JSON-RPC behavior
- Error response format
- STDIO transport (remains non-streaming)

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/test_jsonrpc_protocol.py -v

# Manual streaming test (requires HTTP server running)
curl -N http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tool/ping",
    "params": {"device_id": "dev-001", "target": "8.8.8.8", "count": 4, "stream_progress": true},
    "id": 1
  }'

# Expected output:
# event: progress
# data: {"type":"progress","message":"Reply from 8.8.8.8: 25ms","percent":25}
# ...
# event: result
# data: {"result":{"packets_sent":4,"avg_latency":25}}
```

#### Reference Documentation
- [docs/14](../docs/14-mcp-protocol-integration-and-transport-design.md) - MCP protocol
- [docs/19](../docs/19-json-rpc-error-codes-and-mcp-protocol-specification.md) - JSON-RPC spec
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#31-json-rpc-streaming-support) - Streaming design

---

### Issue #8: Implement tool/ping MCP tool with rate limiting

**Priority**: P1 (High - first diagnostics tool)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `diagnostics`, `tools`

#### Context
Phase 1 deferred diagnostics tools to Phase 4. The `tool/ping` tool sends ICMP ping from a RouterOS device to verify connectivity and measure latency.

This is the first diagnostics tool and establishes the pattern for traceroute and bandwidth-test.

#### Change Request
Implement `ping()` tool in `routeros_mcp/mcp_tools/diagnostics.py`:
1. Accept parameters: device_id, target, count (default: 4), packet_size (default: 64)
2. Call RouterOS REST API: `POST /rest/tool/ping`
3. Support streaming progress if `stream_progress=true`
4. Implement rate limiting: max 10 pings per device per minute
5. Return summary: packets sent/received/lost, avg/min/max latency

#### Acceptance Criteria
- [ ] `@mcp.tool()` decorator registers `ping` tool
- [ ] Tool validates parameters (target is IP/hostname, count is 1-100, packet_size is 28-65500)
- [ ] Calls RouterOS endpoint `POST /rest/tool/ping` with correct parameters
- [ ] Implements rate limiting: 10 pings/device/minute (returns 429 if exceeded)
- [ ] Streams per-packet results if `stream_progress=true`
- [ ] Returns summary: `{"packets_sent": 4, "packets_received": 3, "packet_loss_percent": 25, "avg_latency_ms": 25}`
- [ ] Add unit tests for validation, rate limiting, and result parsing
- [ ] Run `pytest tests/unit/test_mcp_tools_diagnostics.py::test_ping -v` passes

#### Files to Modify
- `routeros_mcp/mcp_tools/diagnostics.py` - Add `ping()` function (currently has scaffold)
- `routeros_mcp/domain/services/diagnostics.py` - Add `ping_host()` method
- `tests/unit/test_mcp_tools_diagnostics.py` - Add ping tests

#### Do Not Change
- Existing diagnostics.py structure
- REST client interface
- Rate limiting mechanism (reuse existing pattern)

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/test_mcp_tools_diagnostics.py::test_ping -v

# E2E test with mock RouterOS device
uv run pytest tests/e2e/test_diagnostics_tools.py::test_ping_e2e -v

# Manual test (requires lab device)
python -c "
from routeros_mcp.mcp_tools.diagnostics import ping
result = ping(device_id='lab-device-001', target='8.8.8.8', count=4)
print(result)
"
```

#### Known Edge Cases
- Target unreachable should return 0% packets received, not error
- Invalid target (not IP or hostname) should return validation error before calling RouterOS
- Timeout (30s) should be enforced, return partial results if timeout exceeded

#### Reference Documentation
- [docs/03](../docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md#diagnostics-endpoints) - RouterOS ping endpoint
- [docs/04](../docs/04-mcp-tools-interface-and-json-schema-specification.md) - Tool specifications
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#32-toolping-implementation) - Ping design

---

### Issue #9: Implement tool/traceroute MCP tool with streaming

**Priority**: P1 (High - diagnostics tool)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `diagnostics`, `tools`

#### Context
Second diagnostics tool for Phase 4. Traceroute traces network path from RouterOS device to target, showing all hops along the way.

This tool demonstrates streaming progress (per-hop updates) using the JSON-RPC streaming protocol from Issue #7.

#### Change Request
Implement `traceroute()` tool in `routeros_mcp/mcp_tools/diagnostics.py`:
1. Accept parameters: device_id, target, max_hops (default: 30)
2. Call RouterOS REST API: `POST /rest/tool/traceroute`
3. Stream per-hop results if `stream_progress=true`
4. Return final result with all hops and success status

#### Acceptance Criteria
- [ ] `@mcp.tool()` decorator registers `traceroute` tool
- [ ] Tool validates parameters (target is IP/hostname, max_hops is 1-64)
- [ ] Calls RouterOS endpoint `POST /rest/tool/traceroute`
- [ ] Streams per-hop updates: `{"type": "progress", "hop": 3, "ip": "10.0.0.1", "latency_ms": 12}`
- [ ] Returns final result: `{"hops": [...], "total_hops": 8, "reached_target": true}`
- [ ] Timeout: 60 seconds
- [ ] Add unit tests for validation and result parsing
- [ ] Run `pytest tests/unit/test_mcp_tools_diagnostics.py::test_traceroute -v` passes

#### Files to Modify
- `routeros_mcp/mcp_tools/diagnostics.py` - Add `traceroute()` function
- `routeros_mcp/domain/services/diagnostics.py` - Add `traceroute_host()` method
- `tests/unit/test_mcp_tools_diagnostics.py` - Add traceroute tests

#### Do Not Change
- Existing diagnostics tools
- Streaming protocol (use from Issue #7)
- REST client interface

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/test_mcp_tools_diagnostics.py::test_traceroute -v

# E2E test with streaming
uv run pytest tests/e2e/test_diagnostics_tools.py::test_traceroute_streaming -v

# Manual streaming test (requires HTTP server + lab device)
curl -N http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tool/traceroute",
    "params": {"device_id": "lab-001", "target": "8.8.8.8", "stream_progress": true},
    "id": 1
  }'
```

#### Known Edge Cases
- Some hops may timeout (* in output) - return null for that hop
- Target may be unreachable before max_hops - set `reached_target: false`
- Streaming must handle connection drop gracefully

#### Reference Documentation
- [docs/03](../docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md#diagnostics-endpoints) - RouterOS traceroute endpoint
- [docs/04](../docs/04-mcp-tools-interface-and-json-schema-specification.md) - Tool specifications
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#33-tooltraceroute-implementation) - Traceroute design

---

### Issue #10: Implement tool/bandwidth-test MCP tool with capability check

**Priority**: P1 (High - diagnostics tool)
**Estimated effort**: 3-4 hours
**Labels**: `phase-4`, `diagnostics`, `tools`

#### Context
Third and final diagnostics tool for Phase 4. Bandwidth test measures throughput between two RouterOS devices. This is a professional-tier tool (high resource usage) and requires target device capability.

#### Change Request
Implement `bandwidth_test()` tool in `routeros_mcp/mcp_tools/diagnostics.py`:
1. Accept parameters: device_id, target_device_id, duration (default: 10), direction (tx/rx/both)
2. Validate target device has `allow_bandwidth_test=true` capability
3. Call RouterOS REST API: `POST /rest/tool/bandwidth-test`
4. Stream throughput updates every second if `stream_progress=true`
5. Return final result: avg TX/RX throughput, packet loss

#### Acceptance Criteria
- [ ] `@mcp.tool()` decorator registers `bandwidth_test` tool
- [ ] Tool validates target device has `allow_bandwidth_test=true` capability (return error if not)
- [ ] Validates parameters (duration is 5-60s, direction is valid enum)
- [ ] Calls RouterOS endpoint with target device IP
- [ ] Streams throughput updates: `{"type": "progress", "elapsed_s": 3, "tx_mbps": 850, "rx_mbps": 920}`
- [ ] Returns final: `{"avg_tx_mbps": 850, "avg_rx_mbps": 920, "packet_loss_percent": 0.1}`
- [ ] Timeout: 180 seconds (3 minutes)
- [ ] Tool tier: `professional` (high resource usage)
- [ ] Add unit tests including capability check
- [ ] Run `pytest tests/unit/test_mcp_tools_diagnostics.py::test_bandwidth_test -v` passes

#### Files to Modify
- `routeros_mcp/mcp_tools/diagnostics.py` - Add `bandwidth_test()` function
- `routeros_mcp/domain/services/diagnostics.py` - Add `test_bandwidth()` method
- `routeros_mcp/domain/models.py` - Add `allow_bandwidth_test` to Device model if missing
- `tests/unit/test_mcp_tools_diagnostics.py` - Add bandwidth-test tests

#### Do Not Change
- Existing diagnostics tools
- Device capability system
- Streaming protocol

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/test_mcp_tools_diagnostics.py::test_bandwidth_test -v

# Test capability check enforcement
python -c "
from routeros_mcp.mcp_tools.diagnostics import bandwidth_test
# Should raise error if target doesn't allow bandwidth test
try:
    bandwidth_test(device_id='dev-001', target_device_id='dev-002', duration=10)
except ValueError as e:
    print(f'Expected error: {e}')
"

# E2E test (requires two lab devices with capability enabled)
uv run pytest tests/e2e/test_diagnostics_tools.py::test_bandwidth_test_e2e -v
```

#### Known Edge Cases
- Target device offline should return clear error before starting test
- Network partition during test should timeout gracefully
- Target device must be RouterOS (cannot test to external host)

#### Reference Documentation
- [docs/03](../docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md#diagnostics-endpoints) - RouterOS bandwidth-test endpoint
- [docs/04](../docs/04-mcp-tools-interface-and-json-schema-specification.md) - Tool specifications, professional tier
- [docs/07](../docs/07-device-control-and-high-risk-operations-safeguards.md) - Professional tool safeguards
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#34-toolbandwidth-test-implementation) - Bandwidth-test design

---

## Sprint 5-7: Multi-Device Coordination (100-150 hours)

### Issue #11: Enhance Job model with progress tracking fields

**Priority**: P0 (Critical - enables multi-device coordination)
**Estimated effort**: 1-2 hours
**Labels**: `phase-4`, `multi-device`, `database`

#### Context
Multi-device coordination requires job-based execution to track progress across multiple devices. Current `Job` model lacks progress tracking fields.

Phase 4 adds: progress percentage, current device ID, per-device results, and cancellation support.

#### Change Request
Enhance `Job` model in `routeros_mcp/infra/db/models.py` with new fields:
1. `progress_percent` (Integer, 0-100)
2. `current_device_id` (UUID, nullable, foreign key to Device)
3. `result_summary` (JSON, stores per-device results)
4. `cancellation_requested` (Boolean, default False)

Create Alembic migration for schema change.

#### Acceptance Criteria
- [ ] Add 4 new fields to `Job` SQLAlchemy model
- [ ] Create Alembic migration: `alembic revision --autogenerate -m "Add job progress tracking fields"`
- [ ] Migration applies successfully: `alembic upgrade head`
- [ ] Migration rollback works: `alembic downgrade -1`
- [ ] Add database constraints (progress_percent 0-100)
- [ ] Update existing job creation to set defaults (progress_percent=0, cancellation_requested=False)
- [ ] Run `pytest tests/unit/test_models.py -v` passes

#### Files to Modify
- `routeros_mcp/infra/db/models.py` - Add fields to Job model
- `alembic/versions/*_add_job_progress_fields.py` - New migration (generated)
- `tests/unit/test_models.py` - Add tests for new fields

#### Do Not Change
- Existing Job model fields
- Job state machine transitions
- Job service logic (separate issue)

#### How to Build & Test
```bash
# Generate migration
uv run alembic revision --autogenerate -m "Add job progress tracking fields"

# Apply migration
uv run alembic upgrade head

# Verify schema
sqlite3 data/routeros_mcp_lab.db ".schema jobs"

# Rollback test
uv run alembic downgrade -1
uv run alembic upgrade head

# Run model tests
uv run pytest tests/unit/test_models.py::test_job_model -v
```

#### Reference Documentation
- [docs/05](../docs/05-domain-model-persistence-and-task-job-model.md) - Job model design
- [docs/18](../docs/18-database-schema-and-orm-specification.md) - Database schema
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#21-job-based-execution-engine) - Job enhancements

---

### Issue #12: Implement job cancellation in JobService

**Priority**: P1 (High - job control)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `multi-device`, `jobs`

#### Context
Multi-device jobs can run for several minutes. Users need ability to cancel long-running jobs gracefully (finish current device, halt next batch).

Phase 4 adds cancellation support with graceful shutdown.

#### Change Request
Enhance `JobService` in `routeros_mcp/domain/services/job.py` to:
1. Add `request_cancellation(job_id)` method to set `cancellation_requested=True`
2. Modify job execution loop to check `cancellation_requested` flag
3. On cancellation: finish current device, mark job as `cancelled`, store partial results
4. Add job status endpoint: `GET /api/admin/jobs/{job_id}`

#### Acceptance Criteria
- [ ] `request_cancellation(job_id)` sets `cancellation_requested=True` in database
- [ ] Job execution loop checks flag after each device
- [ ] On flag=True: finish current device, transition to `cancelled` state
- [ ] Partial results stored in `result_summary` JSON field
- [ ] Add API endpoint: `GET /api/admin/jobs/{job_id}` returns job status + progress
- [ ] Add unit tests for cancellation scenarios
- [ ] Run `pytest tests/unit/test_plan_job_services.py::test_job_cancellation -v` passes

#### Files to Modify
- `routeros_mcp/domain/services/job.py` - Add cancellation logic
- `routeros_mcp/api/admin.py` - Add job status endpoint
- `tests/unit/test_plan_job_services.py` - Add cancellation tests

#### Do Not Change
- Job state machine (add `cancelled` state if needed)
- Job creation logic
- APScheduler integration

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/test_plan_job_services.py::test_job_cancellation -v

# Manual test (requires running server)
# 1. Start a long-running job
curl -X POST http://localhost:8080/api/admin/plans/plan-123/apply

# 2. Get job ID from response, then cancel
curl -X POST http://localhost:8080/api/admin/jobs/job-456/cancel

# 3. Check status
curl http://localhost:8080/api/admin/jobs/job-456
# Expected: {"status": "cancelled", "progress_percent": 40, "result_summary": {...}}
```

#### Known Edge Cases
- Cancellation during device apply should let current device finish (atomic operation)
- Cancelled jobs should be clearly marked in audit log
- Re-starting cancelled job should not be possible (must create new plan)

#### Reference Documentation
- [docs/05](../docs/05-domain-model-persistence-and-task-job-model.md) - Job lifecycle
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#21-job-based-execution-engine) - Job design

---

### Issue #13: Implement multi-device plan creation in PlanService

**Priority**: P0 (Critical - multi-device core)
**Estimated effort**: 4-5 hours
**Labels**: `phase-4`, `multi-device`, `plan-apply`

#### Context
Phase 3 implemented single-device plan/apply. Phase 4 extends to multi-device (2-50 devices) with staged rollout.

This issue implements multi-device plan creation with device validation and batch configuration.

#### Change Request
Enhance `Plan` model and `PlanService`:
1. Add fields to Plan model: `device_ids` (list), `batch_size` (default: 5), `pause_seconds_between_batches` (default: 60), `rollback_on_failure` (boolean)
2. Add `create_multi_device_plan()` method in PlanService
3. Validate all devices are reachable before creating plan
4. Calculate batches and store in plan metadata
5. Generate HMAC approval token (reuse existing logic)

#### Acceptance Criteria
- [ ] Plan model has new fields: device_ids, batch_size, pause_seconds_between_batches, rollback_on_failure, device_statuses
- [ ] `create_multi_device_plan()` accepts list of device IDs (2-50 devices)
- [ ] Method validates all devices exist and are reachable
- [ ] Devices divided into batches (configurable size, default: 5)
- [ ] Returns plan ID and approval token
- [ ] Plan metadata includes batch configuration
- [ ] Add unit tests for validation and batch calculation
- [ ] Run `pytest tests/unit/domain/services/test_plan.py::test_multi_device_plan -v` passes

#### Files to Modify
- `routeros_mcp/domain/models.py` - Add fields to Plan model
- `routeros_mcp/domain/services/plan.py` - Add `create_multi_device_plan()` method
- `alembic/versions/*_add_multi_device_plan_fields.py` - New migration
- `tests/unit/domain/services/test_plan.py` - Add multi-device tests

#### Do Not Change
- Single-device plan creation logic
- HMAC token generation
- Plan state machine

#### How to Build & Test
```bash
# Generate and apply migration
uv run alembic revision --autogenerate -m "Add multi-device plan fields"
uv run alembic upgrade head

# Run unit tests
uv run pytest tests/unit/domain/services/test_plan.py::test_multi_device_plan -v

# Manual test
python -c "
from routeros_mcp.domain.services.plan import PlanService
service = PlanService(...)
plan = service.create_multi_device_plan(
    device_ids=['dev-001', 'dev-002', 'dev-003', 'dev-004', 'dev-005', 'dev-006'],
    change_type='dns_ntp',
    batch_size=2
)
print(f'Plan ID: {plan.id}, Batches: {len(plan.batches)}')
"
```

#### Known Edge Cases
- Device count must be 2-50 (reject if out of range)
- All devices must be in same environment (lab/staging/prod)
- Unreachable devices should fail plan creation immediately

#### Reference Documentation
- [docs/05](../docs/05-domain-model-persistence-and-task-job-model.md) - Plan model
- [docs/07](../docs/07-device-control-and-high-risk-operations-safeguards.md) - Multi-device safeguards
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#22-multi-device-planapply-framework) - Multi-device design

---

### Issue #14: Implement staged rollout logic with health checks

**Priority**: P0 (Critical - multi-device safety)
**Estimated effort**: 5-6 hours
**Labels**: `phase-4`, `multi-device`, `plan-apply`, `health-checks`

#### Context
Multi-device plan application must execute in batches (staged rollout) with health checks between batches to prevent cascading failures. This is the core safety mechanism for Phase 4 multi-device operations.

If health checks fail after a batch, rollout must halt and optionally rollback.

#### Change Request
Implement staged rollout in `PlanService.apply_multi_device_plan()`:
1. Divide devices into batches based on `plan.batch_size`
2. Apply changes to batch 1 devices in parallel
3. Run health checks on batch 1 devices
4. If healthy: wait `pause_seconds_between_batches`, proceed to batch 2
5. If degraded: halt rollout, optionally trigger rollback (if `rollback_on_failure=true`)
6. Track per-device status in `plan.device_statuses`

#### Acceptance Criteria
- [ ] `apply_multi_device_plan()` divides devices into batches
- [ ] Batch application runs devices in parallel (within batch)
- [ ] Health checks run after each batch completes
- [ ] Healthy check: CPU <80%, memory <85%, all critical interfaces up
- [ ] Degraded devices halt rollout immediately
- [ ] Pause between batches is configurable (default: 60 seconds)
- [ ] Per-device status tracked: `pending → applying → applied → rolled_back → failed`
- [ ] Add unit tests for rollout scenarios (healthy, degraded, partial failure)
- [ ] Run `pytest tests/unit/domain/services/test_plan.py::test_staged_rollout -v` passes

#### Files to Modify
- `routeros_mcp/domain/services/plan.py` - Add `apply_multi_device_plan()` method
- `routeros_mcp/domain/services/health.py` - Add batch health check method
- `tests/unit/domain/services/test_plan.py` - Add staged rollout tests

#### Do Not Change
- Single-device plan/apply logic
- Health check collection intervals
- Device model

#### How to Build & Test
```bash
# Run unit tests with mock devices
uv run pytest tests/unit/domain/services/test_plan.py::test_staged_rollout -v

# Integration test with 5 mock devices, batch_size=2
uv run pytest tests/integration/test_multi_device_rollout.py -v

# Manual test scenario: healthy rollout
python -c "
from routeros_mcp.domain.services.plan import PlanService
service = PlanService(...)
# Create plan for 6 devices, batch_size=2
plan = service.create_multi_device_plan(device_ids=[...], batch_size=2)
# Apply (should complete 3 batches successfully)
result = service.apply_multi_device_plan(plan.id, approval_token='...')
print(f'Status: {result.status}, Batches completed: {result.batches_completed}')
"
```

#### Known Edge Cases
- Device failure mid-apply should mark that device as failed, continue with other devices in batch
- Health check timeout should be treated as degraded (fail-safe)
- Network partition during batch should trigger rollback
- All devices in batch must complete before health check runs

#### Reference Documentation
- [docs/07](../docs/07-device-control-and-high-risk-operations-safeguards.md) - Staged rollout design
- [docs/06](../docs/06-system-information-and-metrics-collection-module-design.md) - Health thresholds
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#22-multi-device-planapply-framework) - Staged rollout spec

---

### Issue #15: Implement automatic rollback on health check failure

**Priority**: P1 (High - multi-device safety)
**Estimated effort**: 3-4 hours
**Labels**: `phase-4`, `multi-device`, `rollback`

#### Context
When staged rollout detects degraded devices, it must optionally rollback changes to restore previous state. This prevents leaving devices in inconsistent state.

Rollback restores previous DNS/NTP settings from plan snapshot.

#### Change Request
Implement rollback logic in `PlanService`:
1. Store previous device state in plan metadata (already exists from Phase 3)
2. On health check failure, trigger rollback if `plan.rollback_on_failure=true`
3. Rollback applies previous state to all devices in completed batches
4. Track rollback success/failure per device
5. Transition plan to `rolled_back` state

#### Acceptance Criteria
- [ ] Rollback triggers automatically on health check failure (if enabled)
- [ ] Restores previous DNS/NTP settings from plan metadata
- [ ] Rollback applies to all devices in completed batches (not pending batches)
- [ ] Per-device rollback status tracked: `applied → rolling_back → rolled_back`
- [ ] Plan state transitions: `applying → rolling_back → rolled_back`
- [ ] Rollback failures logged with details
- [ ] Add unit tests for rollback scenarios
- [ ] Run `pytest tests/unit/domain/services/test_plan.py::test_rollback -v` passes

#### Files to Modify
- `routeros_mcp/domain/services/plan.py` - Add rollback logic
- `routeros_mcp/domain/services/dns_ntp.py` - Ensure rollback support for DNS/NTP changes
- `tests/unit/domain/services/test_plan.py` - Add rollback tests

#### Do Not Change
- Plan metadata structure
- Health check logic
- Device connection logic

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/domain/services/test_plan.py::test_rollback -v

# Integration test: trigger rollback
uv run pytest tests/integration/test_rollback_on_failure.py -v

# Manual test: force health check failure
python -c "
from routeros_mcp.domain.services.plan import PlanService
# Apply plan to devices, then force health check to fail
# Verify rollback is triggered and devices restored
"
```

#### Known Edge Cases
- Rollback itself may fail (e.g., device unreachable) - log and continue with other devices
- Partial rollback success should be clearly indicated
- Rollback should not retry indefinitely (max 3 attempts per device)

#### Reference Documentation
- [docs/07](../docs/07-device-control-and-high-risk-operations-safeguards.md) - Rollback safeguards
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#22-multi-device-planapply-framework) - Rollback design

---

### Issue #16: Implement config/plan-dns-ntp-rollout tool

**Priority**: P1 (High - multi-device tool)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `multi-device`, `tools`, `professional-tier`

#### Context
Phase 4 adds professional-tier tools for multi-device operations. `config/plan-dns-ntp-rollout` creates a multi-device plan for DNS/NTP changes across 2-50 devices.

This is the first professional-tier tool and establishes the pattern for other multi-device tools.

#### Change Request
Implement `plan_dns_ntp_rollout()` tool in `routeros_mcp/mcp_tools/config.py`:
1. Accept parameters: device_ids (list, 2-50), dns_servers (list), ntp_servers (list), batch_size (default: 5)
2. Validate all devices exist and are reachable
3. Create multi-device plan using `PlanService.create_multi_device_plan()`
4. Return plan ID, approval token, batch summary

#### Acceptance Criteria
- [ ] `@mcp.tool()` decorator registers `config/plan-dns-ntp-rollout` tool
- [ ] Tool tier: `professional` (multi-device, requires approval)
- [ ] Validates parameters (device_ids length 2-50, valid DNS/NTP server IPs)
- [ ] Calls `PlanService.create_multi_device_plan()` with DNS/NTP change type
- [ ] Returns: `{"plan_id": "...", "approval_token": "...", "batch_count": 3, "devices_per_batch": [5, 5, 2]}`
- [ ] Plan expires in 15 minutes (existing HMAC token logic)
- [ ] Add unit tests for validation and plan creation
- [ ] Run `pytest tests/unit/test_mcp_tools_config.py::test_plan_dns_ntp_rollout -v` passes

#### Files to Modify
- `routeros_mcp/mcp_tools/config.py` - Add `plan_dns_ntp_rollout()` function
- `tests/unit/test_mcp_tools_config.py` - Add tool tests

#### Do Not Change
- Single-device DNS/NTP tools
- Plan approval token generation
- Tool tier system

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/test_mcp_tools_config.py::test_plan_dns_ntp_rollout -v

# Manual test
python -c "
from routeros_mcp.mcp_tools.config import plan_dns_ntp_rollout
result = plan_dns_ntp_rollout(
    device_ids=['dev-001', 'dev-002', 'dev-003'],
    dns_servers=['1.1.1.1', '8.8.8.8'],
    ntp_servers=['time.google.com'],
    batch_size=2
)
print(f'Plan ID: {result[\"plan_id\"]}, Batches: {result[\"batch_count\"]}')
"
```

#### Reference Documentation
- [docs/04](../docs/04-mcp-tools-interface-and-json-schema-specification.md) - Professional tools
- [docs/07](../docs/07-device-control-and-high-risk-operations-safeguards.md) - Multi-device safeguards
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#22-multi-device-planapply-framework) - Multi-device tools

---

### Issue #17: Implement config/apply-dns-ntp-rollout tool with job tracking

**Priority**: P1 (High - multi-device tool)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `multi-device`, `tools`, `professional-tier`

#### Context
Second professional-tier tool for Phase 4. `config/apply-dns-ntp-rollout` executes a multi-device plan with staged rollout, creating a background job for progress tracking.

#### Change Request
Implement `apply_dns_ntp_rollout()` tool in `routeros_mcp/mcp_tools/config.py`:
1. Accept parameters: plan_id, approval_token
2. Validate approval token (reuse existing HMAC validation)
3. Create background job for execution
4. Return job ID for status tracking
5. Job executes staged rollout in background (APScheduler)

#### Acceptance Criteria
- [ ] `@mcp.tool()` decorator registers `config/apply-dns-ntp-rollout` tool
- [ ] Tool tier: `professional`
- [ ] Validates approval token with HMAC (reuse Phase 3 logic)
- [ ] Creates background job via JobService
- [ ] Returns: `{"job_id": "...", "status": "pending", "estimated_duration_minutes": 8}`
- [ ] Job executes `PlanService.apply_multi_device_plan()` in background
- [ ] Add unit tests for token validation and job creation
- [ ] Run `pytest tests/unit/test_mcp_tools_config.py::test_apply_dns_ntp_rollout -v` passes

#### Files to Modify
- `routeros_mcp/mcp_tools/config.py` - Add `apply_dns_ntp_rollout()` function
- `tests/unit/test_mcp_tools_config.py` - Add tool tests

#### Do Not Change
- Approval token validation logic
- Job execution engine
- Staged rollout logic (already in PlanService)

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/test_mcp_tools_config.py::test_apply_dns_ntp_rollout -v

# Manual test (requires plan created first)
python -c "
from routeros_mcp.mcp_tools.config import apply_dns_ntp_rollout
result = apply_dns_ntp_rollout(
    plan_id='plan-123',
    approval_token='token-from-plan-step'
)
print(f'Job ID: {result[\"job_id\"]}')
# Then check job status via GET /api/admin/jobs/{job_id}
"
```

#### Reference Documentation
- [docs/04](../docs/04-mcp-tools-interface-and-json-schema-specification.md) - Professional tools
- [docs/05](../docs/05-domain-model-persistence-and-task-job-model.md) - Job model
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#22-multi-device-planapply-framework) - Apply tool design

---

### Issue #18: Implement config/rollback-plan tool

**Priority**: P2 (Medium - manual rollback)
**Estimated effort**: 1-2 hours
**Labels**: `phase-4`, `multi-device`, `tools`, `professional-tier`

#### Context
Third professional-tier tool for Phase 4. `config/rollback-plan` manually triggers rollback of a plan, useful when automatic rollback is disabled or for manual recovery.

#### Change Request
Implement `rollback_plan()` tool in `routeros_mcp/mcp_tools/config.py`:
1. Accept parameters: plan_id, reason (string, required)
2. Validate plan exists and is in `applied` state
3. Trigger manual rollback via PlanService
4. Return rollback job ID

#### Acceptance Criteria
- [ ] `@mcp.tool()` decorator registers `config/rollback-plan` tool
- [ ] Tool tier: `professional`
- [ ] Validates plan_id exists and state is `applied`
- [ ] Requires `reason` parameter (audit trail)
- [ ] Calls `PlanService.rollback_plan(plan_id, reason)`
- [ ] Returns: `{"job_id": "...", "status": "rolling_back", "devices_affected": 12}`
- [ ] Reason logged in audit trail
- [ ] Add unit tests for validation and rollback trigger
- [ ] Run `pytest tests/unit/test_mcp_tools_config.py::test_rollback_plan -v` passes

#### Files to Modify
- `routeros_mcp/mcp_tools/config.py` - Add `rollback_plan()` function
- `routeros_mcp/domain/services/plan.py` - Add `rollback_plan()` method if missing
- `tests/unit/test_mcp_tools_config.py` - Add tool tests

#### Do Not Change
- Automatic rollback logic
- Plan state machine
- Audit logging system

#### How to Build & Test
```bash
# Run unit tests
uv run pytest tests/unit/test_mcp_tools_config.py::test_rollback_plan -v

# Manual test
python -c "
from routeros_mcp.mcp_tools.config import rollback_plan
result = rollback_plan(
    plan_id='plan-123',
    reason='Discovered DNS resolution issues after rollout'
)
print(f'Rollback job ID: {result[\"job_id\"]}')
"
```

#### Reference Documentation
- [docs/04](../docs/04-mcp-tools-interface-and-json-schema-specification.md) - Professional tools
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#22-multi-device-planapply-framework) - Rollback tool

---

### Issue #19: Add E2E tests for multi-device rollout workflow

**Priority**: P1 (High - validation)
**Estimated effort**: 4-5 hours
**Labels**: `phase-4`, `multi-device`, `testing`, `e2e`

#### Context
Multi-device coordination is complex and needs comprehensive E2E tests to validate the entire workflow: plan → apply → health checks → rollback.

This issue creates E2E tests with mock devices (no real RouterOS needed).

#### Change Request
Create `tests/e2e/test_multi_device_rollout.py` with E2E tests:
1. Test successful rollout (all batches complete)
2. Test rollout with health check failure (triggers rollback)
3. Test manual cancellation mid-rollout
4. Test partial failure (some devices succeed, some fail)

#### Acceptance Criteria
- [ ] New file: `tests/e2e/test_multi_device_rollout.py`
- [ ] Test: `test_successful_rollout_3_batches` (5 devices, batch_size=2, all succeed)
- [ ] Test: `test_rollout_halts_on_health_failure` (batch 2 fails health check, triggers rollback)
- [ ] Test: `test_manual_cancellation` (cancel job after batch 1, batch 2 not started)
- [ ] Test: `test_partial_device_failure` (1 device in batch fails, others continue)
- [ ] All tests use mock devices (no real RouterOS connection)
- [ ] Tests verify job progress updates, device statuses, audit logs
- [ ] Run `pytest tests/e2e/test_multi_device_rollout.py -v` passes all 4+ tests

#### Files to Create
- `tests/e2e/test_multi_device_rollout.py` - New E2E test file

#### Do Not Change
- Existing E2E tests
- Mock device factory
- Test database setup

#### How to Build & Test
```bash
# Run E2E tests
uv run pytest tests/e2e/test_multi_device_rollout.py -v

# Run with coverage
uv run pytest tests/e2e/test_multi_device_rollout.py --cov=routeros_mcp.domain.services.plan -v

# Run single test
uv run pytest tests/e2e/test_multi_device_rollout.py::test_successful_rollout_3_batches -v
```

#### Test Scenarios
1. **Successful rollout**:
   - 5 devices, batch_size=2 (3 batches: 2, 2, 1)
   - All batches complete successfully
   - All devices end in `applied` state
   - Plan state: `applied`

2. **Health check failure**:
   - 6 devices, batch_size=2
   - Batch 1 succeeds, batch 2 health check fails
   - Rollback triggered for batch 1 devices
   - Batch 3 never started
   - Plan state: `rolled_back`

3. **Manual cancellation**:
   - 6 devices, batch_size=2
   - Cancel after batch 1 completes
   - Batch 2 and 3 not started
   - Plan state: `cancelled`

#### Reference Documentation
- [docs/10](../docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md) - E2E testing strategy
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#testing-strategy) - Test requirements

---

## Sprint 8-9: Infrastructure & UI (88-116 hours)

### Issue #20: Add TimescaleDB hypertable migration for health_checks

**Priority**: P2 (Medium - performance optimization)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `infrastructure`, `database`, `timescaledb`

#### Context
Phase 4 adds TimescaleDB support for efficient time-series storage of health check metrics. Converting `health_checks` table to a hypertable improves query performance and enables automatic data retention.

This is optional but recommended for deployments with 50+ devices.

#### Change Request
Create Alembic migration to convert `health_checks` to TimescaleDB hypertable:
1. Check if TimescaleDB extension is available
2. Convert `health_checks` to hypertable partitioned on `timestamp` column
3. Create retention policy (keep 30 days raw data)
4. Create continuous aggregate for hourly summaries

#### Acceptance Criteria
- [ ] New migration: `alembic/versions/*_convert_to_timescaledb.py`
- [ ] Migration checks for TimescaleDB extension availability
- [ ] Converts `health_checks` to hypertable: `SELECT create_hypertable('health_checks', 'timestamp')`
- [ ] Adds retention policy: Drop data older than 30 days
- [ ] Creates continuous aggregate for hourly CPU/memory averages
- [ ] Migration is reversible (downgrade converts back to regular table)
- [ ] Migration skips if TimescaleDB not available (optional feature)
- [ ] Add documentation in docs/06 for TimescaleDB setup
- [ ] Run `uv run alembic upgrade head` succeeds

#### Files to Create
- `alembic/versions/*_convert_to_timescaledb.py` - New migration

#### Files to Modify
- `docs/06-system-information-and-metrics-collection-module-design.md` - Add TimescaleDB setup

#### Do Not Change
- `health_checks` table schema (columns remain same)
- Health check collection logic
- Health query logic (should work with or without TimescaleDB)

#### How to Build & Test
```bash
# Ensure TimescaleDB is installed (PostgreSQL only)
# For SQLite, migration should skip gracefully

# Run migration
uv run alembic upgrade head

# Verify hypertable created
psql -d routeros_mcp -c "SELECT * FROM timescaledb_information.hypertables WHERE hypertable_name = 'health_checks';"

# Test rollback
uv run alembic downgrade -1
uv run alembic upgrade head

# Verify queries still work
python -c "
from routeros_mcp.domain.services.health import HealthService
service = HealthService(...)
recent = service.get_recent_health_checks('dev-001', hours=24)
print(f'Found {len(recent)} health checks')
"
```

#### Known Edge Cases
- SQLite deployment should skip TimescaleDB features gracefully
- Existing data should be preserved during hypertable conversion
- Continuous aggregates need initial refresh after creation

#### Reference Documentation
- [docs/06](../docs/06-system-information-and-metrics-collection-module-design.md) - Metrics design
- [TimescaleDB Documentation](https://docs.timescale.com/use-timescale/latest/hypertables/) - Hypertable creation
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#41-timescaledb-integration) - TimescaleDB design

---

### Issue #21: Implement adaptive polling strategy for health checks

**Priority**: P2 (Medium - performance optimization)
**Estimated effort**: 3-4 hours
**Labels**: `phase-4`, `infrastructure`, `health-checks`

#### Context
Fixed 30-second health check intervals work for Phase 1-3, but Phase 4 with 50+ devices needs intelligent polling. Adaptive polling adjusts intervals based on device stability: stable devices polled less frequently, unstable devices more frequently.

#### Change Request
Enhance `HealthService` to implement adaptive polling:
1. Add device classification: `critical` (poll every 30s) vs `non-critical` (poll every 60s)
2. Increase interval by 50% after 10 consecutive healthy checks (max: 5 minutes)
3. Reset to base interval on any unhealthy check
4. Implement exponential backoff for unreachable devices: 1min, 2min, 4min, 8min, 16min (max)
5. Add device health status: `healthy`, `degraded`, `unreachable`

#### Acceptance Criteria
- [ ] Add `critical` boolean field to Device model (default: False)
- [ ] Critical devices poll every 30s, non-critical every 60s
- [ ] After 10 consecutive healthy checks, interval increases by 50%
- [ ] Max polling interval: 5 minutes (300 seconds)
- [ ] Unhealthy check resets interval to base (30s or 60s)
- [ ] Unreachable devices use exponential backoff (1→2→4→8→16 minutes)
- [ ] Add `health_status` enum to Device: `healthy`, `degraded`, `unreachable`
- [ ] Add unit tests for interval calculation logic
- [ ] Run `pytest tests/unit/test_health_service_adaptive_polling.py -v` passes

#### Files to Modify
- `routeros_mcp/domain/models.py` - Add `critical` and `health_status` fields to Device
- `routeros_mcp/domain/services/health.py` - Add adaptive polling logic
- `routeros_mcp/infra/jobs/scheduler.py` - Support dynamic schedule adjustment
- `alembic/versions/*_add_adaptive_polling_fields.py` - New migration
- `tests/unit/test_health_service_adaptive_polling.py` - New test file

#### Do Not Change
- Health check collection logic
- Health threshold calculations
- Database schema for health_checks table

#### How to Build & Test
```bash
# Generate and run migration
uv run alembic revision --autogenerate -m "Add adaptive polling fields to Device"
uv run alembic upgrade head

# Run unit tests
uv run pytest tests/unit/test_health_service_adaptive_polling.py -v

# Manual test: mark device as critical
python -c "
from routeros_mcp.domain.services.device import DeviceService
service = DeviceService(...)
service.update_device('dev-001', critical=True)
# Verify polling interval is 30s for this device
"

# Simulate 10 healthy checks, verify interval increases
python -c "
from routeros_mcp.domain.services.health import HealthService
service = HealthService(...)
for i in range(10):
    service.collect_health_check('dev-002')  # All healthy
interval = service.get_polling_interval('dev-002')
assert interval == 90  # 60s * 1.5
"
```

#### Known Edge Cases
- Interval adjustment should be gradual (not sudden jumps)
- Device reboots should reset interval to base
- Manual health check requests should not affect adaptive interval

#### Reference Documentation
- [docs/06](../docs/06-system-information-and-metrics-collection-module-design.md) - Health check intervals
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#42-adaptive-polling-strategy) - Adaptive polling design

---

### Issue #22: Create web UI scaffolding with React and Vite

**Priority**: P2 (Medium - web UI foundation)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `web-ui`, `frontend`, `good-first-agent-task`

#### Context
Phase 4 adds a basic web admin UI for device management and plan approval. This issue sets up the frontend project structure using React 18 + Vite + Tailwind CSS.

No backend integration yet—just scaffolding.

#### Change Request
Create frontend project structure:
1. Initialize React project with Vite: `npm create vite@latest frontend -- --template react-ts`
2. Add Tailwind CSS for styling
3. Set up React Router for navigation
4. Create basic layout with header and sidebar
5. Add placeholder pages: Dashboard, Devices, Plans, Audit Log

#### Acceptance Criteria
- [ ] New directory: `frontend/` with Vite React TypeScript project
- [ ] Tailwind CSS configured and working
- [ ] React Router configured with routes: `/`, `/devices`, `/plans`, `/audit`
- [ ] Basic layout component with header (project name) and sidebar (navigation links)
- [ ] Placeholder components for each page (just "Coming soon" message)
- [ ] Dev server runs: `cd frontend && npm run dev` starts on http://localhost:5173
- [ ] Build works: `npm run build` produces production build
- [ ] Add `.gitignore` for node_modules, dist, etc.

#### Files to Create
- `frontend/package.json` - Dependencies
- `frontend/vite.config.ts` - Vite configuration
- `frontend/tailwind.config.js` - Tailwind configuration
- `frontend/src/App.tsx` - Main app component
- `frontend/src/components/Layout.tsx` - Layout component
- `frontend/src/pages/Dashboard.tsx` - Dashboard placeholder
- `frontend/src/pages/Devices.tsx` - Devices placeholder
- `frontend/src/pages/Plans.tsx` - Plans placeholder
- `frontend/src/pages/AuditLog.tsx` - Audit log placeholder

#### Do Not Change
- Backend code
- Python dependencies
- Existing admin CLI

#### How to Build & Test
```bash
# Initialize project
cd frontend
npm install

# Run dev server
npm run dev
# Open http://localhost:5173

# Navigate between pages
# Click Dashboard, Devices, Plans, Audit Log links
# Verify each page renders

# Build for production
npm run build
# Verify dist/ directory created
```

#### Known Edge Cases
- Node.js version should be 18+ (document in README)
- Tailwind CSS purge should not remove used classes

#### Reference Documentation
- [Vite Documentation](https://vitejs.dev/guide/) - Vite setup
- [React Router Documentation](https://reactrouter.com/) - Routing
- [Tailwind CSS Documentation](https://tailwindcss.com/docs/guides/vite) - Tailwind with Vite
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#51-initial-admin-interface) - Web UI design

---

### Issue #23: Implement Device List page with CRUD operations

**Priority**: P2 (Medium - web UI core)
**Estimated effort**: 4-5 hours
**Labels**: `phase-4`, `web-ui`, `frontend`

#### Context
First functional web UI page. Device List displays all devices with status indicators and provides CRUD operations (Create, Read, Update, Delete).

#### Change Request
Implement Device List page in React:
1. Fetch devices from `/api/admin/devices` endpoint
2. Display in table: name, hostname, environment, status, actions
3. Add device form (modal or separate page): hostname, username, password, environment
4. Edit device button opens form with existing data
5. Delete device button with confirmation dialog
6. Test connectivity button (calls `/api/admin/devices/{id}/test`)

#### Acceptance Criteria
- [ ] Device list fetches from API on page load
- [ ] Table columns: Device Name, Hostname, Environment, Status, Actions
- [ ] Status indicator: green (healthy), yellow (degraded), red (unreachable)
- [ ] "Add Device" button opens form modal
- [ ] Form validates: hostname (required), username (required), password (required), environment (enum)
- [ ] Edit button populates form with existing device data
- [ ] Delete button shows confirmation: "Are you sure you want to delete {device_name}?"
- [ ] Test connectivity button shows spinner, displays result
- [ ] Add TypeScript types for Device model
- [ ] Use React hooks (useState, useEffect) for state management
- [ ] Add basic CSS styling (Tailwind classes)

#### Files to Modify
- `frontend/src/pages/Devices.tsx` - Implement device list and CRUD
- `frontend/src/components/DeviceForm.tsx` - New component for add/edit form
- `frontend/src/types/device.ts` - New TypeScript types

#### Files to Create
- `frontend/src/services/api.ts` - API client wrapper (axios or fetch)

#### Do Not Change
- Backend API endpoints (already exist from Phase 3)
- Device model in backend

#### How to Build & Test
```bash
# Start backend server
uv run routeros-mcp --config config/lab.yaml

# Start frontend dev server
cd frontend && npm run dev

# Manual testing:
# 1. Navigate to http://localhost:5173/devices
# 2. Verify device list loads
# 3. Click "Add Device", fill form, submit
# 4. Verify new device appears in list
# 5. Click Edit, modify hostname, submit
# 6. Click Test Connectivity, verify result shown
# 7. Click Delete, confirm, verify device removed
```

#### Known Edge Cases
- Empty device list should show "No devices found. Add your first device."
- API errors should display user-friendly messages
- Form validation should prevent submission with missing required fields

#### Reference Documentation
- Backend API: `routeros_mcp/api/admin.py` - Device endpoints
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#51-initial-admin-interface) - UI requirements

---

### Issue #24: Implement Plan Approval Queue page

**Priority**: P2 (Medium - web UI core)
**Estimated effort**: 3-4 hours
**Labels**: `phase-4`, `web-ui`, `frontend`, `plan-apply`

#### Context
Second functional web UI page. Plan Approval Queue displays pending plans awaiting approval, with details viewer and approve/reject actions.

#### Change Request
Implement Plan Approval Queue page:
1. Fetch pending plans from `/api/admin/plans?status=pending_approval`
2. Display in table: Plan ID, Type, Devices, Created, Actions
3. Click plan row to view details (devices affected, changes, diff)
4. Approve button generates approval token, displays for user to copy
5. Reject button with reason field

#### Acceptance Criteria
- [ ] Pending plans list fetches from API on page load
- [ ] Table columns: Plan ID, Change Type, Device Count, Created At, Actions
- [ ] Click row opens details panel/modal
- [ ] Details show: device list, current vs. proposed settings (diff view)
- [ ] Approve button calls `/api/admin/plans/{id}/approve`, displays token
- [ ] Token displayed in copyable text field with "Copy to Clipboard" button
- [ ] Reject button opens modal with reason textarea (required)
- [ ] After approve/reject, plan removed from pending list
- [ ] Add TypeScript types for Plan model
- [ ] Use React hooks for state management

#### Files to Modify
- `frontend/src/pages/Plans.tsx` - Implement plan queue
- `frontend/src/components/PlanDetails.tsx` - New component for plan details
- `frontend/src/types/plan.ts` - New TypeScript types

#### Do Not Change
- Backend plan approval logic
- Plan model structure

#### How to Build & Test
```bash
# Start backend + frontend
uv run routeros-mcp --config config/lab.yaml
cd frontend && npm run dev

# Manual testing:
# 1. Create a plan via CLI or API:
curl -X POST http://localhost:8080/api/admin/plans \
  -H "Content-Type: application/json" \
  -d '{"device_ids": ["dev-001"], "change_type": "dns_ntp", "dns_servers": ["1.1.1.1"]}'

# 2. Navigate to http://localhost:5173/plans
# 3. Verify plan appears in pending list
# 4. Click plan row, verify details shown
# 5. Click Approve, verify token displayed
# 6. Copy token, verify clipboard works
# 7. Create another plan, reject with reason
# 8. Verify plan removed from list
```

#### Known Edge Cases
- Empty plan queue should show "No pending plans"
- Expired plans should be visually distinguished (grayed out)
- Diff view should handle missing fields gracefully

#### Reference Documentation
- Backend API: `routeros_mcp/api/admin.py` - Plan endpoints
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#51-initial-admin-interface) - UI requirements

---

### Issue #25: Implement Audit Log Viewer page with filtering

**Priority**: P2 (Medium - web UI)
**Estimated effort**: 3-4 hours
**Labels**: `phase-4`, `web-ui`, `frontend`, `audit`

#### Context
Third functional web UI page. Audit Log Viewer displays audit events with search and filtering capabilities.

#### Change Request
Implement Audit Log Viewer page:
1. Fetch audit events from `/api/audit/events` with pagination
2. Display in table: Timestamp, User, Device, Tool, Result, Details
3. Add filters: date range, device, tool, result (success/failure)
4. Add search by keyword
5. Export to CSV button

#### Acceptance Criteria
- [ ] Audit events fetch from API with pagination (20 per page)
- [ ] Table columns: Timestamp, User, Device, Tool/Action, Result, View Details
- [ ] Date range filter (from/to date pickers)
- [ ] Device filter (dropdown, all devices + "All")
- [ ] Tool filter (dropdown, all tools + "All")
- [ ] Result filter (All / Success / Failure)
- [ ] Search box filters by keyword in event details
- [ ] Pagination controls (Previous, Next, page numbers)
- [ ] Export to CSV button downloads filtered results
- [ ] Click "View Details" expands row to show full event JSON
- [ ] Add TypeScript types for AuditEvent model

#### Files to Modify
- `frontend/src/pages/AuditLog.tsx` - Implement audit log viewer
- `frontend/src/types/audit.ts` - New TypeScript types

#### Do Not Change
- Backend audit API endpoints
- Audit event schema

#### How to Build & Test
```bash
# Start backend + frontend
uv run routeros-mcp --config config/lab.yaml
cd frontend && npm run dev

# Manual testing:
# 1. Perform some actions to generate audit events:
curl -X POST http://localhost:8080/api/admin/devices/dev-001/test

# 2. Navigate to http://localhost:5173/audit
# 3. Verify events displayed in table
# 4. Filter by date range, verify results update
# 5. Select device filter, verify only that device's events shown
# 6. Search for "test", verify matching events shown
# 7. Click Export CSV, verify file downloads
# 8. Click View Details on event, verify JSON shown
```

#### Known Edge Cases
- Empty audit log should show "No audit events found"
- Large date ranges should paginate efficiently
- CSV export should handle special characters in event details

#### Reference Documentation
- Backend API: `routeros_mcp/api/audit.py` - Audit endpoints (create if missing)
- [docs/08](../docs/08-observability-logging-metrics-and-diagnostics.md) - Audit design
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#51-initial-admin-interface) - UI requirements

---

### Issue #26: Add SSH key authentication support to Device model

**Priority**: P3 (Low - SSH enhancement)
**Estimated effort**: 3-4 hours
**Labels**: `phase-4`, `ssh`, `security`

#### Context
Phase 4 adds SSH key-based authentication as an alternative to password authentication. This enhances security and supports environments where password auth is disabled.

#### Change Request
Add SSH key credential type to support public key authentication:
1. Add `routeros_ssh_key` credential type to CredentialType enum
2. Enhance Credential model to store encrypted private key
3. Modify SSHClient to try key auth first, fallback to password
4. Add public key fingerprint field for verification

#### Acceptance Criteria
- [ ] Add `routeros_ssh_key` to CredentialType enum
- [ ] Add fields to Credential model: `private_key` (encrypted Text), `public_key_fingerprint` (String)
- [ ] Validate SSH private key format on creation
- [ ] `SSHClient` tries key auth first, falls back to password if key unavailable
- [ ] Private key encrypted with same Fernet key as passwords
- [ ] Add unit tests for key auth and fallback
- [ ] Run `pytest tests/unit/test_ssh_client.py::test_key_auth -v` passes
- [ ] Create migration for new fields

#### Files to Modify
- `routeros_mcp/domain/models.py` - Add credential type and fields
- `routeros_mcp/infra/routeros/ssh_client.py` - Add key auth support
- `routeros_mcp/security/crypto.py` - Add key encryption helpers
- `alembic/versions/*_add_ssh_key_credentials.py` - New migration
- `tests/unit/test_ssh_client.py` - Add key auth tests

#### Do Not Change
- Password-based authentication
- Existing credential encryption
- SSH command execution logic

#### How to Build & Test
```bash
# Generate and run migration
uv run alembic revision --autogenerate -m "Add SSH key credentials"
uv run alembic upgrade head

# Run unit tests
uv run pytest tests/unit/test_ssh_client.py::test_key_auth -v

# Manual test with real SSH key
python -c "
from routeros_mcp.domain.services.device import DeviceService
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

# Generate test key
from cryptography.hazmat.primitives.asymmetric import rsa
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
private_pem = key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm=serialization.NoEncryption()
)

# Add device with SSH key
service = DeviceService(...)
service.add_device_with_ssh_key(
    name='test-device',
    hostname='192.168.1.1',
    username='admin',
    private_key=private_pem.decode()
)
"
```

#### Known Edge Cases
- Invalid SSH key format should fail validation before storage
- Key with passphrase not supported in Phase 4 (document limitation)
- Fallback to password should be seamless if key fails

#### Reference Documentation
- [docs/02](../docs/02-security-oauth-integration-and-access-control.md) - Credential security
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#61-ssh-key-based-authentication) - SSH key auth design

---

### Issue #27: Implement RouterOS version detection for client compatibility

**Priority**: P3 (Low - compatibility)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `compatibility`, `routeros`

#### Context
Phase 4 adds support for RouterOS v6.x devices (currently targets v7.x only). Version detection enables conditional endpoint mapping and field handling for legacy devices.

#### Change Request
Add RouterOS version detection to Device model and REST client:
1. Query `GET /rest/system/package` on first connection
2. Parse RouterOS version from response (e.g., "7.10.2" or "6.48.6")
3. Store version in Device model
4. Add version comparison helpers (is_v6, is_v7, supports_feature)

#### Acceptance Criteria
- [ ] Add `routeros_version` field to Device model (String, nullable)
- [ ] `RESTClient.detect_version()` queries `/rest/system/package` on first connect
- [ ] Parses version string from response: `{"version": "7.10.2"}`
- [ ] Stores version in database on device creation/update
- [ ] Add helper methods: `device.is_v6()`, `device.is_v7()`, `device.version_ge("7.10")`
- [ ] Add unit tests for version parsing and comparison
- [ ] Run `pytest tests/unit/test_rest_client.py::test_version_detection -v` passes
- [ ] Create migration for new field

#### Files to Modify
- `routeros_mcp/domain/models.py` - Add `routeros_version` field
- `routeros_mcp/infra/routeros/rest_client.py` - Add `detect_version()` method
- `alembic/versions/*_add_routeros_version.py` - New migration
- `tests/unit/test_rest_client.py` - Add version detection tests

#### Do Not Change
- Existing REST endpoints
- Device connection logic
- Tool implementations (compatibility mapping is separate issue)

#### How to Build & Test
```bash
# Generate and run migration
uv run alembic revision --autogenerate -m "Add RouterOS version to Device"
uv run alembic upgrade head

# Run unit tests
uv run pytest tests/unit/test_rest_client.py::test_version_detection -v

# Manual test (requires RouterOS device)
python -c "
from routeros_mcp.infra.routeros.rest_client import RESTClient
client = RESTClient(host='192.168.1.1', username='admin', password='...')
version = client.detect_version()
print(f'RouterOS version: {version}')
"
```

#### Known Edge Cases
- Version endpoint may not exist on very old RouterOS versions (handle gracefully)
- Version string format may vary (6.48.6 vs. 7.10.2 vs. 7.11-rc1)
- Offline devices should leave version as NULL until first successful connection

#### Reference Documentation
- [docs/03](../docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md) - RouterOS API
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#62-client-compatibility-modes) - Version detection design

---

### Issue #28: Document automated approval tokens for trusted workflows

**Priority**: P3 (Low - automation convenience)
**Estimated effort**: 1-2 hours
**Labels**: `phase-4`, `documentation`, `automation`

#### Context
Phase 4 adds support for automated approval tokens to streamline trusted workflows (e.g., "lab DNS rollout"). This is a configuration-based feature for runbooks and scheduled operations.

This issue documents the feature without implementing code (code mostly exists from Phase 3).

#### Change Request
Document automated approval token configuration in docs/02:
1. Explain use case: pre-approved workflows in trusted environments
2. YAML configuration format for trusted workflows
3. Security considerations
4. Example configurations for common scenarios

#### Acceptance Criteria
- [ ] New section in docs/02: "Automated Approval Tokens"
- [ ] Documents use cases (runbooks, scheduled maintenance, lab automation)
- [ ] YAML configuration example:
  ```yaml
  trusted_workflows:
    - name: "lab-dns-rollout"
      environment: lab
      device_scope: lab-*
      change_types: [dns_ntp]
      auto_approve: true
  ```
- [ ] Documents security warning: Only use in trusted environments
- [ ] Documents audit trail: Auto-approved plans flagged in logs
- [ ] Example: Lab DNS rollout with auto-approval
- [ ] Example: Staging NTP update with auto-approval
- [ ] Update README.md to reference this feature

#### Files to Modify
- `docs/02-security-oauth-integration-and-access-control.md` - Add automated approval section
- `README.md` - Add brief mention in Phase 4 features

#### Do Not Change
- Existing approval token logic
- Plan/apply workflow

#### How to Build & Test
```bash
# No code changes, verify documentation is clear

# Review checklist:
- [ ] Use cases are clear
- [ ] Security warnings are prominent
- [ ] YAML examples are valid
- [ ] Integration with existing plan/apply is documented
```

#### Reference Documentation
- [docs/02](../docs/02-security-oauth-integration-and-access-control.md) - Current security model
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#63-automated-approval-tokens) - Feature design

---

### Issue #29: Create Phase 4 comprehensive E2E test suite

**Priority**: P1 (High - validation)
**Estimated effort**: 4-5 hours
**Labels**: `phase-4`, `testing`, `e2e`, `validation`

#### Context
Phase 4 adds significant new features (HTTP/SSE, diagnostics, multi-device). A comprehensive E2E test suite validates the complete Phase 4 implementation before release.

#### Change Request
Create `tests/e2e/test_phase4_comprehensive.py` with E2E tests covering:
1. HTTP/SSE transport end-to-end
2. All 3 diagnostics tools
3. Multi-device plan/apply workflow
4. SSE subscriptions for real-time health
5. Web UI basic flows (if UI implemented)

#### Acceptance Criteria
- [ ] New file: `tests/e2e/test_phase4_comprehensive.py`
- [ ] Test: `test_http_transport_full_workflow` (HTTP server, tool invocation, response)
- [ ] Test: `test_sse_health_subscription` (subscribe, receive updates, unsubscribe)
- [ ] Test: `test_diagnostics_tools_all` (ping, traceroute, bandwidth-test)
- [ ] Test: `test_multi_device_rollout_success` (6 devices, 3 batches, all succeed)
- [ ] Test: `test_multi_device_rollout_with_rollback` (health check fails, triggers rollback)
- [ ] All tests use Docker Compose for isolated environment (HTTP server + mock devices)
- [ ] Tests verify metrics are recorded (Prometheus /metrics endpoint)
- [ ] Tests verify audit logs captured
- [ ] Run `pytest tests/e2e/test_phase4_comprehensive.py -v` passes all tests (15-20 minutes)

#### Files to Create
- `tests/e2e/test_phase4_comprehensive.py` - Comprehensive E2E tests

#### Do Not Change
- Existing E2E tests
- Docker Compose setup

#### How to Build & Test
```bash
# Start Docker Compose environment
docker-compose -f tests/e2e/docker-compose.yml up -d
sleep 15  # Wait for services to be ready

# Run comprehensive E2E suite
uv run pytest tests/e2e/test_phase4_comprehensive.py -v

# Expected: 10+ tests, all passing, ~15-20 min runtime

# Cleanup
docker-compose -f tests/e2e/docker-compose.yml down
```

#### Test Coverage Requirements
- HTTP/SSE transport: 2-3 tests
- Diagnostics tools: 3 tests (one per tool)
- Multi-device: 3-4 tests (success, failure, rollback, cancellation)
- SSE subscriptions: 2 tests
- Metrics/audit: 2 tests

#### Reference Documentation
- [docs/10](../docs/10-testing-validation-and-sandbox-strategy-and-safety-nets.md) - Testing strategy
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md#testing-strategy) - Phase 4 testing requirements

---

### Issue #30: Update all Phase 4 documentation and README

**Priority**: P1 (High - documentation)
**Estimated effort**: 2-3 hours
**Labels**: `phase-4`, `documentation`

#### Context
Phase 4 implementation is complete. Final step: update all documentation to reflect Phase 4 features, mark checkboxes complete in README, update tool counts, and add migration guides.

#### Change Request
Update documentation to reflect Phase 4 completion:
1. Mark Phase 4 checkboxes in README.md as complete
2. Update tool count (62 → 68 tools)
3. Update Current Implementation Status section
4. Add Phase 4 migration guide (how to upgrade from Phase 3)
5. Update docs/04 with 6 new tool specifications

#### Acceptance Criteria
- [ ] README.md Phase 4 section: all checkboxes marked complete
- [ ] README.md "Current Implementation Status": tools count 62 → 68
- [ ] README.md: Add "Phase 4 Complete, Phase 5 Planned" banner
- [ ] New doc: `docs/PHASE4_MIGRATION_GUIDE.md` with upgrade instructions
- [ ] docs/04 updated with diagnostics and multi-device tool specs
- [ ] docs/20 updated with final HTTP/SSE deployment instructions
- [ ] All PHASE4_IMPLEMENTATION_PLAN.md acceptance criteria marked complete

#### Files to Modify
- `README.md` - Mark Phase 4 complete, update tool counts
- `docs/04-mcp-tools-interface-and-json-schema-specification.md` - Add 6 new tools
- `docs/20-http-sse-transport-deployment-guide.md` - Final production deployment steps
- `docs/PHASE4_MIGRATION_GUIDE.md` - New migration guide

#### Do Not Change
- Phase 1-3 documentation
- Design documents (00-19) unless factual updates needed

#### How to Build & Test
```bash
# Verify documentation is accurate

# Check tool count
grep -c "@mcp.tool()" routeros_mcp/mcp_tools/*.py
# Expected: 68 tools total

# Verify all checkboxes
grep "\[ \]" README.md | wc -l  # Should be 0 for Phase 4 section

# Verify links work
# Manual: click through all doc links in README
```

#### Migration Guide Contents
1. **Prerequisites**: Phase 3 complete, database backed up
2. **Database Migration**: Run `alembic upgrade head`
3. **Configuration Changes**: Add HTTP/SSE transport config
4. **New Features**: Diagnostics tools, multi-device coordination
5. **Breaking Changes**: None expected
6. **Rollback Instructions**: If needed, `alembic downgrade <previous>`

#### Reference Documentation
- Current README.md Phase 4 section
- [PHASE4_IMPLEMENTATION_PLAN.md](PHASE4_IMPLEMENTATION_PLAN.md) - All features

---

## Issue Summary

**Total Issues Created**: 30
**Sprint 1-2 (HTTP/SSE)**: 6 issues (#1-6)
**Sprint 3-4 (Diagnostics)**: 4 issues (#7-10)
**Sprint 5-7 (Multi-Device)**: 9 issues (#11-19)
**Sprint 8-9 (Infrastructure & UI)**: 11 issues (#20-30)

**Breakdown by Priority**:
- **P0 (Critical)**: 8 issues - HTTP/SSE, multi-device core
- **P1 (High)**: 11 issues - Diagnostics, rollout, testing
- **P2 (Medium)**: 9 issues - Infrastructure, web UI
- **P3 (Low)**: 2 issues - SSH keys, compatibility

**Estimated Total Effort**: 82-104 hours for all 30 issues

**Next Steps**:
1. Review all 30 issues for completeness
2. Create GitHub issues from this document
3. Apply labels: `phase-4`, priority (`P0`-`P3`), sprint, component
4. Assign to milestones and team members
5. Begin implementation with Sprint 1-2 (Issues #1-6)

---

**Quality Checklist for All Issues**:
- ✅ Small, focused tasks (15 min to 6 hours max)
- ✅ Clear context explaining "why this issue exists"
- ✅ Specific change request with actionable steps
- ✅ Measurable acceptance criteria (checkboxes)
- ✅ Explicit file lists (modify + do not change)
- ✅ Concrete test commands (copy-paste ready)
- ✅ Known edge cases documented
- ✅ Reference to design documentation

**GitHub Copilot Agent Optimizations Applied**:
- ✅ Tasks sized for autonomous completion
- ✅ Clear success criteria prevent wandering
- ✅ Explicit boundaries prevent scope creep
- ✅ Self-validation via test commands
- ✅ Protected files prevent risky changes

---

**Note**: This document follows GitHub Copilot agent best practices from `docs/best_practice/github-copilot-coding-agent-best-practices.md`. Each issue is designed for high-quality, autonomous execution with clear reviewability.
