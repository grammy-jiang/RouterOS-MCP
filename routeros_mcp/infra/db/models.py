"""SQLAlchemy ORM models for RouterOS MCP Service.

This module defines the database schema using SQLAlchemy 2.x ORM models.
All models support both SQLite (development) and PostgreSQL (production).

Design Principles:
- Domain models are kept separate (no SQLAlchemy in routeros_mcp/domain/)
- All timestamps use timezone-aware datetime
- JSON fields for flexible metadata storage
- Proper indexes for query performance
- Cascade deletes where appropriate

See docs/18-database-schema-and-orm-specification.md for complete schema details.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models.

    Provides:
    - Async attribute loading via AsyncAttrs
    - Common timestamp fields (created_at, updated_at)
    - Utility methods for dict conversion and repr
    """

    # Common timestamp columns - automatically managed
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Record last update timestamp",
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dictionary representation of model with all column values
        """
        return {column.name: getattr(self, column.name) for column in self.__table__.columns}

    def __repr__(self) -> str:
        """String representation of model."""
        class_name = self.__class__.__name__
        pk_value = getattr(self, "id", None)
        return f"<{class_name}(id={pk_value})>"


class Device(Base):
    """RouterOS device entity.

    Represents a managed MikroTik RouterOS device with its
    configuration, capabilities, and current status.

    Relationships:
        credentials: Device credentials (1:N)
        health_checks: Health check history (1:N)
        snapshots: Configuration snapshots (1:N)
        audit_events: Audit trail (1:N)
    """

    __tablename__ = "devices"

    # Primary key
    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Unique device identifier"
    )

    # Basic information
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True, comment="Human-friendly device name"
    )

    management_ip: Mapped[str] = mapped_column(
        String(45), nullable=False, comment="Management IP address (IPv4 or IPv6)"
    )

    management_port: Mapped[int] = mapped_column(
        Integer, nullable=False, default=443, comment="Management port (1-65535)"
    )

    environment: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="Environment: lab/staging/prod"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="healthy",
        comment="Current status: healthy/degraded/unreachable",
    )

    # Tags stored as JSON
    tags: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, comment="Device tags (key-value pairs)"
    )

    # Capability flags (Phase 2 and Phase 3)
    allow_advanced_writes: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow advanced tier write operations (Phase 2)",
    )

    allow_professional_workflows: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow professional tier workflows (Phase 3+)",
    )

    # Phase 3 topic-specific capability flags
    allow_firewall_writes: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow firewall filter/NAT rule writes (Phase 3)",
    )

    allow_routing_writes: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow static route and routing policy writes (Phase 3)",
    )

    allow_wireless_writes: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow wireless/RF configuration writes (Phase 3)",
    )

    allow_dhcp_writes: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow DHCP server configuration writes (Phase 3)",
    )

    allow_bridge_writes: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow bridge and VLAN configuration writes (Phase 3)",
    )

    # Phase 4 diagnostics capability flags
    allow_bandwidth_test: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow device to be target of bandwidth tests (Phase 4)",
    )

    # Phase 4 adaptive polling fields
    critical: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Critical device (30s base polling) vs non-critical (60s base polling) - Phase 4",
    )

    health_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="healthy",
        comment="Current health status: healthy/degraded/unreachable - Phase 4",
    )

    consecutive_healthy_checks: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Count of consecutive healthy checks for interval adjustment - Phase 4",
    )

    polling_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=60,
        comment="Current adaptive polling interval in seconds - Phase 4",
    )

    last_backoff_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last exponential backoff timestamp for unreachable devices - Phase 4",
    )

    # RouterOS metadata
    routeros_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, comment="RouterOS version string"
    )

    system_identity: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="RouterOS system identity"
    )

    hardware_model: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="Hardware model"
    )

    serial_number: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="Device serial number"
    )

    software_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="Software ID"
    )

    # Timestamps
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last successful contact timestamp"
    )

    # Relationships
    credentials: Mapped[list["Credential"]] = relationship(
        "Credential",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    health_checks: Mapped[list["HealthCheck"]] = relationship(
        "HealthCheck",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="noload",  # Don't load by default
    )

    snapshots: Mapped[list["Snapshot"]] = relationship(
        "Snapshot",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    # Phase 4: Jobs currently processing this device
    jobs_as_current: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="current_device",
        foreign_keys="Job.current_device_id",
        lazy="noload",
    )

    # Indexes
    __table_args__ = (
        Index("idx_device_environment_status", "environment", "status"),
        Index("idx_device_name", "name"),
    )


class Credential(Base):
    """Encrypted device credentials.

    Stores RouterOS access credentials in encrypted form.
    Credentials are never logged or exposed via APIs.

    Relationships:
        device: Parent device (N:1)
    """

    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    credential_type: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="Credential type: rest/ssh/routeros_ssh_key"
    )

    username: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Username (stored in plaintext)"
    )

    encrypted_secret: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Encrypted password/key"
    )

    # Phase 4: SSH key authentication fields
    private_key: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Encrypted SSH private key (Phase 4)"
    )

    public_key_fingerprint: Mapped[str | None] = mapped_column(
        String(128), nullable=True, comment="SSH public key fingerprint for verification (Phase 4)"
    )

    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, comment="Whether credential is active"
    )

    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Last rotation timestamp"
    )

    # Relationship
    device: Mapped["Device"] = relationship("Device", back_populates="credentials")

    __table_args__ = (
        Index("idx_credential_device_credential_type", "device_id", "credential_type"),
    )


class HealthCheck(Base):
    """Device health check result.

    Records periodic health check results including
    system metrics and overall health status.

    Relationships:
        device: Parent device (N:1)
    """

    __tablename__ = "health_checks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Health check timestamp",
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="Status: healthy/warning/critical"
    )

    # Metrics
    cpu_usage_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    memory_used_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    memory_total_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    temperature_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)

    uptime_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if check failed"
    )

    # Relationship
    device: Mapped["Device"] = relationship("Device", back_populates="health_checks")

    __table_args__ = (
        Index("idx_healthcheck_device_timestamp", "device_id", "timestamp"),
        Index("idx_healthcheck_status", "status"),
    )


class Snapshot(Base):
    """Configuration snapshot.

    Stores point-in-time device configuration for
    backup, comparison, and rollback purposes.

    Relationships:
        device: Parent device (N:1)
    """

    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    kind: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Snapshot type: config/dns_ntp/metrics/etc",
    )

    # Snapshot data (compressed)
    data: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, comment="Compressed snapshot data"
    )

    # Metadata (renamed to avoid conflict with SQLAlchemy Base.metadata)
    meta: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Snapshot metadata (size, checksum, etc)",
    )

    # Relationship
    device: Mapped["Device"] = relationship("Device", back_populates="snapshots")

    __table_args__ = (
        Index("idx_snapshot_device_timestamp", "device_id", "timestamp"),
        Index("idx_snapshot_kind", "kind"),
    )


class Plan(Base):
    """Configuration change plan.

    Represents an immutable plan for multi-device
    configuration changes requiring approval.

    Relationships:
        jobs: Execution jobs (1:N)
    """

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    created_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="User sub who created plan",
    )

    tool_name: Mapped[str] = mapped_column(
        String(128), nullable=False, comment="Tool that generated plan"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        index=True,
        comment="Status: draft/approved/applied/cancelled",
    )

    device_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, comment="List of target device IDs"
    )

    summary: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Human-readable plan summary"
    )

    changes: Mapped[dict] = mapped_column(
        JSON, nullable=False, comment="Detailed change specifications"
    )

    # Approval
    approved_by: Mapped[str | None] = mapped_column(
        String(255), nullable=True, comment="User sub who approved plan"
    )

    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="Approval timestamp"
    )

    # Phase 4: Multi-device execution configuration
    batch_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
        server_default=text("5"),
        comment="Number of devices to process per batch (Phase 4)",
    )

    pause_seconds_between_batches: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=60,
        server_default=text("60"),
        comment="Seconds to wait between batches (Phase 4)",
    )

    rollback_on_failure: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
        comment="Whether to rollback changes on failure (Phase 4)",
    )

    device_statuses: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        server_default=text("'{}'"),
        comment="Per-device execution status tracking (Phase 4)",
    )

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(
        "Job", back_populates="plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_plan_created_by", "created_by"),
        Index("idx_plan_status", "status"),
        CheckConstraint(
            "batch_size >= 1 AND batch_size <= 50",
            name="ck_plans_batch_size_range",
        ),
        CheckConstraint(
            "pause_seconds_between_batches >= 0",
            name="ck_plans_pause_seconds_non_negative",
        ),
    )


class Job(Base):
    """Executable job.

    Represents a unit of work, often tied to a plan,
    that can be executed, retried, and monitored.

    Relationships:
        plan: Parent plan (N:1, optional)
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    plan_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    job_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Job type: APPLY_PLAN/HEALTH_CHECK/etc",
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
        comment="Status: pending/running/success/failed/cancelled",
    )

    device_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list, comment="Target device IDs"
    )

    # Retry configuration
    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="Number of attempts made"
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, comment="Maximum retry attempts"
    )

    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Scheduled execution time",
    )

    # Progress tracking (Phase 4)
    progress_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
        comment="Job progress percentage (0-100)",
    )

    current_device_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Current device being processed (Phase 4)",
    )

    # Cancellation support (Phase 4)
    cancellation_requested: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Whether job cancellation has been requested",
    )

    # Results
    result_summary: Mapped[dict | None] = mapped_column(
        JSON, nullable=True, comment="Per-device job results (Phase 4)"
    )

    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if failed"
    )

    # Relationships
    plan: Mapped[Optional["Plan"]] = relationship("Plan", back_populates="jobs")

    # Phase 4: Relationship to current device being processed
    current_device: Mapped[Optional["Device"]] = relationship(
        "Device",
        back_populates="jobs_as_current",
        foreign_keys=[current_device_id],
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_job_status_next_run", "status", "next_run_at"),
        Index("idx_job_type", "job_type"),
        CheckConstraint(
            "progress_percent >= 0 AND progress_percent <= 100", name="chk_job_progress_percent"
        ),
    )


