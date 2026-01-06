"""Add Phase 4 bandwidth test capability flag to devices table.

Revision ID: 29
Revises: 28c6b758594a
Create Date: 2026-01-06 03:36:25.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "29"
down_revision: Union[str, None] = "28c6b758594a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column(
        "devices",
        sa.Column(
            "allow_bandwidth_test",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Allow device to be target of bandwidth tests (Phase 4)",
        ),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("devices", "allow_bandwidth_test")
