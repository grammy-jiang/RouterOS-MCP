# System Information & Metrics Collection Module Design

## Purpose

Define the metrics collection subsystem that gathers device health, performance, and operational data from RouterOS devices via REST API endpoints. Specify how data is normalized, stored, scheduled, exposed via MCP tools, and protected against over-polling.

**Phase 1 Scope**: Single-user deployment with up to 10 RouterOS devices. Metrics collection supports health monitoring and inventory management. Advanced analytics and time-series storage are implemented in Phase 4.

---

## Overview

The metrics collection module is responsible for:

1. **Periodic data collection** from RouterOS devices via REST API
2. **Normalization** of RouterOS-specific responses into standardized domain models
3. **Health assessment** based on configurable thresholds
4. **Storage and retention** of health check results and snapshots
5. **Exposure via MCP tools** for read-only access to metrics and health data
6. **Protection mechanisms** to prevent over-polling and device overload

**Key Design Principles**:
- **REST API first**: All metrics collected via RouterOS REST API (no SSH for metrics)
- **Bounded queries**: All endpoint calls use pagination, limits, and timeouts
- **Device protection**: Per-device rate limiting and concurrency control
- **Phase-aligned**: Metrics support Phase 1 (read-only) and Phase 2+ (write validation)

---

## Data Sources and RouterOS Endpoints

### Phase 1 Metrics Collection Endpoints

The metrics collector queries the following RouterOS REST endpoints per Doc 03 comprehensive mappings:

#### System Metrics

| Endpoint | Purpose | Collection Interval | MCP Tool |
|----------|---------|---------------------|----------|
| `GET /rest/system/resource` | CPU, memory, uptime, version | 60s | `system/get-overview` |
| `GET /rest/system/identity` | Device name/identity | 300s (5min) | `system/get-overview` |
| `GET /rest/system/routerboard` | Hardware model, serial | 3600s (1hr) | `system/get-overview` |
| `GET /rest/system/package` | Installed packages | 3600s (1hr) | `system/get-packages` |
| `GET /rest/system/clock` | System time and timezone | 300s (5min) | `system/get-clock` |

**Field Mappings** (normalized from Doc 03):

```python
# /rest/system/resource → SystemResource
class SystemResource:
    """Normalized system resource metrics."""

    device_id: str
    timestamp: datetime

    # Version and identity
    routeros_version: str           # "7.10.1 (stable)"
    system_identity: str            # "router-lab-01"
    hardware_model: str             # "RB5009UG+S+"

    # Performance
    uptime_seconds: int             # Parsed from "1w2d3h4m5s"
    cpu_usage_percent: float        # Normalized from cpu-load (0-100)
    cpu_count: int                  # Number of CPU cores

    # Memory
    memory_total_bytes: int
    memory_free_bytes: int
    memory_used_bytes: int          # Calculated: total - free
    memory_usage_percent: float     # Calculated: (used / total) * 100

    # Disk (if available)
    disk_total_bytes: int | None
    disk_free_bytes: int | None
```

#### Interface Metrics

| Endpoint | Purpose | Collection Interval | MCP Tool |
|----------|---------|---------------------|----------|
| `GET /rest/interface` | Interface list, status | 60s | `interface/list-interfaces` |
| `GET /rest/interface/monitor-traffic` | Real-time traffic stats | 60s | `interface/get-stats` |

**Field Mappings**:

```python
# /rest/interface → InterfaceInfo
class InterfaceInfo:
    """Normalized interface information."""

    device_id: str
    timestamp: datetime

    interface_id: str               # RouterOS internal ID
    name: str                       # "ether1", "bridge0", etc.
    type: str                       # "ether", "bridge", "vlan", etc.

    # Status
    running: bool                   # Link up/down
    disabled: bool                  # Administratively disabled

    # Configuration
    mtu: int
    mac_address: str
    comment: str | None

    # Traffic counters (if available from monitor-traffic)
    rx_bytes: int | None
    tx_bytes: int | None
    rx_packets: int | None
    tx_packets: int | None
    rx_errors: int | None
    tx_errors: int | None
```

#### IP Address Metrics

| Endpoint | Purpose | Collection Interval | MCP Tool |
|----------|---------|---------------------|----------|
| `GET /rest/ip/address` | IP address assignments | 300s (5min) | `ip/list-addresses` |
| `GET /rest/ip/arp` | ARP table | 300s (5min) | `ip/get-arp-table` |

**Field Mappings**:

```python
# /rest/ip/address → IPAddressInfo
class IPAddressInfo:
    """Normalized IP address assignment."""

    device_id: str
    timestamp: datetime

    address_id: str                 # RouterOS internal ID
    address: str                    # "192.168.1.1/24" (CIDR)
    network: str                    # "192.168.1.0"
    interface: str                  # Interface name
    disabled: bool
    comment: str | None
```

#### DNS and NTP Metrics

| Endpoint | Purpose | Collection Interval | MCP Tool |
|----------|---------|---------------------|----------|
| `GET /rest/ip/dns` | DNS configuration | 300s (5min) | `dns/get-status` |
| `GET /rest/ip/dns/cache` | DNS cache stats | 300s (5min) | `dns/get-cache` |
| `GET /rest/system/ntp/client` | NTP configuration | 300s (5min) | `ntp/get-status` |
| `GET /rest/system/ntp/client/monitor` | NTP sync status | 60s | `ntp/get-status` |

**Field Mappings**:

```python
# /rest/ip/dns → DNSConfig
class DNSConfig:
    """Normalized DNS configuration."""

    device_id: str
    timestamp: datetime

    dns_servers: list[str]          # Parsed from comma-separated
    allow_remote_requests: bool
    cache_size_kb: int
    cache_used_kb: int

# /rest/system/ntp/client/monitor → NTPStatus
class NTPStatus:
    """Normalized NTP sync status."""

    device_id: str
    timestamp: datetime

    enabled: bool
    ntp_servers: list[str]
    status: str                     # "synchronized", "unreachable", etc.
    stratum: int | None
    offset_ms: float | None         # Parsed from "-0.002s"
```

