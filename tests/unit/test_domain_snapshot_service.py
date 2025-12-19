"""Tests for SnapshotService - configuration snapshot capture and management."""

from __future__ import annotations

import gzip
import hashlib
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import Device as DeviceDomain
from routeros_mcp.domain.services import snapshot as snapshot_module
from routeros_mcp.domain.services.snapshot import SnapshotService
from routeros_mcp.infra.db.models import Base
from routeros_mcp.infra.db.models import Credential as CredentialORM
from routeros_mcp.infra.db.models import Device as DeviceORM
from routeros_mcp.infra.db.models import Snapshot as SnapshotORM
from routeros_mcp.infra.routeros.exceptions import RouterOSNetworkError
from routeros_mcp.mcp.errors import ValidationError


class _FakeRestClient:
    """Fake REST client for testing."""

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.closed = False

    async def get(self, path: str):
        if self.should_fail:
            raise Exception("REST API failed")
        return {}

    async def close(self):
        self.closed = True


class _FakeSSHClient:
    """Fake SSH client for testing."""

    def __init__(self, config_output: str | None = None, should_fail: bool = False):
        self.config_output = config_output or "# RouterOS config\n/system identity set name=test\n"
        self.should_fail = should_fail
        self.closed = False
        self.executed_commands = []

    async def execute(self, command: str):
        self.executed_commands.append(command)
        if self.should_fail:
            raise Exception("SSH command failed")
        return self.config_output

    async def close(self):
        self.closed = True


@pytest.fixture
async def db_session() -> AsyncSession:
    """Create in-memory database session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def settings():
    """Create test settings.
    
    Note: Uses a valid Fernet key for testing. This key is only for test purposes
    and should never be used in production.
    """
    return Settings(
        environment="lab",
        encryption_key="IfCjOVHuCLs-lVSMKDJlyK8HINyPnvZODbw3YzIojhQ=",  # Test-only key
        snapshot_max_size_bytes=10 * 1024 * 1024,  # 10MB
        snapshot_compression_level=6,
        snapshot_retention_count=5,
        snapshot_use_ssh_fallback=True,
    )


@pytest.fixture(autouse=True)
def suppress_warnings():
    """Suppress encryption key warnings in tests."""
    import warnings

    warnings.filterwarnings("ignore", category=UserWarning, message=".*encryption_key.*")


@pytest.fixture
async def test_device(db_session: AsyncSession, settings: Settings) -> DeviceORM:
    """Create test device in database."""
    from routeros_mcp.security.crypto import encrypt_string
    
    device = DeviceORM(
        id="dev-test-01",
        name="test-router",
        management_ip="192.0.2.1",
        management_port=443,
        environment="lab",
        status="healthy",
        tags={},
        allow_advanced_writes=True,
        allow_professional_workflows=False,
    )
    db_session.add(device)

    # Add SSH credentials with properly encrypted password
    encrypted_password = encrypt_string("password", settings.encryption_key)
    cred = CredentialORM(
        id="cred-01",
        device_id="dev-test-01",
        credential_type="ssh",
        username="admin",
        encrypted_secret=encrypted_password,
        active=True,
    )
    db_session.add(cred)

    await db_session.commit()
    await db_session.refresh(device)
    return device


@pytest.fixture
def device_domain(test_device: DeviceORM) -> DeviceDomain:
    """Create device domain model from ORM."""
    return DeviceDomain.model_validate(test_device)


@pytest.mark.asyncio
async def test_capture_snapshot_via_ssh_success(
    db_session: AsyncSession,
    settings: Settings,
    device_domain: DeviceDomain,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test successful snapshot capture via SSH."""
    # Setup fake SSH client
    config_text = "# RouterOS config\n/system identity set name=test-router\n"
    fake_ssh = _FakeSSHClient(config_output=config_text)
    monkeypatch.setattr(
        snapshot_module, "RouterOSSSHClient", lambda **kwargs: fake_ssh
    )
    # Make REST fail to force SSH fallback
    fake_rest = _FakeRestClient(should_fail=True)
    monkeypatch.setattr(
        snapshot_module, "RouterOSRestClient", lambda **kwargs: fake_rest
    )

    service = SnapshotService(db_session, settings)

    # Capture snapshot
    snapshot_id = await service.capture_device_snapshot(
        device=device_domain,
        kind="config",
        use_ssh_fallback=True,
    )

    assert snapshot_id.startswith("snap-")
    assert fake_ssh.executed_commands == ["/export compact"]
    assert fake_ssh.closed

    # Verify snapshot in database
    from sqlalchemy import select

    result = await db_session.execute(
        select(SnapshotORM).where(SnapshotORM.id == snapshot_id)
    )
    snapshot = result.scalar_one()

    assert snapshot.device_id == device_domain.id
    assert snapshot.kind == "config"
    assert snapshot.meta["source"] == "ssh"
    assert snapshot.meta["compression"] == "gzip"
    assert "checksum" in snapshot.meta
    assert snapshot.meta["redacted"] is False

    # Verify data is gzip compressed (small text might be larger due to header overhead)
    # Just verify it's not the same as uncompressed
    assert snapshot.data != config_text.encode("utf-8")

    # Decode and verify content
    decoded = await service.decode_snapshot(snapshot)
    assert decoded == config_text


