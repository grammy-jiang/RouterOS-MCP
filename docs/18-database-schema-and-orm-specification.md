# Database Schema & ORM Specification

## Purpose

Define the complete database schema, SQLAlchemy ORM models, and migration strategy supporting both SQLite (development) and PostgreSQL (production). This document provides implementation-ready specifications with full type hints.

---

## Database Support

### Supported Databases

| Database | Driver | URL Format | Use Case |
|----------|--------|------------|----------|
| **SQLite** | aiosqlite | `sqlite:///path/to/db.db` | Development, testing, single-user |
| **PostgreSQL** | asyncpg (preferred) | `postgresql+asyncpg://user:pass@host/db` | Production, multi-user |
| **PostgreSQL** | psycopg (fallback) | `postgresql+psycopg://user:pass@host/db` | Production alternative |

### Database Feature Matrix

| Feature | SQLite | PostgreSQL |
|---------|--------|------------|
| Async support | ✅ (aiosqlite) | ✅ (asyncpg/psycopg) |
| JSON fields | ✅ (JSON1 extension) | ✅ (Native JSONB) |
| Full-text search | ⚠️ (Limited) | ✅ (Native) |
| Concurrent writes | ⚠️ (Limited) | ✅ (Excellent) |
| Scalability | Single file | Horizontal scaling |
| Deployment | Embedded | Client-server |

---

## Schema Overview

### Entity Relationship Diagram

```
┌─────────────┐
│   Device    │
└──────┬──────┘
       │
       │ 1:N
       ▼
┌─────────────┐       ┌─────────────┐
│ Credential  │       │ HealthCheck │
└─────────────┘       └─────────────┘
       │                     │
       │                     │
       │ 1:N                 │ 1:N
       ▼                     ▼
┌─────────────┐       ┌─────────────┐
│  Snapshot   │       │ AuditEvent  │
└─────────────┘       └─────────────┘

┌─────────────┐
│    Plan     │
└──────┬──────┘
       │
       │ 1:N
       ▼
┌─────────────┐
│     Job     │
└─────────────┘
```

---

## SQLAlchemy Models

### Base Model

```python
# routeros_mcp/infra/db/models.py

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models.

    Provides:
    - Async attribute loading via AsyncAttrs
    - Common timestamp fields
    - Utility methods
    """

    # Common timestamp columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Record last update timestamp"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert model to dictionary.

        Returns:
            Dictionary representation of model
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

    def __repr__(self) -> str:
        """String representation of model."""
        class_name = self.__class__.__name__
        pk_value = getattr(self, "id", None)
        return f"<{class_name}(id={pk_value})>"
```

### Device Model

```python
from typing import Optional
from sqlalchemy import String, Boolean, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship


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
        String(64),
        primary_key=True,
        comment="Unique device identifier"
    )

    # Basic information
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
        comment="Human-friendly device name"
    )

    management_address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Management address (host:port)"
    )

    environment: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="Environment: lab/staging/prod"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="healthy",
        comment="Current status: healthy/degraded/unreachable"
    )

    # Tags stored as JSON
    tags: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Device tags (key-value pairs)"
    )

    # Capability flags
    allow_advanced_writes: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow advanced tier write operations"
    )

    allow_professional_workflows: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="Allow professional tier workflows"
    )

    # RouterOS metadata
    routeros_version: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        comment="RouterOS version string"
    )

    system_identity: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="RouterOS system identity"
    )

    hardware_model: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Hardware model"
    )

    serial_number: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Device serial number"
    )

    software_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
        comment="Software ID"
    )

    # Timestamps
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful contact timestamp"
    )

    # Relationships
    credentials: Mapped[list["Credential"]] = relationship(
        "Credential",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    health_checks: Mapped[list["HealthCheck"]] = relationship(
        "HealthCheck",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="noload"  # Don't load by default
    )

    snapshots: Mapped[list["Snapshot"]] = relationship(
        "Snapshot",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="noload"
    )

    audit_events: Mapped[list["AuditEvent"]] = relationship(
        "AuditEvent",
        back_populates="device",
        cascade="all, delete-orphan",
        lazy="noload"
    )

    # Indexes
    __table_args__ = (
        Index("idx_device_environment_status", "environment", "status"),
        Index("idx_device_name", "name"),
    )
```

### Credential Model

