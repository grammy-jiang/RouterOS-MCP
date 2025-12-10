"""Tests for ORM models."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

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


@pytest.fixture
async def db_session():
    """Create an in-memory database session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Create session
    async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session_maker() as session:
        yield session
        
    await engine.dispose()


class TestDeviceModel:
    """Tests for Device model."""
    
    @pytest.mark.asyncio
    async def test_device_creation(self, db_session) -> None:
        """Test creating a Device instance."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_address="198.51.100.1:443",
            environment="lab",
            status="healthy",
            tags={"site": "main", "rack": "A1"},
            allow_advanced_writes=True,
            allow_professional_workflows=False,
        )
        
        db_session.add(device)
        await db_session.commit()
        
        # Query back
        result = await db_session.execute(select(Device).where(Device.id == "dev-001"))
        found = result.scalar_one()
        
        assert found.id == "dev-001"
        assert found.name == "test-router"
        assert found.environment == "lab"
        assert found.tags == {"site": "main", "rack": "A1"}
        assert found.allow_advanced_writes is True
        
    @pytest.mark.asyncio
    async def test_device_timestamps(self, db_session) -> None:
        """Test that timestamps are auto-generated."""
        device = Device(
            id="dev-002",
            name="test-router-2",
            management_address="198.51.100.2:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        
        db_session.add(device)
        await db_session.commit()
        
        assert device.created_at is not None
        assert device.updated_at is not None
        assert isinstance(device.created_at, datetime)
        
    @pytest.mark.asyncio
    async def test_device_to_dict(self, db_session) -> None:
        """Test Device.to_dict() method."""
        device = Device(
            id="dev-003",
            name="test-router-3",
            management_address="198.51.100.3:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        
        device_dict = device.to_dict()
        
        assert device_dict["id"] == "dev-003"
        assert device_dict["name"] == "test-router-3"
        assert "created_at" in device_dict
        
    @pytest.mark.asyncio
    async def test_device_repr(self, db_session) -> None:
        """Test Device.__repr__() method."""
        device = Device(
            id="dev-004",
            name="test-router-4",
            management_address="198.51.100.4:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        
        repr_str = repr(device)
        assert "Device" in repr_str
        assert "dev-004" in repr_str


class TestDeviceRelationships:
    """Tests for Device relationships."""
    
    @pytest.mark.asyncio
    async def test_device_credentials_relationship(self, db_session) -> None:
        """Test Device -> Credential relationship."""
        device = Device(
            id="dev-100",
            name="test-router-100",
            management_address="198.51.100.100:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        db_session.add(device)
        await db_session.commit()
        
        cred = Credential(
            id="cred-100",
            device_id="dev-100",
            kind="routeros_rest",
            username="admin",
            encrypted_secret="encrypted_data",
            active=True,
        )
        db_session.add(cred)
        await db_session.commit()
        
        # Query device and check credentials
        result = await db_session.execute(select(Device).where(Device.id == "dev-100"))
        found_device = result.scalar_one()
        
        assert len(found_device.credentials) == 1
        assert found_device.credentials[0].id == "cred-100"
        
    @pytest.mark.asyncio
    async def test_device_cascade_delete_credentials(self, db_session) -> None:
        """Test that deleting device cascades to credentials."""
        device = Device(
            id="dev-200",
            name="test-router-200",
            management_address="198.51.100.200:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        db_session.add(device)
        
        cred = Credential(
            id="cred-200",
            device_id="dev-200",
            kind="routeros_rest",
            username="admin",
            encrypted_secret="encrypted_data",
            active=True,
        )
        db_session.add(cred)
        await db_session.commit()
        
        # Delete device
        await db_session.delete(device)
        await db_session.commit()
        
        # Credential should be deleted
        result = await db_session.execute(select(Credential).where(Credential.id == "cred-200"))
        found_cred = result.scalar_one_or_none()
        assert found_cred is None


class TestCredentialModel:
    """Tests for Credential model."""
    
    @pytest.mark.asyncio
    async def test_credential_creation(self, db_session) -> None:
        """Test creating a Credential instance."""
        device = Device(
            id="dev-300",
            name="test-router-300",
            management_address="198.51.100.300:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        db_session.add(device)
        
        cred = Credential(
            id="cred-300",
            device_id="dev-300",
            kind="routeros_ssh",
            username="sshuser",
            encrypted_secret="ssh_encrypted_data",
            active=True,
        )
        db_session.add(cred)
        await db_session.commit()
        
        result = await db_session.execute(select(Credential).where(Credential.id == "cred-300"))
        found = result.scalar_one()
        
        assert found.kind == "routeros_ssh"
        assert found.username == "sshuser"
        assert found.active is True


class TestHealthCheckModel:
    """Tests for HealthCheck model."""
    
    @pytest.mark.asyncio
    async def test_healthcheck_creation(self, db_session) -> None:
        """Test creating a HealthCheck instance."""
        device = Device(
            id="dev-400",
            name="test-router-400",
            management_address="198.51.100.400:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        db_session.add(device)
        await db_session.commit()
        
        health_check = HealthCheck(
            id="hc-400",
            device_id="dev-400",
            timestamp=datetime.now(timezone.utc),
            status="healthy",
            cpu_usage_percent=25.5,
            memory_used_bytes=1024 * 1024 * 512,
            memory_total_bytes=1024 * 1024 * 1024,
            temperature_celsius=45.0,
            uptime_seconds=86400,
        )
        db_session.add(health_check)
        await db_session.commit()
        
        result = await db_session.execute(select(HealthCheck).where(HealthCheck.id == "hc-400"))
        found = result.scalar_one()
        
        assert found.status == "healthy"
        assert found.cpu_usage_percent == 25.5
        assert found.memory_used_bytes == 1024 * 1024 * 512


class TestSnapshotModel:
    """Tests for Snapshot model."""
    
    @pytest.mark.asyncio
    async def test_snapshot_creation(self, db_session) -> None:
        """Test creating a Snapshot instance."""
        device = Device(
            id="dev-500",
            name="test-router-500",
            management_address="198.51.100.500:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        db_session.add(device)
        await db_session.commit()
        
        snapshot = Snapshot(
            id="snap-500",
            device_id="dev-500",
            timestamp=datetime.now(timezone.utc),
            kind="config",
            data=b"compressed config data",
            meta={"size": 1024, "checksum": "abc123"},
        )
        db_session.add(snapshot)
        await db_session.commit()
        
        result = await db_session.execute(select(Snapshot).where(Snapshot.id == "snap-500"))
        found = result.scalar_one()
        
        assert found.kind == "config"
        assert found.data == b"compressed config data"
        assert found.meta == {"size": 1024, "checksum": "abc123"}


class TestPlanModel:
    """Tests for Plan model."""
    
    @pytest.mark.asyncio
    async def test_plan_creation(self, db_session) -> None:
        """Test creating a Plan instance."""
        plan = Plan(
            id="plan-600",
            created_by="user-123",
            tool_name="config/plan-dns-ntp-rollout",
            status="draft",
            device_ids=["dev-1", "dev-2", "dev-3"],
            summary="DNS/NTP rollout to 3 devices",
            changes={"dns_servers": ["8.8.8.8", "1.1.1.1"]},
        )
        db_session.add(plan)
        await db_session.commit()
        
        result = await db_session.execute(select(Plan).where(Plan.id == "plan-600"))
        found = result.scalar_one()
        
        assert found.status == "draft"
        assert found.device_ids == ["dev-1", "dev-2", "dev-3"]
        assert found.changes == {"dns_servers": ["8.8.8.8", "1.1.1.1"]}


class TestJobModel:
    """Tests for Job model."""
    
    @pytest.mark.asyncio
    async def test_job_creation(self, db_session) -> None:
        """Test creating a Job instance."""
        job = Job(
            id="job-700",
            job_type="APPLY_PLAN",
            status="pending",
            device_ids=["dev-1"],
            attempts=0,
            max_attempts=3,
        )
        db_session.add(job)
        await db_session.commit()
        
        result = await db_session.execute(select(Job).where(Job.id == "job-700"))
        found = result.scalar_one()
        
        assert found.job_type == "APPLY_PLAN"
        assert found.status == "pending"
        assert found.attempts == 0
        
    @pytest.mark.asyncio
    async def test_job_plan_relationship(self, db_session) -> None:
        """Test Job -> Plan relationship."""
        plan = Plan(
            id="plan-700",
            created_by="user-123",
            tool_name="test-tool",
            status="approved",
            device_ids=["dev-1"],
            summary="Test plan",
            changes={},
        )
        db_session.add(plan)
        await db_session.commit()
        
        job = Job(
            id="job-701",
            plan_id="plan-700",
            job_type="APPLY_PLAN",
            status="pending",
            device_ids=["dev-1"],
            attempts=0,
            max_attempts=3,
        )
        db_session.add(job)
        await db_session.commit()
        
        result = await db_session.execute(select(Job).where(Job.id == "job-701"))
        found_job = result.scalar_one()
        
        assert found_job.plan is not None
        assert found_job.plan.id == "plan-700"


class TestAuditEventModel:
    """Tests for AuditEvent model."""
    
    @pytest.mark.asyncio
    async def test_audit_event_creation(self, db_session) -> None:
        """Test creating an AuditEvent instance."""
        device = Device(
            id="dev-800",
            name="test-router-800",
            management_address="198.51.100.800:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        db_session.add(device)
        await db_session.commit()
        
        audit_event = AuditEvent(
            id="audit-800",
            timestamp=datetime.now(timezone.utc),
            user_sub="phase1-admin",
            user_email=None,
            user_role="admin",
            device_id="dev-800",
            environment="lab",
            action="WRITE",
            tool_name="dns/update-servers",
            tool_tier="advanced",
            result="SUCCESS",
            meta={"dns_servers": ["8.8.8.8"]},
        )
        db_session.add(audit_event)
        await db_session.commit()
        
        result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == "audit-800"))
        found = result.scalar_one()
        
        assert found.action == "WRITE"
        assert found.tool_name == "dns/update-servers"
        assert found.result == "SUCCESS"
        assert found.meta == {"dns_servers": ["8.8.8.8"]}
        
    @pytest.mark.asyncio
    async def test_audit_event_with_device(self, db_session) -> None:
        """Test AuditEvent with device relationship."""
        device = Device(
            id="dev-900",
            name="test-router-900",
            management_address="198.51.100.900:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
        )
        db_session.add(device)
        await db_session.commit()
        
        audit_event = AuditEvent(
            id="audit-900",
            timestamp=datetime.now(timezone.utc),
            user_sub="phase1-admin",
            user_email=None,
            user_role="admin",
            device_id="dev-900",
            environment="lab",
            action="READ_SENSITIVE",
            tool_name="device/get-health-data",
            tool_tier="fundamental",
            result="SUCCESS",
            meta={},
        )
        db_session.add(audit_event)
        await db_session.commit()
        
        # Verify relationship
        result = await db_session.execute(select(AuditEvent).where(AuditEvent.id == "audit-900"))
        found = result.scalar_one()
        assert found.device_id == "dev-900"
        assert found.device is not None
