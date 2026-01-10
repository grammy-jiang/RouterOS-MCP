#!/usr/bin/env bash
set -euo pipefail

# Create missing Phase 5 labels using GitHub CLI (gh).
# Usage:
#   ./scripts/labels/create_phase5_labels.sh [owner/repo]
# Default repo: grammy-jiang/RouterOS-MCP

REPO="${1:-grammy-jiang/RouterOS-MCP}"

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: gh CLI is not installed. Install from https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Error: gh CLI is not authenticated. Run: gh auth login" >&2
  exit 1
fi

owner_repo="$REPO"

ensure_label_update() {
  local name="$1" color="$2" desc="$3"
  local exists
  exists=$(gh label list --repo "$owner_repo" --limit 1000 --json name --jq "map(.name) | any(. == \"$name\")")
  if [[ "$exists" == "true" ]]; then
    echo "Updating label '$name' (color/description) ..."
    gh label edit "$name" --repo "$owner_repo" --color "$color" --description "$desc"
  else
    echo "Creating label '$name'..."
    gh label create "$name" --repo "$owner_repo" --color "$color" --description "$desc"
  fi
}

# Normalize existing Phase 5-related labels
ensure_label_update "auth"         "aaaaaa" "Authentication and OIDC-related work"
ensure_label_update "high-priority" "aaaaaa" "Urgent / prioritized work"
ensure_label_update "backend"      "c2bb57" "Backend/server-side changes"
ensure_label_update "audit"        "ededed" "Audit trails and logging"
ensure_label_update "frontend"     "ededed" "Frontend/UI changes"

# Phase 5 label set (create or update)
ensure_label_update "phase5"       "5319e7" "Phase 5 – Multi-User RBAC & Governance"
ensure_label_update "infra"        "0e8a16" "Infrastructure and platform changes"
ensure_label_update "redis"        "d73a4a" "Redis-related work (sessions, cache, locks)"
ensure_label_update "rbac"         "e99695" "Role-based access control"
ensure_label_update "db"           "0e8a16" "Database schema/migration work"
ensure_label_update "api"          "1d76db" "Public/internal API endpoints"
ensure_label_update "approval"     "c2e0c6" "Approval workflow engine and logic"
ensure_label_update "notifications" "fbca04" "Email/Slack/in-app notifications"
ensure_label_update "compliance"   "94d3a2" "Compliance reporting and dashboards"
ensure_label_update "policy"       "cfd3d7" "Policy engine and enforcement"
ensure_label_update "rate-limit"   "f9d0c4" "Rate limiting and quotas"
ensure_label_update "ha"           "b60205" "High availability and load balancing"
ensure_label_update "ui"           "a2eeef" "User interface components"
ensure_label_update "admin"        "555555" "Admin operations and tooling"

echo "Done. Review labels at: https://github.com/${owner_repo}/labels"
