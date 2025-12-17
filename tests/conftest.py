"""Shared pytest fixtures.

These fixtures live at `tests/` scope so they are available to both unit and e2e
tests.

Key goals:
- Prevent global singletons (DB session manager, resource cache) from leaking
  state across tests.
- Provide a lightweight DB initializer for tests that need a ready-to-use
  session manager.
"""

from __future__ import annotations

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.infra.db.models import Base
from routeros_mcp.infra.db.session import (
    DatabaseSessionManager,
    initialize_session_manager as _initialize_session_manager,
    reset_session_manager,
)
from routeros_mcp.infra.observability.resource_cache import reset_cache


@pytest.fixture(autouse=True)
def _reset_global_singletons() -> None:
    """Ensure global singletons do not leak between tests."""
    reset_cache()
    reset_session_manager()
    yield
    reset_cache()
    reset_session_manager()


@pytest.fixture
async def initialize_session_manager() -> DatabaseSessionManager:
    """Initialize the global DB session manager for tests.

    Some e2e tests depend on this fixture to ensure `get_session_factory()` can
    be used immediately.

    Uses an in-memory SQLite database and creates all tables.
    """
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    manager = await _initialize_session_manager(settings)

    async with manager.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield manager

    await manager.close()