```python
from sqlalchemy import String, ForeignKey, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Credential(Base):
    """Encrypted device credentials.

    Stores RouterOS access credentials in encrypted form.
    Credentials are never logged or exposed via APIs.

    Relationships:
        device: Parent device (N:1)
    """

    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    kind: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Credential type: routeros_rest/routeros_ssh"
    )

    username: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Username (stored in plaintext)"
    )

    encrypted_secret: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Encrypted password/key"
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether credential is active"
    )

    rotated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last rotation timestamp"
    )

    # Relationship
    device: Mapped["Device"] = relationship(
        "Device",
        back_populates="credentials"
    )

    __table_args__ = (
        Index("idx_credential_device_kind", "device_id", "kind"),
    )
```

### Health Check Model

```python
from sqlalchemy import String, ForeignKey, Float, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship


class HealthCheck(Base):
    """Device health check result.

    Records periodic health check results including
    system metrics and overall health status.

    Relationships:
        device: Parent device (N:1)
    """

    __tablename__ = "health_checks"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Health check timestamp"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Status: healthy/warning/critical"
    )

    # Metrics
    cpu_usage_percent: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    memory_used_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True
    )

    memory_total_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True
    )

    temperature_celsius: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True
    )

    uptime_seconds: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if check failed"
    )

    # Relationship
    device: Mapped["Device"] = relationship(
        "Device",
        back_populates="health_checks"
    )

    __table_args__ = (
        Index("idx_healthcheck_device_timestamp", "device_id", "timestamp"),
        Index("idx_healthcheck_status", "status"),
    )
```

### Snapshot Model

```python
from sqlalchemy import String, ForeignKey, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Snapshot(Base):
    """Configuration snapshot.

    Stores point-in-time device configuration for
    backup, comparison, and rollback purposes.

    Relationships:
        device: Parent device (N:1)
    """

    __tablename__ = "snapshots"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )

    kind: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="Snapshot type: config/dns_ntp/metrics/etc"
    )

    # Snapshot data (compressed)
    data: Mapped[bytes] = mapped_column(
        LargeBinary,
        nullable=False,
        comment="Compressed snapshot data"
    )

    # Metadata
    metadata: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Snapshot metadata (size, checksum, etc)"
    )

    # Relationship
    device: Mapped["Device"] = relationship(
        "Device",
        back_populates="snapshots"
    )

    __table_args__ = (
        Index("idx_snapshot_device_timestamp", "device_id", "timestamp"),
        Index("idx_snapshot_kind", "kind"),
    )
```

### Plan Model

```python
from sqlalchemy import String, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Plan(Base):
    """Configuration change plan.

    Represents an immutable plan for multi-device
    configuration changes requiring approval.

    Relationships:
        jobs: Execution jobs (1:N)
    """

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    created_by: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="User sub who created plan"
    )

    tool_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment="Tool that generated plan"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="draft",
        index=True,
        comment="Status: draft/approved/applied/cancelled"
    )

    device_ids: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        comment="List of target device IDs"
    )

    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Human-readable plan summary"
    )

    changes: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        comment="Detailed change specifications"
    )

    # Approval
    approved_by: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="User sub who approved plan"
    )

    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Approval timestamp"
    )

    # Relationships
    jobs: Mapped[list["Job"]] = relationship(
        "Job",
        back_populates="plan",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_plan_created_by", "created_by"),
        Index("idx_plan_status", "status"),
    )
```

### Job Model

```python
from sqlalchemy import String, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Job(Base):
    """Executable job.

    Represents a unit of work, often tied to a plan,
    that can be executed, retried, and monitored.

    Relationships:
        plan: Parent plan (N:1, optional)
    """

    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    plan_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    job_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Job type: APPLY_PLAN/HEALTH_CHECK/etc"
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
        index=True,
        comment="Status: pending/running/success/failed/cancelled"
    )

    device_ids: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=list,
        comment="Target device IDs"
    )

    # Retry configuration
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of attempts made"
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        comment="Maximum retry attempts"
    )

    next_run_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Scheduled execution time"
    )

    # Results
    result_summary: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Job execution summary"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )

    # Relationship
    plan: Mapped[Optional["Plan"]] = relationship(
        "Plan",
        back_populates="jobs"
    )

    __table_args__ = (
        Index("idx_job_status_next_run", "status", "next_run_at"),
        Index("idx_job_type", "job_type"),
    )
```

### Audit Event Model

