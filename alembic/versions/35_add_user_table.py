"""Add User table for Phase 5 per-user device scopes

Revision ID: 35
Revises: 34
Create Date: 2026-01-11 08:40:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "35"
down_revision: str | None = "34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema - add users table."""

    # Create users table
    op.create_table(
        "users",
        sa.Column(
            "sub",
            sa.String(length=255),
            nullable=False,
            comment="OIDC subject (unique user identifier)",
        ),
        sa.Column(
            "email",
            sa.String(length=255),
            nullable=True,
            comment="User email address",
        ),
        sa.Column(
            "display_name",
            sa.String(length=255),
            nullable=True,
            comment="User display name",
        ),
        sa.Column(
            "role_name",
            sa.String(length=64),
            nullable=False,
            comment="Assigned role name",
        ),
        sa.Column(
            "device_scopes",
            sa.JSON(),
            nullable=False,
            server_default="[]",
            comment="Allowed device IDs (empty = full access)",
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Whether user account is active",
        ),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Last successful login timestamp",
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
        sa.PrimaryKeyConstraint("sub"),
        sa.ForeignKeyConstraint(["role_name"], ["roles.name"], ondelete="RESTRICT"),
    )

    # Create indexes
    op.create_index("idx_user_email", "users", ["email"])
    op.create_index("idx_user_role", "users", ["role_name"])
    op.create_index("idx_user_active", "users", ["is_active"])


def downgrade() -> None:
    """Downgrade database schema - remove users table."""

    # Drop indexes
    op.drop_index("idx_user_active", "users")
    op.drop_index("idx_user_role", "users")
    op.drop_index("idx_user_email", "users")

    # Drop table
    op.drop_table("users")
