"""Additional coverage for domain services and utilities.

These tests focus on lightly covered modules to exercise validation paths
and basic success flows without relying on external RouterOS connectivity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import DeviceCreate
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.diagnostics import MAX_PING_COUNT, DiagnosticsService
from routeros_mcp.domain.utils import parse_routeros_uptime
from routeros_mcp.infra.db.models import Base, Device
from routeros_mcp.mcp.errors import AuthenticationError, EnvironmentMismatchError, ValidationError

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
                management_address="10.0.0.1:443",
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
            management_address="192.168.1.1:443",
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

    # Force rest client acquisition to fail
    monkeypatch.setattr(service, "get_rest_client", AsyncMock(side_effect=RuntimeError("boom")))

    # Track status updates
    update_mock = AsyncMock()
    monkeypatch.setattr(service, "update_device", update_mock)

    result = await service.check_connectivity("dev-lab-99")

    assert result is False
    update_mock.assert_awaited_once()
    args, kwargs = update_mock.await_args
    assert args[0] == "dev-lab-99"
    updated = kwargs.get("updates") or (args[1] if len(args) > 1 else None)
    assert updated is not None
    assert updated.status == "unreachable"


# ---------------------------------------------------------------------------
# DiagnosticsService coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diagnostics_ping_success(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """Ping parses RouterOS responses into aggregates and closes the client."""

    # Build service with mocked device_service
    service = DiagnosticsService(session=None, settings=settings)
    service.device_service = Mock()
    service.device_service.get_device = AsyncMock()

    class _FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def post(self, _path: str, _params: dict[str, str]) -> list[dict[str, str]]:
            return [
                {"status": "echo reply", "time": "10ms"},
                {"status": "echo reply", "time": "20ms"},
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = _FakeClient()
    service.device_service.get_rest_client = AsyncMock(return_value=fake_client)

    result = await service.ping("dev-lab-01", "8.8.8.8", count=2)

    assert result["packets_sent"] == 2
    assert result["packets_received"] == 2
    assert result["min_rtt_ms"] == 10.0
    assert result["max_rtt_ms"] == 20.0
    assert fake_client.closed is True


@pytest.mark.asyncio
async def test_diagnostics_ping_validates_count(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """Ping enforces an upper bound on count to protect devices."""

    service = DiagnosticsService(session=None, settings=settings)
    service.device_service = Mock()
    service.device_service.get_device = AsyncMock()

    with pytest.raises(ValidationError):
        await service.ping("dev-lab-01", "8.8.8.8", count=MAX_PING_COUNT + 1)


@pytest.mark.asyncio
async def test_diagnostics_traceroute_parses_hops(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    """Traceroute normalizes hop results and closes the client."""

    service = DiagnosticsService(session=None, settings=settings)
    service.device_service = Mock()
    service.device_service.get_device = AsyncMock()

    class _FakeClient:
        def __init__(self) -> None:
            self.closed = False

        async def post(self, _path: str, _params: dict[str, str]) -> list[dict[str, str]]:
            return [
                {"hop": 1, "address": "192.0.2.1", "time": "5ms"},
                {"hop": 2, "address": "198.51.100.1", "time": "8ms"},
            ]

        async def close(self) -> None:
            self.closed = True

    fake_client = _FakeClient()
    service.device_service.get_rest_client = AsyncMock(return_value=fake_client)

    result = await service.traceroute("dev-lab-01", "9.9.9.9", count=2)

    assert result["hops"] == [
        {"hop": 1, "address": "192.0.2.1", "rtt_ms": 5.0},
        {"hop": 2, "address": "198.51.100.1", "rtt_ms": 8.0},
    ]
    assert fake_client.closed is True
