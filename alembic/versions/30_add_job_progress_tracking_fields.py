"""Add job progress tracking fields

Revision ID: 30
Revises: 29
Create Date: 2026-01-06 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "30"
down_revision: Union[str, None] = "29"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add progress_percent field with constraint
    op.add_column(
        "jobs",
        sa.Column(
            "progress_percent",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="Job progress percentage (0-100)",
        ),
    )
    
    # Add current_device_id field with foreign key
    op.add_column(
        "jobs",
        sa.Column(
            "current_device_id",
            sa.String(64),
            nullable=True,
            comment="Current device being processed (Phase 4)",
        ),
    )
    
    # Add foreign key constraint for current_device_id
    op.create_foreign_key(
        "fk_job_current_device",
        "jobs",
        "devices",
        ["current_device_id"],
        ["id"],
        ondelete="SET NULL",
    )
    
    # Add index for current_device_id
    op.create_index(
        "ix_jobs_current_device_id",
        "jobs",
        ["current_device_id"],
    )
    
    # Handle result_summary type change (Text → JSON)
    # 
    # Important: This migration does NOT alter the result_summary column type in the database.
    # Rationale:
    # - In SQLite: JSON type is stored as TEXT internally, so no schema change is needed
    # - In PostgreSQL: Would require ALTER COLUMN with USING clause to convert data
    # - SQLAlchemy ORM will handle JSON encoding/decoding regardless of DB column type
    # - Existing NULL values and any text content remain compatible
    # - New writes will use JSON serialization automatically
    #
    # For fresh databases: result_summary will be created as JSON type directly
    # For existing databases: Column remains TEXT but functions as JSON via ORM
    # 
    # If explicit PostgreSQL migration is needed later, use:
    #   op.alter_column('jobs', 'result_summary',
    #                   existing_type=sa.Text(),
    #                   type_=sa.JSON(),
    #                   postgresql_using='result_summary::json')
    
    # Add check constraint for progress_percent (0-100)
    op.create_check_constraint(
        "chk_job_progress_percent",
        "jobs",
        "progress_percent >= 0 AND progress_percent <= 100",
    )


def downgrade() -> None:
    """Downgrade database schema."""
    # Drop check constraint
    op.drop_constraint("chk_job_progress_percent", "jobs", type_="check")
    
    # Drop index
    op.drop_index("ix_jobs_current_device_id", table_name="jobs")
    
    # Drop foreign key
    op.drop_constraint("fk_job_current_device", "jobs", type_="foreignkey")
    
    # Drop columns
    op.drop_column("jobs", "current_device_id")
    op.drop_column("jobs", "progress_percent")
    
    # Note: result_summary type change doesn't need rollback as JSON/TEXT are compatible in SQLite