class AuditEvent(Base):
    """Audit event log.

    Immutable record of security-relevant events
    including all writes and sensitive reads.

    Relationships:
        device: Related device (N:1, optional)
    """

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Event timestamp",
    )

    # User information (Phase 4)
    user_sub: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="User subject from OIDC token",
    )

    user_email: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="User email")

    user_role: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="User role at time of action"
    )

    # Device context
    device_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    environment: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True, comment="Device environment"
    )

    # Action details
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Action type: WRITE/READ_SENSITIVE/AUTHZ_DENIED",
    )

    tool_name: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True, comment="MCP tool name"
    )

    tool_tier: Mapped[str] = mapped_column(
        String(32), nullable=False, comment="Tool tier: fundamental/advanced/professional"
    )

    # Plan/Job context
    plan_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    job_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Result
    result: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, comment="Result: SUCCESS/FAILURE"
    )

    # Metadata (renamed to avoid conflict with SQLAlchemy Base.metadata)
    meta: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, comment="Additional event metadata"
    )

    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Error message if failed"
    )

    # Relationship
    device: Mapped[Optional["Device"]] = relationship("Device", back_populates="audit_events")

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_user_action", "user_sub", "action"),
        Index("idx_audit_tool", "tool_name"),
        Index("idx_audit_result", "result"),
    )