#### Routing Metrics

| Endpoint | Purpose | Collection Interval | MCP Tool |
|----------|---------|---------------------|----------|
| `GET /rest/ip/route` | Routing table | 300s (5min) | `routing/get-summary` |

**Field Mappings**:

```python
# /rest/ip/route → RouteInfo
class RouteInfo:
    """Normalized routing table entry."""

    device_id: str
    timestamp: datetime

    route_id: str
    dst_address: str                # "0.0.0.0/0", "192.168.1.0/24"
    gateway: str | None
    distance: int                   # Administrative distance
    scope: int
    active: bool                    # Route is active
    dynamic: bool                   # Route is dynamic (from protocol)
    comment: str | None
```

#### Firewall and Logging Metrics

| Endpoint | Purpose | Collection Interval | MCP Tool |
|----------|---------|---------------------|----------|
| `GET /rest/ip/firewall/filter` | Firewall rules count | On-demand | `firewall/list-filter-rules` |
| `GET /rest/ip/firewall/nat` | NAT rules count | On-demand | `firewall/list-nat-rules` |
| `GET /rest/ip/firewall/address-list` | Address list entries | On-demand | `firewall/list-address-lists` |
| `GET /rest/log` | System logs (bounded) | On-demand | `logs/get-recent` |

**Note**: Firewall and log queries are **on-demand only** (triggered by MCP tool calls, not scheduled collection) to minimize device load.

**Pagination and Token Budgets**:
- All list operations support `limit` (default: 100, max: 1000) and `offset` parameters
- **Token estimation**:
  - Firewall rules: ~80 tokens per rule (complex rules can be 200+ tokens)
  - NAT rules: ~60 tokens per rule
  - Logs: ~40 tokens per entry
  - **Warnings issued** when estimated response >5000 tokens (recommend filtering/pagination)

---

## Normalization and Data Model

### Normalization Goals

1. **Consistent schema**: Normalize RouterOS version-specific field names into stable domain models
2. **Type safety**: Convert RouterOS strings to appropriate Python types (int, float, bool, datetime)
3. **Calculated fields**: Add derived metrics (e.g., memory_usage_percent, uptime_seconds)
4. **Device context**: Include device_id and timestamp with every metric sample

### Data Model Architecture

**Three-tier data model**:

1. **Raw API Response** (Dict[str, Any])
   - Direct response from RouterOS REST API
   - RouterOS-specific field names and formats
   - Stored temporarily for debugging/audit only

2. **Normalized Domain Model** (Pydantic)
   - Normalized field names per coding standards
   - Strong typing with validation
   - Calculated/derived fields added
   - Examples: `SystemResource`, `InterfaceInfo`, `IPAddressInfo`

3. **Health Check Summary** (ORM Entity)
   - Aggregated health status per device
   - Stored in database via `HealthCheck` ORM model (Doc 18)
   - Includes overall status, thresholds, and metadata

### Health Check Status Assessment

Health status is determined by evaluating metrics against thresholds (from Doc 05):

```python
from enum import Enum

class HealthStatus(str, Enum):
    """Health check status levels."""

    HEALTHY = "healthy"         # All metrics within normal range
    WARNING = "warning"         # One or more metrics approaching limits
    CRITICAL = "critical"       # One or more metrics exceeding safe limits
    ERROR = "error"            # Health check failed (connection error, timeout)

class HealthThresholds:
    """Health check thresholds (configurable per device or globally)."""

    # CPU thresholds
    CPU_WARNING_PERCENT = 80.0
    CPU_CRITICAL_PERCENT = 95.0

    # Memory thresholds
    MEMORY_WARNING_PERCENT = 85.0
    MEMORY_CRITICAL_PERCENT = 95.0

    # Disk thresholds (if available)
    DISK_WARNING_PERCENT = 85.0
    DISK_CRITICAL_PERCENT = 95.0

    # Uptime thresholds
    UPTIME_WARNING_SECONDS = 60  # Device recently rebooted

def assess_health(resource: SystemResource, thresholds: HealthThresholds) -> HealthStatus:
    """Assess device health based on resource metrics and thresholds.

    Args:
        resource: Normalized system resource metrics
        thresholds: Health check thresholds

    Returns:
        Overall health status
    """
    # Check critical thresholds first
    if resource.cpu_usage_percent > thresholds.CPU_CRITICAL_PERCENT:
        return HealthStatus.CRITICAL

    if resource.memory_usage_percent > thresholds.MEMORY_CRITICAL_PERCENT:
        return HealthStatus.CRITICAL

    if resource.disk_usage_percent and resource.disk_usage_percent > thresholds.DISK_CRITICAL_PERCENT:
        return HealthStatus.CRITICAL

    # Check warning thresholds
    if (resource.cpu_usage_percent > thresholds.CPU_WARNING_PERCENT or
        resource.memory_usage_percent > thresholds.MEMORY_WARNING_PERCENT or
        (resource.disk_usage_percent and resource.disk_usage_percent > thresholds.DISK_WARNING_PERCENT)):
        return HealthStatus.WARNING

    # Check for recent reboot
    if resource.uptime_seconds < thresholds.UPTIME_WARNING_SECONDS:
        return HealthStatus.WARNING

    return HealthStatus.HEALTHY
```

### Time-Series vs On-Demand Metrics

**Time-Series Metrics** (Phase 1: stored in database, Phase 4: time-series DB):
- System resource metrics (CPU, memory, uptime)
- Interface traffic counters (if available)
- NTP sync status
- Stored as `HealthCheck` records in database (Doc 18)
- Retention: 30 days per device, keep last 1000 records (Doc 05)

**On-Demand Metrics** (queried when MCP tool invoked):
- Interface list and status
- IP address assignments
- DNS configuration
- Routing table
- Firewall rules
- System logs
- Not stored in time-series, cached briefly (5-60s TTL)

