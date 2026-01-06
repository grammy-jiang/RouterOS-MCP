"""Add Phase 3 capability flags to devices table.

Revision ID: 28c6b758594a
Revises: 
Create Date: 2025-12-20 02:19:23.060910

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "28c6b758594a"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column(
        "devices",
        sa.Column(
            "allow_professional_workflows",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Allow professional tier workflows (Phase 3+)",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "allow_firewall_writes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Allow firewall filter/NAT rule writes (Phase 3)",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "allow_routing_writes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Allow static route and routing policy writes (Phase 3)",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "allow_wireless_writes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Allow wireless/RF configuration writes (Phase 3)",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "allow_dhcp_writes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Allow DHCP server configuration writes (Phase 3)",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "allow_bridge_writes",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
            comment="Allow bridge and VLAN configuration writes (Phase 3)",
        ),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("devices", "allow_bridge_writes")
    op.drop_column("devices", "allow_dhcp_writes")
    op.drop_column("devices", "allow_wireless_writes")
    op.drop_column("devices", "allow_routing_writes")
    op.drop_column("devices", "allow_firewall_writes")
    op.drop_column("devices", "allow_professional_workflows")
