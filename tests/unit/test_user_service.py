"""Tests for UserService (Phase 5 RBAC)."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.domain.services.user import UserService
from routeros_mcp.infra.db.models import Role as RoleORM
from routeros_mcp.infra.db.models import User as UserORM
from routeros_mcp.mcp.errors import ValidationError


class TestUserServiceImport:
    """Test that UserService can be imported."""

    def test_user_service_import(self):
        """Test that UserService can be imported."""
        assert UserService is not None


class TestUserServiceInitialization:
    """Test UserService initialization."""

    def test_user_service_can_be_instantiated(self):
        """Test that UserService can be instantiated with a session."""
        session = AsyncMock(spec=AsyncSession)
        service = UserService(session)
        assert service is not None
        assert service.session == session


class TestUserServiceListRoles:
    """Test listing roles."""

    @pytest.mark.asyncio
    async def test_list_roles_returns_empty_list(self):
        """Test listing roles when none exist."""
        session = AsyncMock(spec=AsyncSession)
        service = UserService(session)

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        roles = await service.list_roles()
        assert roles == []

    @pytest.mark.asyncio
    async def test_list_roles_returns_roles(self):
        """Test listing roles when they exist."""
        session = AsyncMock(spec=AsyncSession)
        service = UserService(session)

        # Mock roles
        mock_role1 = RoleORM(id="role-1", name="admin", description="Administrator")
        mock_role2 = RoleORM(id="role-2", name="operator", description="Operator")

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_role1, mock_role2]
        session.execute.return_value = mock_result

        roles = await service.list_roles()
        assert len(roles) == 2
        assert roles[0]["name"] == "admin"
        assert roles[1]["name"] == "operator"


class TestUserServiceListUsers:
    """Test listing users."""

    @pytest.mark.asyncio
    async def test_list_users_returns_empty_list(self):
        """Test listing users when none exist."""
        session = AsyncMock(spec=AsyncSession)
        service = UserService(session)

        # Mock empty result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = mock_result

        users = await service.list_users()
        assert users == []


class TestUserServiceValidation:
    """Test validation logic in UserService."""

    @pytest.mark.asyncio
    async def test_create_user_with_invalid_role_raises_error(self):
        """Test creating a user with an invalid role raises ValidationError."""
        session = AsyncMock(spec=AsyncSession)
        service = UserService(session)

        # Mock role not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValidationError, match="Role 'nonexistent' does not exist"):
            await service.create_user(
                sub="test|123",
                email="test@example.com",
                role_name="nonexistent",
            )

    @pytest.mark.asyncio
    async def test_update_nonexistent_user_raises_error(self):
        """Test updating a nonexistent user raises ValidationError."""
        session = AsyncMock(spec=AsyncSession)
        service = UserService(session)

        # Mock user not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValidationError, match="User with sub 'test\\|123' not found"):
            await service.update_user(
                sub="test|123",
                email="new@example.com",
            )

    @pytest.mark.asyncio
    async def test_delete_nonexistent_user_raises_error(self):
        """Test deleting a nonexistent user raises ValidationError."""
        session = AsyncMock(spec=AsyncSession)
        service = UserService(session)

        # Mock user not found
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(ValidationError, match="User with sub 'test\\|123' not found"):
            await service.delete_user("test|123")
