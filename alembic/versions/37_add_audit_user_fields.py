"""Add user_id, approver_id, and approval_request_id to audit_events for Phase 5

Revision ID: 37
Revises: 36
Create Date: 2026-01-11 12:25:00.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "37"
down_revision: str | None = "36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema - add per-user fields to audit_events.
    
    Adds three new fields for Phase 5 compliance reporting:
    - user_id: User identifier who performed the action (typically same as user_sub)
    - approver_id: User identifier who approved the action (for approval workflows)
    - approval_request_id: Foreign key to approval_requests table
    """
    
    # Add user_id column (nullable for backward compatibility with existing audit events)
    op.add_column(
        "audit_events",
        sa.Column(
            "user_id",
            sa.String(length=255),
            nullable=True,
            comment="User identifier who performed the action (Phase 5)",
        ),
    )
    
    # Add approver_id column (nullable, only set for approved actions)
    op.add_column(
        "audit_events",
        sa.Column(
            "approver_id",
            sa.String(length=255),
            nullable=True,
            comment="User identifier who approved the action (Phase 5)",
        ),
    )
    
    # Add approval_request_id column with foreign key to approval_requests
    op.add_column(
        "audit_events",
        sa.Column(
            "approval_request_id",
            sa.String(length=64),
            nullable=True,
            comment="Associated approval request ID (Phase 5)",
        ),
    )
    
    # Add foreign key constraint for approval_request_id
    # Using SET NULL on delete to preserve audit history even if approval request is deleted
    op.create_foreign_key(
        "fk_audit_events_approval_request_id",
        "audit_events",
        "approval_requests",
        ["approval_request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    
    # Create index for user_id filtering (per-user audit queries)
    op.create_index("idx_audit_user_id", "audit_events", ["user_id"])
    
    # Create index for approver_id filtering (approval audit queries)
    op.create_index("idx_audit_approver_id", "audit_events", ["approver_id"])
    
    # Create index for approval_request_id filtering
    op.create_index("idx_audit_approval_request_id", "audit_events", ["approval_request_id"])


def downgrade() -> None:
    """Downgrade database schema - remove per-user fields from audit_events."""
    
    # Drop indexes
    op.drop_index("idx_audit_approval_request_id", "audit_events")
    op.drop_index("idx_audit_approver_id", "audit_events")
    op.drop_index("idx_audit_user_id", "audit_events")
    
    # Drop foreign key constraint
    op.drop_constraint("fk_audit_events_approval_request_id", "audit_events", type_="foreignkey")
    
    # Drop columns
    op.drop_column("audit_events", "approval_request_id")
    op.drop_column("audit_events", "approver_id")
    op.drop_column("audit_events", "user_id")
