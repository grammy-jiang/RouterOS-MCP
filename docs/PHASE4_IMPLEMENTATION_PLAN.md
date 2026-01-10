# Phase 4 Implementation Plan

**RouterOS MCP Service - Multi-Device Coordination & Diagnostics**

## Overview

Phase 4 builds on the single-device foundations of Phase 1-3 to enable coordinated multi-device operations with safety guarantees. This phase also completes the HTTP/SSE transport implementation and adds the diagnostics tools deferred from Phase 1.

**Status**: Planned (Phase 1-3 Complete)
**Estimated Effort**: 264-376 hours (6-9 weeks @ 40hrs/week)
**New Tools**: +6 (3 diagnostics fundamental, 3 multi-device professional)
**Total Tools After Phase 4**: 68 tools

## Key Objectives

1. **Complete HTTP/SSE Transport** - Enable remote MCP clients with production-ready HTTP server
2. **Multi-Device Coordination** - Safe, orchestrated operations across 2-50 devices
3. **Diagnostics Tools** - Add ping, traceroute, bandwidth-test for network troubleshooting
4. **Infrastructure Scale** - TimescaleDB, adaptive polling, web admin UI
5. **Enhanced Authentication** - SSH key auth and legacy device compatibility

## Phase 4 Feature Breakdown

### 1. HTTP/SSE Transport Completion (HIGH PRIORITY)

**Goal**: Production-ready HTTP/SSE transport for remote MCP clients

**Current Status**: Scaffold exists but not fully wired (7 skipped E2E tests, 4 skipped SSE metrics tests)

#### 1.1 HTTP Server Implementation

**Files to Modify**:
- `routeros_mcp/mcp/transport/http_sse.py` - Complete `_process_mcp_request()` integration
- `routeros_mcp/mcp/server.py` - Wire HTTP mode selection
- `pyproject.toml` - Add `sse-starlette` dependency

**Tasks**:
1. Add `sse-starlette` dependency to `pyproject.toml`
2. Complete `HTTPSSETransport._process_mcp_request()` to integrate with FastMCP
   - Accept JSON-RPC request from HTTP POST
   - Route to appropriate MCP tool via FastMCP
   - Return JSON-RPC response
3. Wire HTTP mode in `mcp/server.py`:
   - Check `settings.mcp_transport == "http"`
   - Start `HTTPSSETransport` instead of stdio
   - Configure host/port from settings
4. Add comprehensive E2E tests:
   - Direct HTTP JSON-RPC requests
   - MCP client tool invocation
   - MCP client resource fetching
   - Error handling

**Estimated Effort**: 16-24 hours

**Acceptance Criteria**:
- [ ] All 7 skipped E2E HTTP tests pass
- [ ] HTTP server responds to JSON-RPC requests on configured port
- [ ] MCP clients can invoke tools and fetch resources via HTTP
- [ ] Error responses are properly formatted JSON-RPC errors

#### 1.2 OAuth/OIDC Middleware

**Goal**: Single service account authentication for Phase 4 HTTP transport

**Files to Create/Modify**:
- `routeros_mcp/mcp/transport/auth_middleware.py` - Enhance existing middleware
- `routeros_mcp/security/oidc.py` - Token validation logic

**Tasks**:
1. Implement bearer token validation in auth middleware:
   - Extract `Authorization: Bearer <token>` header
   - Validate token with OIDC provider (introspection endpoint)
   - Cache validated tokens (5-minute TTL)
   - Return 401 Unauthorized on invalid token
2. Add service account configuration to `Settings`:
   - `oidc_service_account_client_id`
   - `oidc_service_account_client_secret`
3. Document OAuth setup for Phase 4 (single service account) vs. Phase 5 (per-user)
4. Add unit tests for token validation logic

**Estimated Effort**: 12-16 hours

