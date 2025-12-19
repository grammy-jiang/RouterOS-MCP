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
from routeros_mcp.infra.routeros.exceptions import RouterOSClientError, RouterOSSSHTimeoutError
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


class _FakeSSHClient:
    def __init__(self):
        self.calls: list[str] = []
        self.closed = False

    async def execute(self, command: str):
        self.calls.append(command)
        return "ok"

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


@pytest.fixture
def fake_ssh_client(monkeypatch: pytest.MonkeyPatch):
    fake = _FakeSSHClient()
    monkeypatch.setattr(device_module, "RouterOSSSHClient", lambda **kwargs: fake)
    return fake


@pytest.mark.asyncio
async def test_register_and_get_device(db_session: AsyncSession, settings: Settings):
    service = DeviceService(db_session, settings)

    created = await service.register_device(
        DeviceCreate(
            id="dev-1",
            name="router-1",
            management_ip="192.0.2.1",
            management_port=443,
            environment="lab",
        )
    )

    assert created.id == "dev-1"
    fetched = await service.get_device("dev-1")
    assert fetched.name == "router-1"
    assert fetched.management_ip == "192.0.2.1"
    assert fetched.management_port == 443


@pytest.mark.asyncio
async def test_register_validation_errors(db_session: AsyncSession, settings: Settings):
    service = DeviceService(db_session, settings)

    # Environment mismatch
    with pytest.raises(EnvironmentMismatchError):
        await service.register_device(
            DeviceCreate(
                id="dev-env",
                name="bad",
                management_ip="192.0.2.2",
                management_port=443,
                environment="prod",
            )
        )

    # Duplicate
    await service.register_device(
        DeviceCreate(
            id="dev-dup",
            name="router",
            management_ip="192.0.2.3",
            management_port=443,
            environment="lab",
        )
    )
    with pytest.raises(ValidationError):
        await service.register_device(
            DeviceCreate(
                id="dev-dup",
                name="router",
                management_ip="192.0.2.3",
                management_port=443,
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
            management_ip="192.0.2.4",
            management_port=443,
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
            management_ip="10.0.0.1",
            management_port=8443,
            environment="lab",
        )
    )

    await service.add_credential(
        CredentialCreate(
            device_id="dev-cred",
            credential_type="rest",
            username="admin",
            password="pass",
        )
    )

    credential = await db_session.get(CredentialORM, "cred-dev-cred-rest")
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
            management_ip="192.0.2.5",
            management_port=443,
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
async def test_create_device_creates_device_and_rest_credential(
    db_session: AsyncSession, settings: Settings
) -> None:
    service = DeviceService(db_session, settings)

    created = await service.create_device(
        device_id="dev-create",
        name="router-create",
        management_ip="192.0.2.9",
        username="admin",
        password="pass",
        environment="lab",
        management_port=8443,
    )

    assert created.id == "dev-create"
    assert created.management_port == 8443

    credential = await db_session.get(CredentialORM, "cred-dev-create-rest")
    assert credential is not None


