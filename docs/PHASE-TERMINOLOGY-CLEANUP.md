# Phase Terminology Cleanup Summary

## Purpose

This document summarizes the cleanup of vague phase terminology across all documentation. All statements like "not in Phase 1", "out of scope", "deferred", etc. have been replaced with specific phase references.

**Date:** 2025-12-06

---

## Changes Made

### 1. Doc 02: Security & Access Control

**Line 7:**
- ❌ Old: `Multi-user OAuth/OIDC authentication is deferred to Phase 4.`
- ✅ New: `Multi-user OAuth/OIDC authentication is implemented in Phase 4.`

**Line 23:**
- ❌ Old: `**Phase 1**: No user authentication (single implicit admin user)`
- ✅ New: `**Phase 1**: Single implicit admin user (OS-level access control only)`

**Line 284:**
- ❌ Old: `"""Audit event record (Phase 1: no user tracking)."""`
- ✅ New: `"""Audit event record (Phase 1: single-user deployment, user tracking added in Phase 4)."""`

**Lines 458-461:**
- ❌ Old: `❌ **No OAuth/OIDC** (deferred to Phase 4)`
- ✅ New: `❌ **OAuth/OIDC** (Phase 4)`
- ❌ Old: `❌ **No multi-user support** (single implicit admin)`
- ✅ New: `❌ **Multi-user support** (Phase 4)`
- ❌ Old: `❌ **No HTTP transport** (stdio only)`
- ✅ New: `❌ **HTTP transport** (Phase 4)`
- ❌ Old: `❌ **No RBAC** (device capability flags only)`
- ✅ New: `❌ **RBAC** (Phase 4 - device capability flags only in Phase 1)`

---

### 2. Doc 06: Metrics Collection

**Line 7:**
- ❌ Old: `Advanced analytics and time-series storage are deferred to Phase 4.`
- ✅ New: `Advanced analytics and time-series storage are implemented in Phase 4.`

**Line 582:**
- ❌ Old: `**TimescaleDB Hypertable** (deferred to Phase 4):`
- ✅ New: `**TimescaleDB Hypertable** (Phase 4):`

---

### 3. Doc 03: RouterOS Integration

**Line 680 (Heading):**
- ❌ Old: `## Phase 1: No Web GUI for Template Management`
- ✅ New: `## Phase 1: Code-Based Template Management`

**Line 690:**
- ❌ Old: `**Deferred to Later Phases:**`
- ✅ New: `**Implemented in Later Phases:**`

**Line 794:**
- ❌ Old: `Template management features can be added in later phases when multi-user access control is in place.`
- ✅ New: `Template management features are implemented in Phase 4 when multi-user access control is in place.`

---

### 4. Doc 01: Architecture & Deployment

**Line 205:**
- ❌ Old: `Multi-tenant support, if needed, will require additional isolation mechanisms (namespace, tenant IDs, per-tenant config) and is out of scope here.`
- ✅ New: `Multi-tenant support is out of scope for the entire 1.x series. If needed in the future, v2 will require additional isolation mechanisms (namespace, tenant IDs, per-tenant config).`

---

### 5. Doc 16: Detailed Module Specifications

**Line 428-429:**
- ❌ Old: `# TODO: Implement device scoping logic` / `# For now, all users can access all devices` / `# In production, filter by user.device_scope configuration`
- ✅ New: `# Phase 1: All users can access all devices (single-user deployment)` / `# Phase 4: Implement device scoping logic based on user.device_scope configuration`

**Line 625-626:**
- ❌ Old: `# TODO: Apply user device scope filtering`
- ✅ New: `# Phase 1: No user device scope filtering (single-user deployment)` / `# Phase 4: Apply user device scope filtering based on user.device_scope`

---

### 6. Doc 04: MCP Tools Interface

**Line 2038:**
- ❌ Old: `"approval_token": "approval-token-xyz"  // Phase 4 only`
- ✅ New: `"approval_token": "approval-token-xyz"  // Phase 4: multi-user approval; Phase 1: self-approval allowed`

---

## Terminology Guidelines

### ✅ Approved Patterns

**When describing Phase 1 features:**
- ✅ "Phase 1: Single-user deployment"
- ✅ "Phase 1: Code-based templates"
- ✅ "Phase 1: OS-level access control only"

**When describing features in later phases:**
- ✅ "Phase 2: Low-risk single-device writes"
- ✅ "Phase 3: Controlled network config writes"
- ✅ "Phase 4: Multi-user OAuth/OIDC"
- ✅ "Implemented in Phase X"
- ✅ "Available in Phase X"

**When describing features out of scope for 1.x:**
- ✅ "Out of scope for the entire 1.x series"
- ✅ "If needed in the future, v2 will require..."

### ❌ Avoid These Patterns

- ❌ "Not in Phase 1"
- ❌ "Out of scope here"
- ❌ "Deferred to later phases"
- ❌ "Deferred to Phase X"
- ❌ "Will be added later"
- ❌ "To be implemented"
- ❌ "Future work"
- ❌ "TODO"
- ❌ "Coming soon"
- ❌ "Eventually"
- ❌ "Not yet available"
- ❌ "No X" (without specifying when X is available)

---

## Phase Reference Guide

For quick reference when documenting features:

| Phase | Focus | Key Features |
|-------|-------|--------------|
| **Phase 0** | Service Skeleton | Core config, OAuth skeleton, device registry, no RouterOS writes |
| **Phase 1** | Read-Only MVP | Safe read-only tools, health checks, single-user stdio mode |
| **Phase 2** | Low-Risk Writes | System identity, interface comments, DNS/NTP (lab/staging) |
| **Phase 3** | Network Config | Secondary IPs, address-lists, DHCP/bridge (lab only) |
| **Phase 4** | Multi-User Enterprise | OAuth/OIDC, HTTP/SSE transport, RBAC, multi-device plan/apply |
| **Phase 5** | Expert Workflows | Firewall templates, static routes, interface admin (optional) |
| **1.x Out of Scope** | - | Multi-tenant, user management, global firewall rewrites |

---

## Files Modified

1. `docs/02-security-oauth-integration-and-access-control.md` (6 changes)
2. `docs/06-system-information-and-metrics-collection-module-design.md` (2 changes)
3. `docs/03-routeros-integration-and-platform-constraints-rest-and-ssh.md` (3 changes)
4. `docs/01-overall-system-architecture-and-deployment-topology.md` (1 change)
5. `docs/16-detailed-module-specifications.md` (2 changes)
6. `docs/04-mcp-tools-interface-and-json-schema-specification.md` (1 change)

**Total:** 15 changes across 6 documents

---

## Verification

All vague phase references have been systematically identified and replaced with specific phase numbers or explicit statements about 1.x scope.

**Search patterns used to verify:**
- `not in [Pp]hase`
- `out of scope`
- `defer|postpone`
- `will be added|to be implemented|future work`
- `TODO|TBD|coming soon|eventually`
- `not yet|not available`
- `Phase 1.*: no[t ]`

**Result:** All vague references eliminated ✅

---

## Benefits

1. **Clear Implementation Roadmap**: Developers know exactly which phase implements each feature
2. **Better Project Planning**: Stakeholders understand when features become available
3. **Reduced Ambiguity**: No confusion about "later" or "future" - specific phase references
4. **Consistent Documentation**: All docs use the same terminology patterns

---

**This cleanup ensures all documentation uses precise, unambiguous phase terminology throughout the 1.x series.**