**Snapshot Metrics** (captured during change events):
- Pre/post-change configuration snapshots
- Stored as `Snapshot` records (Doc 18)
- Retention: 30-90 days based on snapshot type (Doc 05)

---

## Collection Scheduling and Job Execution

### Scheduler Architecture

The metrics collector uses the job scheduler defined in Doc 05:

```python
from routeros_mcp.infra.jobs.scheduler import JobScheduler
from routeros_mcp.domain.models import Job

class MetricsCollector:
    """Periodic metrics collection scheduler."""

    def __init__(
        self,
        job_scheduler: JobScheduler,
        device_repo: DeviceRepository,
        health_repo: HealthCheckRepository
    ):
        self.scheduler = job_scheduler
        self.device_repo = device_repo
        self.health_repo = health_repo

    async def start(self):
        """Start periodic metrics collection for all devices."""
        devices = await self.device_repo.list_active()

        for device in devices:
            # Schedule health check job (high priority)
            await self.scheduler.schedule(
                type="health_check",
                device_ids=[device.id],
                priority=10,  # High priority
                interval_seconds=60  # Every 60 seconds
            )

            # Schedule metrics collection job (normal priority)
            await self.scheduler.schedule(
                type="collect_metrics",
                device_ids=[device.id],
                priority=5,  # Normal priority
                interval_seconds=300  # Every 5 minutes
            )

    async def execute_health_check(
        self,
        device_id: str,
        correlation_id: str | None = None,
        trigger: str = "scheduled"
    ):
        """Execute health check for a single device.

        Args:
            device_id: Target device ID
            correlation_id: Optional correlation ID from triggering MCP request
            trigger: What initiated this check ("scheduled", "mcp_tool", "plan_validation", "manual")
        """
        # 1. Fetch system resource metrics
        resource = await self.fetch_system_resource(device_id)

        # 2. Assess health status
        status = assess_health(resource, HealthThresholds())

        # 3. Store health check result (MCP-compatible format in metadata)
        health_check = HealthCheck(
            id=generate_id(),
            device_id=device_id,
            timestamp=datetime.utcnow(),
            status=status,
            cpu_usage_percent=resource.cpu_usage_percent,
            memory_usage_percent=resource.memory_usage_percent,
            uptime_seconds=resource.uptime_seconds,
            routeros_version=resource.routeros_version,
            correlation_id=correlation_id,  # Link to MCP request
            check_type="resource",
            response_time_ms=resource.response_time_ms if hasattr(resource, 'response_time_ms') else None,
            metadata={
                "trigger": trigger,  # Track what initiated this check
                "cpu_count": resource.cpu_count,
                "memory_total_bytes": resource.memory_total_bytes,
                "memory_free_bytes": resource.memory_free_bytes,
                "disk_total_bytes": resource.disk_total_bytes,
                "disk_free_bytes": resource.disk_free_bytes
            }
        )
        await self.health_repo.create(health_check)

        # 4. Update device status if changed
        await self.device_repo.update_status(device_id, status)

        # 5. Update MCP resource cache (if Phase 2+)
        await self.update_resource_cache(device_id, health_check, resource)
```

### Collection Intervals

**Phase 1 Collection Intervals** (single-user, up to 10 devices):

| Metric Type | Interval | Rationale |
|-------------|----------|-----------|
| System resource (health check) | 60s | Critical for health monitoring |
| NTP sync status | 60s | Time sync is critical |
| Interface list/status | 60s | Network connectivity monitoring |
| IP addresses | 300s (5min) | Changes infrequently |
| DNS configuration | 300s (5min) | Changes infrequently |
| Routing table | 300s (5min) | Changes infrequently unless dynamic |
| Static config (packages, hardware) | 3600s (1hr) | Changes very rarely |
| Firewall rules | On-demand | Only when MCP tool invoked |
| Logs | On-demand | Only when MCP tool invoked |

**Jitter**: All scheduled jobs include ±10% randomized jitter to avoid thundering herd effects.

**Phase 4 Adjustments** (multi-user, 100+ devices):
- Increase intervals for non-critical metrics (e.g., 120s health checks)
- Implement adaptive polling based on device class/priority
- Add time-series database for efficient storage

### Backoff Strategies

**Exponential Backoff on Failures**:

```python
class CollectionBackoff:
    """Backoff strategy for failed collection attempts."""

    def __init__(self):
        self.base_interval = 60  # Default interval
        self.max_interval = 600  # Max 10 minutes
        self.failure_count = 0

    def next_interval(self) -> int:
        """Calculate next collection interval after failure."""
        if self.failure_count == 0:
            return self.base_interval

        # Exponential backoff: base * 2^failures, capped at max
        interval = min(
            self.base_interval * (2 ** self.failure_count),
            self.max_interval
        )
        return interval

    def record_failure(self):
        """Record a collection failure."""
        self.failure_count += 1

    def reset(self):
        """Reset backoff after successful collection."""
        self.failure_count = 0
```

**Device Status Transitions on Repeated Failures**:

```python
# After 3 consecutive failures (180s): Mark as "degraded"
if failure_count >= 3:
    await device_repo.update_status(device_id, "degraded")
    await health_repo.create(
        device_id=device_id,
        status="warning",
        metadata={"reason": "connection_failures", "count": failure_count}
    )

# After 10 consecutive failures (600s): Mark as "unreachable"
if failure_count >= 10:
    await device_repo.update_status(device_id, "unreachable")
    await health_repo.create(
        device_id=device_id,
        status="error",
        metadata={"reason": "device_unreachable", "count": failure_count}
    )
    # Stop scheduled collection (manual intervention required)
    await scheduler.cancel_jobs(device_id)
```

---

## Storage and Retention

### Phase 1 Storage Strategy (SQLite)

**Database Tables** (from Doc 18):

