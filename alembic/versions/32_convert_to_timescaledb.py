"""Convert health_checks to TimescaleDB hypertable

Revision ID: 32
Revises: 31
Create Date: 2026-01-07 23:15:00.000000

This migration converts the health_checks table to a TimescaleDB hypertable
for improved time-series performance and enables automatic data retention.

Features:
- Converts health_checks to hypertable partitioned on timestamp column
- Adds 30-day data retention policy
- Creates continuous aggregate for hourly CPU/memory summaries
- Gracefully skips if TimescaleDB extension is not available
- Fully reversible (downgrade converts back to regular table)

Deployment Requirements:
- PostgreSQL with TimescaleDB extension (optional)
- For SQLite deployments: migration skips gracefully (no-op)
- For PostgreSQL without TimescaleDB: migration skips gracefully (no-op)

See docs/06-system-information-and-metrics-collection-module-design.md for setup.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "32"
down_revision: str | None = "31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _is_timescaledb_available() -> bool:
    """Check if TimescaleDB extension is available and enabled.
    
    Returns:
        True if TimescaleDB is available, False otherwise
        
    Notes:
        - Returns False for SQLite (not supported)
        - Returns False for PostgreSQL without TimescaleDB extension
        - Returns True only for PostgreSQL with TimescaleDB extension installed
    """
    bind = op.get_bind()
    dialect_name = bind.dialect.name
    
    # TimescaleDB only works with PostgreSQL
    if dialect_name != "postgresql":
        return False
    
    # Check if TimescaleDB extension is installed
    try:
        result = bind.execute(
            text(
                "SELECT COUNT(*) FROM pg_extension WHERE extname = 'timescaledb'"
            )
        )
        count = result.scalar()
        return count > 0
    except Exception:
        # If query fails, TimescaleDB is not available
        return False


def upgrade() -> None:
    """Upgrade database schema.
    
    Converts health_checks to TimescaleDB hypertable if available.
    Skips gracefully if TimescaleDB is not available (SQLite or PostgreSQL without extension).
    """
    if not _is_timescaledb_available():
        # Skip for SQLite or PostgreSQL without TimescaleDB
        # This is expected and safe - health_checks works fine as regular table
        return
    
    bind = op.get_bind()
    
    # Convert health_checks to hypertable partitioned on timestamp
    # chunk_time_interval: 7 days (default for daily data)
    bind.execute(
        text(
            "SELECT create_hypertable('health_checks', 'timestamp', "
            "chunk_time_interval => INTERVAL '7 days', "
            "if_not_exists => TRUE)"
        )
    )
    
    # Add retention policy: automatically drop data older than 30 days
    # This runs as a background job in TimescaleDB
    bind.execute(
        text(
            "SELECT add_retention_policy('health_checks', INTERVAL '30 days', "
            "if_not_exists => TRUE)"
        )
    )
    
    # Create continuous aggregate for hourly summaries
    # Used for dashboards and analytics without scanning raw data
    bind.execute(
        text(
            """
            CREATE MATERIALIZED VIEW IF NOT EXISTS health_checks_hourly
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket('1 hour', timestamp) AS hour,
                device_id,
                COUNT(*) AS check_count,
                AVG(cpu_usage_percent) AS avg_cpu,
                MAX(cpu_usage_percent) AS max_cpu,
                MIN(cpu_usage_percent) AS min_cpu,
                AVG(CASE 
                    WHEN memory_total_bytes > 0 
                    THEN (memory_used_bytes::float / memory_total_bytes::float * 100)
                    ELSE NULL 
                END) AS avg_memory_percent,
                MAX(CASE 
                    WHEN memory_total_bytes > 0 
                    THEN (memory_used_bytes::float / memory_total_bytes::float * 100)
                    ELSE NULL 
                END) AS max_memory_percent,
                AVG(temperature_celsius) AS avg_temperature,
                MAX(temperature_celsius) AS max_temperature
            FROM health_checks
            GROUP BY hour, device_id
            WITH NO DATA
            """
        )
    )
    
    # Refresh the continuous aggregate to populate with existing data
    bind.execute(
        text("CALL refresh_continuous_aggregate('health_checks_hourly', NULL, NULL)")
    )
    
    # Add refresh policy: automatically refresh hourly aggregate every hour
    bind.execute(
        text(
            "SELECT add_continuous_aggregate_policy('health_checks_hourly', "
            "start_offset => INTERVAL '3 hours', "
            "end_offset => INTERVAL '1 hour', "
            "schedule_interval => INTERVAL '1 hour', "
            "if_not_exists => TRUE)"
        )
    )


def downgrade() -> None:
    """Downgrade database schema.
    
    Converts health_checks back to regular table if TimescaleDB is available.
    Skips gracefully if TimescaleDB is not available (was no-op on upgrade).
    """
    if not _is_timescaledb_available():
        # Skip for SQLite or PostgreSQL without TimescaleDB
        # Nothing was done on upgrade, so nothing to undo
        return
    
    bind = op.get_bind()
    
    # Drop continuous aggregate refresh policy
    try:
        bind.execute(
            text(
                "SELECT remove_continuous_aggregate_policy('health_checks_hourly', "
                "if_exists => TRUE)"
            )
        )
    except Exception:
        # Policy might not exist, continue
        pass
    
    # Drop continuous aggregate view
    bind.execute(
        text("DROP MATERIALIZED VIEW IF EXISTS health_checks_hourly CASCADE")
    )
    
    # Remove retention policy
    try:
        bind.execute(
            text(
                "SELECT remove_retention_policy('health_checks', if_exists => TRUE)"
            )
        )
    except Exception:
        # Policy might not exist, continue
        pass
    
    # Convert hypertable back to regular table
    # This preserves all data but removes TimescaleDB optimizations
    bind.execute(
        text(
            """
            DO $$
            BEGIN
                -- Check if table is a hypertable before dropping
                IF EXISTS (
                    SELECT 1 FROM timescaledb_information.hypertables 
                    WHERE hypertable_name = 'health_checks'
                ) THEN
                    -- Create temporary table with data
                    CREATE TABLE health_checks_backup AS 
                    SELECT * FROM health_checks;
                    
                    -- Drop hypertable
                    DROP TABLE health_checks CASCADE;
                    
                    -- Recreate as regular table (schema from models.py)
                    CREATE TABLE health_checks (
                        id VARCHAR(64) PRIMARY KEY,
                        device_id VARCHAR(64) NOT NULL,
                        timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        cpu_usage_percent DOUBLE PRECISION,
                        memory_used_bytes BIGINT,
                        memory_total_bytes BIGINT,
                        temperature_celsius DOUBLE PRECISION,
                        uptime_seconds BIGINT,
                        error_message TEXT,
                        created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                        CONSTRAINT fk_healthcheck_device 
                            FOREIGN KEY (device_id) 
                            REFERENCES devices(id) 
                            ON DELETE CASCADE
                    );
                    
                    -- Restore data
                    INSERT INTO health_checks SELECT * FROM health_checks_backup;
                    
                    -- Drop backup
                    DROP TABLE health_checks_backup;
                    
                    -- Recreate indexes
                    CREATE INDEX idx_healthcheck_device_timestamp 
                        ON health_checks(device_id, timestamp);
                    CREATE INDEX idx_healthcheck_status 
                        ON health_checks(status);
                END IF;
            END $$;
            """
        )
    )