@pytest.mark.asyncio
async def test_list_devices_filters_by_environment_and_status(
    db_session: AsyncSession, settings: Settings
) -> None:
    service = DeviceService(db_session, settings)

    await service.register_device(
        DeviceCreate(
            id="dev-lab-pending",
            name="lab-pending",
            management_ip="192.0.2.20",
            management_port=443,
            environment="lab",
        )
    )
    await service.register_device(
        DeviceCreate(
            id="dev-lab-healthy",
            name="lab-healthy",
            management_ip="192.0.2.21",
            management_port=443,
            environment="lab",
        )
    )
    await service.update_device("dev-lab-healthy", DeviceUpdate(status="healthy"))

    # Insert a "prod" device directly to exercise environment filter without hitting register_device safeguards.
    db_session.add(
        DeviceORM(
            id="dev-prod",
            name="prod",
            management_ip="192.0.2.22",
            management_port=443,
            environment="prod",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
    )
    await db_session.commit()

    lab_only = await service.list_devices(environment="lab")
    assert {d.id for d in lab_only} == {"dev-lab-pending", "dev-lab-healthy"}

    healthy_only = await service.list_devices(status="healthy")
    assert {d.id for d in healthy_only} == {"dev-lab-healthy", "dev-prod"}


@pytest.mark.asyncio
async def test_update_device_invalidates_cache_on_status_change(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(environment="lab", encryption_key="secret-key")
    settings.mcp_resource_cache_auto_invalidate = True
    service = DeviceService(db_session, settings)

    await service.register_device(
        DeviceCreate(
            id="dev-cache",
            name="router",
            management_ip="192.0.2.30",
            management_port=443,
            environment="lab",
        )
    )

    class _FakeCache:
        async def invalidate_device(self, _device_id: str) -> int:
            return 2

    monkeypatch.setattr(
        "routeros_mcp.infra.observability.resource_cache.get_cache", lambda: _FakeCache()
    )

    recorded: list[tuple[str, str]] = []

    def _record(component: str, reason: str) -> None:
        recorded.append((component, reason))

    monkeypatch.setattr(device_module.metrics, "record_cache_invalidation", _record)

    await service.update_device("dev-cache", DeviceUpdate(status="healthy"))

    assert recorded == [("device", "status_change")]


@pytest.mark.asyncio
async def test_get_rest_client_raises_authentication_error_on_decrypt_failure(
    db_session: AsyncSession, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-decrypt",
            name="router",
            management_ip="192.0.2.40",
            management_port=443,
            environment="lab",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-decrypt",
            credential_type="rest",
            username="admin",
            password="pass",
        )
    )

    def _boom(_value: str, _key: str) -> str:
        raise RuntimeError("decrypt failed")

    monkeypatch.setattr(device_module, "decrypt_string", _boom)

    with pytest.raises(AuthenticationError):
        await service.get_rest_client("dev-decrypt")


@pytest.mark.asyncio
async def test_check_connectivity_records_status_code_and_classifies_failures(
    db_session: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-errors",
            name="router",
            management_ip="192.0.2.50",
            management_port=443,
            environment="lab",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-errors",
            credential_type="rest",
            username="admin",
            password="pass",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-errors",
            credential_type="ssh",
            username="admin",
            password="pass",
        )
    )

    class _RestBoom:
        async def get(self, _path: str) -> dict:
            raise RouterOSClientError("bad", status_code=418)

        async def close(self) -> None:
            return None

    async def _fake_rest_client(_device_id: str):
        return _RestBoom()

    class _SSHTimeout:
        async def execute(self, _cmd: str) -> str:
            raise RouterOSSSHTimeoutError("ssh timeout")

        async def close(self) -> None:
            return None

    async def _fake_ssh_client(_device_id: str):
        return _SSHTimeout()

    monkeypatch.setattr(service, "get_rest_client", _fake_rest_client)
    monkeypatch.setattr(service, "get_ssh_client", _fake_ssh_client)

    reachable, meta = await service.check_connectivity("dev-errors")
    assert reachable is False
    assert meta["attempted_transports"] == ["rest", "ssh"]
    assert meta["fallback_used"] is True
    assert meta["status_code"] == 418
    assert meta["failure_reason"] == "timeout"

    device = await db_session.get(DeviceORM, "dev-errors")
    assert device.status == "unreachable"


@pytest.mark.asyncio
async def test_check_connectivity_success(
    db_session: AsyncSession,
    settings: Settings,
    fake_rest_client: _FakeRestClient,
    fake_ssh_client: _FakeSSHClient,
):
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-ok",
            name="router",
            management_ip="192.0.2.6",
            management_port=443,
            environment="lab",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-ok",
            credential_type="rest",
            username="admin",
            password="pass",
        )
    )

    reachable, meta = await service.check_connectivity("dev-ok")
    assert reachable is True
    assert meta["failure_reason"] is None
    assert meta["transport"] == "rest"
    assert meta["attempted_transports"] == ["rest"]
    assert meta["fallback_used"] is False
    device = await db_session.get(DeviceORM, "dev-ok")
    assert device.status == "healthy"
    assert device.last_seen_at is not None
    assert "close" in fake_rest_client.calls


