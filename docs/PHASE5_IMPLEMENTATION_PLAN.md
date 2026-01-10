# Phase 5 Implementation Plan

**RouterOS MCP Service - Multi-User RBAC & Governance**

## Overview

Phase 5 transforms the single-user Phase 4 system into an enterprise-ready multi-user platform with comprehensive role-based access control, approval workflows, and governance features. This phase enables organizations to safely delegate network operations across teams with proper separation of duties and compliance tracking.

**Status**: Planned (Phase 4 required first)
**Estimated Effort**: 396-564 hours (10-14 weeks @ 40hrs/week)
**New Tools**: 0 (Phase 5 focuses on governance around existing 68 tools)
**Total Tools After Phase 5**: 68 tools (unchanged)

## Key Objectives

1. **Multi-User Authentication** - Per-user OAuth 2.1/OIDC with Authorization Code flow
2. **RBAC** - Five roles with per-tool, per-device, per-environment permissions
3. **Approval Workflows** - Formal approval process with separate approver roles
4. **Governance** - Per-user audit trails, compliance reporting, policy enforcement
5. **Enterprise Scale** - Horizontal scaling, high availability, multi-instance deployment

## Phase 5 Feature Breakdown

### 1. Authentication & Authorization (HIGH PRIORITY)

#### 1.1 OAuth 2.1 / OIDC Full Integration

**Goal**: Per-user authentication with Authorization Code flow + PKCE

**Current Phase 4 State**: Single service account with bearer token validation

**Files to Modify**:
- `routeros_mcp/security/oidc.py` - Add Authorization Code flow
- `routeros_mcp/mcp/transport/auth_middleware.py` - Per-user token handling
- `routeros_mcp/domain/models.py` - Add `User` model

**Tasks**:
1. Create `User` model:
   ```python
   class User(Base):
       id: UUID
       oidc_sub: str  # OIDC subject claim (unique per provider)
       email: str
       display_name: str
       role: str  # read_only, ops_rw, admin, approver
       device_scopes: List[UUID]  # Accessible device IDs
       active: bool
       created_at: datetime
       last_login_at: datetime
   ```
2. Implement Authorization Code flow:
   - Add login endpoint: `GET /auth/login` → Redirect to OIDC provider
   - Add callback endpoint: `GET /auth/callback` → Exchange code for tokens
   - Store access token and refresh token securely
   - Extract user identity from ID token claims
   - Create or update `User` record from OIDC claims
3. Implement token refresh:
   - Detect expired access token (401 from API)
   - Use refresh token to get new access token
   - Update stored tokens
4. Add logout endpoint:
   - Revoke tokens with OIDC provider
   - Clear session data
5. Support multiple OIDC providers:
   - Azure AD (existing docs/21)
   - Okta (existing docs/22)
   - Auth0 (existing docs/23)
   - Custom OIDC (generic configuration)
6. Add session management:
   - Store sessions in Redis (multi-instance support)
   - 8-hour session timeout (configurable)
   - Refresh on activity (sliding window)

**Estimated Effort**: 40-60 hours

**Acceptance Criteria**:
- [ ] Users can log in via OIDC provider
- [ ] User identity is extracted from ID token
- [ ] Access tokens are refreshed automatically
- [ ] Multiple OIDC providers are supported
- [ ] Sessions are stored in Redis for multi-instance

#### 1.2 Multi-User RBAC

**Goal**: Five roles with granular permissions

**Roles**:
1. **read_only**: Fundamental tools only (read-only, diagnostics)
2. **ops_rw**: Advanced tools (single-device writes)
3. **admin**: Professional tools (multi-device, management)
4. **approver**: Can approve high-risk operations (no tool execution)
5. **custom_roles**: Organization-defined (Phase 5.1+)

**Files to Create/Modify**:
- `routeros_mcp/security/rbac.py` - New RBAC engine
- `routeros_mcp/security/authz.py` - Enhance authorization checks
- `routeros_mcp/domain/models.py` - Add `Role`, `Permission` models