**Acceptance Criteria**:
- [ ] HTTP endpoints require valid bearer token
- [ ] Invalid tokens return 401 Unauthorized with clear error message
- [ ] Token validation is cached for performance
- [ ] Service account configuration is documented

#### 1.3 SSE Resource Subscriptions

**Goal**: Real-time health monitoring via Server-Sent Events

**Files to Modify**:
- `routeros_mcp/mcp/transport/sse_manager.py` - Complete subscription implementation
- `routeros_mcp/mcp_resources/device.py` - Mark health resource as subscribable

**Tasks**:
1. Complete `SSEManager.subscribe()` implementation:
   - Accept resource URI (e.g., `device://{device_id}/health`)
   - Validate resource is subscribable
   - Register subscription with connection ID
   - Start periodic updates (every 30 seconds)
2. Implement periodic health updates:
   - Fetch current health check from database
   - Send SSE event to subscribed clients
   - Handle connection drops gracefully
3. Add subscription management endpoints:
   - `POST /sse/subscribe` - Create subscription
   - `DELETE /sse/unsubscribe` - Cancel subscription
4. Add SSE metrics:
   - Active subscription count
   - Events sent per subscription
   - Subscription errors/timeouts

**Estimated Effort**: 16-24 hours

**Acceptance Criteria**:
- [ ] All 4 skipped SSE metrics tests pass
- [ ] Clients can subscribe to `device://{device_id}/health`
- [ ] Health updates are sent every 30 seconds
- [ ] Subscriptions are cleaned up on disconnect
- [ ] SSE metrics are exposed via Prometheus

---

### 2. Multi-Device Coordination (HIGH PRIORITY)

**Goal**: Execute DNS/NTP rollouts across 2-50 devices with staged rollout and safety checks

#### 2.1 Job-Based Execution Engine

**Files to Create**:
- `routeros_mcp/domain/services/job.py` - Enhance existing job service
- `routeros_mcp/infra/jobs/runner.py` - Enhance existing job runner
- `routeros_mcp/infra/db/models.py` - Add job result fields

**Tasks**:
1. Enhance `Job` model with additional fields:
   - `progress_percent` (0-100)
   - `current_device_id` (for multi-device jobs)
   - `result_summary` (JSON: per-device results)
   - `cancellation_requested` (boolean)
2. Implement job state machine:
   - `pending` → `running` → `completed`/`failed`/`cancelled`
   - State transition validation
   - Audit logging on state changes
3. Add job cancellation support:
   - Check `cancellation_requested` flag in job loop
   - Graceful shutdown (finish current device, halt next batch)
   - Mark job as `cancelled` with partial results
4. Add job progress reporting:
   - Update `progress_percent` after each device
   - Store per-device results in `result_summary`
   - Expose job status endpoint: `GET /api/admin/jobs/{job_id}`

**Estimated Effort**: 20-30 hours

**Acceptance Criteria**:
- [ ] Jobs track progress percentage and current device
- [ ] Job cancellation works gracefully (finishes current device)
- [ ] Job status endpoint returns progress and results
- [ ] State transitions are validated and audited

#### 2.2 Multi-Device Plan/Apply Framework

**Files to Create/Modify**:
- `routeros_mcp/domain/services/plan.py` - Enhance with multi-device support
- `routeros_mcp/domain/services/dns_ntp.py` - Add multi-device methods
- `routeros_mcp/mcp_tools/config.py` - Add new multi-device tools

**Tasks**:
1. Extend `Plan` model for multi-device support:
   - `device_ids` (list of affected devices)
   - `batch_size` (default: 5)
   - `pause_seconds_between_batches` (default: 60)
   - `rollback_on_failure` (boolean, default: true)
   - `device_statuses` (JSON: per-device apply status)
2. Implement `plan_dns_ntp_rollout()` tool:
   - Accept list of device IDs (2-50 devices)
   - Validate all devices are reachable
   - Generate plan with staged batches
   - Calculate risk score per device
   - Return plan ID and approval token