1. **HealthCheck** - Time-series health check results
   ```sql
   CREATE TABLE health_checks (
       id TEXT PRIMARY KEY,
       device_id TEXT NOT NULL REFERENCES devices(id),
       timestamp TIMESTAMP NOT NULL,
       status TEXT NOT NULL,  -- healthy, warning, critical, error
       cpu_usage_percent REAL,
       memory_usage_percent REAL,
       uptime_seconds INTEGER,
       routeros_version TEXT,
       metadata JSON,
       created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
   );

   CREATE INDEX idx_health_checks_device_timestamp
       ON health_checks(device_id, timestamp DESC);
   ```

2. **Snapshot** - Configuration snapshots (pre/post-change)
   ```sql
   CREATE TABLE snapshots (
       id TEXT PRIMARY KEY,
       device_id TEXT NOT NULL REFERENCES devices(id),
       timestamp TIMESTAMP NOT NULL,
       snapshot_type TEXT NOT NULL,  -- routine, pre_change, post_change
       trigger TEXT,  -- health_check, plan_apply, manual
       payload TEXT,  -- Full config export
       metadata JSON,
       created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
   );
   ```

### Retention Policies (from Doc 05)

| Entity | Retention Period | Cleanup Strategy |
|--------|------------------|------------------|
| HealthCheck | 30 days per device | Keep last 1000 records per device, delete older |
| Snapshot (routine) | 7 days | Delete payload, keep metadata 30 days |
| Snapshot (change-related) | 30 days | Delete payload, keep metadata 90 days |

**Retention Enforcement Job**:

```python
async def cleanup_old_health_checks(device_id: str):
    """Retain last 1000 health checks per device, delete older."""
    await db.execute("""
        DELETE FROM health_checks
        WHERE device_id = :device_id
          AND id NOT IN (
              SELECT id FROM health_checks
              WHERE device_id = :device_id
              ORDER BY timestamp DESC
              LIMIT 1000
          )
    """, {"device_id": device_id})

async def cleanup_old_snapshots():
    """Delete snapshot payloads after retention period."""
    # Routine snapshots: 7 days
    await db.execute("""
        UPDATE snapshots
        SET payload = NULL
        WHERE snapshot_type = 'routine'
          AND timestamp < NOW() - INTERVAL '7 days'
          AND payload IS NOT NULL
    """)

    # Change-related snapshots: 30 days
    await db.execute("""
        UPDATE snapshots
        SET payload = NULL
        WHERE snapshot_type IN ('pre_change', 'post_change')
          AND timestamp < NOW() - INTERVAL '30 days'
          AND payload IS NOT NULL
    """)
```

**Scheduled Cleanup**: Retention cleanup job runs daily at 02:00 UTC.

### Phase 4 Time-Series Database (PostgreSQL + TimescaleDB)

**TimescaleDB Hypertable** (Phase 4):

```sql
-- Convert health_checks to TimescaleDB hypertable
SELECT create_hypertable('health_checks', 'timestamp');

-- Automatic data retention policy
SELECT add_retention_policy('health_checks', INTERVAL '30 days');

-- Continuous aggregates for dashboards
CREATE MATERIALIZED VIEW health_checks_hourly
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', timestamp) AS hour,
    device_id,
    avg(cpu_usage_percent) AS avg_cpu,
    max(cpu_usage_percent) AS max_cpu,
    avg(memory_usage_percent) AS avg_memory,
    max(memory_usage_percent) AS max_memory
FROM health_checks
GROUP BY hour, device_id;
```

---

## MCP Tool Exposure

Metrics and health data are exposed via read-only MCP tools (Phase 1 - Fundamental tier):

### Device Health Tools

**`device/check-connectivity`** (Doc 04):
- Tests connectivity to a single device
- Returns health status and basic metrics
- On-demand (not scheduled)

**Example**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tools/call",
  "params": {
    "name": "device/check-connectivity",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}

// Response
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "content": [{"type": "text", "text": "Device dev-lab-01 is reachable"}],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "reachable": true,
      "latency_ms": 15.2,
      "status": "healthy"
    }
  }
}
```

### System Metrics Tools

**`system/get-overview`** (Doc 04):
- Returns comprehensive system information
- Combines `/rest/system/resource`, `/rest/system/identity`, `/rest/system/routerboard`
- Cached for 60s (health check interval)

**Example**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "method": "tools/call",
  "params": {
    "name": "system/get-overview",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}

// Response includes _meta with full SystemResource normalized data
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "result": {
    "content": [{"type": "text", "text": "System overview for router-lab-01..."}],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "identity": "router-lab-01",
      "routeros_version": "7.10.1 (stable)",
      "hardware_model": "RB5009UG+S+",
      "uptime_seconds": 864000,
      "cpu": {
        "usage_percent": 5.2,
        "count": 4
      },
      "memory": {
        "total_bytes": 536870912,
        "free_bytes": 268435456,
        "used_bytes": 268435456,
        "usage_percent": 50.0
      }
    }
  }
}
```

### Interface Metrics Tools

**`interface/list-interfaces`** (Doc 04):
- Lists all interfaces with status
- Calls `/rest/interface`
- Cached for 60s
- **Supports pagination**: `limit` (default: 100, max: 1000), `offset` parameters
- **Token estimation**: ~50 tokens per interface, warns if >100 interfaces

**`interface/get-stats`** (Doc 04):
- Returns real-time traffic statistics
- Calls `/rest/interface/monitor-traffic`
- Not cached (real-time)
- **Bounded**: Returns stats for specified interface only (required parameter)

### Fleet Health Tools (Phase 1/2)

**`logs/get-recent`** (Doc 04):
- Returns recent log entries (bounded)
- Calls `/rest/log` with limit and filters
- On-demand only

**Integration with Plan/Apply Workflows** (Phase 2+):

Pre-change health checks:
```python
async def validate_device_before_change(device_id: str) -> bool:
    """Validate device health before applying changes."""
    # Get latest health check
    health = await health_repo.get_latest(device_id)

    # Reject if device unhealthy
    if health.status in ["critical", "error"]:
        raise ValidationError(
            f"Device {device_id} is {health.status}, cannot apply changes"
        )

    # Warn if degraded
    if health.status == "warning":
        logger.warning(
            f"Device {device_id} is {health.status}, proceeding with caution",
            device_id=device_id,
            cpu_usage=health.cpu_usage_percent,
            memory_usage=health.memory_usage_percent
        )

    return True
```