@pytest.mark.asyncio
async def test_check_connectivity_failure_updates_status(
    db_session: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    fake_ssh_client: _FakeSSHClient,
):
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-fail",
            name="router",
            management_ip="192.0.2.7",
            management_port=443,
            environment="lab",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-fail",
            credential_type="rest",
            username="admin",
            password="pass",
        )
    )

    async def _boom_rest(*_args, **_kwargs):
        raise RuntimeError("boom-rest")

    async def _boom_ssh(*_args, **_kwargs):
        raise RuntimeError("boom-ssh")

    monkeypatch.setattr(service, "get_rest_client", _boom_rest)
    monkeypatch.setattr(service, "get_ssh_client", _boom_ssh)

    reachable, meta = await service.check_connectivity("dev-fail")
    assert reachable is False
    assert meta["failure_reason"] == "unknown"
    assert meta["fallback_used"] is True  # attempted SSH
    assert meta["attempted_transports"] == ["rest", "ssh"]
    device = await db_session.get(DeviceORM, "dev-fail")
    assert device.status == "unreachable"


@pytest.mark.asyncio
async def test_check_connectivity_ssh_fallback_success(
    db_session: AsyncSession,
    settings: Settings,
    fake_rest_client: _FakeRestClient,
    fake_ssh_client: _FakeSSHClient,
    monkeypatch: pytest.MonkeyPatch,
):
    service = DeviceService(db_session, settings)
    await service.register_device(
        DeviceCreate(
            id="dev-ssh",
            name="router",
            management_ip="192.0.2.8",
            management_port=443,
            environment="lab",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-ssh",
            credential_type="rest",
            username="admin",
            password="pass",
        )
    )
    await service.add_credential(
        CredentialCreate(
            device_id="dev-ssh",
            credential_type="ssh",
            username="admin",
            password="pass",
        )
    )

    async def _rest_fail(*_args, **_kwargs):
        raise RuntimeError("rest-down")

    monkeypatch.setattr(service, "get_rest_client", _rest_fail)

    reachable, meta = await service.check_connectivity("dev-ssh")
    assert reachable is True
    assert meta["failure_reason"] is None
    assert meta["transport"] == "ssh"
    assert meta["fallback_used"] is True
    assert meta["attempted_transports"] == ["rest", "ssh"]
    device = await db_session.get(DeviceORM, "dev-ssh")
    assert device.status == "healthy"
    assert device.last_seen_at is not None
    assert "/system/resource/print" in fake_ssh_client.calls