**Tasks**:
1. Create RBAC models:
   ```python
   class Role(Base):
       name: str  # read_only, ops_rw, admin, approver
       description: str
       permissions: List[Permission]  # Many-to-many

   class Permission(Base):
       resource_type: str  # tool, device, environment
       resource_id: str  # tool name, device ID, environment name
       action: str  # execute, read, write, approve
   ```
2. Implement permission matrix:
   - **read_only**: Can execute all fundamental tools on any device
   - **ops_rw**: Can execute advanced tools on assigned devices
   - **admin**: Can execute professional tools on assigned devices
   - **approver**: Can approve requests (no tool execution)
3. Add per-role, per-tool authorization:
   - Check `user.role` has permission for `tool_name`
   - Check tool tier (fundamental/advanced/professional) matches role
4. Add per-role, per-device authorization:
   - Check `device_id` in `user.device_scopes`
   - If empty, user has access to all devices (admin default)
5. Add per-role, per-environment authorization:
   - Check `device.environment` matches user's allowed environments
   - Example: `ops_rw` can only access lab/staging, not prod
6. Implement authorization middleware:
   - Extract user from session
   - Check permissions before tool execution
   - Return 403 Forbidden if unauthorized
7. Add authorization audit logging:
   - Log all permission checks (allowed and denied)
   - Include user, tool, device, environment in audit context

**Estimated Effort**: 40-60 hours

**Acceptance Criteria**:
- [ ] Five roles are defined with clear permissions
- [ ] Per-tool, per-device, per-environment authorization works
- [ ] Unauthorized attempts return 403 with clear message
- [ ] All authorization checks are audited

#### 1.3 Per-User Device Scopes

**Goal**: Fine-grained device access control per user

**Files to Modify**:
- `routeros_mcp/domain/models.py` - Add `DeviceGroup`, `UserDeviceScope`
- `routeros_mcp/api/admin.py` - Add device scope management endpoints

**Tasks**:
1. Create device grouping:
   ```python
   class DeviceGroup(Base):
       id: UUID
       name: str  # "Production Routers", "Lab Devices"
       description: str
       device_ids: List[UUID]
       owner_user_id: UUID
       team_name: str  # Optional: "Network Team"
   ```
2. Create user device scopes:
   ```python
   class UserDeviceScope(Base):
       user_id: UUID
       device_id: UUID | None  # Explicit device
       device_group_id: UUID | None  # Device group
       granted_by_user_id: UUID  # Admin who granted access
       granted_at: datetime
   ```
3. Implement scope resolution:
   - User has explicit device scopes (individual devices)
   - User has group scopes (all devices in group)
   - Admin role has implicit access to all devices
4. Add scope management API:
   - `POST /api/admin/users/{user_id}/device-scopes` - Grant access
   - `DELETE /api/admin/users/{user_id}/device-scopes/{scope_id}` - Revoke access
   - `GET /api/admin/users/{user_id}/device-scopes` - List user's scopes
5. Add device tagging:
   - `device.owner_user_id` - Device owner
   - `device.team_name` - Team responsible for device
   - `device.tags` - Free-form tags (JSON)
6. Audit scope changes:
   - Log all scope grants and revocations
   - Include granting user, granted user, device/group

**Estimated Effort**: 20-30 hours

**Acceptance Criteria**:
- [ ] Users can be granted access to specific devices or groups
- [ ] Scope resolution works (individual + group + admin)
- [ ] Scope management API is functional
- [ ] All scope changes are audited

---

### 2. Approval Workflow Engine (HIGH PRIORITY)

#### 2.1 Approval Queue System

**Goal**: Formal approval process for high-risk operations

**Files to Create**:
- `routeros_mcp/domain/services/approval.py` - Approval service
- `routeros_mcp/domain/models.py` - Add `ApprovalRequest` model
- `routeros_mcp/api/approval.py` - Approval API endpoints

**Tasks**:
1. Create `ApprovalRequest` model:
   ```python
   class ApprovalRequest(Base):
       id: UUID
       plan_id: UUID  # Associated plan
       requester_user_id: UUID  # Who requested
       assigned_approver_user_id: UUID  # Who can approve
       status: str  # pending, approved, rejected, expired
       risk_level: str  # low, medium, high, critical
       request_comment: str  # Why this change is needed
       approval_comment: str | None  # Approver's notes
       requested_at: datetime
       approved_rejected_at: datetime | None
       expires_at: datetime  # 24 hours from request
   ```