Post-change validation:
```python
async def validate_device_after_change(device_id: str, pre_change_snapshot: Snapshot) -> bool:
    """Validate device health after applying changes."""
    # Wait for health check to run
    await asyncio.sleep(65)  # Wait for next health check

    # Get post-change health
    post_health = await health_repo.get_latest(device_id)

    # Compare CPU usage (should not increase significantly)
    if post_health.cpu_usage_percent > pre_change_snapshot.metadata["cpu_usage_percent"] + 20:
        logger.error(
            "CPU usage increased significantly after change",
            device_id=device_id,
            pre_cpu=pre_change_snapshot.metadata["cpu_usage_percent"],
            post_cpu=post_health.cpu_usage_percent
        )
        return False

    return True
```

---

## Protections Against Over-Polling and RouterOS Overload

### Per-Device Concurrency and Rate Limiting

**Concurrency Control** (from Doc 03):

```python
from asyncio import Semaphore

class DeviceRateLimiter:
    """Per-device concurrency and rate limiting."""

    def __init__(self):
        # Max concurrent requests per device
        self.semaphores: dict[str, Semaphore] = {}
        self.max_concurrent = 2  # Phase 1: Conservative limit

    async def acquire(self, device_id: str):
        """Acquire semaphore for device."""
        if device_id not in self.semaphores:
            self.semaphores[device_id] = Semaphore(self.max_concurrent)

        return await self.semaphores[device_id].acquire()

    def release(self, device_id: str):
        """Release semaphore for device."""
        if device_id in self.semaphores:
            self.semaphores[device_id].release()

# Usage in RouterOS client
async def call_rest_api(device_id: str, endpoint: str):
    """Call RouterOS REST API with concurrency control."""
    await rate_limiter.acquire(device_id)
    try:
        response = await httpx_client.get(
            f"https://{device.management_address}{endpoint}",
            timeout=5.0
        )
        return response.json()
    finally:
        rate_limiter.release(device_id)
```

**Rate Limiting**:

```python
from asyncio import Lock
from datetime import datetime, timedelta

class TokenBucket:
    """Token bucket rate limiter."""

    def __init__(self, rate: int, capacity: int):
        self.rate = rate          # Tokens per second
        self.capacity = capacity  # Bucket capacity
        self.tokens = capacity
        self.last_update = datetime.utcnow()
        self.lock = Lock()

    async def consume(self, tokens: int = 1) -> bool:
        """Consume tokens from bucket."""
        async with self.lock:
            now = datetime.utcnow()
            elapsed = (now - self.last_update).total_seconds()

            # Refill tokens
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now

            # Check if enough tokens
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True

            return False

# Per-device rate limiters
device_rate_limiters: dict[str, TokenBucket] = {}

async def rate_limit_device(device_id: str):
    """Apply rate limiting to device requests."""
    if device_id not in device_rate_limiters:
        # Phase 1: 5 requests/second per device (conservative)
        device_rate_limiters[device_id] = TokenBucket(rate=5, capacity=10)

    while not await device_rate_limiters[device_id].consume():
        await asyncio.sleep(0.1)  # Wait for tokens
```

### Query Bounding and Timeouts

**All REST API calls use**:

1. **Timeouts** (from Doc 03):
   - Connect timeout: 3 seconds
   - Read timeout: 5 seconds
   - Total timeout: 10 seconds

2. **Pagination and Limits**:
   ```python
   # Limit results for expensive queries
   async def get_firewall_rules(device_id: str, limit: int = 100):
       """Get firewall rules with limit."""
       endpoint = f"/rest/ip/firewall/filter?limit={limit}"
       return await call_rest_api(device_id, endpoint)

   # Bounded log queries
   async def get_logs(device_id: str, limit: int = 50, topics: list[str] | None = None):
       """Get recent logs with bounded results."""
       query_params = f"?limit={limit}"
       if topics:
           query_params += f"&topics={','.join(topics)}"

       endpoint = f"/rest/log{query_params}"
       return await call_rest_api(device_id, endpoint)
   ```

3. **Retries with Exponential Backoff** (from Doc 03):
   ```python
   from tenacity import retry, stop_after_attempt, wait_exponential

   @retry(
       stop=stop_after_attempt(3),
       wait=wait_exponential(multiplier=1, min=1, max=10),
       reraise=True
   )
   async def fetch_with_retry(device_id: str, endpoint: str):
       """Fetch from RouterOS with retries on transient errors."""
       try:
           return await call_rest_api(device_id, endpoint)
       except (TimeoutError, ConnectionError) as e:
           logger.warning(
               "Transient error fetching from device, retrying",
               device_id=device_id,
               endpoint=endpoint,
               error=str(e)
           )
           raise  # Retry
       except Exception as e:
           logger.error(
               "Permanent error fetching from device",
               device_id=device_id,
               endpoint=endpoint,
               error=str(e)
           )
           raise  # No retry
   ```

### Adaptive Polling for Degraded Devices

**Reduce collection frequency for unhealthy devices**:

```python
async def adjust_collection_interval(device_id: str, status: str):
    """Adjust collection interval based on device health."""
    if status == "healthy":
        # Normal interval
        interval = 60
    elif status == "warning":
        # Slightly increased interval
        interval = 90
    elif status == "degraded":
        # Reduced polling
        interval = 180
    elif status in ["critical", "unreachable"]:
        # Minimal polling or stop
        interval = 300

    await scheduler.update_job_interval(
        device_id=device_id,
        job_type="health_check",
        interval_seconds=interval
    )
```

### Coordination Between Scheduled Jobs and MCP Tool Requests

**Problem**: When an MCP tool requests device metrics, we don't want to trigger a duplicate health check if one just ran 5 seconds ago via scheduled collection.

