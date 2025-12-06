# Operations, Deployment, Self-Update & Rollback Runbook

## Purpose

Document how the service is operated over time: deployment workflows, configuration management, schema migrations, self-update and rollback strategies, and emergency procedures. This document is aimed at operators and SREs.

---

## Configuration model (env vars, config files, secrets, per-environment overrides)

- **Configuration sources**:
  - Environment variables (primary).  
  - Optional configuration files (YAML/TOML/JSON) for structured settings.  
  - Secret sources (environment, secret manager) for sensitive values.

- **Key configuration areas**:
  - Database connection (URLs, pools).  
  - OIDC provider settings (issuer, client ID, client secret, redirect URIs).  
  - Cloudflare Tunnel origin port and hostname.  
  - RouterOS integration defaults (timeouts, retries, per-device limits).  
  - Logging and metrics (exporter endpoints, log level).  
  - Environment tag for the MCP deployment itself (e.g., `MCP_ENV=lab|staging|prod`).

- **Per-environment overrides**:
  - Use separate configuration profiles for lab, staging, prod.  
  - Avoid sharing secrets or DBs between environments.  
  - Capability flags default more permissive in lab, restrictive in prod.

---

## Deployment modes (systemd unit, container orchestrator, or both)

- **Systemd-based deployment**:
  - MCP is installed as a binary or application on a Linux host.  
  - A `systemd` unit manages the process:
    - Ensures automatic restart on failure.  
    - Integrates with journald or log forwarders.  
  - Cloudflare Tunnel may run as a separate service on the same host.

- **Container-based deployment**:
  - MCP packaged as a container image.  
  - Deployed via:
    - Docker Compose, or  
    - Kubernetes (Deployment/StatefulSet) with Service and Ingress/Tunnel integration.
  - Config provided via environment variables/config maps, secrets via secret resources.

In both modes:

- Health and readiness endpoints are used for orchestration (k8s probes or systemd watchdogs).  
- Horizontal scaling is achieved by running multiple instances behind a load balancer.

---

## Deployment pipelines (build, test, deploy, rollback)

- **Build stage**:
  - Linting, unit tests, and basic integration tests run in CI.  
  - Container image built and tagged (e.g., with git SHA or semantic version).

- **Pre-deploy tests**:
  - Optional: deploy to a lab environment and run end-to-end tests:
    - Integration with one or more lab RouterOS devices.  
    - Sanity checks of key MCP tools.

- **Deploy stage**:
  - Staged rollout:
    - Lab → staging → production.  
    - For production, introduce changes to a subset of instances first if possible.

- **Rollback**:
  - CI/CD must support rapid rollback to a previous known-good version.  
  - Rollback includes:
    - Application binaries/containers.  
    - Configuration (versioned).  
    - Database migrations (see next section).

---

## Database/schema and data migrations strategy

- **Schema migrations**:
  - Managed via a migration tool (e.g., Alembic, Flyway, Liquibase).  
  - Migrations are versioned and applied in order as part of deployment.

- **Backward compatibility**:
  - Whenever possible, migrations are:
    - **Additive** (adding columns/tables) before removing old fields.  
    - Carefully designed so that old application versions can still function during rollout.

- **Rollback of migrations**:
  - For high-risk schema changes, define reversible migrations or a data backup strategy.  
  - For non-trivial migrations, deploy in two phases (add new schema, deploy code; only later remove old schema).

---

## Device lifecycle operations (register, update metadata, rotate credentials, decommission)

- **Register**:
  - Phase 0: define the Device and Credential model and enable secure storage (no user-facing input yet).  
  - Phase 1: operator uses a secured **admin HTTP API** to:
    - Provide device management address, environment, tags.  
    - Provide RouterOS credentials (or reference to a secret).  
    - Confirm connectivity and basic health (using Phase 0–1 tools).  
  - Phase 2: add convenience tooling on top of the admin API:
    - A CLI wrapper for registration flows.  
    - A simple browser-based admin console for device onboarding and credential rotation.  
  - Phase 3: optionally add automated onboarding:
    - A RouterOS-side bootstrap script or similar mechanism that creates MCP service accounts and reports credentials to the MCP registration API in a controlled way.

