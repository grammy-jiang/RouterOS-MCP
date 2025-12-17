"""Additional coverage for domain services and utilities.

These tests focus on lightly covered modules to exercise validation paths
and basic success flows without relying on external RouterOS connectivity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import DeviceCreate
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.utils import parse_routeros_uptime
from routeros_mcp.infra.db.models import Base, Device
from routeros_mcp.mcp.errors import AuthenticationError, EnvironmentMismatchError

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session() -> AsyncSession:
    """Create an in-memory database session for device-oriented tests."""

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def settings() -> Settings:
    """Provide default settings (lab env gives an encryption key by default)."""

    return Settings()


# ---------------------------------------------------------------------------
# Utility coverage
# ---------------------------------------------------------------------------


def test_parse_routeros_uptime() -> None:
    """Ensure uptime strings are parsed into seconds across mixed units."""

    assert (
        parse_routeros_uptime("1w2d3h4m5s")
        == (7 * 24 * 3600) + (2 * 24 * 3600) + (3 * 3600) + (4 * 60) + 5
    )
    assert parse_routeros_uptime("5h30m") == (5 * 3600) + (30 * 60)
    assert parse_routeros_uptime("15m10s") == (15 * 60) + 10
    assert parse_routeros_uptime("") == 0


# ---------------------------------------------------------------------------
# DeviceService coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_device_environment_mismatch(
    db_session: AsyncSession, settings: Settings
) -> None:
    """Registration should fail when device environment differs from service environment."""

    service = DeviceService(db_session, settings)
    with pytest.raises(EnvironmentMismatchError):
        await service.register_device(
            DeviceCreate(
                id="dev-prod-01",
                name="prod-router",
                management_ip="10.0.0.1",
                management_port=443,
                environment="prod",
            )
        )


@pytest.mark.asyncio
async def test_get_rest_client_missing_credentials(
    db_session: AsyncSession, settings: Settings
) -> None:
    """get_rest_client should raise AuthenticationError when no active credentials exist."""

    # Seed a device without credentials
    db_session.add(
        Device(
            id="dev-lab-01",
            name="router-lab-01",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="pending",
            tags={},
            allow_advanced_writes=True,
            allow_professional_workflows=True,
        )
    )
    await db_session.commit()

    service = DeviceService(db_session, settings)

    with pytest.raises(AuthenticationError, match="No active REST credentials"):
        await service.get_rest_client("dev-lab-01")


@pytest.mark.asyncio
async def test_check_connectivity_failure_marks_unreachable(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """check_connectivity should return False and mark unreachable on errors."""

    service = DeviceService(session=None, settings=settings)  # session unused in this path

    # Provide a stub session to satisfy internal credential existence check
    class _StubResult:
        @staticmethod
        def scalar_one_or_none() -> None:
            return None

    stub_session = AsyncMock()
    stub_session.execute = AsyncMock(return_value=_StubResult())
    service.session = stub_session

    # Force rest client acquisition to fail
    monkeypatch.setattr(service, "get_rest_client", AsyncMock(side_effect=RuntimeError("boom")))

    # Track status updates
    update_mock = AsyncMock()
    monkeypatch.setattr(service, "update_device", update_mock)

    reachable, meta = await service.check_connectivity("dev-lab-99")

    assert reachable is False
    assert meta["failure_reason"] == "unknown"
    update_mock.assert_awaited_once()
    args, kwargs = update_mock.await_args
    assert args[0] == "dev-lab-99"
    updated = kwargs.get("updates") or (args[1] if len(args) > 1 else None)
    assert updated is not None
    assert updated.status == "unreachable"