3. Implement `apply_dns_ntp_rollout()` tool:
   - Validate approval token
   - Create background job for execution
   - Return job ID for status tracking
4. Implement staged rollout logic:
   - Divide devices into batches (configurable size)
   - Apply changes to batch 1
   - Run health checks on batch 1 devices
   - If healthy, proceed to batch 2
   - If degraded, halt and optionally rollback
   - Continue until all batches complete or failure
5. Add `rollback_plan()` tool:
   - Restore previous DNS/NTP settings per device
   - Track rollback success/failure
   - Update plan status to `rolled_back`

**Estimated Effort**: 40-60 hours

**Acceptance Criteria**:
- [ ] `config/plan-dns-ntp-rollout` creates multi-device plans
- [ ] `config/apply-dns-ntp-rollout` executes staged rollout with job tracking
- [ ] Health checks halt rollout on degradation
- [ ] `config/rollback-plan` restores previous state
- [ ] All operations are fully audited

---

### 3. Diagnostics Tools (HIGH PRIORITY)

**Goal**: Add network diagnostics tools deferred from Phase 1

#### 3.1 JSON-RPC Streaming Support

**Files to Create/Modify**:
- `routeros_mcp/mcp/protocol/jsonrpc.py` - Add streaming support
- `routeros_mcp/mcp/transport/http_sse.py` - Stream progress via SSE

**Tasks**:
1. Extend JSON-RPC protocol with streaming:
   - Accept `stream_progress=true` parameter
   - Return intermediate progress messages
   - Final message includes `result` field
2. Implement streaming in HTTP transport:
   - Use SSE for progress updates
   - Keep connection alive during execution
   - Send final result as last SSE event
3. Add timeout handling:
   - Per-tool timeout (ping: 30s, traceroute: 60s, bandwidth-test: 180s)
   - Send timeout error if exceeded
4. Document streaming protocol in docs/14 and docs/19

**Estimated Effort**: 20-30 hours

**Acceptance Criteria**:
- [ ] Tools can request `stream_progress=true`
- [ ] Progress updates are sent as SSE events
- [ ] Final result is marked clearly
- [ ] Streaming protocol is documented

#### 3.2 `tool/ping` Implementation

**Files to Create/Modify**:
- `routeros_mcp/mcp_tools/diagnostics.py` - Add `ping()` function
- `routeros_mcp/domain/services/diagnostics.py` - Add `ping_host()` method

**Tasks**:
1. Implement `ping()` MCP tool:
   - Parameters: `device_id`, `target`, `count` (default: 4), `packet_size` (default: 64)
   - RouterOS endpoint: `POST /rest/tool/ping`
   - Timeout: 30 seconds
   - Stream per-packet results if `stream_progress=true`
2. Add rate limiting:
   - Max 10 pings per device per minute
   - Return 429 Too Many Requests if exceeded
3. Add validation:
   - Validate target is IP address or hostname
   - Validate count is 1-100
   - Validate packet size is 28-65500 bytes
4. Return result:
   - Packets sent/received/lost
   - Average/min/max latency
   - Per-packet details if streaming

**Estimated Effort**: 8-12 hours

**Acceptance Criteria**:
- [ ] `tool/ping` successfully pings remote hosts
- [ ] Rate limiting prevents abuse
- [ ] Streaming returns per-packet results
- [ ] Non-streaming returns summary

#### 3.3 `tool/traceroute` Implementation

**Files to Modify**:
- `routeros_mcp/mcp_tools/diagnostics.py` - Add `traceroute()` function
- `routeros_mcp/domain/services/diagnostics.py` - Add `traceroute_host()` method

**Tasks**:
1. Implement `traceroute()` MCP tool:
   - Parameters: `device_id`, `target`, `max_hops` (default: 30)
   - RouterOS endpoint: `POST /rest/tool/traceroute`
   - Timeout: 60 seconds
   - Stream per-hop results if `stream_progress=true`