- **Update metadata**:
  - Change name, tags, environment, capability flags as needed.  
  - Such changes may require explicit approval or admin-only rights.

- **Rotate credentials**:
  - Operator triggers rotation for a device:  
    - MCP creates new secret on RouterOS (via appropriate method).  
    - Updates stored credentials.  
    - Validates that operations work with new credentials.  
    - Disables old credential.

- **Decommission**:
  - MCP marks device as inactive.  
  - Optionally triggers cleanup on RouterOS (e.g., removing service accounts), if policy allows.  
  - Retains audit events and selected snapshots for historical reference.

---

## Self-update and versioning strategy for MCP tools and service

- **Service versioning**:
  - Semantic versioning (e.g., `1.2.3`).  
  - Clearly indicate breaking changes in major versions.

- **Tool versioning**:
  - Tools may embed version identifiers (e.g., `system.get_overview.v1`).  
  - New incompatible behavior introduces new tool versions; old ones are deprecated and eventually removed.

- **Self-update**:
  - Where supported, the service may:
    - Check for new versions (e.g., via a release endpoint).  
    - Notify operators via logs or UI; it should not silently self-upgrade in production.  
  - Actual upgrade is preferred via external CI/CD, not fully self-managed.

- **Rollout strategy**:
  - New versions:
    - First deployed and tested in lab.  
    - Then in staging.  
    - Lastly in production, possibly with canary instances.

---

## Rollback procedures (service binaries, configuration, database, and RouterOS-facing behavior)

- **Service & config rollback**:
  - Maintain previous app versions and configuration snapshots.  
  - If a new version causes issues:
    - Roll back container image or binary.  
    - Restore previous configuration (from version control or config store).

- **Database rollback**:
  - For additive migrations, rollback often not needed if old version can work with new schema.  
  - For destructive changes:
    - Take DB backups before migration.  
    - Roll back to a backup only in severe cases, accepting some downtime if necessary.

- **RouterOS-facing behavior**:
  - Rollbacks must ensure:
    - No half-applied plans are left in limbo.  
    - High-risk tools can be disabled quickly (e.g., via config flag) if misbehavior is discovered.

---

## Backup/restore procedures and disaster recovery

- **Backups**:
  - Database backups on a regular schedule (e.g., daily full, incremental as supported).  
  - Snapshot of configuration (app config, secrets references, not secrets themselves).  
  - Optional snapshots of critical RouterOS configs (if policy allows).

- **Restore**:
  - Document steps to:
    - Restore DB to a new instance.  
    - Redeploy MCP pointing at the restored DB.  
    - Re-establish connections to RouterOS devices and IdP.

- **Disaster recovery**:
  - Define RPO (Recovery Point Objective) and RTO (Recovery Time Objective) for each environment.  
  - Ensure backup and restore processes are periodically tested.

---

## Runbooks for common incidents (RouterOS API down, auth failures, misbehaving tools)

Example incident types and high-level runbook bullets:

- **RouterOS REST/SSH unavailable**:
  - Check network connectivity between MCP and device.  
  - Verify RouterOS service availability.  
  - Review MCP logs for error codes and diagnostics for the device.  
  - If many devices are affected, investigate upstream network or firewall changes.

- **Auth failures (IdP or token issues)**:
  - Check IdP health dashboards.  
  - Validate configuration (issuer, client ID, secrets).  
  - Consider activating break-glass access for essential operations (e.g., local accounts).

- **Misbehaving tools (unexpected changes or error spikes)**:
  - Identify tool(s) and user(s) from logs and audit events.  
  - Temporarily disable affected tools or reduce capability flags.  
  - If high-risk operations are involved, pause all plan/apply workflows until root cause is found.

- **Performance degradation**:
  - Inspect metrics: CPU/memory on MCP, DB load, RouterOS latency.  
  - Reduce health check and metrics collection frequency if necessary.  
  - Scale out MCP instances or adjust DB resources.

Each runbook should be expanded in the ops documentation with step-by-step commands and dashboards specific to the deployment.
