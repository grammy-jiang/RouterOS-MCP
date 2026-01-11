"""Tests for RBAC models (Role, Permission, RolePermission) - Phase 5."""

from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.infra.db.models import (
    Base,
    Permission,
    Role,
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


class TestRoleModel:
    """Tests for Role model."""

    @pytest.mark.asyncio
    async def test_role_creation(self, db_session) -> None:
        """Test creating a Role instance."""
        role = Role(
            id="role-001",
            name="read_only",
            description="Read-only access to fundamental tier tools",
        )

        db_session.add(role)
        await db_session.commit()

        # Query back
        result = await db_session.execute(select(Role).where(Role.id == "role-001"))
        found = result.scalar_one()

        assert found.id == "role-001"
        assert found.name == "read_only"
        assert found.description == "Read-only access to fundamental tier tools"

    @pytest.mark.asyncio
    async def test_role_timestamps(self, db_session) -> None:
        """Test that timestamps are auto-generated."""
        role = Role(
            id="role-002",
            name="ops_rw",
            description="Read-write access to advanced tier tools",
        )

        db_session.add(role)
        await db_session.commit()

        result = await db_session.execute(select(Role).where(Role.id == "role-002"))
        found = result.scalar_one()

        assert found.created_at is not None
        assert found.updated_at is not None
        assert isinstance(found.created_at, datetime)
        assert isinstance(found.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_role_unique_name(self, db_session) -> None:
        """Test that role names must be unique."""
        role1 = Role(
            id="role-003",
            name="admin",
            description="Admin role",
        )
        role2 = Role(
            id="role-004",
            name="admin",  # Duplicate name
            description="Another admin role",
        )

        db_session.add(role1)
        await db_session.commit()

        db_session.add(role2)
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):  # Should raise integrity error
            await db_session.commit()


class TestPermissionModel:
    """Tests for Permission model."""

    @pytest.mark.asyncio
    async def test_permission_creation(self, db_session) -> None:
        """Test creating a Permission instance."""
        permission = Permission(
            id="perm-001",
            resource_type="device",
            resource_id="*",
            action="read",
            description="Read access to all devices",
        )

        db_session.add(permission)
        await db_session.commit()

        # Query back
        result = await db_session.execute(select(Permission).where(Permission.id == "perm-001"))
        found = result.scalar_one()

        assert found.id == "perm-001"
        assert found.resource_type == "device"
        assert found.resource_id == "*"
        assert found.action == "read"
        assert found.description == "Read access to all devices"

    @pytest.mark.asyncio
    async def test_permission_timestamps(self, db_session) -> None:
        """Test that timestamps are auto-generated."""
        permission = Permission(
            id="perm-002",
            resource_type="plan",
            resource_id="*",
            action="approve",
        )

        db_session.add(permission)
        await db_session.commit()

        result = await db_session.execute(select(Permission).where(Permission.id == "perm-002"))
        found = result.scalar_one()

        assert found.created_at is not None
        assert found.updated_at is not None
        assert isinstance(found.created_at, datetime)
        assert isinstance(found.updated_at, datetime)

    @pytest.mark.asyncio
    async def test_permission_optional_description(self, db_session) -> None:
        """Test that permission description is optional."""
        permission = Permission(
            id="perm-003",
            resource_type="tool",
            resource_id="dns/update-servers",
            action="execute",
        )

        db_session.add(permission)
        await db_session.commit()

        result = await db_session.execute(select(Permission).where(Permission.id == "perm-003"))
        found = result.scalar_one()

        assert found.description is None


class TestRolePermissionRelationship:
    """Tests for Role-Permission many-to-many relationship."""

    @pytest.mark.asyncio
    async def test_role_permission_association(self, db_session) -> None:
        """Test associating permissions with roles."""
        # Create a role
        role = Role(
            id="role-100",
            name="test_role",
            description="Test role for M2M relationship",
        )

        # Create permissions
        perm1 = Permission(
            id="perm-100",
            resource_type="device",
            resource_id="*",
            action="read",
        )
        perm2 = Permission(
            id="perm-101",
            resource_type="plan",
            resource_id="*",
            action="read",
        )

        # Associate permissions with role
        role.permissions.append(perm1)
        role.permissions.append(perm2)

        db_session.add(role)
        await db_session.commit()

        # Query back and verify relationship
        result = await db_session.execute(select(Role).where(Role.id == "role-100"))
        found_role = result.scalar_one()

        assert len(found_role.permissions) == 2
        permission_ids = {p.id for p in found_role.permissions}
        assert "perm-100" in permission_ids
        assert "perm-101" in permission_ids

    @pytest.mark.asyncio
    async def test_permission_roles_reverse_relationship(self, db_session) -> None:
        """Test reverse relationship from permission to roles."""
        # Create permissions
        permission = Permission(
            id="perm-200",
            resource_type="device",
            resource_id="dev-001",
            action="write",
        )

        # Create roles and associate with permission
        role1 = Role(
            id="role-200",
            name="role1",
            description="First role",
        )
        role2 = Role(
            id="role-201",
            name="role2",
            description="Second role",
        )

        permission.roles.append(role1)
        permission.roles.append(role2)

        db_session.add(permission)
        await db_session.commit()

        # Query back and verify reverse relationship
        result = await db_session.execute(select(Permission).where(Permission.id == "perm-200"))
        found_permission = result.scalar_one()

        assert len(found_permission.roles) == 2
        role_ids = {r.id for r in found_permission.roles}
        assert "role-200" in role_ids
        assert "role-201" in role_ids

    @pytest.mark.asyncio
    async def test_role_permission_lookup(self, db_session) -> None:
        """Test looking up permissions for a role (typical authorization query)."""
        # Create role with permissions
        role = Role(
            id="role-300",
            name="ops_user",
            description="Operations user",
        )

        permissions = [
            Permission(
                id=f"perm-30{i}",
                resource_type="device",
                resource_id="*",
                action=action,
            )
            for i, action in enumerate(["read", "write"])
        ]

        for perm in permissions:
            role.permissions.append(perm)

        db_session.add(role)
        await db_session.commit()

        # Query role and check permissions
        result = await db_session.execute(select(Role).where(Role.name == "ops_user"))
        found_role = result.scalar_one()

        # Verify we can check if role has specific permission
        actions = {p.action for p in found_role.permissions if p.resource_type == "device"}
        assert "read" in actions
        assert "write" in actions
        assert len(actions) == 2

    @pytest.mark.asyncio
    async def test_cascade_delete_role(self, db_session) -> None:
        """Test that deleting a role removes role_permission associations."""
        # Create role with permissions
        role = Role(
            id="role-400",
            name="temp_role",
            description="Temporary role",
        )
        permission = Permission(
            id="perm-400",
            resource_type="device",
            resource_id="*",
            action="read",
        )
        role.permissions.append(permission)

        db_session.add(role)
        db_session.add(permission)
        await db_session.commit()

        # Delete the role
        await db_session.delete(role)
        await db_session.commit()

        # Verify role is deleted
        result = await db_session.execute(select(Role).where(Role.id == "role-400"))
        assert result.scalar_one_or_none() is None

        # Verify permission still exists (refresh to get updated relationships)
        result = await db_session.execute(select(Permission).where(Permission.id == "perm-400"))
        found_permission = result.scalar_one()
        assert found_permission is not None

        # Refresh the permission to load updated relationships
        await db_session.refresh(found_permission)

        # Verify association is removed
        assert len(found_permission.roles) == 0

    @pytest.mark.asyncio
    async def test_cascade_delete_permission(self, db_session) -> None:
        """Test that deleting a permission removes role_permission associations."""
        # Create role with permission
        role = Role(
            id="role-500",
            name="stable_role",
            description="Stable role",
        )
        permission = Permission(
            id="perm-500",
            resource_type="device",
            resource_id="*",
            action="read",
        )
        role.permissions.append(permission)

        db_session.add(role)
        db_session.add(permission)
        await db_session.commit()

        # Delete the permission
        await db_session.delete(permission)
        await db_session.commit()

        # Verify permission is deleted
        result = await db_session.execute(select(Permission).where(Permission.id == "perm-500"))
        assert result.scalar_one_or_none() is None

        # Verify role still exists (refresh to get updated relationships)
        result = await db_session.execute(select(Role).where(Role.id == "role-500"))
        found_role = result.scalar_one()
        assert found_role is not None

        # Refresh the role to load updated relationships
        await db_session.refresh(found_role)

        # Verify association is removed
        assert len(found_role.permissions) == 0