2. Add validation:
   - Validate target is IP address or hostname
   - Validate max_hops is 1-64
3. Return result:
   - Per-hop: IP address, hostname, latency
   - Total hops reached
   - Success/failure (reached target)

**Estimated Effort**: 8-12 hours

**Acceptance Criteria**:
- [ ] `tool/traceroute` successfully traces network paths
- [ ] Streaming returns per-hop results
- [ ] Final result includes success status

#### 3.4 `tool/bandwidth-test` Implementation

**Files to Modify**:
- `routeros_mcp/mcp_tools/diagnostics.py` - Add `bandwidth_test()` function
- `routeros_mcp/domain/services/diagnostics.py` - Add `test_bandwidth()` method

**Tasks**:
1. Implement `bandwidth_test()` MCP tool:
   - Parameters: `device_id`, `target_device_id`, `duration` (default: 10), `direction` (tx/rx/both)
   - RouterOS endpoint: `POST /rest/tool/bandwidth-test`
   - Timeout: 180 seconds
   - Stream throughput updates every second if `stream_progress=true`
2. Add validation:
   - Validate target device has `allow_bandwidth_test=true` capability
   - Validate duration is 5-60 seconds
   - Validate direction is valid enum
3. Return result:
   - TX throughput (Mbps)
   - RX throughput (Mbps)
   - Packet loss percentage
   - Periodic updates if streaming

**Estimated Effort**: 12-16 hours

**Acceptance Criteria**:
- [ ] `tool/bandwidth-test` measures throughput between devices
- [ ] Only works if target device has capability enabled
- [ ] Streaming returns periodic throughput updates
- [ ] Final result includes average throughput

---

### 4. Infrastructure Improvements (MEDIUM PRIORITY)

#### 4.1 TimescaleDB Integration

**Files to Modify**:
- `routeros_mcp/infra/db/models.py` - Mark `health_checks` for hypertable
- `alembic/versions/*_timescaledb.py` - Create migration
- `routeros_mcp/domain/services/health.py` - Update queries for TimescaleDB

**Tasks**:
1. Create Alembic migration for TimescaleDB:
   - Convert `health_checks` to hypertable on `timestamp` column
   - Create retention policy (30 days raw, aggregate older)
   - Create continuous aggregates (hourly CPU/memory)
2. Update health check queries:
   - Use time_bucket() for aggregations
   - Leverage continuous aggregates for dashboard queries
3. Document TimescaleDB setup in docs/06
4. Add TimescaleDB to optional dependencies

**Estimated Effort**: 12-16 hours

**Acceptance Criteria**:
- [ ] `health_checks` is a TimescaleDB hypertable
- [ ] Retention policy automatically drops old data
- [ ] Continuous aggregates improve query performance
- [ ] Setup is documented

#### 4.2 Adaptive Polling Strategy

**Files to Modify**:
- `routeros_mcp/domain/services/health.py` - Add adaptive intervals
- `routeros_mcp/infra/jobs/scheduler.py` - Dynamic schedule adjustment

**Tasks**:
1. Implement device classification:
   - Critical devices: Poll every 30 seconds
   - Non-critical devices: Poll every 60 seconds
   - Configurable per-device via `critical` flag
2. Implement interval adjustment:
   - Start at base interval (30s or 60s)
   - If 10 consecutive healthy checks, increase interval by 50%
   - If any unhealthy check, reset to base interval
   - Max interval: 5 minutes
3. Implement exponential backoff on failures:
   - On unreachable: Retry after 1min, 2min, 4min, 8min, 16min (max)
   - Return to base interval when reachable again
4. Add device health status:
   - `healthy`: All checks passing
   - `degraded`: Some checks failing
   - `unreachable`: Device not responding

**Estimated Effort**: 16-20 hours

**Acceptance Criteria**:
- [ ] Critical devices polled more frequently
- [ ] Stable devices polled less frequently
- [ ] Unreachable devices use exponential backoff
- [ ] Device status reflects health state