2. Implement approval request creation:
   - When high-risk tool is invoked, create approval request
   - Determine assigned approver based on:
     - Device criticality
     - Environment (prod requires senior approver)
     - Operation type (multi-device requires additional approval)
   - Send approval request notification
3. Implement approval/rejection flow:
   - Approver reviews request via web UI or API
   - Approver adds comment explaining decision
   - On approval: Generate approval token, return to requester
   - On rejection: Notify requester with reason
4. Implement expiration:
   - Approval requests expire after 24 hours
   - Cron job marks expired requests
   - Requester must create new request if expired
5. Add approval queue API:
   - `GET /api/approvals/pending` - List pending approvals (for approver)
   - `GET /api/approvals/my-requests` - List user's requests
   - `POST /api/approvals/{id}/approve` - Approve request
   - `POST /api/approvals/{id}/reject` - Reject request
6. Add approval metrics:
   - Approval request count per user
   - Approval SLA (time to approve)
   - Approval/rejection ratio

**Estimated Effort**: 40-60 hours

**Acceptance Criteria**:
- [ ] High-risk operations create approval requests
- [ ] Approvers can approve/reject via API
- [ ] Approval tokens are generated on approval
- [ ] Expired requests are handled
- [ ] Approval metrics are tracked

#### 2.2 Separate Approver Roles

**Goal**: Separation of duties (requester ≠ approver)

**Files to Modify**:
- `routeros_mcp/security/rbac.py` - Add approver role logic
- `routeros_mcp/domain/services/approval.py` - Enforce no self-approval

**Tasks**:
1. Define approver role permissions:
   - Can view approval requests
   - Can approve/reject requests
   - Cannot execute tools (read-only for context)
2. Implement approver assignment logic:
   - Per-device approver: Specified in device config
   - Per-environment approver: Prod requires specific approvers
   - Fallback to admin role if no specific approver
3. Enforce no self-approval:
   - Check `requester_user_id != approver_user_id`
   - Return error if user tries to approve own request
4. Implement delegation:
   - Approver can delegate to another approver
   - Delegation is audited
5. Implement escalation:
   - If approval not granted in SLA (4 hours), escalate
   - Notify backup approver
   - Send reminder to original approver

**Estimated Effort**: 20-30 hours

**Acceptance Criteria**:
- [ ] Approver role can approve/reject but not execute
- [ ] Self-approval is blocked
- [ ] Delegation and escalation work
- [ ] Approver assignment is flexible (per-device, per-environment)

#### 2.3 Approval Notifications

**Goal**: Notify approvers of pending requests

**Files to Create**:
- `routeros_mcp/infra/notifications/notifier.py` - Notification service
- `routeros_mcp/infra/notifications/email.py` - Email provider
- `routeros_mcp/infra/notifications/slack.py` - Slack provider

**Tasks**:
1. Implement notification service:
   - Abstract interface: `send_notification(user_id, message, channel)`
   - Support multiple channels: in-app, email, Slack, Teams, webhooks
2. Implement email notifications:
   - SMTP configuration in settings
   - HTML email template for approval requests
   - Include: requester, devices, changes, approve/reject links
