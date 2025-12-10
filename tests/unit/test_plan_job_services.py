"""Tests for Plan and Job services."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.services.job import JobService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.models import Base, Device


@pytest.fixture
async def db_session() -> AsyncSession:
    """Create an in-memory database session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        yield session

    await engine.dispose()


@pytest.fixture
async def test_devices(db_session: AsyncSession) -> list[str]:
    """Create test devices in the database."""
    device_ids = ["dev-lab-01", "dev-lab-02", "dev-lab-03"]

    for device_id in device_ids:
        device = Device(
            id=device_id,
            name=f"router-{device_id}",
            management_address="192.168.1.1:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=True,
            allow_professional_workflows=True,
        )
        db_session.add(device)

    await db_session.commit()
    return device_ids


class TestPlanService:
    """Tests for PlanService."""

    @pytest.mark.asyncio
    async def test_create_plan(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test creating a plan."""
        service = PlanService(db_session)

        plan = await service.create_plan(
            tool_name="config/plan-dns-ntp-rollout",
            created_by="test-user",
            device_ids=test_devices,
            summary="Test DNS/NTP rollout",
            changes={"dns_servers": ["8.8.8.8", "8.8.4.4"]},
            risk_level="medium",
        )

        assert plan["plan_id"].startswith("plan-")
        assert "approval_token" in plan
        assert plan["approval_token"].startswith("approve-")
        assert plan["device_count"] == len(test_devices)
        assert plan["risk_level"] == "medium"
        assert plan["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_plan_no_devices(self, db_session: AsyncSession) -> None:
        """Test creating a plan with no devices raises error."""
        service = PlanService(db_session)

        with pytest.raises(ValueError, match="At least one device must be specified"):
            await service.create_plan(
                tool_name="test-tool",
                created_by="test-user",
                device_ids=[],
                summary="Test plan",
                changes={},
                risk_level="low",
            )

    @pytest.mark.asyncio
    async def test_create_plan_invalid_device(self, db_session: AsyncSession) -> None:
        """Test creating a plan with nonexistent device raises error."""
        service = PlanService(db_session)

        with pytest.raises(ValueError, match="Devices not found"):
            await service.create_plan(
                tool_name="test-tool",
                created_by="test-user",
                device_ids=["nonexistent-device"],
                summary="Test plan",
                changes={},
                risk_level="low",
            )

    @pytest.mark.asyncio
    async def test_get_plan(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test retrieving a plan."""
        service = PlanService(db_session)

        # Create plan
        created_plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=test_devices,
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Retrieve plan
        plan = await service.get_plan(created_plan["plan_id"])

        assert plan["plan_id"] == created_plan["plan_id"]
        assert plan["status"] == "draft"
        assert plan["device_ids"] == test_devices

    @pytest.mark.asyncio
    async def test_get_plan_not_found(self, db_session: AsyncSession) -> None:
        """Test retrieving nonexistent plan raises error."""
        service = PlanService(db_session)

        with pytest.raises(ValueError, match="Plan not found"):
            await service.get_plan("nonexistent-plan")

    @pytest.mark.asyncio
    async def test_approve_plan(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test approving a plan."""
        service = PlanService(db_session)

        # Create plan
        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=test_devices,
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Approve plan
        approved_plan = await service.approve_plan(
            plan["plan_id"], plan["approval_token"], "approver-user"
        )

        assert approved_plan["status"] == "approved"
        assert approved_plan["approved_by"] == "approver-user"
        assert approved_plan["approved_at"] is not None

    @pytest.mark.asyncio
    async def test_approve_plan_invalid_token(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test approving plan with invalid token raises error."""
        service = PlanService(db_session)

        # Create plan
        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=test_devices,
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Try to approve with invalid token
        with pytest.raises(ValueError, match="Invalid approval token"):
            await service.approve_plan(plan["plan_id"], "invalid-token", "approver-user")

    @pytest.mark.asyncio
    async def test_approve_plan_already_approved(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test approving already approved plan raises error."""
        service = PlanService(db_session)

        # Create and approve plan
        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=test_devices,
            summary="Test plan",
            changes={},
            risk_level="low",
        )
        await service.approve_plan(plan["plan_id"], plan["approval_token"], "approver-user")

        # Try to approve again
        with pytest.raises(ValueError, match="already approved"):
            await service.approve_plan(plan["plan_id"], plan["approval_token"], "approver-user")

    @pytest.mark.asyncio
    async def test_update_plan_status(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test updating plan status."""
        service = PlanService(db_session)

        # Create plan
        plan = await service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=test_devices,
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Update status
        await service.update_plan_status(plan["plan_id"], "applied")

        # Verify update
        updated_plan = await service.get_plan(plan["plan_id"])
        assert updated_plan["status"] == "applied"

    @pytest.mark.asyncio
    async def test_list_plans(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test listing plans."""
        service = PlanService(db_session)

        # Create multiple plans
        await service.create_plan(
            tool_name="tool-1",
            created_by="user-1",
            device_ids=test_devices[:1],
            summary="Plan 1",
            changes={},
            risk_level="low",
        )
        await service.create_plan(
            tool_name="tool-2",
            created_by="user-2",
            device_ids=test_devices[:2],
            summary="Plan 2",
            changes={},
            risk_level="medium",
        )

        # List all plans
        plans = await service.list_plans()
        assert len(plans) == 2

        # List plans by creator
        user1_plans = await service.list_plans(created_by="user-1")
        assert len(user1_plans) == 1
        assert user1_plans[0]["created_by"] == "user-1"


class TestJobService:
    """Tests for JobService."""

    @pytest.mark.asyncio
    async def test_create_job(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test creating a job."""
        service = JobService(db_session)

        job = await service.create_job(
            job_type="APPLY_DNS_NTP_ROLLOUT",
            device_ids=test_devices,
        )

        assert job["job_id"].startswith("job-")
        assert job["job_type"] == "APPLY_DNS_NTP_ROLLOUT"
        assert job["status"] == "pending"
        assert job["device_ids"] == test_devices

    @pytest.mark.asyncio
    async def test_create_job_with_plan(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test creating a job linked to a plan."""
        plan_service = PlanService(db_session)
        job_service = JobService(db_session)

        # Create plan
        plan = await plan_service.create_plan(
            tool_name="test-tool",
            created_by="test-user",
            device_ids=test_devices,
            summary="Test plan",
            changes={},
            risk_level="low",
        )

        # Create job with plan
        job = await job_service.create_job(
            job_type="APPLY_PLAN",
            device_ids=test_devices,
            plan_id=plan["plan_id"],
        )

        assert job["plan_id"] == plan["plan_id"]

    @pytest.mark.asyncio
    async def test_create_job_invalid_plan(self, db_session: AsyncSession) -> None:
        """Test creating job with nonexistent plan raises error."""
        service = JobService(db_session)

        with pytest.raises(ValueError, match="Plan not found"):
            await service.create_job(
                job_type="APPLY_PLAN",
                device_ids=["dev-001"],
                plan_id="nonexistent-plan",
            )

    @pytest.mark.asyncio
    async def test_get_job(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test retrieving a job."""
        service = JobService(db_session)

        # Create job
        created_job = await service.create_job(
            job_type="TEST_JOB",
            device_ids=test_devices,
        )

        # Retrieve job
        job = await service.get_job(created_job["job_id"])

        assert job["job_id"] == created_job["job_id"]
        assert job["status"] == "pending"
        assert job["device_ids"] == test_devices

    @pytest.mark.asyncio
    async def test_get_job_not_found(self, db_session: AsyncSession) -> None:
        """Test retrieving nonexistent job raises error."""
        service = JobService(db_session)

        with pytest.raises(ValueError, match="Job not found"):
            await service.get_job("nonexistent-job")

    @pytest.mark.asyncio
    async def test_list_jobs(
        self, db_session: AsyncSession, test_devices: list[str]
    ) -> None:
        """Test listing jobs."""
        service = JobService(db_session)

        # Create multiple jobs
        await service.create_job(
            job_type="TYPE_A",
            device_ids=test_devices[:1],
        )
        await service.create_job(
            job_type="TYPE_B",
            device_ids=test_devices[:2],
        )

        # List all jobs
        jobs = await service.list_jobs()
        assert len(jobs) == 2

        # List jobs by type
        type_a_jobs = await service.list_jobs(job_type="TYPE_A")
        assert len(type_a_jobs) == 1
        assert type_a_jobs[0]["job_type"] == "TYPE_A"