```python
from sqlalchemy import String, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship


class AuditEvent(Base):
    """Audit event log.

    Immutable record of security-relevant events
    including all writes and sensitive reads.

    Relationships:
        device: Related device (N:1, optional)
    """

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(
        String(64),
        primary_key=True
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        comment="Event timestamp"
    )

    # User information
    user_sub: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="User subject from OIDC token"
    )

    user_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="User email"
    )

    user_role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="User role at time of action"
    )

    # Device context
    device_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    environment: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
        index=True,
        comment="Device environment"
    )

    # Action details
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        comment="Action type: WRITE/READ_SENSITIVE/AUTHZ_DENIED"
    )

    tool_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
        comment="MCP tool name"
    )

    tool_tier: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Tool tier: fundamental/advanced/professional"
    )

    # Plan/Job context
    plan_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True
    )

    job_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
        index=True
    )

    # Result
    result: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        index=True,
        comment="Result: SUCCESS/FAILURE"
    )

    # Metadata
    metadata: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
        comment="Additional event metadata"
    )

    error_message: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Error message if failed"
    )

    # Relationship
    device: Mapped[Optional["Device"]] = relationship(
        "Device",
        back_populates="audit_events"
    )

    __table_args__ = (
        Index("idx_audit_timestamp", "timestamp"),
        Index("idx_audit_user_action", "user_sub", "action"),
        Index("idx_audit_tool", "tool_name"),
        Index("idx_audit_result", "result"),
    )
```

---

## Database Session Management

### Session Factory

```python
# routeros_mcp/infra/db/session.py

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from routeros_mcp.config import Settings


class DatabaseSessionManager:
    """Database session manager with connection pooling.

    Manages SQLAlchemy async engine and session creation
    with support for both SQLite and PostgreSQL.

    Example:
        manager = DatabaseSessionManager(settings)
        await manager.init()

        async with manager.session() as session:
            result = await session.execute(select(Device))
            devices = result.scalars().all()

        await manager.close()
    """

    def __init__(self, settings: Settings):
        """Initialize session manager.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def init(self) -> None:
        """Initialize database engine and session factory."""
        # SQLite-specific configuration
        if self.settings.is_sqlite:
            connect_args = {
                "check_same_thread": False,  # Required for async
                "timeout": 30.0,  # Lock timeout
            }
            pool_config = {}  # SQLite uses NullPool by default
        else:
            connect_args = {}
            pool_config = {
                "pool_size": self.settings.database_pool_size,
                "max_overflow": self.settings.database_max_overflow,
                "pool_pre_ping": True,  # Verify connections
                "pool_recycle": 3600,  # Recycle after 1 hour
            }

        self._engine = create_async_engine(
            self.settings.database_url,
            echo=self.settings.database_echo,
            connect_args=connect_args,
            **pool_config,
        )

        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def close(self) -> None:
        """Close database engine and cleanup."""
        if self._engine:
            await self._engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get database session context manager.

        Yields:
            AsyncSession instance

        Example:
            async with manager.session() as session:
                result = await session.execute(select(Device))
        """
        if self._session_factory is None:
            raise RuntimeError("SessionManager not initialized. Call init() first.")

        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            else:
                await session.commit()

    @property
    def engine(self) -> AsyncEngine:
        """Get database engine.

        Returns:
            AsyncEngine instance

        Raises:
            RuntimeError: If not initialized
        """
        if self._engine is None:
            raise RuntimeError("SessionManager not initialized. Call init() first.")
        return self._engine


# Global session manager instance
_session_manager: DatabaseSessionManager | None = None


def get_session_manager(settings: Settings | None = None) -> DatabaseSessionManager:
    """Get global session manager instance.

    Args:
        settings: Application settings (required on first call)

    Returns:
        DatabaseSessionManager instance

    Raises:
        RuntimeError: If not initialized and settings not provided
    """
    global _session_manager

    if _session_manager is None:
        if settings is None:
            from routeros_mcp.config import get_settings
            settings = get_settings()
        _session_manager = DatabaseSessionManager(settings)

    return _session_manager


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session (FastAPI dependency).

    Yields:
        AsyncSession instance

    Example:
        @app.get("/devices")
        async def list_devices(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Device))
            return result.scalars().all()
    """
    manager = get_session_manager()
    async with manager.session() as session:
        yield session
```

---

## Database Migrations (Alembic)

### Alembic Configuration