**Solution**: Use resource cache as coordination mechanism (Phase 2):

```python
async def get_device_health_coordinated(
    device_id: str,
    correlation_id: str | None = None,
    max_age_seconds: int = 30
) -> dict:
    """Get device health with coordination between scheduled and on-demand checks.

    Args:
        device_id: Target device ID
        correlation_id: MCP request correlation ID
        max_age_seconds: Maximum age of cached data before triggering new check

    Returns:
        Health data dict
    """
    resource_cache = get_resource_cache()

    # 1. Check resource cache first
    cached_health = await resource_cache.get_device_health(device_id)

    if cached_health:
        cached_at = datetime.fromisoformat(cached_health["_meta"]["cached_at"])
        age_seconds = (datetime.utcnow() - cached_at).total_seconds()

        # Use cached data if recent enough
        if age_seconds < max_age_seconds:
            logger.debug(
                "Using cached health data",
                correlation_id=correlation_id,
                device_id=device_id,
                age_seconds=age_seconds,
                cached_trigger=cached_health["_meta"]["trigger"]
            )
            return cached_health

    # 2. Acquire per-device lock to prevent duplicate checks
    async with device_health_locks.get_lock(device_id):
        # Double-check cache (another request may have refreshed it)
        cached_health = await resource_cache.get_device_health(device_id)
        if cached_health:
            cached_at = datetime.fromisoformat(cached_health["_meta"]["cached_at"])
            age_seconds = (datetime.utcnow() - cached_at).total_seconds()
            if age_seconds < max_age_seconds:
                return cached_health

        # 3. Trigger on-demand health check
        logger.info(
            "Triggering on-demand health check",
            correlation_id=correlation_id,
            device_id=device_id,
            reason="cache_miss_or_stale"
        )

        await metrics_collector.execute_health_check(
            device_id=device_id,
            correlation_id=correlation_id,
            trigger="mcp_tool"
        )

        # 4. Return newly cached data
        return await resource_cache.get_device_health(device_id)

# Per-device locks to prevent duplicate checks
from asyncio import Lock

class DeviceHealthLocks:
    """Per-device locks for coordinating health check access."""

    def __init__(self):
        self.locks: dict[str, Lock] = {}

    def get_lock(self, device_id: str) -> Lock:
        """Get or create lock for device."""
        if device_id not in self.locks:
            self.locks[device_id] = Lock()
        return self.locks[device_id]

device_health_locks = DeviceHealthLocks()
```

**Benefits**:
- Scheduled health checks populate cache every 60s
- MCP tools use cached data if <30s old (configurable)
- On cache miss/staleness, MCP tool triggers on-demand check
- Per-device locks prevent concurrent duplicate checks
- All checks update resource cache for other consumers
- Correlation ID tracks whether check was scheduled or on-demand

### Metrics Collection Safety Checklist

**Before adding a new metric**:

- [ ] **REST endpoint exists** in Doc 03 endpoint mappings
- [ ] **MCP tool defined** in Doc 04 with proper tier and phase
- [ ] **Bounded query**: Uses limit, pagination, or filters
- [ ] **Timeout configured**: 5-10s max per request
- [ ] **Collection interval justified**: Not more frequent than necessary
- [ ] **Retention policy defined**: Data lifecycle in Doc 05
- [ ] **Normalization documented**: Field mappings and types
- [ ] **Error handling**: Graceful degradation on failures
- [ ] **Rate limiting**: Respects per-device concurrency limits
- [ ] **Health impact assessed**: Won't overload small routers

**MCP-Specific Checklist** (Phase 2+):

- [ ] **Correlation ID propagation**: Health checks link to triggering MCP requests
- [ ] **Resource cache integration**: Metrics update MCP resource cache (Doc 05)
- [ ] **Token budget estimated**: Large responses include token warnings
- [ ] **Pagination support**: List operations support limit/offset parameters
- [ ] **Trigger tracking**: Health checks record trigger source ("scheduled", "mcp_tool", etc.)
- [ ] **MCP response format**: Tool responses use {content, _meta} structure
- [ ] **Cache coordination**: Avoid duplicate polling when MCP tools access cached data

---

## Error Handling and Observability

### Error Classification (from Doc 19)

Metrics collection errors are classified and logged per Doc 19:

```python
from routeros_mcp.domain.errors import (
    DeviceUnreachableError,
    DeviceTimeoutError,
    DeviceAuthenticationError,
    InvalidResponseError
)

async def collect_metrics_safe(device_id: str):
    """Collect metrics with comprehensive error handling."""
    try:
        resource = await fetch_system_resource(device_id)
        status = assess_health(resource, HealthThresholds())

        await health_repo.create(
            device_id=device_id,
            status=status,
            cpu_usage_percent=resource.cpu_usage_percent,
            memory_usage_percent=resource.memory_usage_percent,
            # ...
        )

        return {"status": "success"}

    except DeviceUnreachableError as e:
        logger.error("Device unreachable", device_id=device_id, error=str(e))
        await health_repo.create(
            device_id=device_id,
            status="error",
            metadata={"error": "device_unreachable", "details": str(e)}
        )
        return {"status": "failed", "error": "DEVICE_UNREACHABLE"}

    except DeviceTimeoutError as e:
        logger.warning("Device timeout", device_id=device_id, error=str(e))
        await health_repo.create(
            device_id=device_id,
            status="warning",
            metadata={"error": "timeout", "details": str(e)}
        )
        return {"status": "failed", "error": "DEVICE_TIMEOUT"}

    except DeviceAuthenticationError as e:
        logger.error("Authentication failed", device_id=device_id, error=str(e))
        await device_repo.update_status(device_id, "unreachable")
        return {"status": "failed", "error": "AUTHENTICATION_FAILED"}

    except InvalidResponseError as e:
        logger.error("Invalid response from device", device_id=device_id, error=str(e))
        return {"status": "failed", "error": "INVALID_RESPONSE"}
```

### Observability

**Structured Logging** (all metrics collection events):

