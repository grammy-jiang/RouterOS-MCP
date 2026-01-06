"""Add multi-device plan fields

Revision ID: 31
Revises: 30
Create Date: 2026-01-06 14:10:00.000000

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "31"
down_revision: str | None = "30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add batch_size field
    op.add_column(
        "plans",
        sa.Column(
            "batch_size",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
            comment="Number of devices to process per batch (Phase 4)",
        ),
    )

    # Add pause_seconds_between_batches field
    op.add_column(
        "plans",
        sa.Column(
            "pause_seconds_between_batches",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("60"),
            comment="Seconds to wait between batches (Phase 4)",
        ),
    )

    # Add rollback_on_failure field
    op.add_column(
        "plans",
        sa.Column(
            "rollback_on_failure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
            comment="Whether to rollback changes on failure (Phase 4)",
        ),
    )

    # Add device_statuses field (JSON for per-device status tracking)
    op.add_column(
        "plans",
        sa.Column(
            "device_statuses",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
            comment="Per-device execution status tracking (Phase 4)",
        ),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("plans", "device_statuses")
    op.drop_column("plans", "rollback_on_failure")
    op.drop_column("plans", "pause_seconds_between_batches")
    op.drop_column("plans", "batch_size")