@pytest.mark.asyncio
async def test_capture_snapshot_size_limit_exceeded(
    db_session: AsyncSession,
    settings: Settings,
    device_domain: DeviceDomain,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test snapshot capture fails when size limit exceeded."""
    # Create large config that exceeds limit
    large_config = "# RouterOS config\n" + ("x" * (settings.snapshot_max_size_bytes + 1))
    fake_ssh = _FakeSSHClient(config_output=large_config)
    monkeypatch.setattr(
        snapshot_module, "RouterOSSSHClient", lambda **kwargs: fake_ssh
    )
    fake_rest = _FakeRestClient(should_fail=True)
    monkeypatch.setattr(
        snapshot_module, "RouterOSRestClient", lambda **kwargs: fake_rest
    )

    service = SnapshotService(db_session, settings)

    # Should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        await service.capture_device_snapshot(
            device=device_domain,
            kind="config",
        )

    assert "exceeds limit" in str(exc_info.value)


@pytest.mark.asyncio
async def test_capture_snapshot_both_rest_and_ssh_fail(
    db_session: AsyncSession,
    settings: Settings,
    device_domain: DeviceDomain,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test snapshot capture fails when both REST and SSH fail."""
    # Make both fail
    fake_rest = _FakeRestClient(should_fail=True)
    fake_ssh = _FakeSSHClient(should_fail=True)
    monkeypatch.setattr(
        snapshot_module, "RouterOSRestClient", lambda **kwargs: fake_rest
    )
    monkeypatch.setattr(
        snapshot_module, "RouterOSSSHClient", lambda **kwargs: fake_ssh
    )

    service = SnapshotService(db_session, settings)

    # Should raise RouterOSNetworkError
    with pytest.raises(RouterOSNetworkError) as exc_info:
        await service.capture_device_snapshot(
            device=device_domain,
            kind="config",
        )

    assert "Failed to capture config snapshot" in str(exc_info.value)


@pytest.mark.asyncio
async def test_capture_snapshot_no_credentials(
    db_session: AsyncSession,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
):
    """Test snapshot capture fails when no credentials exist."""
    # Create device without credentials
    device = DeviceORM(
        id="dev-no-creds",
        name="no-creds-router",
        management_ip="192.0.2.2",
        management_port=443,
        environment="lab",
        status="healthy",
        tags={},
        allow_advanced_writes=True,
        allow_professional_workflows=False,
    )
    db_session.add(device)
    await db_session.commit()

    device_domain = DeviceDomain.model_validate(device)
    service = SnapshotService(db_session, settings)

    # Should raise ValidationError
    with pytest.raises(ValidationError) as exc_info:
        await service.capture_device_snapshot(
            device=device_domain,
            kind="config",
        )

    assert "No credentials found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_latest_snapshot(
    db_session: AsyncSession,
    settings: Settings,
    device_domain: DeviceDomain,
):
    """Test retrieving the latest snapshot."""
    service = SnapshotService(db_session, settings)

    # Create multiple snapshots
    config_text = "# RouterOS config\n"
    compressed_data = gzip.compress(config_text.encode("utf-8"), compresslevel=6)
    checksum = hashlib.sha256(config_text.encode("utf-8")).hexdigest()

    for i in range(3):
        snapshot = SnapshotORM(
            id=f"snap-00{i}",
            device_id=device_domain.id,
            timestamp=datetime.now(UTC),
            kind="config",
            data=compressed_data,
            meta={
                "size_bytes": len(config_text),
                "compressed_size_bytes": len(compressed_data),
                "checksum": checksum,
                "source": "ssh",
            },
        )
        db_session.add(snapshot)

    await db_session.commit()

    # Get latest
    latest = await service.get_latest_snapshot(device_domain.id, kind="config")

    assert latest is not None
    assert latest.id == "snap-002"  # Last one created


