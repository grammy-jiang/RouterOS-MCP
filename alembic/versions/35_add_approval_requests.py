"""Add approval_requests table for Phase 5 approval workflow

Revision ID: 35
Revises: 34
Create Date: 2026-01-11 09:55:00.000000

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
    """Upgrade database schema - add approval_requests table."""

    op.create_table(
        "approval_requests",
        sa.Column(
            "id",
            sa.String(length=64),
            nullable=False,
            comment="Unique approval request identifier",
        ),
        sa.Column(
            "plan_id",
            sa.String(length=64),
            nullable=False,
            comment="Plan requiring approval",
        ),
        sa.Column(
            "requested_by",
            sa.String(length=255),
            nullable=False,
            comment="User sub who requested approval",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="Request creation timestamp",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="pending",
            comment="Approval status: pending/approved/rejected",
        ),
        sa.Column(
            "approved_by",
            sa.String(length=255),
            nullable=True,
            comment="User sub who approved request",
        ),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Approval timestamp",
        ),
        sa.Column(
            "rejected_by",
            sa.String(length=255),
            nullable=True,
            comment="User sub who rejected request",
        ),
        sa.Column(
            "rejected_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Rejection timestamp",
        ),
        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
            comment="Notes explaining approval/rejection decision",
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
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for efficient querying
    op.create_index("idx_approval_request_plan_id", "approval_requests", ["plan_id"])
    op.create_index("idx_approval_request_status", "approval_requests", ["status"])
    op.create_index("idx_approval_request_requested_by", "approval_requests", ["requested_by"])
    op.create_index("idx_approval_request_requested_at", "approval_requests", ["requested_at"])


def downgrade() -> None:
    """Downgrade database schema - remove approval_requests table."""

    # Drop indexes
    op.drop_index("idx_approval_request_requested_at", "approval_requests")
    op.drop_index("idx_approval_request_requested_by", "approval_requests")
    op.drop_index("idx_approval_request_status", "approval_requests")
    op.drop_index("idx_approval_request_plan_id", "approval_requests")

    # Drop table
    op.drop_table("approval_requests")