```python
# alembic/env.py

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Import all models
from routeros_mcp.infra.db.models import Base
from routeros_mcp.config import get_settings

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Get settings and set database URL
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url)

# Target metadata
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Run migrations with connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """Run async migrations."""
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = settings.database_url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Initial Migration

```python
# alembic/versions/001_initial_schema.py

"""Initial schema

Revision ID: 001
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial schema."""
    # Devices table
    op.create_table(
        'devices',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, unique=True),
        sa.Column('management_address', sa.String(255), nullable=False),
        sa.Column('environment', sa.String(32), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('tags', sa.JSON(), nullable=False),
        sa.Column('allow_advanced_writes', sa.Boolean(), nullable=False),
        sa.Column('allow_professional_workflows', sa.Boolean(), nullable=False),
        sa.Column('routeros_version', sa.String(64)),
        sa.Column('system_identity', sa.String(255)),
        sa.Column('hardware_model', sa.String(128)),
        sa.Column('serial_number', sa.String(128)),
        sa.Column('software_id', sa.String(128)),
        sa.Column('last_seen_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_device_environment_status', 'devices', ['environment', 'status'])
    op.create_index('idx_device_name', 'devices', ['name'])

    # Credentials table
    op.create_table(
        'credentials',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('device_id', sa.String(64), sa.ForeignKey('devices.id', ondelete='CASCADE')),
        sa.Column('kind', sa.String(32), nullable=False),
        sa.Column('username', sa.String(255), nullable=False),
        sa.Column('encrypted_secret', sa.Text(), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('rotated_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_credential_device_kind', 'credentials', ['device_id', 'kind'])

    # Health checks table
    op.create_table(
        'health_checks',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('device_id', sa.String(64), sa.ForeignKey('devices.id', ondelete='CASCADE')),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('cpu_usage_percent', sa.Float()),
        sa.Column('memory_used_bytes', sa.BigInteger()),
        sa.Column('memory_total_bytes', sa.BigInteger()),
        sa.Column('temperature_celsius', sa.Float()),
        sa.Column('uptime_seconds', sa.BigInteger()),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_healthcheck_device_timestamp', 'health_checks', ['device_id', 'timestamp'])

    # Snapshots table
    op.create_table(
        'snapshots',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('device_id', sa.String(64), sa.ForeignKey('devices.id', ondelete='CASCADE')),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('kind', sa.String(64), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_snapshot_device_timestamp', 'snapshots', ['device_id', 'timestamp'])

    # Plans table
    op.create_table(
        'plans',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('created_by', sa.String(255), nullable=False),
        sa.Column('tool_name', sa.String(128), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('device_ids', sa.JSON(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('changes', sa.JSON(), nullable=False),
        sa.Column('approved_by', sa.String(255)),
        sa.Column('approved_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_plan_status', 'plans', ['status'])

    # Jobs table
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('plan_id', sa.String(64), sa.ForeignKey('plans.id', ondelete='CASCADE')),
        sa.Column('job_type', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('device_ids', sa.JSON(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('max_attempts', sa.Integer(), nullable=False),
        sa.Column('next_run_at', sa.DateTime(timezone=True)),
        sa.Column('result_summary', sa.Text()),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_job_status_next_run', 'jobs', ['status', 'next_run_at'])

    # Audit events table
    op.create_table(
        'audit_events',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('user_sub', sa.String(255), nullable=False),
        sa.Column('user_email', sa.String(255)),
        sa.Column('user_role', sa.String(32), nullable=False),
        sa.Column('device_id', sa.String(64), sa.ForeignKey('devices.id', ondelete='SET NULL')),
        sa.Column('environment', sa.String(32)),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('tool_name', sa.String(128), nullable=False),
        sa.Column('tool_tier', sa.String(32), nullable=False),
        sa.Column('plan_id', sa.String(64)),
        sa.Column('job_id', sa.String(64)),
        sa.Column('result', sa.String(32), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=False),
        sa.Column('error_message', sa.Text()),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('idx_audit_timestamp', 'audit_events', ['timestamp'])
    op.create_index('idx_audit_user_action', 'audit_events', ['user_sub', 'action'])


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table('audit_events')
    op.drop_table('jobs')
    op.drop_table('plans')
    op.drop_table('snapshots')
    op.drop_table('health_checks')
    op.drop_table('credentials')
    op.drop_table('devices')
```

---

## Usage Examples

### Creating Tables

```bash
# Create all tables
uv run alembic upgrade head

# Rollback one version
uv run alembic downgrade -1

# Show current version
uv run alembic current

# Show migration history
uv run alembic history
```

### CRUD Operations

```python
from sqlalchemy import select
from routeros_mcp.infra.db.models import Device
from routeros_mcp.infra.db.session import get_session_manager

# Initialize session manager
manager = get_session_manager()
await manager.init()

# Create device
async with manager.session() as session:
    device = Device(
        id="dev-001",
        name="lab-router-01",
        management_address="192.168.1.1:443",
        environment="lab",
        status="healthy",
        tags={"site": "main", "role": "edge"},
        allow_advanced_writes=True,
    )
    session.add(device)

# Read device
async with manager.session() as session:
    result = await session.execute(
        select(Device).where(Device.id == "dev-001")
    )
    device = result.scalar_one()

# Update device
async with manager.session() as session:
    result = await session.execute(
        select(Device).where(Device.id == "dev-001")
    )
    device = result.scalar_one()
    device.status = "degraded"

# Delete device
async with manager.session() as session:
    result = await session.execute(
        select(Device).where(Device.id == "dev-001")
    )
    device = result.scalar_one()
    await session.delete(device)

# Cleanup
await manager.close()
```

---

## MCP Best Practices Integration

### Domain/Infrastructure Separation (MCP Section B2)

Following MCP best practice B2 (Project Structure and Layering), separate domain logic from database infrastructure:

```
routeros_mcp/
├── domain/                    # Pure business logic, NO SQLAlchemy imports
│   ├── __init__.py
│   ├── models.py             # Domain models (Pydantic/dataclasses)
│   ├── device_service.py     # Device business logic
│   ├── plan_service.py       # Plan business logic
│   └── validation.py         # Domain validation rules
│
└── infra/                     # Infrastructure layer
    ├── db/
    │   ├── __init__.py
    │   ├── models.py         # SQLAlchemy ORM models (THIS document)
    │   ├── session.py        # Session management
    │   ├── repositories.py   # Data access patterns
    │   └── migrations/       # Alembic migrations
    └── routeros/
        └── client.py          # RouterOS API client
```

**Example: Domain Model (Pure Python)**

```python
# routeros_mcp/domain/models.py
# NO SQLAlchemy imports - pure domain logic

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class DeviceDomain:
    """Domain model for RouterOS device.

    This is the domain representation, independent of persistence.
    Following MCP best practice B2: domain logic has no MCP or DB dependencies.
    """
    id: str
    name: str
    management_address: str
    environment: str
    status: str
    tags: dict[str, str]
    allow_advanced_writes: bool
    allow_professional_workflows: bool

    # Metadata
    routeros_version: Optional[str] = None
    hardware_model: Optional[str] = None
    last_seen_at: Optional[datetime] = None

    def is_reachable(self) -> bool:
        """Check if device is considered reachable."""
        return self.status in ["healthy", "degraded"]

    def can_execute_tier(self, tier: str) -> bool:
        """Check if device allows operations from specific tier."""
        if tier == "fundamental":
            return True  # Always allowed
        elif tier == "advanced":
            return self.allow_advanced_writes
        elif tier == "professional":
            return self.allow_professional_workflows
        return False

    def validate_environment_match(self, service_environment: str) -> bool:
        """Validate device environment matches service environment."""
        return self.environment == service_environment
```

**Example: Repository Pattern (Infrastructure Layer)**

```python
# routeros_mcp/infra/db/repositories.py

from typing import Optional, Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.domain.models import DeviceDomain
from routeros_mcp.infra.db.models import Device as DeviceORM


class DeviceRepository:
    """Device data access repository.

    Translates between domain models and ORM models.
    Following MCP best practice B2: infrastructure layer adapts domain to persistence.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, device_id: str) -> Optional[DeviceDomain]:
        """Get device by ID.

        Returns:
            Domain model or None
        """
        result = await self.session.execute(
            select(DeviceORM).where(DeviceORM.id == device_id)
        )
        orm_device = result.scalar_one_or_none()

        if orm_device is None:
            return None

        # Convert ORM → Domain
        return self._to_domain(orm_device)

    async def list_by_environment(self, environment: str) -> Sequence[DeviceDomain]:
        """List devices by environment."""
        result = await self.session.execute(
            select(DeviceORM)
            .where(DeviceORM.environment == environment)
            .order_by(DeviceORM.name)
        )
        orm_devices = result.scalars().all()

        return [self._to_domain(d) for d in orm_devices]

    async def save(self, device: DeviceDomain) -> DeviceDomain:
        """Save device (create or update)."""
        # Check if exists
        existing = await self.session.get(DeviceORM, device.id)

        if existing:
            # Update existing
            self._update_orm(existing, device)
        else:
            # Create new
            orm_device = self._to_orm(device)
            self.session.add(orm_device)

        await self.session.flush()

        # Return refreshed domain model
        result = await self.session.get(DeviceORM, device.id)
        return self._to_domain(result)

    def _to_domain(self, orm: DeviceORM) -> DeviceDomain:
        """Convert ORM model to domain model."""
        return DeviceDomain(
            id=orm.id,
            name=orm.name,
            management_address=orm.management_address,
            environment=orm.environment,
            status=orm.status,
            tags=orm.tags,
            allow_advanced_writes=orm.allow_advanced_writes,
            allow_professional_workflows=orm.allow_professional_workflows,
            routeros_version=orm.routeros_version,
            hardware_model=orm.hardware_model,
            last_seen_at=orm.last_seen_at,
        )

    def _to_orm(self, domain: DeviceDomain) -> DeviceORM:
        """Convert domain model to ORM model."""
        return DeviceORM(
            id=domain.id,
            name=domain.name,
            management_address=domain.management_address,
            environment=domain.environment,
            status=domain.status,
            tags=domain.tags,
            allow_advanced_writes=domain.allow_advanced_writes,
            allow_professional_workflows=domain.allow_professional_workflows,
            routeros_version=domain.routeros_version,
            hardware_model=domain.hardware_model,
            last_seen_at=domain.last_seen_at,
        )

    def _update_orm(self, orm: DeviceORM, domain: DeviceDomain) -> None:
        """Update ORM model from domain model."""
        orm.name = domain.name
        orm.management_address = domain.management_address
        orm.environment = domain.environment
        orm.status = domain.status
        orm.tags = domain.tags
        orm.allow_advanced_writes = domain.allow_advanced_writes
        orm.allow_professional_workflows = domain.allow_professional_workflows
        orm.routeros_version = domain.routeros_version
        orm.hardware_model = domain.hardware_model
        orm.last_seen_at = domain.last_seen_at
```

### Observability for Database Operations (MCP Section A9)

Following MCP instrumentation guidelines, add observability to database operations:

```python
# routeros_mcp/infra/db/observability.py

import time
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@asynccontextmanager
async def traced_session(
    session_factory,
    operation: str,
    request_id: str
) -> AsyncGenerator[AsyncSession, None]:
    """Session context manager with tracing.

    Following MCP Section A9: log every database operation with
    correlation ID, duration, and outcome.

    Args:
        session_factory: Session factory
        operation: Operation name (e.g., "get_device", "list_plans")
        request_id: JSON-RPC request ID for correlation

    Example:
        async with traced_session(manager.session, "get_device", req_id) as session:
            device = await session.get(Device, device_id)
    """
    start_time = time.time()

    async with session_factory() as session:
        try:
            yield session

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "database_operation",
                extra={
                    "request_id": request_id,
                    "operation": operation,
                    "status": "success",
                    "duration_ms": duration_ms,
                }
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "database_operation_error",
                extra={
                    "request_id": request_id,
                    "operation": operation,
                    "status": "error",
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                }
            )

            raise


# Enhanced repository with tracing
class TracedDeviceRepository(DeviceRepository):
    """Device repository with observability."""

    def __init__(self, session: AsyncSession, request_id: str):
        super().__init__(session)
        self.request_id = request_id

    async def get_by_id(self, device_id: str) -> Optional[DeviceDomain]:
        """Get device with tracing."""
        start = time.time()

        try:
            result = await super().get_by_id(device_id)

            logger.info(
                "repository_operation",
                extra={
                    "request_id": self.request_id,
                    "operation": "get_device",
                    "device_id": device_id,
                    "found": result is not None,
                    "duration_ms": int((time.time() - start) * 1000),
                }
            )

            return result

        except Exception as e:
            logger.error(
                "repository_error",
                extra={
                    "request_id": self.request_id,
                    "operation": "get_device",
                    "device_id": device_id,
                    "error": str(e),
                    "duration_ms": int((time.time() - start) * 1000),
                }
            )
            raise
```

### Performance Best Practices (MCP Section B8)

Following MCP performance guidelines:

#### 1. Pagination

**Always paginate queries to avoid unbounded result sets:**

```python
# routeros_mcp/infra/db/repositories.py

from typing import Tuple


class DeviceRepository:
    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 20,
        environment: Optional[str] = None
    ) -> Tuple[Sequence[DeviceDomain], int]:
        """List devices with pagination.

        Following MCP Section B8: Never return unbounded result sets.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page (max 100)
            environment: Optional environment filter

        Returns:
            Tuple of (devices, total_count)
        """
        # Enforce maximum page size
        page_size = min(page_size, 100)
        offset = (page - 1) * page_size

        # Build query
        query = select(DeviceORM)
        if environment:
            query = query.where(DeviceORM.environment == environment)

        # Get total count
        count_query = select(func.count()).select_from(DeviceORM)
        if environment:
            count_query = count_query.where(DeviceORM.environment == environment)

        count_result = await self.session.execute(count_query)
        total = count_result.scalar()

        # Get page
        query = query.offset(offset).limit(page_size).order_by(DeviceORM.name)
        result = await self.session.execute(query)
        devices = result.scalars().all()

        return [self._to_domain(d) for d in devices], total
```

#### 2. Selective Loading (Avoid N+1 Queries)

```python
# Use selectinload for relationships to avoid N+1 queries

from sqlalchemy.orm import selectinload

async def get_device_with_credentials(self, device_id: str) -> Optional[DeviceDomain]:
    """Get device with credentials loaded efficiently."""
    result = await self.session.execute(
        select(DeviceORM)
        .where(DeviceORM.id == device_id)
        .options(selectinload(DeviceORM.credentials))  # Eager load
    )
    device = result.scalar_one_or_none()

    if device is None:
        return None

    return self._to_domain(device)
```

#### 3. Connection Pooling Configuration

**SQLite:**
```python
# For SQLite, use minimal pooling
if settings.is_sqlite:
    pool_config = {
        "poolclass": NullPool,  # No pooling for SQLite
    }
```

**PostgreSQL:**
```python
# For PostgreSQL, optimize pool size
if settings.is_postgresql:
    pool_config = {
        "pool_size": 10,           # Base connections
        "max_overflow": 20,        # Burst capacity
        "pool_pre_ping": True,     # Verify connections
        "pool_recycle": 3600,      # Recycle after 1 hour
        "pool_timeout": 30,        # Connection timeout
    }
```

### Testing Strategy (MCP Section B9)

Following MCP testing best practices:

#### Unit Tests for Domain Logic

```python
# tests/domain/test_device.py

from routeros_mcp.domain.models import DeviceDomain


def test_device_can_execute_fundamental_tier():
    """Fundamental tier is always allowed."""
    device = DeviceDomain(
        id="dev-001",
        name="test",
        management_address="192.168.1.1:443",
        environment="lab",
        status="healthy",
        tags={},
        allow_advanced_writes=False,
        allow_professional_workflows=False,
    )

    assert device.can_execute_tier("fundamental") is True


def test_device_cannot_execute_advanced_tier_when_disabled():
    """Advanced tier requires flag."""
    device = DeviceDomain(
        id="dev-001",
        name="test",
        management_address="192.168.1.1:443",
        environment="lab",
        status="healthy",
        tags={},
        allow_advanced_writes=False,  # Disabled
        allow_professional_workflows=False,
    )

    assert device.can_execute_tier("advanced") is False


def test_device_environment_validation():
    """Device environment must match service environment."""
    device = DeviceDomain(
        id="dev-001",
        name="test",
        management_address="192.168.1.1:443",
        environment="prod",
        status="healthy",
        tags={},
        allow_advanced_writes=True,
        allow_professional_workflows=True,
    )

    assert device.validate_environment_match("prod") is True
    assert device.validate_environment_match("lab") is False
```

#### Integration Tests for Database Operations

```python
# tests/infra/db/test_repositories.py

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.domain.models import DeviceDomain
from routeros_mcp.infra.db.repositories import DeviceRepository


@pytest.mark.asyncio
async def test_device_repository_save_and_retrieve(db_session: AsyncSession):
    """Test saving and retrieving device."""
    repo = DeviceRepository(db_session)

    # Create device
    device = DeviceDomain(
        id="dev-test-001",
        name="test-router",
        management_address="192.168.1.1:443",
        environment="lab",
        status="healthy",
        tags={"role": "edge"},
        allow_advanced_writes=True,
        allow_professional_workflows=False,
    )

    # Save
    saved = await repo.save(device)
    await db_session.commit()

    # Retrieve
    retrieved = await repo.get_by_id("dev-test-001")

    assert retrieved is not None
    assert retrieved.id == device.id
    assert retrieved.name == device.name
    assert retrieved.tags == {"role": "edge"}


@pytest.mark.asyncio
async def test_device_repository_pagination(db_session: AsyncSession):
    """Test paginated device listing."""
    repo = DeviceRepository(db_session)

    # Create multiple devices
    for i in range(25):
        device = DeviceDomain(
            id=f"dev-{i:03d}",
            name=f"router-{i:03d}",
            management_address=f"192.168.1.{i}:443",
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=True,
            allow_professional_workflows=False,
        )
        await repo.save(device)

    await db_session.commit()

    # Get first page
    devices_page1, total = await repo.list_paginated(page=1, page_size=10)

    assert len(devices_page1) == 10
    assert total == 25

    # Get second page
    devices_page2, total = await repo.list_paginated(page=2, page_size=10)

    assert len(devices_page2) == 10
    assert total == 25

    # Verify no overlap
    page1_ids = {d.id for d in devices_page1}
    page2_ids = {d.id for d in devices_page2}
    assert page1_ids.isdisjoint(page2_ids)


# Pytest fixtures
@pytest.fixture
async def db_session(test_db_engine):
    """Provide test database session."""
    async with test_db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(test_db_engine) as session:
        yield session
        await session.rollback()

    async with test_db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
```

### Database Migration Best Practices

#### Safe Migration Patterns

```python
# alembic/versions/002_add_device_metadata.py

"""Add device metadata fields

Revision ID: 002
Revises: 001
Create Date: 2024-01-15 10:00:00

"""
from alembic import op
import sqlalchemy as sa


def upgrade() -> None:
    """Add new fields with safe defaults."""
    # Add nullable columns first
    op.add_column('devices', sa.Column('firmware_variant', sa.String(64), nullable=True))
    op.add_column('devices', sa.Column('license_level', sa.String(32), nullable=True))

    # Create index
    op.create_index('idx_device_firmware', 'devices', ['firmware_variant'], unique=False)


def downgrade() -> None:
    """Revert changes."""
    op.drop_index('idx_device_firmware', table_name='devices')
    op.drop_column('devices', 'license_level')
    op.drop_column('devices', 'firmware_variant')
```

#### Zero-Downtime Migrations

**For production PostgreSQL:**

1. Add columns as nullable
2. Backfill data in batches
3. Add NOT NULL constraint later (if needed)
4. Never drop columns in same deployment as code change

---

## Database Best Practices Checklist

### Design

- [ ] Domain models separated from ORM models (B2)
- [ ] Repository pattern for data access
- [ ] All queries use pagination (B8)
- [ ] Relationships configured with appropriate lazy loading
- [ ] Indexes on frequently queried columns
- [ ] Foreign keys with appropriate CASCADE/SET NULL

### Performance

- [ ] Connection pooling configured per database type
- [ ] Eager loading (selectinload) used to avoid N+1 queries
- [ ] Query results limited to prevent memory issues
- [ ] Large binary data compressed before storage
- [ ] Pagination enforced (max 100 items per page)

### Observability

- [ ] Database operations logged with correlation IDs (A9)
- [ ] Latency tracked (P50/P95/P99)
- [ ] Error rates monitored
- [ ] Connection pool metrics exposed
- [ ] Slow query logging enabled

### Testing

- [ ] Unit tests for domain logic (no database)
- [ ] Integration tests with real database
- [ ] Test fixtures isolate test data
- [ ] Migrations tested in both directions (upgrade/downgrade)

---

This database schema specification provides:

✅ **Full type hints** for all models
✅ **SQLite and PostgreSQL** support
✅ **Async-first** with SQLAlchemy 2.0+
✅ **Comprehensive relationships** with proper cascades
✅ **Indexes** for query performance
✅ **Migration strategy** with Alembic
✅ **Session management** with proper cleanup
✅ **Implementation-ready** code examples
✅ **Domain/Infrastructure separation** following MCP best practices (B2)
✅ **Repository pattern** for clean data access
✅ **Observability** with traced operations (A9)
✅ **Performance optimization** with pagination and connection pooling (B8)
✅ **Comprehensive testing strategy** (B9)