---

### 5. Web Admin UI (MEDIUM PRIORITY)

#### 5.1 Initial Admin Interface

**Goal**: Web UI for device management and plan approval

**Technology Stack**:
- Frontend: React 18+ or Vue 3+
- Backend: FastAPI (existing)
- Styling: Tailwind CSS or Material UI
- State Management: React Context / Redux or Vue Pinia

**Files to Create**:
- `frontend/` - New directory for SPA
- `frontend/src/pages/DeviceList.tsx` - Device management page
- `frontend/src/pages/PlanApproval.tsx` - Plan approval page
- `frontend/src/pages/AuditLog.tsx` - Audit log viewer

**Tasks**:
1. Set up frontend project:
   - Initialize React/Vue project with Vite
   - Configure Tailwind CSS / Material UI
   - Set up routing (React Router / Vue Router)
   - Configure API client (axios or fetch)
2. Implement Device Management page:
   - List all devices with status indicators
   - Add device form (hostname, credentials)
   - Edit device details
   - Remove device (with confirmation)
   - Test connectivity button
3. Implement Plan Approval page:
   - List pending plans
   - Show plan details (affected devices, changes)
   - Diff view (current vs. proposed)
   - Approve/reject buttons
   - Approval comment field
4. Implement Audit Log viewer:
   - Paginated list of audit events
   - Filter by user, device, tool, date range
   - Search functionality
   - Export to CSV
5. Add authentication:
   - Login page (Phase 4: service account, Phase 5: per-user)
   - Store bearer token in localStorage
   - Add token to all API requests
   - Redirect to login on 401

**Estimated Effort**: 60-80 hours

**Acceptance Criteria**:
- [ ] Device CRUD operations work via UI
- [ ] Plan approval queue is functional
- [ ] Audit log viewer displays events
- [ ] UI is responsive and accessible

---

### 6. SSH & Compatibility (LOW PRIORITY)

#### 6.1 SSH Key-Based Authentication

**Files to Modify**:
- `routeros_mcp/domain/models.py` - Add `routeros_ssh_key` credential type
- `routeros_mcp/infra/routeros/ssh_client.py` - Support key auth
- `routeros_mcp/security/crypto.py` - Add key encryption

**Tasks**:
1. Add `routeros_ssh_key` credential type:
   - Fields: `private_key` (encrypted), `public_key_fingerprint`
   - Validation: Valid SSH private key format
2. Modify `SSHClient` to support key auth:
   - Try key auth first, fallback to password
   - Load encrypted private key from database
   - Decrypt key using encryption key
3. Add key rotation API:
   - Generate new SSH key pair
   - Upload public key to RouterOS
   - Store encrypted private key
   - Revoke old key
4. Document key setup in docs/02

**Estimated Effort**: 16-24 hours

**Acceptance Criteria**:
- [ ] SSH key auth works as alternative to password
- [ ] Keys are stored encrypted
- [ ] Key rotation is supported
- [ ] Fallback to password if key unavailable

#### 6.2 Client Compatibility Modes

**Files to Modify**:
- `routeros_mcp/infra/routeros/rest_client.py` - Add version detection
- `routeros_mcp/domain/services/*` - Add conditional endpoint logic

**Tasks**:
1. Implement version detection:
   - Query `GET /rest/system/package` on first connect
   - Parse RouterOS version (e.g., "7.10.2")
   - Store version in `Device` model
2. Create endpoint mapping:
   - Map v6.x endpoints to v7.x equivalents
   - Handle renamed fields (e.g., `interface/ether` → `interface/ethernet`)
3. Add conditional field handling:
   - Skip fields not available in older versions
   - Provide default values for missing fields
4. Document compatibility in docs/03

**Estimated Effort**: 20-30 hours

**Acceptance Criteria**:
- [ ] RouterOS v6.x devices are detected
- [ ] Endpoints are mapped correctly
- [ ] Fields are handled conditionally
- [ ] Compatibility is documented

