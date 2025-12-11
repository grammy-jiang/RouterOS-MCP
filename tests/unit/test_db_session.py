"""Tests for database session manager utilities."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.infra.db.session import (
    DatabaseSessionManager,
    get_session_factory,
    get_session_manager,
    initialize_session_manager,
    reset_session_manager,
)


@pytest.fixture(autouse=True)
def _reset_manager() -> None:
    reset_session_manager()
    yield
    reset_session_manager()


def make_sqlite_settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite:///:memory:")


@pytest.mark.asyncio
async def test_init_creates_engine_and_session_factory() -> None:
    settings = make_sqlite_settings()
    manager = DatabaseSessionManager(settings)
    await manager.init()

    # Engine and session factory should be set
    assert manager.engine is not None

    async with manager.session() as session:
        assert isinstance(session, AsyncSession)


@pytest.mark.asyncio
async def test_session_commits_and_rolls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_sqlite_settings()
    manager = DatabaseSessionManager(settings)
    await manager.init()

    # Track commit calls
    commit_called = False

    async def fake_commit() -> None:
        nonlocal commit_called
        commit_called = True
        await orig_commit()

    async with manager.session() as session:
        orig_commit = session.commit
        monkeypatch.setattr(session, "commit", fake_commit)

    assert commit_called

    # Track rollback on error
    rollback_called = False

    async def fake_rollback() -> None:
        nonlocal rollback_called
        rollback_called = True
        await orig_rollback()

    class CustomError(Exception):
        pass

    with pytest.raises(CustomError):
        async with manager.session() as session:
            orig_rollback = session.rollback
            monkeypatch.setattr(session, "rollback", fake_rollback)
            raise CustomError()

    assert rollback_called


@pytest.mark.asyncio
async def test_global_session_manager_singleton() -> None:
    settings = make_sqlite_settings()
    manager = await initialize_session_manager(settings)
    same_manager = get_session_manager()
    assert manager is same_manager

    factory = get_session_factory(settings)
    assert factory is manager


@pytest.mark.asyncio
async def test_session_before_init_raises() -> None:
    settings = make_sqlite_settings()
    manager = DatabaseSessionManager(settings)

    with pytest.raises(RuntimeError):
        async with manager.session():
            pass

    with pytest.raises(RuntimeError):
        _ = manager.engine
