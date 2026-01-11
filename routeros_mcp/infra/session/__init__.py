"""Session store infrastructure for multi-instance deployments.

Provides pluggable session storage backends for horizontal scaling:
- Redis backend for distributed session state
- Abstract interface for custom backends

See issue grammy-jiang/RouterOS-MCP#3 (Phase 5).
"""

from routeros_mcp.infra.session.store import (
    RedisSessionStore,
    SessionData,
    SessionStore,
    SessionStoreError,
)

__all__ = [
    "SessionStore",
    "RedisSessionStore",
    "SessionStoreError",
    "SessionData",
]
