"""Tests for per-user device scope filtering (Phase 5 #6).

This module tests the device scope functionality added in Phase 5:
- User model with device_scopes field
- DeviceService filtering by allowed_device_ids
- PlanService filtering by allowed_device_ids
- Authorization checks via check_device_scope
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.config import Settings
from routeros_mcp.infra.db.models import (
    Base,
    Device as DeviceORM,
    Plan as PlanORM,
    Role,
    User,
)
from routeros_mcp.mcp.errors import DeviceNotFoundError
from routeros_mcp.security.authz import check_device_scope, DeviceScopeError


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
        # Seed a default role
        role = Role(
            id="role-test-001",
            name="ops_rw",
            description="Test role",
        )
        session.add(role)
        await session.commit()

        yield session

    await engine.dispose()


@pytest.fixture
async def test_devices(db_session):
    """Create test devices."""
    devices = [
        DeviceORM(
            id="dev-lab-001",
            name="Router Lab 1",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
        ),
        DeviceORM(
            id="dev-lab-002",
            name="Router Lab 2",
            management_ip="192.168.1.2",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
        ),
        DeviceORM(
            id="dev-staging-001",
            name="Router Staging 1",
            management_ip="192.168.2.1",
            management_port=443,
            environment="staging",
            status="healthy",
            tags={},
        ),
        DeviceORM(
            id="dev-prod-001",
            name="Router Prod 1",
            management_ip="192.168.3.1",
            management_port=443,
            environment="prod",
            status="healthy",
            tags={},
        ),
    ]

    for device in devices:
        db_session.add(device)
    await db_session.commit()

    return devices


class TestUserModel:
    """Tests for User ORM model."""

    @pytest.mark.asyncio
    async def test_user_creation_with_device_scopes(self, db_session) -> None:
        """Test creating a User with device scopes."""
        user = User(
            sub="user-001",
            email="user1@example.com",
            display_name="Test User 1",
            role_name="ops_rw",
            device_scopes=["dev-lab-001", "dev-lab-002"],
            is_active=True,
        )

        db_session.add(user)
        await db_session.commit()

        # Query back
        result = await db_session.execute(select(User).where(User.sub == "user-001"))
        found = result.scalar_one()

        assert found.sub == "user-001"
        assert found.email == "user1@example.com"
        assert found.role_name == "ops_rw"
        assert found.device_scopes == ["dev-lab-001", "dev-lab-002"]
        assert found.is_active is True

    @pytest.mark.asyncio
    async def test_user_creation_with_full_access(self, db_session) -> None:
        """Test creating a User with full access (empty device_scopes)."""
        user = User(
            sub="admin-001",
            email="admin@example.com",
            display_name="Admin User",
            role_name="ops_rw",
            device_scopes=[],  # Empty = full access
            is_active=True,
        )

        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.sub == "admin-001"))
        found = result.scalar_one()

        assert found.device_scopes == []

    @pytest.mark.asyncio
    async def test_user_role_relationship(self, db_session) -> None:
        """Test User-Role relationship."""
        user = User(
            sub="user-002",
            email="user2@example.com",
            display_name="Test User 2",
            role_name="ops_rw",
            device_scopes=[],
            is_active=True,
        )

        db_session.add(user)
        await db_session.commit()

        result = await db_session.execute(select(User).where(User.sub == "user-002"))
        found = result.scalar_one()

        # Verify relationship loads
        assert found.role is not None
        assert found.role.name == "ops_rw"


class TestDeviceServiceScoping:
    """Tests for DeviceService device scope filtering."""

    @pytest.mark.asyncio
    async def test_list_devices_with_full_access(self, db_session, test_devices) -> None:
        """Test listing devices with no scope restrictions (None)."""
        settings = Settings(environment="lab")
        service = DeviceService(db_session, settings)

        devices = await service.list_devices(allowed_device_ids=None)

        # Should return all devices
        assert len(devices) == 4
        device_ids = [d.id for d in devices]
        assert "dev-lab-001" in device_ids
        assert "dev-staging-001" in device_ids

    @pytest.mark.asyncio
    async def test_list_devices_with_restricted_scope(self, db_session, test_devices) -> None:
        """Test listing devices with restricted scope."""
        settings = Settings(environment="lab")
        service = DeviceService(db_session, settings)

        # User only has access to lab devices
        allowed_ids = ["dev-lab-001", "dev-lab-002"]
        devices = await service.list_devices(allowed_device_ids=allowed_ids)

        assert len(devices) == 2
        device_ids = [d.id for d in devices]
        assert "dev-lab-001" in device_ids
        assert "dev-lab-002" in device_ids
        assert "dev-staging-001" not in device_ids

    @pytest.mark.asyncio
    async def test_list_devices_scope_with_environment_filter(
        self, db_session, test_devices
    ) -> None:
        """Test combining scope and environment filters."""
        settings = Settings(environment="lab")
        service = DeviceService(db_session, settings)

        # User has access to both lab and staging, but filter by lab
        allowed_ids = ["dev-lab-001", "dev-lab-002", "dev-staging-001"]
        devices = await service.list_devices(
            environment="lab", allowed_device_ids=allowed_ids
        )

        assert len(devices) == 2
        device_ids = [d.id for d in devices]
        assert all("lab" in d_id for d_id in device_ids)

    @pytest.mark.asyncio
    async def test_get_device_with_full_access(self, db_session, test_devices) -> None:
        """Test getting device with no scope restrictions."""
        settings = Settings(environment="lab")
        service = DeviceService(db_session, settings)

        device = await service.get_device("dev-lab-001", allowed_device_ids=None)

        assert device.id == "dev-lab-001"
        assert device.name == "Router Lab 1"

    @pytest.mark.asyncio
    async def test_get_device_in_scope(self, db_session, test_devices) -> None:
        """Test getting device that is in user's scope."""
        settings = Settings(environment="lab")
        service = DeviceService(db_session, settings)

        allowed_ids = ["dev-lab-001", "dev-lab-002"]
        device = await service.get_device("dev-lab-001", allowed_device_ids=allowed_ids)

        assert device.id == "dev-lab-001"

    @pytest.mark.asyncio
    async def test_get_device_not_in_scope(self, db_session, test_devices) -> None:
        """Test getting device that is NOT in user's scope."""
        settings = Settings(environment="lab")
        service = DeviceService(db_session, settings)

        allowed_ids = ["dev-lab-001", "dev-lab-002"]

        with pytest.raises(DeviceNotFoundError) as exc_info:
            await service.get_device("dev-staging-001", allowed_device_ids=allowed_ids)

        assert "not found or not accessible" in str(exc_info.value)


