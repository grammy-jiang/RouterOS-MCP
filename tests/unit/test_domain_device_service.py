from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import CredentialCreate, DeviceCreate, DeviceUpdate
from routeros_mcp.domain.services import device as device_module
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.models import Base
from routeros_mcp.infra.db.models import Credential as CredentialORM
from routeros_mcp.infra.db.models import Device as DeviceORM
from routeros_mcp.mcp.errors import (
    AuthenticationError,
    DeviceNotFoundError,
    EnvironmentMismatchError,
    ValidationError,
)


class _FakeRestClient:
    def __init__(self):
        self.calls: list[str] = []
        self.closed = False

    async def get(self, path: str):
        self.calls.append(path)
        return {}

    async def close(self):
        self.closed = True
        self.calls.append("close")


@pytest.fixture
async def db_session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def settings():
    return Settings(environment="lab", encryption_key="secret-key")


@pytest.fixture(autouse=True)
def patch_crypto(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(device_module, "encrypt_string", lambda value, key: f"enc-{value}-{key}")
    monkeypatch.setattr(
        device_module,
        "decrypt_string",
        lambda value, key: value.replace(f"-{key}", "").replace("enc-", ""),
    )


@pytest.fixture
def fake_rest_client(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeRestClient()
    monkeypatch.setattr(device_module, "RouterOSRestClient", lambda **kwargs: fake)
    return fake


@pytest.mark.asyncio
async def test_register_and_get_device(db_session: AsyncSession, settings: Settings):
    service = DeviceService(db_session, settings)

    created = await service.register_device(
        DeviceCreate(
            id="dev-1",
            name="router-1",
            management_address="192.0.2.1:443",
            environment="lab",
        )
    )

    assert created.id == "dev-1"
    fetched = await service.get_device("dev-1")
    assert fetched.name == "router-1"


@pytest.mark.asyncio
async def test_register_validation_errors(db_session: AsyncSession, settings: Settings):
    service = DeviceService(db_session, settings)

    # Environment mismatch
    with pytest.raises(EnvironmentMismatchError):
        await service.register_device(
            DeviceCreate(
                id="dev-env",
                name="bad",
                management_address="192.0.2.2:443",
                environment="prod",
            )
        )

    # Duplicate
    await service.register_device(
        DeviceCreate(
            id="dev-dup",
            name="router",
            management_address="192.0.2.3:443",
            environment="lab",
        )
    )
    with pytest.raises(ValidationError):
        await service.register_device(
            DeviceCreate(
                id="dev-dup",
                name="router",
                management_address="192.0.2.3:443",
                environment="lab",
            )
        )


@pytest.mark.asyncio
async def test_update_device_and_not_found(db_session: AsyncSession, settings: Settings):
    service = DeviceService(db_session, settings)
    with pytest.raises(DeviceNotFoundError):
        await service.update_device("missing", DeviceUpdate(name="x"))

    await service.register_device(
        DeviceCreate(
            id="dev-2",
            name="router-2",
            management_address="192.0.2.4:443",
            environment="lab",
        )
    )
    updated = await service.update_device("dev-2", DeviceUpdate(name="new-name", status="healthy"))
    assert updated.name == "new-name"
    assert updated.status == "healthy"


@pytest.mark.asyncio
async def test_add_credential_and_get_rest_client(
    db_session: AsyncSession, settings: Settings, fake_rest_client: _FakeRestClient
):
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-cred",
            name="router",
            management_address="router.lab:8443",
            environment="lab",
        )
    )

    await service.add_credential(
        CredentialCreate(
            device_id="dev-cred",
            kind="routeros_rest",
            username="admin",
            password="pass",
        )
    )

    credential = await db_session.get(CredentialORM, "cred-dev-cred-routeros_rest")
    assert credential is not None
    assert credential.encrypted_secret.startswith("enc-pass")

    client = await service.get_rest_client("dev-cred")
    assert client is fake_rest_client
    assert fake_rest_client.closed is False


@pytest.mark.asyncio
async def test_get_rest_client_no_credentials(db_session: AsyncSession, settings: Settings):
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-none",
            name="router",
            management_address="192.0.2.5",
            environment="lab",
        )
    )

    with pytest.raises(AuthenticationError):
        await service.get_rest_client("dev-none")


@pytest.mark.asyncio
async def test_get_device_not_found(db_session: AsyncSession, settings: Settings):
    service = DeviceService(db_session, settings)
    with pytest.raises(DeviceNotFoundError):
        await service.get_device("missing")


@pytest.mark.asyncio
async def test_check_connectivity_success(
    db_session: AsyncSession, settings: Settings, fake_rest_client: _FakeRestClient
):
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-ok",
            name="router",
            management_address="192.0.2.6:443",
            environment="lab",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-ok",
            kind="routeros_rest",
            username="admin",
            password="pass",
        )
    )

    reachable = await service.check_connectivity("dev-ok")
    assert reachable is True
    device = await db_session.get(DeviceORM, "dev-ok")
    assert device.status == "healthy"
    assert device.last_seen_at is not None
    assert "close" in fake_rest_client.calls


@pytest.mark.asyncio
async def test_check_connectivity_failure_updates_status(
    db_session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
):
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-fail",
            name="router",
            management_address="192.0.2.7:443",
            environment="lab",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-fail",
            kind="routeros_rest",
            username="admin",
            password="pass",
        )
    )

    async def _boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "get_rest_client", _boom)

    reachable = await service.check_connectivity("dev-fail")
    assert reachable is False
    device = await db_session.get(DeviceORM, "dev-fail")
    assert device.status == "unreachable"