#### 6.3 Automated Approval Tokens

**Files to Modify**:
- `routeros_mcp/domain/services/plan.py` - Add auto-approval logic
- `routeros_mcp/config.py` - Add trusted workflows config

**Tasks**:
1. Add trusted workflow configuration:
   - YAML field: `trusted_workflows` (list of workflow names)
   - Workflow definition: name, device_scope, environment
2. Implement auto-approval logic:
   - Check if plan matches trusted workflow
   - Validate device scope and environment
   - Generate approval token automatically
   - Log auto-approval with automation context
3. Add auditing for auto-approved plans:
   - Flag in audit log: `auto_approved=true`
   - Workflow name in audit context

**Estimated Effort**: 12-16 hours

**Acceptance Criteria**:
- [ ] Trusted workflows can be configured
- [ ] Matching plans get auto-generated tokens
- [ ] Auto-approvals are clearly audited

---

## Testing Strategy

### Unit Tests
- [ ] Multi-device plan service tests
- [ ] Job state machine tests
- [ ] Diagnostics tool tests (ping, traceroute, bandwidth-test)
- [ ] JSON-RPC streaming tests
- [ ] OAuth middleware tests
- [ ] SSE subscription tests

### Integration Tests
- [ ] Multi-device rollout integration test (5 mock devices)
- [ ] Staged rollout with health check halt
- [ ] Diagnostics tools with real RouterOS (lab)
- [ ] SSE subscription end-to-end

### E2E Tests
- [ ] Fix 7 skipped HTTP transport E2E tests
- [ ] Fix 4 skipped SSE metrics tests
- [ ] Add multi-device coordination E2E test
- [ ] Add web UI E2E tests (Playwright or Cypress)

### Performance Tests
- [ ] Load test: 50 devices, 5 concurrent rollouts
- [ ] SSE subscription scalability (100 subscriptions)
- [ ] TimescaleDB query performance vs. PostgreSQL

**Coverage Target**: Maintain 82%+ overall, 95%+ for core modules

---

## Documentation Updates

### Docs to Update
- [ ] **docs/01** - Add Phase 4 architecture details (multi-device, web UI)
- [ ] **docs/02** - Document SSH key auth and service account OIDC
- [ ] **docs/03** - Add diagnostics endpoints
- [ ] **docs/04** - Add 6 new tools with schemas
- [ ] **docs/05** - Update Plan and Job models
- [ ] **docs/06** - Document TimescaleDB and adaptive polling
- [ ] **docs/14** - Add JSON-RPC streaming protocol
- [ ] **docs/20** - Update HTTP/SSE deployment guide

### New Docs to Create
- [ ] **docs/PHASE4_IMPLEMENTATION_PLAN.md** (this document)
- [ ] **docs/25-web-admin-ui-design.md** - Web UI architecture
- [ ] **docs/26-multi-device-orchestration.md** - Staged rollout design

---

## Sprint Plan (Recommended)

### Sprint 1-2: HTTP/SSE Foundation (80-120 hours)
**Goal**: Complete HTTP/SSE transport and fix skipped tests

**Week 1-2**:
- [ ] Add `sse-starlette` dependency
- [ ] Complete HTTP server implementation
- [ ] Wire HTTP mode in `mcp/server.py`
- [ ] Fix 7 skipped E2E HTTP tests

**Week 3-4**:
- [ ] OAuth/OIDC middleware for service account
- [ ] SSE resource subscriptions
- [ ] Fix 4 skipped SSE metrics tests
- [ ] Integration tests

**Deliverable**: Production-ready HTTP/SSE transport

---

### Sprint 3-4: Diagnostics & Streaming (68-100 hours)
**Goal**: Add network diagnostics with streaming support

**Week 5-6**:
- [ ] JSON-RPC streaming protocol
- [ ] `tool/ping` implementation with rate limiting
- [ ] `tool/traceroute` implementation
- [ ] Unit tests