class TestPlanServiceScoping:
    """Tests for PlanService device scope filtering."""

    @pytest.fixture
    async def test_plans(self, db_session, test_devices):
        """Create test plans."""
        plans = [
            PlanORM(
                id="plan-001",
                created_by="user-001",
                tool_name="dns/update-servers",
                status="pending",
                device_ids=["dev-lab-001"],
                summary="Update DNS on lab device 1",
                changes={"servers": ["8.8.8.8"]},
            ),
            PlanORM(
                id="plan-002",
                created_by="user-001",
                tool_name="dns/update-servers",
                status="pending",
                device_ids=["dev-lab-001", "dev-lab-002"],
                summary="Update DNS on lab devices",
                changes={"servers": ["8.8.8.8"]},
            ),
            PlanORM(
                id="plan-003",
                created_by="user-002",
                tool_name="routing/add-static-route",
                status="approved",
                device_ids=["dev-staging-001"],
                summary="Add route on staging",
                changes={"route": "10.0.0.0/8"},
            ),
            PlanORM(
                id="plan-004",
                created_by="user-001",
                tool_name="firewall/add-filter-rule",
                status="pending",
                device_ids=["dev-lab-001", "dev-staging-001"],
                summary="Add firewall rule on mixed devices",
                changes={"rule": "accept"},
            ),
        ]

        for plan in plans:
            db_session.add(plan)
        await db_session.commit()

        return plans

    @pytest.mark.asyncio
    async def test_list_plans_with_full_access(self, db_session, test_plans) -> None:
        """Test listing plans with no scope restrictions."""
        service = PlanService(db_session)

        plans = await service.list_plans(allowed_device_ids=None)

        # Should return all plans
        assert len(plans) == 4

    @pytest.mark.asyncio
    async def test_list_plans_with_restricted_scope(self, db_session, test_plans) -> None:
        """Test listing plans with restricted device scope."""
        service = PlanService(db_session)

        # User only has access to lab devices
        allowed_ids = ["dev-lab-001", "dev-lab-002"]
        plans = await service.list_plans(allowed_device_ids=allowed_ids)

        # Should return only plans with devices in scope
        # plan-001: [dev-lab-001] ✓
        # plan-002: [dev-lab-001, dev-lab-002] ✓
        # plan-003: [dev-staging-001] ✗
        # plan-004: [dev-lab-001, dev-staging-001] ✗ (has out-of-scope device)
        assert len(plans) == 2
        plan_ids = [p["plan_id"] for p in plans]
        assert "plan-001" in plan_ids
        assert "plan-002" in plan_ids
        assert "plan-003" not in plan_ids
        assert "plan-004" not in plan_ids

    @pytest.mark.asyncio
    async def test_get_plan_with_full_access(self, db_session, test_plans) -> None:
        """Test getting plan with no scope restrictions."""
        service = PlanService(db_session)

        plan = await service.get_plan("plan-001", allowed_device_ids=None)

        assert plan["plan_id"] == "plan-001"
        assert plan["device_ids"] == ["dev-lab-001"]

    @pytest.mark.asyncio
    async def test_get_plan_in_scope(self, db_session, test_plans) -> None:
        """Test getting plan with devices in user's scope."""
        service = PlanService(db_session)

        allowed_ids = ["dev-lab-001", "dev-lab-002"]
        plan = await service.get_plan("plan-002", allowed_device_ids=allowed_ids)

        assert plan["plan_id"] == "plan-002"

    @pytest.mark.asyncio
    async def test_get_plan_not_in_scope(self, db_session, test_plans) -> None:
        """Test getting plan with devices NOT in user's scope."""
        service = PlanService(db_session)

        allowed_ids = ["dev-lab-001", "dev-lab-002"]

        with pytest.raises(ValueError) as exc_info:
            await service.get_plan("plan-003", allowed_device_ids=allowed_ids)

        assert "not in allowed scope" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_plan_partially_in_scope(self, db_session, test_plans) -> None:
        """Test getting plan where some devices are in scope but not all."""
        service = PlanService(db_session)

        # plan-004 has both dev-lab-001 (in scope) and dev-staging-001 (out of scope)
        allowed_ids = ["dev-lab-001", "dev-lab-002"]

        with pytest.raises(ValueError) as exc_info:
            await service.get_plan("plan-004", allowed_device_ids=allowed_ids)

        assert "not in allowed scope" in str(exc_info.value)
        assert "dev-staging-001" in str(exc_info.value)