```python
from contextvars import ContextVar

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

logger.info(
    "Health check completed",
    correlation_id=correlation_id_var.get(),  # Include correlation ID for tracing
    device_id=device_id,
    status=health_status,
    cpu_usage=cpu_usage_percent,
    memory_usage=memory_usage_percent,
    duration_ms=duration_ms,
    trigger=trigger  # "scheduled", "mcp_tool", "plan_validation"
)
```

**Prometheus Metrics** (Phase 2+):

```python
from prometheus_client import Counter, Histogram, Gauge

# Collection metrics
health_checks_total = Counter(
    "routeros_health_checks_total",
    "Total health checks executed",
    ["device_id", "status"]
)

health_check_duration = Histogram(
    "routeros_health_check_duration_seconds",
    "Health check duration",
    ["device_id"]
)

device_cpu_usage = Gauge(
    "routeros_device_cpu_usage_percent",
    "Device CPU usage",
    ["device_id"]
)

device_memory_usage = Gauge(
    "routeros_device_memory_usage_percent",
    "Device memory usage",
    ["device_id"]
)
```

---

## MCP Resource Cache Integration (Phase 2)

### Resource Cache for Metrics Data

Building on the ResourceCache design from Doc 05, metrics collection integrates with the MCP resource cache to provide efficient access to device health and metrics data via MCP resources.

**Resource URI Mappings**:

| MCP Resource URI | Cache Key | TTL | Refresh Strategy |
|------------------|-----------|-----|------------------|
| `device://{id}/health` | `device_health:{id}` | 60s | Background job (health_check) |
| `device://{id}/metrics` | `device_metrics:{id}` | 60s | Background job (collect_metrics) |
| `device://{id}/interfaces` | `device_interfaces:{id}` | 60s | On-demand with cache |
| `fleet://health-summary` | `fleet_health` | 120s | Background aggregation |

**Integration with Health Check Execution**:

```python
async def update_resource_cache(
    self,
    device_id: str,
    health_check: HealthCheck,
    resource: SystemResource
):
    """Update MCP resource cache after health check.

    Called from execute_health_check() to ensure resource cache reflects
    latest metrics data.
    """
    resource_cache = get_resource_cache()

    # Build resource-compatible health data
    health_data = {
        "uri": f"device://{device_id}/health",
        "name": f"Health Status - {resource.system_identity}",
        "description": f"Real-time health metrics for {resource.system_identity}",
        "mimeType": "application/json",
        "content": {
            "device_id": device_id,
            "status": health_check.status,
            "timestamp": health_check.timestamp.isoformat(),
            "uptime_seconds": health_check.uptime_seconds,
            "routeros_version": health_check.routeros_version,
            "cpu": {
                "usage_percent": health_check.cpu_usage_percent,
                "count": resource.cpu_count
            },
            "memory": {
                "total_bytes": resource.memory_total_bytes,
                "free_bytes": resource.memory_free_bytes,
                "used_bytes": resource.memory_used_bytes,
                "usage_percent": health_check.memory_usage_percent
            },
            "disk": {
                "total_bytes": resource.disk_total_bytes,
                "free_bytes": resource.disk_free_bytes,
                "usage_percent": resource.disk_usage_percent
            } if resource.disk_total_bytes else None
        },
        "_meta": {
            "correlation_id": health_check.correlation_id,
            "trigger": health_check.metadata.get("trigger", "scheduled"),
            "cached_at": datetime.utcnow().isoformat()
        }
    }

    # Cache with device_health:{id} key
    await resource_cache.set_device_health(device_id, health_data)

    logger.debug(
        "Updated resource cache for device health",
        correlation_id=health_check.correlation_id,
        device_id=device_id,
        status=health_check.status
    )
```

**MCP Resource Handler for Health Status**:

```python
from routeros_mcp.mcp.server import mcp_server

@mcp_server.list_resources()
async def list_health_resources() -> list[Resource]:
    """List available health monitoring resources."""
    resource_cache = get_resource_cache()
    devices = await device_repo.list_active()

    resources = []
    for device in devices:
        # Get cached health data
        health_data = await resource_cache.get_device_health(device.id)

        if health_data:
            resources.append(Resource(
                uri=f"device://{device.id}/health",
                name=f"Health Status - {device.name}",
                description=f"Real-time health metrics for {device.name}",
                mimeType="application/json"
            ))

    # Add fleet-wide summary
    resources.append(Resource(
        uri="fleet://health-summary",
        name="Fleet Health Summary",
        description="Aggregated health status across all devices",
        mimeType="application/json"
    ))

    return resources

@mcp_server.read_resource()
async def read_health_resource(uri: str) -> str:
    """Read health monitoring resource by URI."""
    resource_cache = get_resource_cache()

    if uri.startswith("device://"):
        # Extract device_id from URI: device://{id}/health
        parts = uri.replace("device://", "").split("/")
        device_id = parts[0]

        # Get from cache
        health_data = await resource_cache.get_device_health(device_id)

        if not health_data:
            # Cache miss - fetch fresh data
            device = await device_repo.get(device_id)
            if not device:
                raise ResourceNotFoundError(f"Device {device_id} not found")

            # Trigger on-demand health check
            await metrics_collector.execute_health_check(
                device_id=device_id,
                correlation_id=correlation_id_var.get(),
                trigger="mcp_resource"
            )

            # Retrieve newly cached data
            health_data = await resource_cache.get_device_health(device_id)

        return json.dumps(health_data["content"], indent=2)

    elif uri == "fleet://health-summary":
        # Get fleet summary from cache
        summary = await resource_cache.get_fleet_summary()
        return json.dumps(summary, indent=2)

    else:
        raise ResourceNotFoundError(f"Unknown resource URI: {uri}")
```

### Token Budget Management for Large Responses

**Token Estimation Utilities**:

