"""Database infrastructure module.

This module provides database models, session management, and repository patterns
for persisting RouterOS MCP service data.

Key components:
- models: SQLAlchemy ORM models
- session: Database session management with connection pooling
"""

from routeros_mcp.infra.db.models import (
    AuditEvent,
    Base,
    Credential,
    Device,
    HealthCheck,
    Job,
    Plan,
    Snapshot,
)
from routeros_mcp.infra.db.session import (
    DatabaseSessionManager,
    get_session,
    get_session_manager,
    reset_session_manager,
)

__all__ = [
    # Models
    "Base",
    "Device",
    "Credential",
    "HealthCheck",
    "Snapshot",
    "Plan",
    "Job",
    "AuditEvent",
    # Session management
    "DatabaseSessionManager",
    "get_session_manager",
    "get_session",
    "reset_session_manager",
]