class TestAuthzDeviceScope:
    """Tests for check_device_scope authorization helper."""

    def test_check_device_scope_full_access_none(self) -> None:
        """Test device scope check with None (full access)."""
        # Should not raise
        check_device_scope("dev-lab-001", device_scopes=None, user_sub="user-001")

    def test_check_device_scope_full_access_empty_list(self) -> None:
        """Test device scope check with empty list (full access)."""
        # Empty list means full access (typical for admins)
        check_device_scope("dev-lab-001", device_scopes=[], user_sub="admin-001")

    def test_check_device_scope_in_scope(self) -> None:
        """Test device scope check when device is in scope."""
        check_device_scope(
            "dev-lab-001",
            device_scopes=["dev-lab-001", "dev-lab-002"],
            user_sub="user-001",
        )

    def test_check_device_scope_not_in_scope(self) -> None:
        """Test device scope check when device is NOT in scope."""
        with pytest.raises(DeviceScopeError) as exc_info:
            check_device_scope(
                "dev-staging-001",
                device_scopes=["dev-lab-001", "dev-lab-002"],
                user_sub="user-001",
            )

        error_msg = str(exc_info.value)
        assert "not in allowed scope" in error_msg
        assert "dev-staging-001" in error_msg

    def test_check_device_scope_error_message_truncation(self) -> None:
        """Test that error message truncates long device lists."""
        # Create a long list of device IDs
        many_devices = [f"dev-{i:03d}" for i in range(10)]

        with pytest.raises(DeviceScopeError) as exc_info:
            check_device_scope(
                "dev-other",
                device_scopes=many_devices,
                user_sub="user-001",
            )

        error_msg = str(exc_info.value)
        # Should show count and truncated list
        assert "10 device" in error_msg
        assert "..." in error_msg  # Indicates truncation


class TestCrossUserIsolation:
    """Tests to verify users cannot access each other's scoped devices."""

    @pytest.fixture
    async def test_users(self, db_session):
        """Create test users with different scopes."""
        users = [
            User(
                sub="user-ops-1",
                email="ops1@example.com",
                display_name="Ops User 1",
                role_name="ops_rw",
                device_scopes=["dev-lab-001"],
                is_active=True,
            ),
            User(
                sub="user-ops-2",
                email="ops2@example.com",
                display_name="Ops User 2",
                role_name="ops_rw",
                device_scopes=["dev-lab-002"],
                is_active=True,
            ),
            User(
                sub="user-admin",
                email="admin@example.com",
                display_name="Admin User",
                role_name="ops_rw",  # Using ops_rw since admin role needs to exist
                device_scopes=[],  # Empty = full access
                is_active=True,
            ),
        ]

        for user in users:
            db_session.add(user)
        await db_session.commit()

        return users

    @pytest.mark.asyncio
    async def test_user1_cannot_access_user2_devices(
        self, db_session, test_devices, test_users
    ) -> None:
        """Test that user-ops-1 cannot access user-ops-2's devices."""
        settings = Settings(environment="lab")
        service = DeviceService(db_session, settings)

        # User 1 scope: dev-lab-001 only
        user1_scope = ["dev-lab-001"]

        # Try to access user 2's device
        with pytest.raises(DeviceNotFoundError):
            await service.get_device("dev-lab-002", allowed_device_ids=user1_scope)

        # List should only return user 1's devices
        devices = await service.list_devices(allowed_device_ids=user1_scope)
        assert len(devices) == 1
        assert devices[0].id == "dev-lab-001"

    @pytest.mark.asyncio
    async def test_admin_can_access_all_devices(
        self, db_session, test_devices, test_users
    ) -> None:
        """Test that admin with empty scope can access all devices."""
        settings = Settings(environment="lab")
        service = DeviceService(db_session, settings)

        # Admin scope: [] (empty = full access)
        admin_scope = []

        # Should be able to access any device
        device1 = await service.get_device("dev-lab-001", allowed_device_ids=admin_scope)
        device2 = await service.get_device("dev-lab-002", allowed_device_ids=admin_scope)

        assert device1.id == "dev-lab-001"
        assert device2.id == "dev-lab-002"

        # List should return all devices
        devices = await service.list_devices(allowed_device_ids=admin_scope)
        assert len(devices) == 4
