"""Add SSH key authentication fields to credentials table

Revision ID: 33
Revises: 32
Create Date: 2026-01-08 21:00:00.000000

This migration adds support for SSH key-based authentication by adding
private_key and public_key_fingerprint fields to the credentials table.

Phase 4 Enhancement:
- Adds private_key field (encrypted Text) for storing SSH private keys
- Adds public_key_fingerprint field (String) for key verification
- Supports credential_type 'routeros_ssh_key' in addition to 'rest' and 'ssh'
- Private keys are encrypted using the same Fernet key as passwords
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "33"
down_revision: Union[str, None] = "de268cf36ca1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # Add private_key column for encrypted SSH private keys
    op.add_column(
        "credentials",
        sa.Column(
            "private_key",
            sa.Text(),
            nullable=True,
            comment="Encrypted SSH private key (Phase 4)",
        ),
    )
    
    # Add public_key_fingerprint column for SSH key verification
    op.add_column(
        "credentials",
        sa.Column(
            "public_key_fingerprint",
            sa.String(128),
            nullable=True,
            comment="SSH public key fingerprint for verification (Phase 4)",
        ),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("credentials", "public_key_fingerprint")
    op.drop_column("credentials", "private_key")
