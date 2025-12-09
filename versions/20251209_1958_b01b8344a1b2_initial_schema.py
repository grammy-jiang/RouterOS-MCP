"""Initial schema

Revision ID: 001
Revises:
Create Date: 2024-12-09 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema with all tables and indexes."""
    # Devices table
    op.create_table(
        "devices",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("management_address", sa.String(255), nullable=False),
        sa.Column("environment", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("allow_advanced_writes", sa.Boolean(), nullable=False),
        sa.Column("allow_professional_workflows", sa.Boolean(), nullable=False),
        sa.Column("routeros_version", sa.String(64)),
        sa.Column("system_identity", sa.String(255)),
        sa.Column("hardware_model", sa.String(128)),
        sa.Column("serial_number", sa.String(128)),
        sa.Column("software_id", sa.String(128)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_device_environment_status", "devices", ["environment", "status"])
    op.create_index("idx_device_name", "devices", ["name"])

    # Credentials table
    op.create_table(
        "credentials",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("encrypted_secret", sa.Text(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_credential_device_kind", "credentials", ["device_id", "kind"])

    # Health checks table
    op.create_table(
        "health_checks",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("cpu_usage_percent", sa.Float()),
        sa.Column("memory_used_bytes", sa.BigInteger()),
        sa.Column("memory_total_bytes", sa.BigInteger()),
        sa.Column("temperature_celsius", sa.Float()),
        sa.Column("uptime_seconds", sa.BigInteger()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_healthcheck_device_timestamp", "health_checks", ["device_id", "timestamp"])
    op.create_index("idx_healthcheck_status", "health_checks", ["status"])

    # Snapshots table
    op.create_table(
        "snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_snapshot_device_timestamp", "snapshots", ["device_id", "timestamp"])
    op.create_index("idx_snapshot_kind", "snapshots", ["kind"])

    # Plans table
    op.create_table(
        "plans",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("device_ids", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("approved_by", sa.String(255)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_plan_created_by", "plans", ["created_by"])
    op.create_index("idx_plan_status", "plans", ["status"])

    # Jobs table
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "plan_id",
            sa.String(64),
            sa.ForeignKey("plans.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("job_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("device_ids", sa.JSON(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("result_summary", sa.Text()),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_job_status_next_run", "jobs", ["status", "next_run_at"])
    op.create_index("idx_job_type", "jobs", ["job_type"])

    # Audit events table
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_sub", sa.String(255), nullable=False),
        sa.Column("user_email", sa.String(255)),
        sa.Column("user_role", sa.String(32), nullable=False),
        sa.Column(
            "device_id",
            sa.String(64),
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("environment", sa.String(32)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("tool_name", sa.String(128), nullable=False),
        sa.Column("tool_tier", sa.String(32), nullable=False),
        sa.Column("plan_id", sa.String(64)),
        sa.Column("job_id", sa.String(64)),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_audit_timestamp", "audit_events", ["timestamp"])
    op.create_index("idx_audit_user_action", "audit_events", ["user_sub", "action"])
    op.create_index("idx_audit_tool", "audit_events", ["tool_name"])
    op.create_index("idx_audit_result", "audit_events", ["result"])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("audit_events")
    op.drop_table("jobs")
    op.drop_table("plans")
    op.drop_table("snapshots")
    op.drop_table("health_checks")
    op.drop_table("credentials")
    op.drop_table("devices")