class TestDeviceServiceSSLVerification:
    """Tests for SSL verification configuration in DeviceService."""

    @pytest.mark.asyncio
    async def test_get_rest_client_passes_verify_ssl_true(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that get_rest_client passes verify_ssl=True when setting is True."""
        settings = Settings(
            environment="lab", encryption_key="secret-key", routeros_verify_ssl=True
        )
        service = DeviceService(db_session, settings)

        # Register device and credential
        await service.register_device(
            DeviceCreate(
                id="dev-ssl-true",
                name="router",
                management_ip="192.0.2.10",
                management_port=443,
                environment="lab",
            )
        )
        await service.add_credential(
            CredentialCreate(
                device_id="dev-ssl-true",
                credential_type="rest",
                username="admin",
                password="pass",
            )
        )

        # Capture RouterOSRestClient kwargs
        captured_kwargs: list[dict] = []

        def capture_client(**kwargs):
            captured_kwargs.append(kwargs)
            return _FakeRestClient()

        monkeypatch.setattr(device_module, "RouterOSRestClient", capture_client)

        await service.get_rest_client("dev-ssl-true")

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["verify_ssl"] is True

    @pytest.mark.asyncio
    async def test_get_rest_client_passes_verify_ssl_false(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ):
        """Test that get_rest_client passes verify_ssl=False when setting is False."""
        settings = Settings(
            environment="lab", encryption_key="secret-key", routeros_verify_ssl=False
        )
        service = DeviceService(db_session, settings)

        # Register device and credential
        await service.register_device(
            DeviceCreate(
                id="dev-ssl-false",
                name="router",
                management_ip="192.0.2.11",
                management_port=443,
                environment="lab",
            )
        )
        await service.add_credential(
            CredentialCreate(
                device_id="dev-ssl-false",
                credential_type="rest",
                username="admin",
                password="pass",
            )
        )

        # Capture RouterOSRestClient kwargs
        captured_kwargs: list[dict] = []

        def capture_client(**kwargs):
            captured_kwargs.append(kwargs)
            return _FakeRestClient()

        monkeypatch.setattr(device_module, "RouterOSRestClient", capture_client)

        await service.get_rest_client("dev-ssl-false")

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["verify_ssl"] is False


# ============================================================================
# Phase 3 Capability Check Tests
# ============================================================================


@pytest.mark.asyncio
async def test_capability_checks_when_lab_device_with_professional_workflows_allowed_passes(
    db_session: AsyncSession, settings: Settings
):
    """Test capability check passes for lab device with professional workflows enabled."""
    from routeros_mcp.domain.models import DeviceCapability

    service = DeviceService(db_session, settings)
    
    # Create lab device with professional workflows enabled
    await service.register_device(
        DeviceCreate(
            id="dev-lab-01",
            name="router-lab-01",
            management_ip="192.0.2.1",
            environment="lab",
            allow_professional_workflows=True,
        )
    )
    
    # Check should pass
    device = await service.check_device_capabilities(
        device_id="dev-lab-01",
        required_capabilities=[DeviceCapability.PROFESSIONAL_WORKFLOWS],
        operation="test_operation",
    )
    
    assert device.id == "dev-lab-01"
    assert device.environment == "lab"
    assert device.allow_professional_workflows is True


@pytest.mark.asyncio
async def test_capability_checks_when_staging_device_with_firewall_writes_allowed_passes(
    db_session: AsyncSession
):
    """Test capability check passes for staging device with firewall writes enabled."""
    from routeros_mcp.domain.models import DeviceCapability

    # Create service with staging environment to register staging device
    settings_staging = Settings(environment="staging", encryption_key="secret-key")
    service = DeviceService(db_session, settings_staging)
    
    # Create staging device with firewall writes enabled
    await service.register_device(
        DeviceCreate(
            id="dev-staging-01",
            name="router-staging-01",
            management_ip="192.0.2.2",
            environment="staging",
            allow_firewall_writes=True,
        )
    )
    
    # Check should pass
    device = await service.check_device_capabilities(
        device_id="dev-staging-01",
        required_capabilities=[DeviceCapability.FIREWALL_WRITES],
        allowed_environments=["lab", "staging"],
        operation="firewall_write",
    )
    
    assert device.id == "dev-staging-01"
    assert device.allow_firewall_writes is True


@pytest.mark.asyncio
async def test_capability_checks_when_prod_device_blocked_by_environment(
    db_session: AsyncSession
):
    """Test capability check fails for prod device (environment restriction)."""
    from routeros_mcp.domain.exceptions import EnvironmentNotAllowedError
    from routeros_mcp.domain.models import DeviceCapability

    # Create service with prod environment to register prod device
    settings_prod = Settings(environment="prod", encryption_key="secret-key")
    service = DeviceService(db_session, settings_prod)
    
    # Create prod device with capability enabled (should still fail on environment)
    await service.register_device(
        DeviceCreate(
            id="dev-prod-01",
            name="router-prod-01",
            management_ip="192.0.2.3",
            environment="prod",
            allow_professional_workflows=True,
        )
    )
    
    # Check should fail due to environment restriction
    with pytest.raises(EnvironmentNotAllowedError) as exc_info:
        await service.check_device_capabilities(
            device_id="dev-prod-01",
            required_capabilities=[DeviceCapability.PROFESSIONAL_WORKFLOWS],
            allowed_environments=["lab", "staging"],  # prod not allowed
            operation="professional_operation",
        )
    
    # Verify error context
    assert exc_info.value.context["device_id"] == "dev-prod-01"
    assert exc_info.value.context["device_environment"] == "prod"
    assert exc_info.value.context["allowed_environments"] == ["lab", "staging"]


@pytest.mark.asyncio
async def test_capability_checks_when_prod_device_with_explicit_override_passes(
    db_session: AsyncSession
):
    """Test capability check passes for prod device when explicitly allowed."""
    from routeros_mcp.domain.models import DeviceCapability

    # Create service with prod environment to register prod device
    settings_prod = Settings(environment="prod", encryption_key="secret-key")
    service = DeviceService(db_session, settings_prod)
    
    # Create prod device with capability enabled
    await service.register_device(
        DeviceCreate(
            id="dev-prod-02",
            name="router-prod-02",
            management_ip="192.0.2.4",
            environment="prod",
            allow_routing_writes=True,
        )
    )
    
    # Check should pass when prod is in allowed environments
    device = await service.check_device_capabilities(
        device_id="dev-prod-02",
        required_capabilities=[DeviceCapability.ROUTING_WRITES],
        allowed_environments=["lab", "staging", "prod"],  # Explicitly allow prod
        operation="routing_write",
    )
    
    assert device.id == "dev-prod-02"
    assert device.environment == "prod"
    assert device.allow_routing_writes is True


@pytest.mark.asyncio
async def test_capability_checks_when_capability_flag_disabled_raises_error(
    db_session: AsyncSession, settings: Settings
):
    """Test capability check fails when required capability flag is disabled."""
    from routeros_mcp.domain.exceptions import CapabilityNotAllowedError
    from routeros_mcp.domain.models import DeviceCapability

    service = DeviceService(db_session, settings)
    
    # Create lab device WITHOUT firewall writes enabled
    await service.register_device(
        DeviceCreate(
            id="dev-lab-02",
            name="router-lab-02",
            management_ip="192.0.2.5",
            environment="lab",
            allow_firewall_writes=False,  # Explicitly disabled
        )
    )
    
    # Check should fail due to missing capability
    with pytest.raises(CapabilityNotAllowedError) as exc_info:
        await service.check_device_capabilities(
            device_id="dev-lab-02",
            required_capabilities=[DeviceCapability.FIREWALL_WRITES],
            operation="firewall_write",
        )
    
    # Verify error context
    assert exc_info.value.context["device_id"] == "dev-lab-02"
    assert exc_info.value.context["required_capability"] == "allow_firewall_writes"
    assert exc_info.value.context["current_value"] is False


@pytest.mark.asyncio
async def test_capability_checks_when_multiple_capabilities_required_all_must_pass(
    db_session: AsyncSession, settings: Settings
):
    """Test capability check with multiple required capabilities."""
    from routeros_mcp.domain.exceptions import CapabilityNotAllowedError
    from routeros_mcp.domain.models import DeviceCapability

    service = DeviceService(db_session, settings)
    
    # Create device with only one of two required capabilities
    await service.register_device(
        DeviceCreate(
            id="dev-lab-03",
            name="router-lab-03",
            management_ip="192.0.2.6",
            environment="lab",
            allow_firewall_writes=True,
            allow_routing_writes=False,  # Missing this one
        )
    )
    
    # Check should fail because routing_writes is not enabled
    with pytest.raises(CapabilityNotAllowedError) as exc_info:
        await service.check_device_capabilities(
            device_id="dev-lab-03",
            required_capabilities=[
                DeviceCapability.FIREWALL_WRITES,
                DeviceCapability.ROUTING_WRITES,  # This will fail
            ],
            operation="combined_operation",
        )
    
    assert exc_info.value.context["required_capability"] == "allow_routing_writes"


@pytest.mark.asyncio
async def test_capability_checks_when_no_capabilities_required_only_checks_environment(
    db_session: AsyncSession, settings: Settings
):
    """Test capability check with no capabilities required (environment only)."""
    service = DeviceService(db_session, settings)
    
    # Create lab device
    await service.register_device(
        DeviceCreate(
            id="dev-lab-04",
            name="router-lab-04",
            management_ip="192.0.2.7",
            environment="lab",
        )
    )
    
    # Check should pass with no capability requirements
    device = await service.check_device_capabilities(
        device_id="dev-lab-04",
        required_capabilities=None,  # No capabilities required
        operation="environment_only_check",
    )
    
    assert device.id == "dev-lab-04"


@pytest.mark.asyncio
async def test_capability_checks_when_device_not_found_raises_error(
    db_session: AsyncSession, settings: Settings
):
    """Test capability check fails when device doesn't exist."""
    from routeros_mcp.domain.models import DeviceCapability

    service = DeviceService(db_session, settings)
    
    # Check should fail with DeviceNotFoundError
    with pytest.raises(DeviceNotFoundError):
        await service.check_device_capabilities(
            device_id="non-existent-device",
            required_capabilities=[DeviceCapability.PROFESSIONAL_WORKFLOWS],
            operation="test_operation",
        )


@pytest.mark.asyncio
async def test_capability_checks_all_phase3_capability_flags(
    db_session: AsyncSession, settings: Settings
):
    """Test all Phase 3 capability flags individually."""
    from routeros_mcp.domain.models import DeviceCapability

    service = DeviceService(db_session, settings)
    
    # Create device with all Phase 3 capabilities enabled
    await service.register_device(
        DeviceCreate(
            id="dev-lab-05",
            name="router-lab-05",
            management_ip="192.0.2.8",
            environment="lab",
            allow_professional_workflows=True,
            allow_firewall_writes=True,
            allow_routing_writes=True,
            allow_wireless_writes=True,
            allow_dhcp_writes=True,
            allow_bridge_writes=True,
        )
    )
    
    # Test each capability individually
    capabilities_to_test = [
        DeviceCapability.PROFESSIONAL_WORKFLOWS,
        DeviceCapability.FIREWALL_WRITES,
        DeviceCapability.ROUTING_WRITES,
        DeviceCapability.WIRELESS_WRITES,
        DeviceCapability.DHCP_WRITES,
        DeviceCapability.BRIDGE_WRITES,
    ]
    
    for capability in capabilities_to_test:
        device = await service.check_device_capabilities(
            device_id="dev-lab-05",
            required_capabilities=[capability],
            operation=f"test_{capability.value}",
        )
        assert device.id == "dev-lab-05"


@pytest.mark.asyncio
async def test_capability_checks_default_phase3_environments(
    db_session: AsyncSession
):
    """Test default allowed environments for Phase 3 (lab/staging only)."""
    from routeros_mcp.domain.exceptions import EnvironmentNotAllowedError
    from routeros_mcp.domain.models import DeviceCapability

    # Create service with prod environment to register prod device
    settings_prod = Settings(environment="prod", encryption_key="secret-key")
    service = DeviceService(db_session, settings_prod)
    
    # Create prod device
    await service.register_device(
        DeviceCreate(
            id="dev-prod-03",
            name="router-prod-03",
            management_ip="192.0.2.9",
            environment="prod",
            allow_professional_workflows=True,
        )
    )
    
    # Check should fail with default environments (None = lab/staging only)
    with pytest.raises(EnvironmentNotAllowedError):
        await service.check_device_capabilities(
            device_id="dev-prod-03",
            required_capabilities=[DeviceCapability.PROFESSIONAL_WORKFLOWS],
            allowed_environments=None,  # Defaults to lab/staging only
            operation="phase3_operation",
        )


@pytest.mark.asyncio
async def test_capability_checks_with_empty_capabilities_list(
    db_session: AsyncSession, settings: Settings
):
    """Test capability check with empty capabilities list (environment only)."""
    service = DeviceService(db_session, settings)
    
    # Create lab device
    await service.register_device(
        DeviceCreate(
            id="dev-lab-06",
            name="router-lab-06",
            management_ip="192.0.2.10",
            environment="lab",
        )
    )
    
    # Check should pass with empty capability list
    device = await service.check_device_capabilities(
        device_id="dev-lab-06",
        required_capabilities=[],  # Empty list
        operation="environment_only_check",
    )
    
    assert device.id == "dev-lab-06"