class Role(Base):
    """User role for RBAC (Phase 5).

    Defines a named role with associated permissions.
    Roles are assigned to users and control access to resources.

    Default roles (seeded by migration):
    - read_only: Read-only access to fundamental tier tools
    - ops_rw: Read-write access to advanced tier tools
    - admin: Full access to all tools and administrative functions
    - approver: Can approve professional tier plans

    Relationships:
        permissions: Associated permissions (M:N via role_permissions)
    """

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="Unique role identifier")

    name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        comment="Role name (read_only, ops_rw, admin, approver)",
    )

    description: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Human-readable role description"
    )

    # Many-to-many relationship with Permission
    permissions: Mapped[list["Permission"]] = relationship(
        "Permission",
        secondary="role_permissions",
        back_populates="roles",
        lazy="selectin",
    )

    __table_args__ = (Index("idx_role_name", "name"),)


class Permission(Base):
    """Permission for RBAC (Phase 5).

    Defines granular access control to specific resources and actions.
    Permissions are associated with roles via many-to-many relationship.

    Permission structure:
    - resource_type: Type of resource (device, plan, tool, etc.)
    - resource_id: Specific resource ID (or '*' for wildcard)
    - action: Allowed action (read, write, execute, approve, etc.)

    Examples:
    - resource_type='device', resource_id='*', action='read'
    - resource_type='device', resource_id='dev-001', action='write'
    - resource_type='plan', resource_id='*', action='approve'
    - resource_type='tool', resource_id='dns/update-servers', action='execute'

    Relationships:
        roles: Associated roles (M:N via role_permissions)
    """

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, comment="Unique permission identifier"
    )

    resource_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Resource type (device, plan, tool, etc.)",
    )

    resource_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Resource ID or wildcard (*)",
    )

    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Allowed action (read, write, execute, approve, etc.)",
    )

    description: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Optional permission description"
    )

    # Many-to-many relationship with Role
    roles: Mapped[list["Role"]] = relationship(
        "Role",
        secondary="role_permissions",
        back_populates="permissions",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_permission_resource_type", "resource_type"),
        Index("idx_permission_resource_action", "resource_type", "resource_id", "action"),
    )


# Many-to-many association table for Role and Permission
class RolePermission(Base):
    """Association table for Role-Permission many-to-many relationship (Phase 5).

    Links roles to their associated permissions.
    """

    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Role ID",
    )

    permission_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
        comment="Permission ID",
    )

    __table_args__ = (
        Index("idx_role_permission_role", "role_id"),
        Index("idx_role_permission_permission", "permission_id"),
    )