3. Implement Slack notifications:
   - Slack webhook URL in settings
   - Post to specific channel (#approvals)
   - Include interactive buttons (approve/reject)
4. Implement in-app notifications:
   - Store notifications in database
   - API endpoint: `GET /api/notifications`
   - Mark as read: `POST /api/notifications/{id}/read`
   - Real-time via SSE if user is connected
5. Implement custom webhooks:
   - POST approval request JSON to configured URL
   - Support HMAC signature for security
   - Retry on failure (3 attempts)
6. Add notification preferences per user:
   - User can choose channels (email, Slack, etc.)
   - User can set quiet hours
   - User can set notification frequency (immediate, digest)

**Estimated Effort**: 20-30 hours

**Acceptance Criteria**:
- [ ] Approvers receive email notifications
- [ ] Slack notifications include interactive buttons
- [ ] In-app notifications are visible in web UI
- [ ] Custom webhooks work
- [ ] Users can configure notification preferences

---

### 3. Governance & Compliance (MEDIUM PRIORITY)

#### 3.1 Per-User Audit Trails

**Goal**: Track all operations by user identity

**Current Phase 4 State**: Audit trails exist but user = "system"

**Files to Modify**:
- `routeros_mcp/domain/models.py` - Add `user_id` to audit events
- `routeros_mcp/infra/observability/logging.py` - Include user context
- `routeros_mcp/api/audit.py` - Enhanced audit API

**Tasks**:
1. Enhance `AuditEvent` model:
   ```python
   class AuditEvent(Base):
       # Existing fields
       id: UUID
       timestamp: datetime
       event_type: str
       device_id: UUID | None

       # New Phase 5 fields
       user_id: UUID  # User who performed action
       user_email: str  # For display
       tool_name: str | None  # Tool executed
       approval_request_id: UUID | None  # If approved
       result: str  # success, failure, denied
   ```
2. Include user context in all audit logging:
   - Extract user from session/token
   - Add to logging context
   - All tool executions include `user_id`
3. Log authorization denials:
   - Log denied tool executions (403)
   - Include attempted tool, device, reason
4. Add pre/post state snapshots:
   - Before tool execution: Snapshot device config
   - After tool execution: Snapshot device config
   - Store diff in audit event
5. Enhance audit API:
   - `GET /api/audit/events` - List events with pagination
   - Filter by: user, device, tool, date range, result
   - Search by: device name, user email, tool name
   - Export to: CSV, JSON, PDF

**Estimated Effort**: 16-24 hours

**Acceptance Criteria**:
- [ ] All operations include user ID in audit logs
- [ ] Authorization denials are logged
- [ ] Pre/post snapshots are stored
- [ ] Audit API supports filtering and export

#### 3.2 Compliance Reporting

**Goal**: Generate reports for compliance audits

**Files to Create**:
- `routeros_mcp/domain/services/compliance.py` - Compliance service
- `routeros_mcp/api/compliance.py` - Compliance API
- `routeros_mcp/templates/reports/` - Report templates

**Tasks**:
1. Implement production change report:
   - All changes to production devices in date range
   - Grouped by user, device, tool
   - Include: timestamp, user, device, tool, result
   - Show approval status (who approved)
2. Implement approval SLA report:
   - Average time to approve per approver
   - Expired requests (approval SLA miss)
   - Approval/rejection ratio
3. Implement policy violation report:
   - Unauthorized access attempts (403 errors)
   - Self-approval attempts
   - Changes without approval
4. Implement risk exposure report:
   - Users with admin role
   - Devices with write capability enabled
   - High-risk tools usage frequency
5. Implement trend analysis:
   - Change frequency per device (over time)
   - Tool usage trends
   - Error rate trends
6. Add report generation API:
   - `POST /api/compliance/reports/production-changes` - Generate report
   - `POST /api/compliance/reports/approval-sla` - Generate report
   - `GET /api/compliance/reports/{id}` - Download report
7. Support multiple export formats:
   - PDF (professional format with logo)
   - CSV (for Excel import)
   - JSON (for SIEM integration)

**Estimated Effort**: 30-40 hours

**Acceptance Criteria**:
- [ ] Production change reports are accurate
- [ ] Approval SLA reports highlight missed SLAs
- [ ] Policy violation reports catch unauthorized attempts
- [ ] Reports export to PDF, CSV, JSON

#### 3.3 Policy Enforcement

**Goal**: Enforce organizational compliance policies

**Files to Create**:
- `routeros_mcp/domain/services/policy.py` - Policy engine
- `routeros_mcp/config.py` - Add policy configuration

**Tasks**:
1. Define policy types:
   ```yaml
   policies:
     - name: mandatory-prod-approval
       type: approval-required
       scope: environment=prod
       description: All prod changes require approval

     - name: require-audit-comments
       type: require-comment
       scope: tier=professional
       description: High-risk ops require justification

     - name: max-changes-per-day
       type: rate-limit
       scope: user=*
       limit: 50
       description: Max 50 changes per user per day

     - name: no-business-hours-changes
       type: time-window
       scope: environment=prod
       deny: Mon-Fri 08:00-18:00 EST
       description: No prod changes during business hours
   ```
2. Implement policy evaluation:
   - Before tool execution, evaluate policies
   - Check if any policy blocks the operation
   - Return 403 with policy violation message
3. Implement policy types:
   - **approval-required**: Requires approval for matching scope
   - **require-comment**: Requires comment in request
   - **rate-limit**: Enforces max operations per time window
   - **time-window**: Blocks operations in specific time windows
4. Add policy configuration:
   - YAML file: `config/policies.yaml`
   - Web UI for policy management (Phase 5.1)
5. Add policy violation logging:
   - Log all policy violations
   - Include policy name, user, attempted operation

**Estimated Effort**: 24-32 hours

**Acceptance Criteria**:
- [ ] Policies can be defined in YAML
- [ ] Policy engine evaluates policies before execution
- [ ] Policy violations return clear error messages
- [ ] Policy violations are logged

#### 3.4 Resource Quotas & Rate Limiting

**Goal**: Prevent abuse by limiting operations per user

**Files to Create**:
- `routeros_mcp/infra/rate_limit/limiter.py` - Rate limiter service
- `routeros_mcp/mcp/transport/rate_limit_middleware.py` - Middleware

**Tasks**:
1. Implement per-user rate limiting:
   - Store rate limit state in Redis
   - Key: `rate_limit:{user_id}:{window}` (e.g., `rate_limit:user-123:hourly`)
   - Increment on each API call
   - Check limit before tool execution
2. Define default quotas per role:
   ```python
   RATE_LIMITS = {
       "read_only": {"hourly": 1000, "daily": 10000},
       "ops_rw": {"hourly": 500, "daily": 5000},
       "admin": {"hourly": 200, "daily": 2000},
       "approver": {"hourly": 100, "daily": 1000},
   }
   ```
3. Implement quota types:
   - **API calls per hour**: Total API requests
   - **Tool executions per hour**: Actual tool invocations
   - **Concurrent operations**: Max simultaneous tool executions
   - **Devices per plan**: Max devices in multi-device plan
4. Add rate limit headers:
   - `X-RateLimit-Limit`: Max requests per window
   - `X-RateLimit-Remaining`: Remaining requests
   - `X-RateLimit-Reset`: When limit resets (timestamp)
5. Return 429 Too Many Requests on exceeded:
   - Include `Retry-After` header
   - Clear error message with limit and reset time
6. Add rate limit metrics:
   - Rate limit hits per user
   - Top rate-limited users

**Estimated Effort**: 12-16 hours

**Acceptance Criteria**:
- [ ] Per-user rate limits are enforced
- [ ] Rate limit headers are returned
- [ ] 429 errors are returned on exceeded limits
- [ ] Rate limits are stored in Redis (multi-instance safe)

---

### 4. Multi-Instance Deployment (MEDIUM PRIORITY)

#### 4.1 Horizontal Scaling Infrastructure

**Goal**: Support multiple MCP server instances with shared state

**Current Phase 4 State**: Single instance with APScheduler and in-memory cache

**Files to Modify**:
- `routeros_mcp/infra/db/session.py` - PostgreSQL connection pooling
- `routeros_mcp/infra/observability/resource_cache.py` - Redis cache backend
- `routeros_mcp/infra/jobs/scheduler.py` - Distributed task scheduling
- `routeros_mcp/config.py` - Add Redis configuration

**Tasks**:
1. Add Redis configuration:
   ```python
   class Settings(BaseSettings):
       # Existing fields...

       # Redis (Phase 5)
       redis_url: str = "redis://localhost:6379/0"
       redis_pool_size: int = 10
       redis_timeout_seconds: float = 5.0
   ```
2. Implement Redis-backed resource cache:
   - Replace in-memory cache with Redis
   - Use Redis keys: `resource_cache:{uri}:{version}`
   - Set TTL on cached resources (5 minutes for health, 1 hour for config)
   - Distributed cache invalidation via Redis pub/sub
3. Implement Redis-backed session store:
   - Store user sessions in Redis
   - Key: `session:{session_id}`
   - 8-hour expiration (configurable)
   - All instances read from shared Redis
4. Implement distributed health check scheduling:
   - Use Redis distributed lock for scheduling
   - Only one instance schedules health checks per device
   - Lock key: `health_check_lock:{device_id}`
   - Lock TTL: 2x health check interval
5. Add Redis connection pooling:
   - Connection pool with max connections
   - Health check on checkout
   - Auto-reconnect on failure
6. Document multi-instance deployment:
   - Update docs/01 with multi-instance architecture
   - Add load balancer configuration examples
   - Document Redis setup and tuning

**Estimated Effort**: 40-60 hours

**Acceptance Criteria**:
- [ ] Resource cache uses Redis backend
- [ ] Sessions are stored in Redis
- [ ] Health checks don't duplicate across instances
- [ ] Multi-instance deployment is documented

#### 4.2 High Availability Configuration

**Goal**: Production-grade HA with load balancer

**Files to Create**:
- `deploy/haproxy.cfg` - HAProxy configuration template
- `deploy/nginx-lb.conf` - Nginx load balancer template

**Tasks**:
1. Add health check endpoint:
   - `GET /health` - Returns 200 OK if instance is healthy
   - Check: Database connection, Redis connection
   - Return 503 Service Unavailable if unhealthy
2. Create HAProxy configuration:
   - Backend pool of MCP server instances
   - Health check via `/health` endpoint
   - Round-robin load balancing
   - Sticky sessions via cookie (optional)
3. Create Nginx load balancer configuration:
   - Alternative to HAProxy
   - Upstream block with MCP servers
   - Health checks
   - SSL/TLS termination
4. Add graceful shutdown:
   - On SIGTERM, stop accepting new requests
   - Finish processing current requests (30s timeout)
   - Close database and Redis connections
   - Exit with code 0
5. Add load balancer-aware rate limiting:
   - Rate limit by user ID (not IP)
   - Store rate limit state in Redis
   - All instances enforce same limits
6. Document HA deployment:
   - Load balancer setup
   - SSL/TLS certificate configuration
   - Health check tuning
   - Monitoring and alerting

**Estimated Effort**: 24-32 hours

**Acceptance Criteria**:
- [ ] Health check endpoint is functional
- [ ] HAProxy and Nginx configs are provided
- [ ] Graceful shutdown works
- [ ] HA deployment is documented

---

### 5. Web Admin UI Enhancements (MEDIUM PRIORITY)

#### 5.1 User Management Interface

**Goal**: Admin UI for managing users, roles, and device scopes

**Files to Create**:
- `frontend/src/pages/UserManagement.tsx` - User management page
- `frontend/src/pages/RoleManagement.tsx` - Role management page

**Tasks**:
1. Implement User Management page:
   - List all users with role and status
   - Add user button (creates user from OIDC)
   - Edit user: Change role, device scopes, active status
   - Delete user (with confirmation)
   - View user's recent activity
2. Implement Role Assignment:
   - Dropdown to select role (read_only, ops_rw, admin, approver)
   - Role description tooltip
   - Confirm role change with warning
3. Implement Device Scope Assignment:
   - Multi-select dropdown for devices
   - Device group selector
   - Visual indicator of inherited scopes
   - Search/filter devices
4. Add user activity dashboard:
   - Recent tool executions
   - Approval requests submitted
   - Authorization denials
   - Chart: Activity over time

**Estimated Effort**: 30-40 hours

**Acceptance Criteria**:
- [ ] Admins can view all users
- [ ] Admins can change user roles and device scopes
- [ ] User activity dashboard shows recent operations

#### 5.2 Enhanced Compliance Dashboards

**Goal**: Visual dashboards for compliance metrics

**Files to Create**:
- `frontend/src/pages/ComplianceDashboard.tsx` - Main compliance page
- `frontend/src/components/ApprovalQueueWidget.tsx` - Approval queue widget
- `frontend/src/components/AuditLogWidget.tsx` - Audit log widget

**Tasks**:
1. Implement Fleet Health Dashboard:
   - All devices with health status (green/yellow/red)
   - Click device for detailed health metrics
   - Drill-down to specific device page
   - Chart: Fleet health over time (last 7 days)
2. Implement Approval Queue Dashboard:
   - Pending approvals count
   - Approval SLA violations highlighted
   - Chart: Approval time distribution
   - Chart: Approval/rejection ratio
3. Implement Audit Trail Viewer:
   - Paginated audit log
   - Advanced filters: user, device, tool, date range, result
   - Search by keyword
   - Export to CSV
   - Highlight policy violations
4. Implement Compliance Metrics:
   - Total changes this month
   - Changes requiring approval vs. approved
   - Policy violations count
   - Top users by change volume
   - Chart: Changes over time
5. Add Grafana integration:
   - Embed Grafana dashboards in UI
   - Pre-built dashboard templates
   - Custom dashboards per organization

**Estimated Effort**: 40-60 hours

**Acceptance Criteria**:
- [ ] Fleet health dashboard visualizes device status
- [ ] Approval queue dashboard shows SLA metrics
- [ ] Audit trail viewer supports advanced filtering
- [ ] Compliance metrics are displayed
- [ ] Grafana dashboards can be embedded

---

## Testing Strategy

### Unit Tests
- [ ] OAuth 2.1 Authorization Code flow tests
- [ ] RBAC permission evaluation tests
- [ ] Approval request lifecycle tests
- [ ] Policy enforcement tests
- [ ] Rate limiting tests
- [ ] Redis session store tests

### Integration Tests
- [ ] Multi-user authentication flow
- [ ] Approval workflow end-to-end
- [ ] Policy violation blocking
- [ ] Multi-instance session sharing (Redis)
- [ ] Distributed cache consistency

### E2E Tests
- [ ] User login via OIDC
- [ ] User creates approval request
- [ ] Approver approves request
- [ ] User executes with approval token
- [ ] Audit trail captures full workflow
- [ ] Multi-instance load balancing

### Performance Tests
- [ ] Load test: 100 concurrent users
- [ ] Session store performance (Redis)
- [ ] Rate limiting accuracy under load
- [ ] Multi-instance health check coordination

**Coverage Target**: Maintain 82%+ overall, 95%+ for core modules

---

## Documentation Updates

### Docs to Update
- [ ] **docs/01** - Multi-instance architecture, load balancer setup
- [ ] **docs/02** - RBAC model, OAuth 2.1 flow, approver roles
- [ ] **docs/05** - User, Role, Permission, ApprovalRequest models
- [ ] **docs/08** - Per-user audit trails, compliance reporting

### New Docs to Create
- [ ] **docs/PHASE5_IMPLEMENTATION_PLAN.md** (this document)
- [ ] **docs/27-rbac-and-authorization-model.md** - RBAC deep dive
- [ ] **docs/28-approval-workflow-design.md** - Approval engine architecture
- [ ] **docs/29-compliance-and-governance.md** - Compliance features
- [ ] **docs/30-multi-instance-deployment.md** - HA deployment guide

---

## Sprint Plan (Recommended)

### Sprint 1-2: OAuth & RBAC (80-120 hours)
**Goal**: Per-user authentication with role-based access control

**Week 1-2**:
- [ ] User model and database migrations
- [ ] OAuth 2.1 Authorization Code flow
- [ ] OIDC callback and token refresh
- [ ] Session management with Redis

**Week 3-4**:
- [ ] RBAC role and permission models
- [ ] Per-tool, per-device authorization
- [ ] Authorization middleware
- [ ] Unit and integration tests

**Deliverable**: Multi-user authentication with RBAC

---

### Sprint 3-4: Approval Workflows (60-90 hours)
**Goal**: Formal approval process with separate approver roles

**Week 5-6**:
- [ ] ApprovalRequest model
- [ ] Approval request creation on high-risk ops
- [ ] Approval/rejection API
- [ ] Approval expiration logic

**Week 7-8**:
- [ ] Separate approver role
- [ ] No self-approval enforcement
- [ ] Notification service (email, Slack)
- [ ] Approval queue API

**Deliverable**: Functional approval workflow engine

---

### Sprint 5-6: Governance (54-80 hours)
**Goal**: Compliance features with audit trails and reporting

**Week 9-10**:
- [ ] Per-user audit trails
- [ ] Authorization denial logging
- [ ] Pre/post state snapshots
- [ ] Enhanced audit API

**Week 11-12**:
- [ ] Compliance reporting service
- [ ] Production change reports
- [ ] Approval SLA reports
- [ ] Policy enforcement engine
- [ ] Resource quotas and rate limiting

**Deliverable**: Compliance and governance features

---

### Sprint 7-8: Multi-Instance & HA (64-92 hours)
**Goal**: Horizontal scaling with high availability

**Week 13-14**:
- [ ] Redis-backed resource cache
- [ ] Redis-backed session store
- [ ] Distributed health check scheduling
- [ ] Redis connection pooling

**Week 15-16**:
- [ ] Health check endpoint
- [ ] HAProxy and Nginx configs
- [ ] Graceful shutdown
- [ ] HA deployment documentation

**Deliverable**: Multi-instance deployment support

---

### Sprint 9-10: Web UI Enhancements (70-100 hours)
**Goal**: Admin UI for users, roles, and compliance

**Week 17-18**:
- [ ] User management page
- [ ] Role assignment UI
- [ ] Device scope management UI
- [ ] User activity dashboard

**Week 19-20**:
- [ ] Fleet health dashboard
- [ ] Approval queue dashboard
- [ ] Enhanced audit trail viewer
- [ ] Compliance metrics
- [ ] Grafana integration

**Deliverable**: Complete web admin UI

---

## Success Criteria

Phase 5 is complete when:

1. **Multi-User Authentication**: ✅
   - [ ] Users log in via OIDC with Authorization Code flow
   - [ ] Per-user access tokens and refresh tokens
   - [ ] Sessions stored in Redis for multi-instance
   - [ ] Multiple OIDC providers supported

2. **RBAC**: ✅
   - [ ] Five roles with clear permissions
   - [ ] Per-tool, per-device, per-environment authorization
   - [ ] Unauthorized attempts return 403 with clear message
   - [ ] All authorization checks audited

3. **Approval Workflows**: ✅
   - [ ] High-risk ops create approval requests
   - [ ] Approver role can approve/reject
   - [ ] No self-approval enforcement
   - [ ] Notifications via email, Slack, in-app

4. **Governance**: ✅
   - [ ] All operations logged with user ID
   - [ ] Compliance reports generate correctly
   - [ ] Policy enforcement blocks violations
   - [ ] Resource quotas and rate limiting work

5. **Multi-Instance**: ✅
   - [ ] Multiple instances share state via Redis
   - [ ] Load balancer distributes requests
   - [ ] Health checks coordinate across instances
   - [ ] Graceful shutdown works

6. **Web UI**: ✅
   - [ ] User management interface functional
   - [ ] Compliance dashboards visualize metrics
   - [ ] Approval queue interface works

7. **Quality**: ✅
   - [ ] 82%+ test coverage maintained
   - [ ] All E2E tests pass
   - [ ] Performance targets met (100 concurrent users)
   - [ ] Documentation complete

---

## Dependencies

**Phase 5 depends on**:
- Phase 4 HTTP/SSE transport complete
- OAuth/OIDC provider configured (Azure AD, Okta, Auth0)
- Redis 6.0+ for session/cache storage
- PostgreSQL 14+ for user/role storage

---

## Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| OAuth integration complexity | High | Medium | Use well-tested libraries (authlib), comprehensive testing |
| RBAC permission explosion | Medium | Medium | Keep roles simple (5 core roles), custom roles in Phase 5.1 |
| Approval workflow adoption | High | Low | Clear documentation, training, gradual rollout |
| Multi-instance coordination bugs | High | Medium | Extensive integration tests, Redis lock testing |
| Performance degradation | Medium | Low | Load testing, caching, query optimization |

---

## References

- **README.md**: Phase 5 section (lines 349-438)
- **docs/01**: Architecture & deployment
- **docs/02**: Security model
- **docs/05**: Domain model
- **docs/08**: Observability & audit trails
- **docs/21-24**: OAuth setup guides

---

**Document Version**: 1.0
**Last Updated**: 2026-01-05
**Status**: Ready for Planning (Phase 4 required first)