**Week 7-8**:
- [ ] `tool/bandwidth-test` implementation
- [ ] E2E diagnostics tests with lab device
- [ ] Documentation updates (docs/03, docs/04)

**Deliverable**: Functional diagnostics tools

---

### Sprint 5-7: Multi-Device Coordination (100-150 hours)
**Goal**: Orchestrated multi-device operations with safety

**Week 9-11**:
- [ ] Job-based execution engine enhancements
- [ ] Multi-device plan/apply framework
- [ ] Staged rollout logic with health checks

**Week 12-14**:
- [ ] Rollback mechanism
- [ ] E2E multi-device tests (5 mock devices)
- [ ] Load tests (50 devices)
- [ ] Documentation updates (docs/05, docs/26)

**Deliverable**: Safe multi-device DNS/NTP rollouts

---

### Sprint 8-9: Infrastructure & UI (Optional - 88-116 hours)
**Goal**: Scale infrastructure and web admin UI

**Week 15-16**:
- [ ] TimescaleDB integration
- [ ] Adaptive polling strategy
- [ ] Performance benchmarks

**Week 17-18**:
- [ ] Web Admin UI scaffolding
- [ ] Device management page
- [ ] Plan approval page
- [ ] Audit log viewer

**Deliverable**: Basic web admin interface

---

## Success Criteria

Phase 4 is complete when:

1. **HTTP/SSE Transport**: ✅
   - [ ] All 11 skipped tests pass (7 HTTP + 4 SSE)
   - [ ] HTTP server handles JSON-RPC requests
   - [ ] SSE subscriptions deliver real-time updates
   - [ ] OAuth middleware validates tokens

2. **Multi-Device Coordination**: ✅
   - [ ] DNS/NTP rollouts across 2-50 devices work
   - [ ] Staged rollout halts on health check failure
   - [ ] Rollback restores previous state
   - [ ] Job tracking provides progress updates

3. **Diagnostics Tools**: ✅
   - [ ] `tool/ping`, `tool/traceroute`, `tool/bandwidth-test` work
   - [ ] Streaming provides real-time progress
   - [ ] Rate limiting prevents abuse

4. **Infrastructure**: ✅
   - [ ] TimescaleDB efficiently stores metrics
   - [ ] Adaptive polling adjusts intervals
   - [ ] Web UI provides device and plan management

5. **Quality**: ✅
   - [ ] 82%+ test coverage maintained
   - [ ] All E2E tests pass
   - [ ] Performance targets met (50 devices, 5 concurrent rollouts)
   - [ ] Documentation updated

---

## Dependencies

**Phase 4 depends on**:
- Phase 1-3 complete ✅
- PostgreSQL 14+ (or SQLite for dev)
- Optional: TimescaleDB extension for PostgreSQL

**Phase 5 depends on**:
- Phase 4 HTTP/SSE transport complete
- OAuth/OIDC provider (Azure AD, Okta, Auth0)

---

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Multi-device rollout complexity | High | Medium | Start with 2-5 devices, comprehensive testing |
| Diagnostics tool abuse | Medium | Low | Rate limiting, timeout enforcement |
| TimescaleDB learning curve | Low | Medium | Optional feature, can defer |
| Web UI scope creep | Medium | High | Phase 4 UI is minimal, Phase 5 adds full features |
| HTTP/SSE testing challenges | Medium | Medium | Use Docker Compose for E2E tests |

---

## References

- **README.md**: Phase 4 section (lines 282-347)
- **docs/01**: Architecture & deployment
- **docs/02**: Security model
- **docs/03**: RouterOS endpoints
- **docs/04**: MCP tools specification
- **docs/14**: MCP protocol & transport
- **docs/20-24**: HTTP/SSE deployment & OAuth guides

---

**Document Version**: 1.0
**Last Updated**: 2026-01-05
**Status**: Ready for Implementation
