"""Add Phase 5 RBAC models (Role, Permission, RolePermission)

Revision ID: 34
Revises: 33
Create Date: 2026-01-11 04:20:00.000000

"""

import uuid
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "34"
down_revision: str | None = "33"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema - add RBAC tables and seed default roles."""

    # Create roles table
    op.create_table(
        "roles",
        sa.Column("id", sa.String(length=64), nullable=False, comment="Unique role identifier"),
        sa.Column(
            "name",
            sa.String(length=64),
            nullable=False,
            comment="Role name (read_only, ops_rw, admin, approver)",
        ),
        sa.Column(
            "description", sa.Text(), nullable=False, comment="Human-readable role description"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Record creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Record last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("idx_role_name", "roles", ["name"])

    # Create permissions table
    op.create_table(
        "permissions",
        sa.Column(
            "id", sa.String(length=64), nullable=False, comment="Unique permission identifier"
        ),
        sa.Column(
            "resource_type",
            sa.String(length=64),
            nullable=False,
            comment="Resource type (device, plan, tool, etc.)",
        ),
        sa.Column(
            "resource_id",
            sa.String(length=255),
            nullable=False,
            comment="Resource ID or wildcard (*)",
        ),
        sa.Column(
            "action",
            sa.String(length=64),
            nullable=False,
            comment="Allowed action (read, write, execute, approve, etc.)",
        ),
        sa.Column(
            "description", sa.Text(), nullable=True, comment="Optional permission description"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Record creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Record last update timestamp",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_permission_resource_type", "permissions", ["resource_type"])
    op.create_index(
        "idx_permission_resource_action", "permissions", ["resource_type", "resource_id", "action"]
    )

    # Create role_permissions association table
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.String(length=64), nullable=False, comment="Role ID"),
        sa.Column("permission_id", sa.String(length=64), nullable=False, comment="Permission ID"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Record creation timestamp",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
            comment="Record last update timestamp",
        ),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_index("idx_role_permission_role", "role_permissions", ["role_id"])
    op.create_index("idx_role_permission_permission", "role_permissions", ["permission_id"])

    # Seed default roles
    roles_data = [
        {
            "id": f"role-{uuid.uuid4().hex[:12]}",
            "name": "read_only",
            "description": "Read-only access to fundamental tier tools. Cannot modify device configurations.",
        },
        {
            "id": f"role-{uuid.uuid4().hex[:12]}",
            "name": "ops_rw",
            "description": "Read-write access to advanced tier tools. Can make low-risk configuration changes.",
        },
        {
            "id": f"role-{uuid.uuid4().hex[:12]}",
            "name": "admin",
            "description": "Full access to all tools and administrative functions. Can manage devices, users, and system configuration.",
        },
        {
            "id": f"role-{uuid.uuid4().hex[:12]}",
            "name": "approver",
            "description": "Can approve professional tier plans. Typically combined with other roles for plan approval workflows.",
        },
    ]

    # Insert roles using bulk insert
    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("id", sa.String),
            sa.column("name", sa.String),
            sa.column("description", sa.Text),
        ),
        roles_data,
    )


def downgrade() -> None:
    """Downgrade database schema - remove RBAC tables."""

    # Drop tables in reverse order (association table first)
    op.drop_index("idx_role_permission_permission", "role_permissions")
    op.drop_index("idx_role_permission_role", "role_permissions")
    op.drop_table("role_permissions")

    op.drop_index("idx_permission_resource_action", "permissions")
    op.drop_index("idx_permission_resource_type", "permissions")
    op.drop_table("permissions")

    op.drop_index("idx_role_name", "roles")
    op.drop_table("roles")