@pytest.mark.asyncio
async def test_prune_old_snapshots(
    db_session: AsyncSession,
    settings: Settings,
    device_domain: DeviceDomain,
):
    """Test pruning old snapshots based on retention policy."""
    service = SnapshotService(db_session, settings)

    # Create 10 snapshots
    config_text = "# RouterOS config\n"
    compressed_data = gzip.compress(config_text.encode("utf-8"), compresslevel=6)
    checksum = hashlib.sha256(config_text.encode("utf-8")).hexdigest()

    for i in range(10):
        snapshot = SnapshotORM(
            id=f"snap-{i:03d}",
            device_id=device_domain.id,
            timestamp=datetime.now(UTC),
            kind="config",
            data=compressed_data,
            meta={
                "size_bytes": len(config_text),
                "compressed_size_bytes": len(compressed_data),
                "checksum": checksum,
                "source": "ssh",
            },
        )
        db_session.add(snapshot)

    await db_session.commit()

    # Prune, keeping only 5
    deleted = await service.prune_old_snapshots(
        device_id=device_domain.id,
        kind="config",
        keep_count=5,
    )

    assert deleted == 5

    # Commit to persist the deletes
    await db_session.commit()

    # Verify only 5 remain
    from sqlalchemy import select

    result = await db_session.execute(
        select(SnapshotORM).where(
            SnapshotORM.device_id == device_domain.id,
            SnapshotORM.kind == "config",
        )
    )
    remaining = result.scalars().all()
    assert len(remaining) == 5


@pytest.mark.asyncio
async def test_decode_snapshot_success(
    db_session: AsyncSession,
    settings: Settings,
    device_domain: DeviceDomain,
):
    """Test decoding a compressed snapshot."""
    service = SnapshotService(db_session, settings)

    # Create snapshot with compressed data
    config_text = "# RouterOS config\n/system identity set name=test\n"
    compressed_data = gzip.compress(config_text.encode("utf-8"), compresslevel=6)

    snapshot = SnapshotORM(
        id="snap-decode-test",
        device_id=device_domain.id,
        timestamp=datetime.now(UTC),
        kind="config",
        data=compressed_data,
        meta={
            "size_bytes": len(config_text),
            "compressed_size_bytes": len(compressed_data),
            "compression": "gzip",
            "checksum": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
            "source": "ssh",
        },
    )
    db_session.add(snapshot)
    await db_session.commit()

    # Decode
    decoded = await service.decode_snapshot(snapshot)

    assert decoded == config_text


@pytest.mark.asyncio
async def test_decode_snapshot_uncompressed(
    db_session: AsyncSession,
    settings: Settings,
    device_domain: DeviceDomain,
):
    """Test decoding an uncompressed snapshot."""
    service = SnapshotService(db_session, settings)

    # Create snapshot with uncompressed data
    config_text = "# RouterOS config\n"
    snapshot = SnapshotORM(
        id="snap-uncompressed",
        device_id=device_domain.id,
        timestamp=datetime.now(UTC),
        kind="config",
        data=config_text.encode("utf-8"),
        meta={
            "size_bytes": len(config_text),
            "compression": None,
            "checksum": hashlib.sha256(config_text.encode("utf-8")).hexdigest(),
            "source": "ssh",
        },
    )
    db_session.add(snapshot)
    await db_session.commit()

    # Decode
    decoded = await service.decode_snapshot(snapshot)

    assert decoded == config_text
