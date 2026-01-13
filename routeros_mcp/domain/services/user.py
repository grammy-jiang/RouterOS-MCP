"""User service for user management and RBAC (Phase 5).

Provides business logic for user CRUD operations, role assignment,
and device scope management.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.infra.db.models import Role as RoleORM
from routeros_mcp.infra.db.models import User as UserORM
from routeros_mcp.mcp.errors import ValidationError

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management and RBAC.

    Responsibilities:
    - User CRUD operations
    - Role assignment and validation
    - Device scope management
    - User listing with filters

    Example:
        async with get_session() as session:
            service = UserService(session)

            # Create user
            user = await service.create_user(
                sub="auth0|123456",
                email="user@example.com",
                display_name="John Doe",
                role_name="ops_rw"
            )

            # Update device scopes
            await service.update_device_scopes(
                "auth0|123456",
                ["dev-001", "dev-002"]
            )
    """

    def __init__(self, session: AsyncSession):
        """Initialize UserService.

        Args:
            session: SQLAlchemy async session
        """
        self.session = session

    async def list_users(
        self,
        is_active: bool | None = None,
        role_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List all users with optional filters.

        Args:
            is_active: Filter by active status
            role_name: Filter by role name

        Returns:
            List of user dictionaries with role information
        """
        query = select(UserORM)

        if is_active is not None:
            query = query.where(UserORM.is_active == is_active)

        if role_name:
            query = query.where(UserORM.role_name == role_name)

        query = query.order_by(UserORM.email)

        result = await self.session.execute(query)
        users = result.scalars().all()

        return [
            {
                "sub": user.sub,
                "email": user.email,
                "display_name": user.display_name,
                "role_name": user.role_name,
                "role_description": user.role.description if user.role else None,
                "device_scopes": user.device_scopes,
                "is_active": user.is_active,
                "last_login_at": user.last_login_at,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
            }
            for user in users
        ]

    async def get_user(self, sub: str) -> dict[str, Any] | None:
        """Get user by subject (sub).

        Args:
            sub: OIDC subject identifier

        Returns:
            User dictionary or None if not found
        """
        result = await self.session.execute(
            select(UserORM).where(UserORM.sub == sub)
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        return {
            "sub": user.sub,
            "email": user.email,
            "display_name": user.display_name,
            "role_name": user.role_name,
            "role_description": user.role.description if user.role else None,
            "device_scopes": user.device_scopes,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    async def create_user(
        self,
        sub: str,
        role_name: str,
        email: str | None = None,
        display_name: str | None = None,
        device_scopes: list[str] | None = None,
        is_active: bool = True,
    ) -> dict[str, Any]:
        """Create a new user.

        Args:
            sub: OIDC subject identifier
            role_name: Role to assign
            email: User email address
            display_name: User display name
            device_scopes: List of device IDs user can access (empty = full access)
            is_active: Whether user is active

        Returns:
            Created user dictionary

        Raises:
            ValidationError: If role doesn't exist or user already exists
        """
        # Check if role exists
        role_result = await self.session.execute(
            select(RoleORM).where(RoleORM.name == role_name)
        )
        role = role_result.scalar_one_or_none()

        if not role:
            raise ValidationError(f"Role '{role_name}' does not exist")

        # Check if user already exists
        existing = await self.session.execute(
            select(UserORM).where(UserORM.sub == sub)
        )
        if existing.scalar_one_or_none():
            raise ValidationError(f"User with sub '{sub}' already exists")

        # Create user
        user = UserORM(
            sub=sub,
            email=email,
            display_name=display_name,
            role_name=role_name,
            device_scopes=device_scopes or [],
            is_active=is_active,
        )

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        logger.info(f"Created user: sub={sub}, role={role_name}")

        return {
            "sub": user.sub,
            "email": user.email,
            "display_name": user.display_name,
            "role_name": user.role_name,
            "role_description": user.role.description if user.role else None,
            "device_scopes": user.device_scopes,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    async def update_user(
        self,
        sub: str,
        email: str | None = None,
        display_name: str | None = None,
        role_name: str | None = None,
        device_scopes: list[str] | None = None,
        is_active: bool | None = None,
    ) -> dict[str, Any]:
        """Update user information.

        Args:
            sub: OIDC subject identifier
            email: New email address (if provided)
            display_name: New display name (if provided)
            role_name: New role name (if provided)
            device_scopes: New device scopes (if provided)
            is_active: New active status (if provided)

        Returns:
            Updated user dictionary

        Raises:
            ValidationError: If user or role doesn't exist
        """
        # Get user
        result = await self.session.execute(
            select(UserORM).where(UserORM.sub == sub)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ValidationError(f"User with sub '{sub}' not found")

        # Validate role if provided
        if role_name is not None:
            role_result = await self.session.execute(
                select(RoleORM).where(RoleORM.name == role_name)
            )
            role = role_result.scalar_one_or_none()

            if not role:
                raise ValidationError(f"Role '{role_name}' does not exist")

            user.role_name = role_name

        # Update fields
        if email is not None:
            user.email = email

        if display_name is not None:
            user.display_name = display_name

        if device_scopes is not None:
            user.device_scopes = device_scopes

        if is_active is not None:
            user.is_active = is_active

        await self.session.commit()
        await self.session.refresh(user)

        logger.info(f"Updated user: sub={sub}")

        return {
            "sub": user.sub,
            "email": user.email,
            "display_name": user.display_name,
            "role_name": user.role_name,
            "role_description": user.role.description if user.role else None,
            "device_scopes": user.device_scopes,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    async def update_device_scopes(
        self,
        sub: str,
        device_scopes: list[str],
    ) -> dict[str, Any]:
        """Update user's device scopes (bulk operation).

        Args:
            sub: OIDC subject identifier
            device_scopes: List of device IDs user can access (empty = full access)

        Returns:
            Updated user dictionary

        Raises:
            ValidationError: If user doesn't exist
        """
        return await self.update_user(sub=sub, device_scopes=device_scopes)

    async def delete_user(self, sub: str) -> None:
        """Delete a user.

        Args:
            sub: OIDC subject identifier

        Raises:
            ValidationError: If user doesn't exist
        """
        result = await self.session.execute(
            select(UserORM).where(UserORM.sub == sub)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ValidationError(f"User with sub '{sub}' not found")

        await self.session.delete(user)
        await self.session.commit()

        logger.info(f"Deleted user: sub={sub}")

    async def list_roles(self) -> list[dict[str, Any]]:
        """List all available roles.

        Returns:
            List of role dictionaries
        """
        result = await self.session.execute(select(RoleORM).order_by(RoleORM.name))
        roles = result.scalars().all()

        return [
            {
                "id": role.id,
                "name": role.name,
                "description": role.description,
            }
            for role in roles
        ]
