# Phase 5 Issue Plan — Ready for Review

This document proposes a set of well-scoped GitHub issues to implement Phase 5 (Multi-User RBAC & Governance) features. Each issue follows the best practices in docs/best_practice/github-copilot-coding-agent-best-practices.md: tight scope, commands early, concrete acceptance criteria, explicit file targets, and clear do-not-change boundaries.

## How to Use
- Review and edit these issue drafts as needed.
- When approved, create GitHub issues from each section. Use labels and cross-links as provided.
- Execute in sprints as outlined in PHASE5_IMPLEMENTATION_PLAN.md.

## Quick Commands (used in issues below)
- Run fast unit tests: `uv run pytest tests/unit -q`
- Run full suite: `uv run pytest`
- Lint: `ruff check routeros_mcp tests`
- Format: `black routeros_mcp tests`
- Type check: `mypy routeros_mcp tests`

---

## Index
- [1. OAuth 2.1 Authorization Code Flow (Base)](#1-oauth-21-authorization-code-flow-base)
- [2. OIDC Callback, Token Refresh, Logout](#2-oidc-callback-token-refresh-logout)
- [3. Redis-Backed Session Store](#3-redis-backed-session-store)
- [4. RBAC Models (Role, Permission) + Migration](#4-rbac-models-role-permission--migration)
- [5. Authorization Middleware (Per-Tool/Device/Environment)](#5-authorization-middleware-per-tooldeviceenvironment)
- [6. Per-User Device Scopes (Models + Admin API)](#6-per-user-device-scopes-models--admin-api)
- [7. ApprovalRequest Model + Approval API (Skeleton)](#7-approvalrequest-model--approval-api-skeleton)
- [8. Approver Role Enforcement (No Self-Approval)](#8-approver-role-enforcement-no-self-approval)
- [9. Notification Service (Email + Slack) Minimal](#9-notification-service-email--slack-minimal)
- [10. AuditEvent: Per-User Fields + Logging](#10-auditevent-per-user-fields--logging)
- [11. Compliance Reports: Production Changes (Baseline)](#11-compliance-reports-production-changes-baseline)
- [12. Policy Engine Framework + YAML Policies](#12-policy-engine-framework--yaml-policies)
- [13. Rate Limiting Middleware + Redis Limiter](#13-rate-limiting-middleware--redis-limiter)
- [14. Redis Resource Cache + Distributed Health Scheduling](#14-redis-resource-cache--distributed-health-scheduling)
- [15. Health Endpoint + Graceful Shutdown](#15-health-endpoint--graceful-shutdown)
- [16. Web Admin UI: User Management (Skeleton)](#16-web-admin-ui-user-management-skeleton)
- [17. Web Admin UI: Compliance Dashboard (Skeleton)](#17-web-admin-ui-compliance-dashboard-skeleton)

---

## 1. OAuth 2.1 Authorization Code Flow (Base)

**Labels:** `phase5`, `auth`, `high-priority`, `backend`

**Context:** Phase 5 requires per-user authentication via OAuth 2.1/OIDC (Authorization Code + PKCE). Establish base client and flow wrappers.

**Change Request:** Implement foundational code to initiate the Authorization Code flow and PKCE generation utilities.

**Acceptance Criteria:**
- [ ] Utility generates PKCE verifier/challenge securely.
- [ ] Login endpoint returns redirect to configured OIDC authorization URL with correct params.
- [ ] Configuration keys added to `Settings` for OIDC (issuer, client_id, redirect_uri, scopes).
- [ ] Unit tests cover PKCE generation and login redirect builder.
- [ ] `ruff`, `black`, `mypy` pass; unit tests pass.

**Files to Modify / Add:**
- routeros_mcp/security/oidc.py (new): PKCE helpers, auth URL builder.
- routeros_mcp/config.py: Add OIDC config fields.
- routeros_mcp/api/http.py: Wire login route (stub only).
- tests/unit/security/test_oidc.py (new).

**Do Not Change:**
- Existing MCP tool behaviors.
- Production configuration defaults beyond adding new optional fields.

**How to Test:**
- `uv run pytest tests/unit/security -q`
- `ruff check routeros_mcp tests && black --check routeros_mcp tests && mypy routeros_mcp`

**Dependencies:** None (entry point for Phase 5 auth).

---

## 2. OIDC Callback, Token Refresh, Logout

**Labels:** `phase5`, `auth`, `backend`

**Context:** After login redirect, handle provider callback, exchange code for tokens, parse ID token claims, and support logout & refresh.

**Change Request:** Implement callback handler to exchange authorization code for tokens, extract user claims, and create minimal session object. Add logout and refresh.

**Acceptance Criteria:**
- [ ] Callback endpoint exchanges code for tokens and validates ID token.
- [ ] Basic `UserSession` object created with `sub`, `email`, `display_name`.
- [ ] Refresh endpoint renews access token on expiry; logout revokes tokens.
- [ ] Unit tests mock provider responses; happy-path and error-path covered.
- [ ] `ruff`, `black`, `mypy` pass; unit tests pass.

**Files to Modify / Add:**
- routeros_mcp/security/oidc.py: Token exchange, validation, refresh, logout.
- routeros_mcp/api/http.py: Add `/auth/callback`, `/auth/refresh`, `/auth/logout`.
- tests/unit/security/test_oidc_callback.py (new).

**Do Not Change:**
- MCP stdio transport behavior.

**How to Test:**
- `uv run pytest tests/unit/security -q`

**Dependencies:** Issue 1.

---

## 3. Redis-Backed Session Store

**Labels:** `phase5`, `infra`, `redis`, `backend`

**Context:** Multi-instance requires shared session state. Store sessions in Redis with TTL.

**Change Request:** Implement Redis session storage and pluggable session backend.

**Acceptance Criteria:**
- [ ] `Settings` includes Redis config (url, pool, timeouts).
- [ ] Session CRUD backed by Redis with 8-hour TTL (sliding window).
- [ ] Unit tests simulate concurrent access and expiration.
- [ ] `ruff`, `black`, `mypy` pass; unit tests pass.

**Files to Modify / Add:**
- routeros_mcp/infra/session/store.py (new): Redis-backed store.
- routeros_mcp/config.py: Add Redis settings (redis_url, pool_size, timeout).
- tests/unit/infra/test_session_store.py (new).

**Do Not Change:**
- Database schema unrelated to sessions.

**How to Test:**
- `uv run pytest tests/unit/infra -q`

**Dependencies:** Issues 1–2.

---

## 4. RBAC Models (Role, Permission) + Migration

**Labels:** `phase5`, `rbac`, `backend`, `db`

**Context:** Introduce `Role` and `Permission` models with migrations to support RBAC.

**Change Request:** Define SQLAlchemy models and Alembic migration; seed default roles.

**Acceptance Criteria:**
- [ ] Models: `Role(name, description)`, `Permission(resource_type, resource_id, action)`; M2M relation.
- [ ] Alembic migration installs tables; seed roles: read_only, ops_rw, admin, approver.
- [ ] Unit tests validate role-permission lookups.
- [ ] `ruff`, `black`, `mypy` pass; unit tests pass.

**Files to Modify / Add:**
- routeros_mcp/infra/db/models.py: Add Role, Permission.
- alembic/versions/xxxx_phase5_rbac.py (new).
- tests/unit/security/test_rbac_models.py (new).

**Do Not Change:**
- Existing device/plan tables.

**How to Test:**
- `uv run pytest tests/unit/security -q`
- `alembic upgrade head` locally to verify migration.

**Dependencies:** Issue 3 (sessions optional), can proceed in parallel.

---

## 5. Authorization Middleware (Per-Tool/Device/Environment)

**Labels:** `phase5`, `rbac`, `backend`

**Context:** Enforce RBAC and device scopes before tool execution.

**Change Request:** Implement middleware that maps user to permissions and validates tool tier, device scopes, and environment.

**Acceptance Criteria:**
- [ ] Middleware blocks unauthorized tool executions with 403 and clear message.
- [ ] Audit logs include authorization decisions (allow/deny).
- [ ] Unit tests cover tier mismatches, device scope denials, env restrictions.
- [ ] `ruff`, `black`, `mypy` pass; unit tests pass.

**Files to Modify / Add:**
- routeros_mcp/security/authz.py: Authorization checks.
- routeros_mcp/mcp/middleware/auth.py: Wire per-request enforcement.
- tests/unit/security/test_authz_middleware.py (new).

**Do Not Change:**
- Tool implementations; only guard execution.

**How to Test:**
- `uv run pytest tests/unit/security -q`

**Dependencies:** Issues 3–4.

---

## 6. Per-User Device Scopes (Models + Admin API)

**Labels:** `phase5`, `rbac`, `backend`, `api`, `db`

**Context:** Grant users access to specific devices or groups.

**Change Request:** Implement `DeviceGroup`, `UserDeviceScope` models and admin endpoints to manage scopes.

**Acceptance Criteria:**
- [ ] Models and migration created; scope resolution supports explicit devices and groups.
- [ ] Admin API: grant, revoke, list scopes.
- [ ] Audit logs for scope changes.
- [ ] Unit tests for resolution logic and API.
- [ ] `ruff`, `black`, `mypy` pass; unit tests pass.

**Files to Modify / Add:**
- routeros_mcp/infra/db/models.py: DeviceGroup, UserDeviceScope.
- alembic/versions/xxxx_phase5_scopes.py (new).
- routeros_mcp/api/admin.py: Scope management endpoints.
- tests/unit/api/test_admin_scopes.py (new).

**Do Not Change:**
- MCP tool contracts.

**How to Test:**
- `uv run pytest tests/unit/api -q`

**Dependencies:** Issues 4–5.

---

## 7. ApprovalRequest Model + Approval API (Skeleton)

**Labels:** `phase5`, `approval`, `backend`, `api`, `db`

**Context:** High-risk operations require a formal approval request.

**Change Request:** Create `ApprovalRequest` model and minimal API to list/create/approve/reject.

**Acceptance Criteria:**
- [ ] Model includes requester, approver, status, risk_level, timestamps.
- [ ] API: list pending, my requests, approve, reject.
- [ ] Expiration job marks requests expired after 24h.
- [ ] Unit tests for lifecycle; `ruff`, `black`, `mypy` pass.

**Files to Modify / Add:**
- routeros_mcp/infra/db/models.py: ApprovalRequest.
- alembic/versions/xxxx_phase5_approval.py (new).
- routeros_mcp/domain/services/approval.py (new): business logic.
- routeros_mcp/api/approval.py (new): endpoints.
- tests/unit/approval/test_approval_service.py (new).

**Do Not Change:**
- Plan/apply semantics in tools.

**How to Test:**
- `uv run pytest tests/unit/approval -q`

**Dependencies:** Issues 4–6.

---

## 8. Approver Role Enforcement (No Self-Approval)

**Labels:** `phase5`, `approval`, `rbac`, `backend`

**Context:** Separation of duties requires blocking self-approval and enabling delegation/escalation.

**Change Request:** Enforce approver role for approvals, block requester==approver, add delegation and escalation.

**Acceptance Criteria:**
- [ ] Approvals require `approver` role; requester cannot self-approve.
- [ ] Delegation recorded and audited.
- [ ] Escalation triggers on SLA breach (configurable, default 4h).
- [ ] Unit tests for denial, delegation, escalation.

**Files to Modify / Add:**
- routeros_mcp/security/rbac.py: Approver role checks.
- routeros_mcp/domain/services/approval.py: Enforcement logic.
- tests/unit/approval/test_approver_rules.py (new).

**Do Not Change:**
- Approval request schema.

**How to Test:**
- `uv run pytest tests/unit/approval -q`

**Dependencies:** Issue 7.

---

## 9. Notification Service (Email + Slack) Minimal

**Labels:** `phase5`, `notifications`, `backend`, `infra`

**Context:** Notify approvers of pending requests via email and Slack.

**Change Request:** Implement a minimal notifier abstraction with email (SMTP) and Slack webhook providers.

**Acceptance Criteria:**
- [ ] Notifier interface and implementations for email and Slack.
- [ ] Settings support SMTP and Slack webhook configuration.
- [ ] Unit tests stub providers; no external calls in tests.

**Files to Modify / Add:**
- routeros_mcp/infra/notifications/notifier.py (new).
- routeros_mcp/infra/notifications/email.py (new).
- routeros_mcp/infra/notifications/slack.py (new).
- routeros_mcp/config.py: Add SMTP/Slack settings.
- tests/unit/infra/test_notifications.py (new).

**Do Not Change:**
- Approval API behavior.

**How to Test:**
- `uv run pytest tests/unit/infra -q`

**Dependencies:** Issue 7.

---

## 10. AuditEvent: Per-User Fields + Logging

**Labels:** `phase5`, `audit`, `backend`, `db`

**Context:** Governance requires per-user audit trails for all operations.

**Change Request:** Extend `AuditEvent` with `user_id`, `user_email`, `tool_name`, `result`, optional `approval_request_id`; include auth denials.

**Acceptance Criteria:**
- [ ] Model updated; migration applied.
- [ ] Logging helpers attach user context to all tool calls.
- [ ] Denied authorizations logged with reason.
- [ ] Unit tests validate audit entries.

**Files to Modify / Add:**
- routeros_mcp/infra/db/models.py: AuditEvent fields.
- alembic/versions/xxxx_phase5_audit.py (new).
- routeros_mcp/infra/observability/logging.py: Context enrichment.
- tests/unit/infra/test_audit_logging.py (new).

**Do Not Change:**
- Existing log formats (extend with fields only).

**How to Test:**
- `uv run pytest tests/unit/infra -q`

**Dependencies:** Issues 3–5.

---

## 11. Compliance Reports: Production Changes (Baseline)

**Labels:** `phase5`, `compliance`, `backend`, `api`

**Context:** Generate production change report by user/device/tool over a date range.

**Change Request:** Implement report service and API for production changes with CSV/JSON export.

**Acceptance Criteria:**
- [ ] Service aggregates audit data per spec.
- [ ] API generates and returns CSV/JSON.
- [ ] Unit tests validate aggregation and formatting.

**Files to Modify / Add:**
- routeros_mcp/domain/services/compliance.py (new).
- routeros_mcp/api/compliance.py (new).
- tests/unit/compliance/test_production_changes_report.py (new).

**Do Not Change:**
- Audit logging semantics.

**How to Test:**
- `uv run pytest tests/unit/compliance -q`

**Dependencies:** Issue 10.

---

## 12. Policy Engine Framework + YAML Policies

**Labels:** `phase5`, `policy`, `backend`

**Context:** Enforce organizational policies before tool execution.

**Change Request:** Implement policy engine, YAML parser, and evaluation hooks.

**Acceptance Criteria:**
- [ ] YAML schema supports approval-required, require-comment, rate-limit, time-window.
- [ ] Engine evaluates policies and blocks with 403 on violation.
- [ ] Unit tests cover each policy type.

**Files to Modify / Add:**
- routeros_mcp/domain/services/policy.py (new).
- routeros_mcp/config/policies.yaml (example, non-prod) (new).
- tests/unit/policy/test_policy_engine.py (new).

**Do Not Change:**
- RBAC decisions (policies are additional layer).

**How to Test:**
- `uv run pytest tests/unit/policy -q`

**Dependencies:** Issues 5, 10, 13.

---

## 13. Rate Limiting Middleware + Redis Limiter

**Labels:** `phase5`, `rate-limit`, `backend`, `infra`

**Context:** Prevent abuse via per-user quotas with Redis-backed counters.

**Change Request:** Implement rate limit middleware with role-based defaults and headers.

**Acceptance Criteria:**
- [ ] Enforces hourly/daily limits per role as defaults.
- [ ] Returns `429` with `Retry-After` and `X-RateLimit-*` headers.
- [ ] Unit tests for limit hit, reset, and concurrency.

**Files to Modify / Add:**
- routeros_mcp/infra/rate_limit/limiter.py (new).
- routeros_mcp/mcp/middleware/rate_limit.py (new).
- tests/unit/infra/test_rate_limit.py (new).

**Do Not Change:**
- Business logic in tools.

**How to Test:**
- `uv run pytest tests/unit/infra -q`

**Dependencies:** Issue 3.

---

## 14. Redis Resource Cache + Distributed Health Scheduling

**Labels:** `phase5`, `infra`, `redis`, `backend`

**Context:** Replace in-memory resource cache with Redis and coordinate health checks via distributed locks.

**Change Request:** Implement Redis cache for resources and scheduler locks for health checks.

**Acceptance Criteria:**
- [ ] Resource cache keys and TTLs per design (health 5m, config 1h as example).
- [ ] Health scheduling uses Redis lock per device; no duplicate checks.
- [ ] Unit tests simulate multi-instance behavior.

**Files to Modify / Add:**
- routeros_mcp/infra/observability/resource_cache.py (new or modified to use Redis).
- routeros_mcp/infra/jobs/scheduler.py: Add lock handling.
- tests/unit/infra/test_resource_cache.py (new).

**Do Not Change:**
- Tool outputs.

**How to Test:**
- `uv run pytest tests/unit/infra -q`

**Dependencies:** Issue 3.

---

## 15. Health Endpoint + Graceful Shutdown

**Labels:** `phase5`, `infra`, `ha`, `backend`

**Context:** Provide `/health` endpoint and graceful shutdown for HA deployments.

**Change Request:** Implement health check endpoint and SIGTERM handling.

**Acceptance Criteria:**
- [ ] `/health` returns 200 when DB and Redis ok; 503 otherwise.
- [ ] Graceful shutdown stops accepting new requests and drains in-flight within timeout.
- [ ] Unit tests for endpoint and shutdown hooks.

**Files to Modify / Add:**
- routeros_mcp/api/http.py: Add `/health` route.
- routeros_mcp/main.py: SIGTERM handling.
- tests/unit/api/test_health_endpoint.py (new).

**Do Not Change:**
- MCP protocol stdout semantics.

**How to Test:**
- `uv run pytest tests/unit/api -q`

**Dependencies:** Issue 3.

---

## 16. Web Admin UI: User Management (Skeleton)

**Labels:** `phase5`, `frontend`, `ui`, `admin`

**Context:** Admins need to manage users, roles, and device scopes.

**Change Request:** Add a skeleton page to list users, edit roles, and assign device scopes.

**Acceptance Criteria:**
- [ ] Page renders user list via API; edit role via dropdown; assign scopes via multi-select.
- [ ] Basic input validation; no visual polish required (skeleton).
- [ ] Unit tests (frontend) where applicable; backend API already covered.

**Files to Modify / Add:**
- frontend/src/pages/UserManagement.tsx (new).
- frontend/src/services/api.ts (extend): fetch users/roles/scopes.

**Do Not Change:**
- Existing build tooling or global styles.

**How to Test:**
- `npm test` (if configured) and manual run when applicable.

**Dependencies:** Issues 4–6 (backend APIs).

---

## 17. Web Admin UI: Compliance Dashboard (Skeleton)

**Labels:** `phase5`, `frontend`, `ui`, `compliance`

**Context:** Visualize approval queue, audit trail filters, and key compliance metrics.

**Change Request:** Add a skeleton compliance dashboard with widgets and basic charts.

**Acceptance Criteria:**
- [ ] Approval queue widget shows pending approvals.
- [ ] Audit log widget lists events with filters.
- [ ] Metrics summary shows counts (changes, violations, top users).

**Files to Modify / Add:**
- frontend/src/pages/ComplianceDashboard.tsx (new).
- frontend/src/components/ApprovalQueueWidget.tsx (new).
- frontend/src/components/AuditLogWidget.tsx (new).

**Do Not Change:**
- Backend semantics; UI calls existing APIs.

**How to Test:**
- `npm test` and manual verification.

**Dependencies:** Issues 7, 10, 11.

---

## Sprint Guidance
- Sprints 1–2: Issues 1–5 (Auth & RBAC core)
- Sprints 3–4: Issues 7–9 (Approvals & Notifications)
- Sprints 5–6: Issues 10–13 (Governance, Policy, Rate Limiting)
- Sprints 7–8: Issues 14–15 (Multi-Instance & HA)
- Sprints 9–10: Issues 16–17 (Web Admin UI skeletons)

## Notes
- Keep changes focused; avoid repo-wide refactors.
- Always run lint/format/type checks and unit tests locally before PR.
- Add only necessary dependencies; ask before introducing heavy frameworks.