```python
def estimate_metric_response_tokens(metric_type: str, count: int) -> int:
    """Estimate token count for metric responses.

    Args:
        metric_type: Type of metric ("interface", "firewall_rule", "log_entry", etc.)
        count: Number of items

    Returns:
        Estimated token count
    """
    # Token estimates per item type
    TOKEN_ESTIMATES = {
        "interface": 50,          # Interface with stats
        "firewall_rule": 80,      # Typical firewall rule
        "firewall_rule_complex": 200,  # Complex rule with multiple matchers
        "nat_rule": 60,
        "route": 40,
        "ip_address": 30,
        "log_entry": 40,
        "arp_entry": 25,
        "dns_cache_entry": 30
    }

    per_item = TOKEN_ESTIMATES.get(metric_type, 50)  # Default: 50 tokens/item
    return count * per_item

def check_token_budget_warning(
    metric_type: str,
    count: int,
    warning_threshold: int = 5000
) -> dict | None:
    """Check if metric response exceeds token budget warning threshold.

    Returns:
        Warning dict if threshold exceeded, None otherwise
    """
    estimated_tokens = estimate_metric_response_tokens(metric_type, count)

    if estimated_tokens > warning_threshold:
        return {
            "warning": "large_response",
            "estimated_tokens": estimated_tokens,
            "item_count": count,
            "metric_type": metric_type,
            "recommendation": f"Consider filtering or pagination (limit parameter) to reduce response size"
        }

    return None

# Example usage in MCP tool
async def list_firewall_rules(device_id: str, limit: int = 100, offset: int = 0):
    """List firewall rules with token budget warnings."""
    # Fetch rules
    rules = await fetch_firewall_rules(device_id, limit=limit, offset=offset)
    total_count = rules["total"]

    # Check token budget for full result set
    warning = check_token_budget_warning("firewall_rule", total_count)

    return {
        "content": [{"type": "text", "text": f"Found {len(rules['items'])} of {total_count} firewall rules"}],
        "isError": False,
        "_meta": {
            "device_id": device_id,
            "rules": rules["items"],
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "token_budget_warning": warning  # Include warning if present
        }
    }
```

**Automatic Pagination Recommendations**:

When MCP tools detect large result sets, they automatically recommend pagination:

```python
async def list_interfaces(device_id: str, limit: int = 100, offset: int = 0):
    """List network interfaces with automatic pagination recommendations."""
    interfaces = await fetch_interfaces(device_id)
    total_count = len(interfaces)

    # Check if pagination recommended
    pagination_info = {}
    if total_count > limit:
        pagination_info = {
            "total_count": total_count,
            "current_page_size": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count,
            "next_offset": offset + limit if (offset + limit) < total_count else None,
            "recommendation": f"Showing {limit} of {total_count} interfaces. Use 'offset' parameter to fetch more."
        }

    # Check token budget
    token_warning = check_token_budget_warning("interface", total_count)

    return {
        "content": [{"type": "text", "text": f"Found {total_count} interfaces on {device_id}"}],
        "isError": False,
        "_meta": {
            "device_id": device_id,
            "interfaces": interfaces[offset:offset+limit],
            "pagination": pagination_info,
            "token_budget_warning": token_warning
        }
    }
```

---

## Phase 1 vs Phase 4 Differences

### Phase 1: Single-User, Local Development

- **Storage**: SQLite with retention enforcement
- **Collection**: Scheduled jobs via job scheduler (Doc 05)
- **Devices**: Up to 10 devices
- **Intervals**: 60s health checks, 300s metrics
- **Exposure**: MCP tools only (stdio transport)
- **Retention**: 30 days health checks, 1000 records per device

### Phase 4: Multi-User, Production Scale

- **Storage**: PostgreSQL + TimescaleDB for time-series
- **Collection**: Distributed job queue (Celery, RQ)
- **Devices**: 100+ devices
- **Intervals**: Adaptive (60-300s) based on device class/priority
- **Exposure**: MCP tools + HTTP API + dashboards
- **Retention**: 90 days with continuous aggregates
- **Advanced Features**:
  - Anomaly detection (ML-based)
  - Predictive alerts (trend analysis)
  - Fleet-wide dashboards
  - Capacity planning reports

---

## Summary

The metrics collection module provides:

✅ **Comprehensive coverage** of RouterOS REST endpoints per Doc 03
✅ **Normalized data model** with strong typing and validation
✅ **Health assessment** with configurable thresholds
✅ **Scheduled collection** via job scheduler (Doc 05)
✅ **MCP tool exposure** for read-only access (Doc 04)
✅ **Protection mechanisms** against over-polling and device overload
✅ **Error handling** per Doc 19 error code specification
✅ **Retention policies** aligned with Doc 05 lifecycle management
✅ **Phase 1 focus**: Single-user, SQLite, up to 10 devices
✅ **Phase 4 path**: TimescaleDB, distributed jobs, 100+ devices

**MCP Integration Enhancements** (Phase 2):

✅ **Correlation ID propagation** - Health checks link to triggering MCP requests for end-to-end tracing
✅ **MCP Resource Cache integration** - Metrics populate resource cache for efficient MCP resource access
✅ **Token budget management** - Automatic estimation and warnings for large metric responses
✅ **Pagination support** - All list operations support limit/offset parameters with total_count
✅ **Trigger tracking** - Health checks record trigger source (scheduled vs mcp_tool vs plan_validation)
✅ **Cache coordination** - Per-device locks prevent duplicate polling between scheduled jobs and MCP tools
✅ **Structured logging with correlation** - All metrics events include correlation_id for observability

**This module is implementation-ready for Phase 1 with comprehensive MCP integration patterns for Phase 2 and a clear evolution path to Phase 4.**

---

**Cross-References**:
- Doc 03: RouterOS Integration & Platform Constraints (REST endpoint mappings)
- Doc 04: MCP Tools Interface (tool catalog and JSON-RPC schemas)
- Doc 05: Domain Model & Persistence (HealthCheck, Snapshot, Job entities)
- Doc 18: Database Schema & ORM (HealthCheck, Snapshot table definitions)
- Doc 19: JSON-RPC Error Codes (error handling specification)
