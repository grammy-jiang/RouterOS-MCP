# RouterOS Integration & Platform Constraints (REST & SSH)

## Purpose

Specify how the service interacts with RouterOS v7 via REST API as the primary channel and SSH/CLI as tightly-scoped fallback, including error handling, idempotency, capability coverage, and RouterOS-specific constraints and quirks.

---

## RouterOS REST Endpoint Summary

This section provides a comprehensive summary of all RouterOS v7 REST API endpoints used by the MCP service, organized by topic.

**Related Documents:**

- [Doc 04: MCP Tools Interface](04-mcp-tools-interface-and-json-schema-specification.md) - Tool-to-endpoint mapping
- [Doc 06: System Information & Metrics Collection](06-system-information-and-metrics-collection-module-design.md) - Metrics collection patterns

### Complete Endpoint Catalog

| Method         | Endpoint                              | Topic     | Purpose                             | MCP Tier     | Phase |
| -------------- | ------------------------------------- | --------- | ----------------------------------- | ------------ | ----- |
| **System**     |
| GET            | `/rest/system/resource`               | System    | CPU, memory, uptime, version        | Fundamental  | 1     |
| GET            | `/rest/system/identity`               | System    | Device name/identity                | Fundamental  | 1     |
| PUT/PATCH      | `/rest/system/identity`               | System    | Change device name                  | Advanced     | 2     |
| GET            | `/rest/system/routerboard`            | System    | Hardware model, serial              | Fundamental  | 1     |
| GET            | `/rest/system/package`                | System    | Installed packages                  | Fundamental  | 1     |
| GET            | `/rest/system/clock`                  | System    | Current time and timezone           | Fundamental  | 1     |
| **Interface**  |
| GET            | `/rest/interface`                     | Interface | List all interfaces                 | Fundamental  | 1     |
| GET            | `/rest/interface/{id}`                | Interface | Get specific interface              | Fundamental  | 1     |
| PATCH          | `/rest/interface/{id}`                | Interface | Update interface (comment, disable) | Advanced     | 2     |
| GET            | `/rest/interface/monitor-traffic`     | Interface | Real-time traffic stats             | Fundamental  | 1     |
| **IP Address** |
| GET            | `/rest/ip/address`                    | IP        | List all IP addresses               | Fundamental  | 1     |
| GET            | `/rest/ip/address/{id}`               | IP        | Get specific address                | Fundamental  | 1     |
| PUT            | `/rest/ip/address`                    | IP        | Add new IP address                  | Advanced     | 3     |
| DELETE         | `/rest/ip/address/{id}`               | IP        | Remove IP address                   | Professional | 3     |
| GET            | `/rest/ip/arp`                        | IP        | ARP table                           | Fundamental  | 1     |
| **DNS**        |
| GET            | `/rest/ip/dns`                        | DNS       | DNS server configuration            | Fundamental  | 1     |
| PUT/PATCH      | `/rest/ip/dns`                        | DNS       | Update DNS servers                  | Advanced     | 2     |
| GET            | `/rest/ip/dns/cache`                  | DNS       | View DNS cache                      | Fundamental  | 1     |
| POST           | `/rest/ip/dns/cache/flush`            | DNS       | Clear DNS cache                     | Advanced     | 2     |
| **NTP**        |
| GET            | `/rest/system/ntp/client`             | NTP       | NTP configuration                   | Fundamental  | 1     |
| PUT/PATCH      | `/rest/system/ntp/client`             | NTP       | Update NTP servers                  | Advanced     | 2     |
| GET            | `/rest/system/ntp/client/monitor`     | NTP       | NTP sync status                     | Fundamental  | 1     |
| **Routing**    |
| GET            | `/rest/ip/route`                      | Routing   | Routing table                       | Fundamental  | 1     |
| GET            | `/rest/ip/route/{id}`                 | Routing   | Get specific route                  | Fundamental  | 1     |
| PUT            | `/rest/ip/route`                      | Routing   | Add static route                    | Professional | 4     |
| DELETE         | `/rest/ip/route/{id}`                 | Routing   | Delete route                        | Professional | 4     |
| **Firewall**   |
| GET            | `/rest/ip/firewall/filter`            | Firewall  | Firewall filter rules               | Fundamental  | 1     |
| GET            | `/rest/ip/firewall/nat`               | Firewall  | NAT rules                           | Fundamental  | 1     |
| GET            | `/rest/ip/firewall/address-list`      | Firewall  | Address lists                       | Fundamental  | 1     |
| PUT            | `/rest/ip/firewall/address-list`      | Firewall  | Add address-list entry              | Advanced     | 2     |
| DELETE         | `/rest/ip/firewall/address-list/{id}` | Firewall  | Remove address-list entry           | Advanced     | 2     |
| **Logging**    |
| GET            | `/rest/log`                           | Logging   | System logs (bounded)               | Fundamental  | 1     |
| GET            | `/rest/system/logging`                | Logging   | Logging configuration               | Fundamental  | 1     |

**Total: 38 endpoints (Phase 1 scope)** (22 read-only fundamental, 10 advanced writes, 6 professional/high-risk). Diagnostics endpoints (ping/traceroute/bandwidth-test) are **deferred to Phase 3** and excluded from Phase 1-2 scope.

### Endpoint Categories

**Fundamental Tier (Read-Only):** 22 endpoints

- Safe for broad access
- No device configuration changes

**Advanced Tier (Single-Device Writes):** 10 endpoints

- Low-risk configuration changes
- Single-device scope
- Includes DNS/NTP updates, interface comments, address-list management

**Professional Tier (High-Risk):** 6 endpoints

- High-risk operations requiring plan/apply workflow
- Routing changes, IP address deletion
- Requires human approval in production

### Topic Distribution

| Topic       | Endpoints | Read-Only | Write Operations |
| ----------- | --------- | --------- | ---------------- |
| System      | 6         | 5         | 1                |
| Interface   | 4         | 3         | 1                |
| IP Address  | 5         | 3         | 2                |
| DNS         | 4         | 2         | 2                |
| NTP         | 3         | 2         | 1                |
| Routing     | 4         | 2         | 2                |
| Firewall    | 5         | 3         | 2                |
| Logging     | 2         | 2         | 0                |
| Diagnostics | Deferred  | Deferred  | Deferred         |

**Note:** MCP device management operations (device registration, updates) have no RouterOS endpoint - they are MCP-internal operations stored in the PostgreSQL database.

---

## RouterOS REST client design (HTTP library, retries, timeouts, auth)

- **HTTP client responsibilities**:

  - Handle HTTP(S) connections to RouterOS `/rest/...` endpoints.
  - Enforce timeouts, retries, backoff, and per-device concurrency limits.
  - Map low-level HTTP/network errors into domain-level error types for MCP tools.

- **Authentication**:
  - Use basic auth or RouterOS API tokens per device, based on configured credentials.
  - Credentials are retrieved from the secrets store, decrypted in-memory, and never logged.
    - Supported today: username/password (HTTP Basic) and API token presented as the password. No OAuth/OIDC to RouterOS.
      - Not supported by RouterOS REST: bearer tokens, OAuth/OIDC, client TLS cert auth, Kerberos/NTLM.
      - Phase 1 (current): MCP uses HTTP Basic with username/password or API token-as-password for REST; SSH fallback uses username/password only.
      - Phase 2: No change to REST auth (still Basic/token). SSH fallback will add optional SSH key authentication (see below).

**Future (Phase 2+)**: Add SSH key-based authentication support for the SSH fallback path. This will require:

- Extending the credential model to store SSH private key material (and optional passphrase) separately from passwords.
- Updating `RouterOSSSHClient` to attempt key auth before password auth when a key is present.
- Ensuring key material remains encrypted at rest, decrypted only in-memory, and never logged.
- Guardrails: keep the existing whitelisted-command enforcement and audit logging unchanged.

---

## Mandatory SSH Fallback Policy

**CRITICAL REQUIREMENT: ALL read-only REST API endpoints MUST implement SSH fallback.**

This policy ensures service resilience when REST API is unreachable or slow (timeouts > 10s).

### Fallback Activation Rules

1. **When to trigger SSH fallback:**

   - REST API call times out after 10 seconds
   - REST API returns 5xx server errors (connection refused, socket timeout, etc.)
   - REST API is explicitly disabled in configuration

2. **When NOT to trigger SSH fallback:**

   - REST API returns 4xx client errors (invalid auth, permission denied, malformed request)
   - Write operations (PUT, PATCH, DELETE) - these require REST API transactional safety
   - Commands requiring structured JSON response that SSH CLI cannot provide

3. **Read-only endpoints requiring SSH fallback:**
   - System info: `/rest/system/resource`, `/rest/system/identity`, `/rest/system/clock`, `/rest/system/package`
   - Network: `/rest/interface`, `/rest/interface/monitor-traffic`
   - IP/ARP: `/rest/ip/address`, `/rest/ip/arp`
   - DNS/NTP: `/rest/ip/dns`, `/rest/system/ntp/client`
   - Routing: `/rest/ip/route`
   - Firewall: `/rest/ip/firewall/filter`, `/rest/ip/firewall/nat`, `/rest/ip/firewall/address-list`
   - Logs/Diagnostics: `/rest/log`, `/rest/system/logging`

### Implementation Requirements

- **All domain services** (`routeros_mcp/domain/services/*.py`) implementing read-only endpoints MUST:

  1. Try REST API first (primary path)
  2. On timeout or 5xx: catch exception and attempt SSH fallback
  3. Log fallback activation with context (device, endpoint, reason)
  4. Parse SSH CLI output into the same response structure as REST
  5. Return unified response (client should not know which transport was used)

- **Fallback path must:**

  - Use whitelisted SSH commands only (defined in `ssh_client.py`)
  - Handle device-specific output variations (different RouterOS versions)
  - Provide equivalent data to REST response (exact field names, types)
  - **Parse ALL fields from RouterOS output** - no information should be lost between RouterOS and MCP server (multi-line values, continuation lines, optional fields must all be captured)
  - Include `transport: "ssh"` and `fallback_used: True` in response metadata

- **Never fallback for:**
  - Write operations (all mutations MUST use REST)
  - Commands with security implications (must enforce API auth/authz)
  - Operations requiring atomic multi-step transactions

### Expected Coverage

- **Phase 1 endpoints** (fundamental, read-only): 90%+ with SSH fallback
- **Advanced writes**: No SSH fallback (REST only, requires proper auth)
- **Professional/high-risk**: No SSH fallback (plan/apply workflow, REST only)

---

- Conservative timeouts for each REST call, configurable per deployment.
- Retries with exponential backoff for transient network or 5xx errors.
- No retries on clear 4xx errors (auth failure, forbidden, validation errors).

- **Per-device concurrency and rate limiting**:

  - Centralized per-device concurrency control: at most N in-flight REST calls per device (N default 2–3).
  - Per-device rate limiting to avoid overwhelming small routers, especially for health checks and metrics.

- **Connection pooling**:
  - Use `httpx.AsyncClient` with connection pooling for efficient HTTP/2 or HTTP/1.1 persistent connections.
  - Configure per-device pool limits (max connections per host) to prevent connection exhaustion.
  - Enable keep-alive for reduced handshake overhead on sequential requests.

**Implementation Example:**

```python
import httpx
from contextlib import asynccontextmanager

class RouterOSRestClient:
    """Async HTTP client for RouterOS REST API."""

    def __init__(self, device: Device):
        self.device = device
        self._client: httpx.AsyncClient | None = None

        # Connection pool settings
        self.limits = httpx.Limits(
            max_connections=5,        # Max total connections per device
            max_keepalive_connections=3,  # Max idle keep-alive connections
            keepalive_expiry=30.0     # Keep-alive timeout in seconds
        )

        # Timeout settings
        self.timeout = httpx.Timeout(
            connect=5.0,   # Connection timeout
            read=30.0,     # Read timeout
            write=10.0,    # Write timeout
            pool=5.0       # Pool acquisition timeout
        )

    @asynccontextmanager
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            auth = await self._get_device_credentials()
            self._client = httpx.AsyncClient(
                base_url=f"https://{self.device.host}:{self.device.port}",
                auth=auth,
                limits=self.limits,
                timeout=self.timeout,
                verify=self.device.verify_ssl,
                follow_redirects=False
            )

        try:
            yield self._client
        finally:
            # Keep client alive for connection reuse
            pass

    async def close(self):
        """Close HTTP client and cleanup connections."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get(self, path: str) -> dict:
        """Execute GET request with retries and error handling."""
        async with self.get_client() as client:
            for attempt in range(3):  # Max 3 retries
                try:
                    response = await client.get(path)
                    response.raise_for_status()
                    return response.json()

                except httpx.TimeoutException as e:
                    if attempt == 2:  # Last attempt
                        raise RouterOSTimeoutError(f"Timeout calling {path}") from e
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

                except httpx.HTTPStatusError as e:
                    # Don't retry on 4xx errors
                    if 400 <= e.response.status_code < 500:
                        raise RouterOSClientError(
                            f"Client error: {e.response.status_code}"
                        ) from e

                    # Retry on 5xx errors
                    if attempt == 2:
                        raise RouterOSServerError(
                            f"Server error: {e.response.status_code}"
                        ) from e
                    await asyncio.sleep(2 ** attempt)

                except httpx.NetworkError as e:
                    if attempt == 2:
                        raise RouterOSNetworkError(
                            f"Network error connecting to {self.device.host}"
                        ) from e
                    await asyncio.sleep(2 ** attempt)

    async def patch(self, path: str, data: dict) -> dict:
        """Execute PATCH request for updates."""
        async with self.get_client() as client:
            response = await client.patch(path, json=data)
            response.raise_for_status()
            return response.json()

    async def put(self, path: str, data: dict) -> dict:
        """Execute PUT request for creates."""
        async with self.get_client() as client:
            response = await client.put(path, json=data)
            response.raise_for_status()
            return response.json()
```

---

## Endpoint Mapping for Core Topics

### System Topic

**Endpoints:**

| Operation            | Method    | Path                       | Purpose                         | MCP Tool Tier |
| -------------------- | --------- | -------------------------- | ------------------------------- | ------------- |
| Get system resources | GET       | `/rest/system/resource`    | CPU, memory, uptime, version    | Fundamental   |
| Get system identity  | GET       | `/rest/system/identity`    | Device name/identity            | Fundamental   |
| Set system identity  | PUT/PATCH | `/rest/system/identity`    | Change device name              | Advanced      |
| Get routerboard info | GET       | `/rest/system/routerboard` | Hardware model, serial number   | Fundamental   |
| Get system package   | GET       | `/rest/system/package`     | Installed packages and versions | Fundamental   |
| Get system clock     | GET       | `/rest/system/clock`       | Current time and timezone       | Fundamental   |

**Field Mappings:**

```python
# /rest/system/resource response
{
    "uptime": "1w2d3h4m5s",          # → uptime_seconds: int
    "version": "7.10.1 (stable)",     # → routeros_version: str
    "cpu-load": 5,                    # → cpu_usage_percent: float
    "free-memory": 123456789,         # → memory_free_bytes: int
    "total-memory": 536870912,        # → memory_total_bytes: int
    "board-name": "RB5009UG+S+",      # → hardware_model: str
}

# /rest/system/identity response
{
    "name": "router-lab-01"           # → system_identity: str
}

# /rest/system/routerboard response
{
    "model": "RB5009UG+S+",           # → hardware_model: str
    "serial-number": "ABC12345678",   # → serial_number: str
    "firmware": "7.10"                # → firmware_version: str
}
```

---

### Interface Topic

**Endpoints:**

| Operation           | Method | Path                              | Purpose                             | MCP Tool Tier |
| ------------------- | ------ | --------------------------------- | ----------------------------------- | ------------- |
| List all interfaces | GET    | `/rest/interface`                 | Get all interfaces                  | Fundamental   |
| Get interface by ID | GET    | `/rest/interface/{id}`            | Get specific interface              | Fundamental   |
| Update interface    | PATCH  | `/rest/interface/{id}`            | Modify interface (comment, disable) | Advanced      |
| Get interface stats | GET    | `/rest/interface/monitor-traffic` | Real-time traffic stats             | Fundamental   |

**Field Mappings:**

```python
# /rest/interface response
{
    ".id": "*1",                      # → interface_id: str
    "name": "ether1",                 # → name: str
    "type": "ether",                  # → type: str (ether, bridge, vlan, etc.)
    "running": true,                  # → running: bool
    "disabled": false,                # → disabled: bool
    "comment": "WAN uplink",          # → comment: str
    "mtu": 1500,                      # → mtu: int
    "mac-address": "AA:BB:CC:DD:EE:FF" # → mac_address: str
}

# Allowed operations (Advanced tier - Phase 2):
# - Set comment: PATCH /rest/interface/{id} {"comment": "..."}
# - Enable/disable: PATCH /rest/interface/{id} {"disabled": true/false}
#
# Higher-risk operations (Phase 3):
# - Delete interfaces
# - MTU changes
# - Admin down (use disable instead)
```

---

### IP Address Topic

**Endpoints:**

| Operation         | Method | Path                    | Purpose              | MCP Tool Tier |
| ----------------- | ------ | ----------------------- | -------------------- | ------------- |
| List IP addresses | GET    | `/rest/ip/address`      | Get all IP addresses | Fundamental   |
| Get address by ID | GET    | `/rest/ip/address/{id}` | Get specific address | Fundamental   |
| Add IP address    | PUT    | `/rest/ip/address`      | Add new IP address   | Advanced      |
| Remove IP address | DELETE | `/rest/ip/address/{id}` | Remove IP address    | Professional  |
| Get ARP entries   | GET    | `/rest/ip/arp`          | ARP table            | Fundamental   |

**Field Mappings:**

```python
# /rest/ip/address response
{
    ".id": "*2",                      # → address_id: str
    "address": "192.168.1.1/24",      # → address: str (CIDR notation)
    "network": "192.168.1.0",         # → network: str
    "interface": "ether1",            # → interface: str
    "disabled": false,                # → disabled: bool
    "comment": "LAN gateway"          # → comment: str
}

# Add secondary IP (Advanced tier):
# PUT /rest/ip/address
# {
#     "address": "192.168.1.2/24",
#     "interface": "ether1",
#     "comment": "Secondary IP"
# }
```

---

### IP DNS Topic

**Endpoints:**

| Operation        | Method    | Path                       | Purpose                  | MCP Tool Tier |
| ---------------- | --------- | -------------------------- | ------------------------ | ------------- |
| Get DNS settings | GET       | `/rest/ip/dns`             | DNS server configuration | Fundamental   |
| Set DNS servers  | PUT/PATCH | `/rest/ip/dns`             | Update DNS servers       | Advanced      |
| Get DNS cache    | GET       | `/rest/ip/dns/cache`       | View DNS cache           | Fundamental   |
| Flush DNS cache  | POST      | `/rest/ip/dns/cache/flush` | Clear DNS cache          | Advanced      |

**Field Mappings:**

```python
# /rest/ip/dns response
{
    "servers": "8.8.8.8,8.8.4.4",     # → dns_servers: list[str]
    "allow-remote-requests": true,     # → allow_remote_requests: bool
    "cache-size": 2048,                # → cache_size_kb: int
    "cache-used": 156                  # → cache_used_kb: int
}

# Set DNS servers (Advanced tier, lab/staging only by default):
# PATCH /rest/ip/dns
# {
#     "servers": "1.1.1.1,1.0.0.1"
# }
```

---

### System NTP Client Topic

**Endpoints:**

| Operation             | Method    | Path                              | Purpose            | MCP Tool Tier |
| --------------------- | --------- | --------------------------------- | ------------------ | ------------- |
| Get NTP client config | GET       | `/rest/system/ntp/client`         | NTP configuration  | Fundamental   |
| Set NTP servers       | PUT/PATCH | `/rest/system/ntp/client`         | Update NTP servers | Advanced      |
| Get NTP client status | GET       | `/rest/system/ntp/client/monitor` | NTP sync status    | Fundamental   |

**Field Mappings:**

```python
# /rest/system/ntp/client response
{
    "enabled": true,                   # → enabled: bool
    "servers": "time.cloudflare.com,pool.ntp.org", # → ntp_servers: list[str]
    "mode": "unicast"                  # → mode: str
}

# /rest/system/ntp/client/monitor response
{
    "status": "synchronized",          # → status: str
    "stratum": 2,                      # → stratum: int
    "offset": "-0.002s"                # → offset_ms: float
}

# Set NTP servers (Advanced tier, lab/staging only by default):
# PATCH /rest/system/ntp/client
# {
#     "enabled": true,
#     "servers": "time.cloudflare.com"
# }
```

---

### IP Route Topic

**Endpoints:**

| Operation        | Method | Path                  | Purpose        | MCP Tool Tier |
| ---------------- | ------ | --------------------- | -------------- | ------------- |
| List routes      | GET    | `/rest/ip/route`      | Routing table  | Fundamental   |
| Get route by ID  | GET    | `/rest/ip/route/{id}` | Specific route | Fundamental   |
| Add static route | PUT    | `/rest/ip/route`      | Add route      | Professional  |
| Remove route     | DELETE | `/rest/ip/route/{id}` | Delete route   | Professional  |

**Field Mappings:**

```python
# /rest/ip/route response
{
    ".id": "*3",                       # → route_id: str
    "dst-address": "0.0.0.0/0",        # → dst_address: str
    "gateway": "192.168.1.254",        # → gateway: str
    "distance": 1,                     # → distance: int (admin distance)
    "scope": 30,                       # → scope: int
    "target-scope": 10,                # → target_scope: int
    "comment": "Default route"         # → comment: str
}

# Note: Route manipulation is Professional tier (high risk)
```

---

### IP Firewall Topic

**Endpoints:**

| Operation                 | Method | Path                                  | Purpose               | MCP Tool Tier |
| ------------------------- | ------ | ------------------------------------- | --------------------- | ------------- |
| List filter rules         | GET    | `/rest/ip/firewall/filter`            | Firewall filter rules | Fundamental   |
| List NAT rules            | GET    | `/rest/ip/firewall/nat`               | NAT rules             | Fundamental   |
| List address lists        | GET    | `/rest/ip/firewall/address-list`      | Address lists         | Fundamental   |
| Add address-list entry    | PUT    | `/rest/ip/firewall/address-list`      | Add to address list   | Advanced      |
| Remove address-list entry | DELETE | `/rest/ip/firewall/address-list/{id}` | Remove from list      | Advanced      |

**Field Mappings:**

```python
# /rest/ip/firewall/filter response
{
    ".id": "*4",                       # → rule_id: str
    "chain": "input",                  # → chain: str
    "action": "accept",                # → action: str
    "protocol": "tcp",                 # → protocol: str
    "dst-port": "22,8080",             # → dst_port: str
    "comment": "Allow SSH and HTTP",   # → comment: str
    "disabled": false                  # → disabled: bool
}

# /rest/ip/firewall/address-list response
{
    ".id": "*5",                       # → entry_id: str
    "list": "mcp-managed-hosts",       # → list_name: str
    "address": "10.0.1.100",           # → address: str
    "comment": "MCP server",           # → comment: str
    "timeout": "1d"                    # → timeout: str (optional)
}

# Note: Only MCP-owned address lists (prefix: "mcp-") can be modified
# Filter/NAT rule changes are Professional tier or disabled
```

---

### System Logging Topic

**Endpoints:**

| Operation       | Method | Path                   | Purpose               | MCP Tool Tier         |
| --------------- | ------ | ---------------------- | --------------------- | --------------------- |
| Get log entries | GET    | `/rest/log`            | System logs           | Fundamental (bounded) |
| Get log topics  | GET    | `/rest/system/logging` | Logging configuration | Fundamental           |

**Field Mappings:**

```python
# /rest/log response (with query params for filtering)
{
    ".id": "*6",                       # → log_id: str
    "time": "jan/15/2024 10:30:45",    # → timestamp: datetime
    "topics": "system,info",           # → topics: list[str]
    "message": "System started"        # → message: str
}

# Query parameters for bounded reads:
# GET /rest/log?limit=100&topics=system,error
# - limit: Max 1000 entries (MCP enforced)
# - topics: Filter by topics
# - No free-form log streaming (use bounded tail)

# Token budget consideration:
# Each log entry ~50-200 tokens depending on message length
# Max 1000 entries = ~50,000-200,000 tokens
# Recommend default limit of 100 entries (~5,000-20,000 tokens)
```

---

### Tool (Diagnostics) Topic _(Deferred to Phase 3)_

Diagnostics tools (ping/traceroute/bandwidth-test) are deferred to Phase 3 and are not part of Phase 1-2 implementation. The mappings below are retained for future planning only.

**Endpoints:**

| Operation      | Method | Path                        | Purpose            | MCP Tool Tier      |
| -------------- | ------ | --------------------------- | ------------------ | ------------------ |
| Ping           | POST   | `/rest/tool/ping`           | ICMP ping          | Phase 3 (deferred) |
| Traceroute     | POST   | `/rest/tool/traceroute`     | Network traceroute | Phase 3 (deferred) |
| Bandwidth test | POST   | `/rest/tool/bandwidth-test` | Speed test         | Phase 3 (deferred) |

**Field Mappings:**

```python
# POST /rest/tool/ping request
{
    "address": "8.8.8.8",              # Target IP/hostname
    "count": 4,                        # Number of pings (max 10)
    "interval": "1s"                   # Interval between pings
}

# Response (streaming or final summary)
{
    "host": "8.8.8.8",                 # → host: str
    "sent": 4,                         # → packets_sent: int
    "received": 4,                     # → packets_received: int
    "packet-loss": 0,                  # → packet_loss_percent: int
    "min-rtt": "10ms",                 # → min_rtt_ms: float
    "avg-rtt": "12ms",                 # → avg_rtt_ms: float
    "max-rtt": "15ms"                  # → max_rtt_ms: float
}

# POST /rest/tool/traceroute request
{
    "address": "8.8.8.8",              # Target IP/hostname
    "count": 1                         # Probes per hop (max 3)
}

# Note: Diagnostics are bounded (max 10 pings, max 30 hops for traceroute)
```

---

### Field Mapping Strategy

**General Principles:**

1. **Normalize field names**: RouterOS uses kebab-case (`cpu-load`), Python uses snake_case (`cpu_load`)
2. **Type conversion**: RouterOS strings → Python types (durations to seconds, percentages to floats)
3. **Hide internal fields**: Fields starting with `.` (except `.id`) are internal and not exposed
4. **Enrich with metadata**: Add device context, timestamps, environment tags
5. **Validate ranges**: Enforce MCP-specific bounds (max log entries, max ping count)
6. **Complete data fidelity**: **No information loss** - all fields returned by RouterOS must be captured and made available to MCP clients. Parsers must handle all output formats (multi-line values, continuation lines, field variations across RouterOS versions) to ensure complete data coverage.

**Implementation Pattern:**

```python
class SystemMapper:
    """Map RouterOS system responses to domain models."""

    @staticmethod
    def map_resource(ros_data: dict) -> SystemResource:
        """Map /rest/system/resource response."""
        return SystemResource(
            uptime_seconds=parse_duration(ros_data["uptime"]),
            routeros_version=ros_data["version"],
            cpu_usage_percent=float(ros_data["cpu-load"]),
            memory_free_bytes=int(ros_data["free-memory"]),
            memory_total_bytes=int(ros_data["total-memory"]),
            hardware_model=ros_data.get("board-name"),
        )

    @staticmethod
    def map_identity(ros_data: dict) -> str:
        """Map /rest/system/identity response."""
        return ros_data["name"]
```

Each domain service (system, interface, ip, dns, etc.) uses these mappers so that MCP tools work with clean, typed domain models instead of raw RouterOS dictionaries.

---

## RouterOS platform constraints (resource usage, API rate limits, connection limits, timeouts)

The integration must respect RouterOS device constraints:

- **CPU & memory limits**:

  - Avoid heavy polling; prefer **metrics collection jobs** with reasonable intervals and jitter.
  - Diagnostics (ping/traceroute) and logs retrieval must be bounded in time and volume.

- **API and connection limits**:

  - Some devices may have lower capabilities; per-device concurrency limits ensure we do not saturate API handlers.
  - The integration should be prepared for RouterOS to close idle or long-running connections; keep connections short-lived or properly pooled.

- **Timeout behavior**:
  - RouterOS may time out long-running commands; REST client should treat timeouts as first-class errors and not spin.

These constraints influence:

- The maximum frequency and volume of health checks and metrics pulls.
- The design of multi-device workflows (e.g., staggering changes across devices).

---

## Known /rest quirks (pagination behavior, common error patterns, status codes)

While exact details depend on RouterOS version, the integration should anticipate:

- **Pagination**:

  - Some endpoints may paginate results or limit the number of returned items.
  - The client must handle pagination or query parameters if applicable (e.g., offsets, `?numbers=` filters).

- **Error responses**:

  - RouterOS may return error details in response bodies; client should parse and surface them as structured error objects.
  - Distinguish between:
    - Authentication/authorization issues.
    - Validation errors (bad parameters).
    - Operational errors (e.g., resource busy, unknown item).

- **Status codes**:
  - Validate that 2xx / 4xx / 5xx codes are handled consistently; do not rely solely on code—also parse body.
  - Certain API inconsistencies (e.g., non-2xx with useful body) should be normalized internally.

The design should explicitly record any RouterOS `/rest` quirks discovered during testing and encode them in the client layer, not in higher-level services.

---

## Error Handling & MCP Error Mapping

**Mapping RouterOS errors to MCP JSON-RPC error responses:**

The integration layer must translate RouterOS-specific errors into standardized MCP JSON-RPC error responses that LLM clients can understand and handle.

### HTTP Status Code Mapping

| RouterOS Status          | HTTP Code | MCP Error Code | Error Type          | Retry?             |
| ------------------------ | --------- | -------------- | ------------------- | ------------------ |
| Success                  | 200-299   | N/A            | N/A                 | N/A                |
| Authentication failure   | 401       | -32001         | AuthenticationError | No                 |
| Insufficient permissions | 403       | -32002         | AuthorizationError  | No                 |
| Endpoint not found       | 404       | -32003         | NotFoundError       | No                 |
| Invalid parameters       | 400       | -32602         | InvalidParams       | No                 |
| Resource conflict        | 409       | -32004         | ConflictError       | No                 |
| Rate limited             | 429       | -32005         | RateLimitError      | Yes (with backoff) |
| Server error             | 500-599   | -32000         | InternalError       | Yes (3 attempts)   |
| Timeout                  | N/A       | -32006         | TimeoutError        | Yes (3 attempts)   |
| Network error            | N/A       | -32007         | NetworkError        | Yes (3 attempts)   |

### RouterOS Error Response Format

**RouterOS error responses typically include:**

```json
{
  "error": "failure: item not found",
  "detail": "No such item (*99)"
}
```

**MCP JSON-RPC error response format:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-123",
  "error": {
    "code": -32003,
    "message": "RouterOS resource not found",
    "data": {
      "routeros_error": "failure: item not found",
      "routeros_detail": "No such item (*99)",
      "device_id": "dev-001",
      "correlation_id": "corr-456",
      "endpoint": "/rest/ip/address/*99"
    }
  }
}
```

### Error Mapping Implementation

```python
import httpx
from typing import Any
from enum import IntEnum

class MCPErrorCode(IntEnum):
    """MCP JSON-RPC error codes."""

    # Standard JSON-RPC errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP-specific errors (custom range: -32000 to -32099)
    ROUTEROS_INTERNAL_ERROR = -32000
    AUTHENTICATION_ERROR = -32001
    AUTHORIZATION_ERROR = -32002
    NOT_FOUND_ERROR = -32003
    CONFLICT_ERROR = -32004
    RATE_LIMIT_ERROR = -32005
    TIMEOUT_ERROR = -32006
    NETWORK_ERROR = -32007


class RouterOSError(Exception):
    """Base exception for RouterOS integration errors."""

    mcp_error_code: int = MCPErrorCode.INTERNAL_ERROR
    retryable: bool = False

    def __init__(
        self,
        message: str,
        routeros_error: str | None = None,
        device_id: str | None = None,
        endpoint: str | None = None
    ):
        super().__init__(message)
        self.message = message
        self.routeros_error = routeros_error
        self.device_id = device_id
        self.endpoint = endpoint

    def to_mcp_error(self, correlation_id: str | None = None) -> dict[str, Any]:
        """Convert to MCP JSON-RPC error response."""
        error_data = {
            "device_id": self.device_id,
            "endpoint": self.endpoint,
            "correlation_id": correlation_id
        }

        if self.routeros_error:
            error_data["routeros_error"] = self.routeros_error

        return {
            "code": self.mcp_error_code,
            "message": self.message,
            "data": error_data
        }


class RouterOSAuthenticationError(RouterOSError):
    """Authentication failed (401)."""
    mcp_error_code = MCPErrorCode.AUTHENTICATION_ERROR
    retryable = False


class RouterOSAuthorizationError(RouterOSError):
    """Insufficient permissions (403)."""
    mcp_error_code = MCPErrorCode.AUTHORIZATION_ERROR
    retryable = False


class RouterOSNotFoundError(RouterOSError):
    """Resource not found (404)."""
    mcp_error_code = MCPErrorCode.NOT_FOUND_ERROR
    retryable = False


class RouterOSConflictError(RouterOSError):
    """Resource conflict (409)."""
    mcp_error_code = MCPErrorCode.CONFLICT_ERROR
    retryable = False


class RouterOSRateLimitError(RouterOSError):
    """Rate limit exceeded (429)."""
    mcp_error_code = MCPErrorCode.RATE_LIMIT_ERROR
    retryable = True


class RouterOSServerError(RouterOSError):
    """Server error (5xx)."""
    mcp_error_code = MCPErrorCode.ROUTEROS_INTERNAL_ERROR
    retryable = True


class RouterOSTimeoutError(RouterOSError):
    """Request timeout."""
    mcp_error_code = MCPErrorCode.TIMEOUT_ERROR
    retryable = True


class RouterOSNetworkError(RouterOSError):
    """Network connectivity error."""
    mcp_error_code = MCPErrorCode.NETWORK_ERROR
    retryable = True


class RouterOSClientError(RouterOSError):
    """Client error (4xx, excluding auth/authz/not-found)."""
    mcp_error_code = MCPErrorCode.INVALID_PARAMS
    retryable = False


def map_httpx_exception_to_routeros_error(
    exc: Exception,
    device_id: str,
    endpoint: str
) -> RouterOSError:
    """Map httpx exceptions to RouterOS error types.

    Args:
        exc: httpx exception
        device_id: Device identifier
        endpoint: REST endpoint path

    Returns:
        Appropriate RouterOSError subclass
    """
    if isinstance(exc, httpx.TimeoutException):
        return RouterOSTimeoutError(
            message=f"Request to {endpoint} timed out",
            device_id=device_id,
            endpoint=endpoint
        )

    if isinstance(exc, httpx.NetworkError):
        return RouterOSNetworkError(
            message=f"Network error connecting to device {device_id}",
            device_id=device_id,
            endpoint=endpoint
        )

    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code

        # Try to extract RouterOS error message
        routeros_error = None
        try:
            error_body = exc.response.json()
            routeros_error = error_body.get("error") or error_body.get("detail")
        except Exception:
            routeros_error = exc.response.text[:200]  # Truncate

        # Map status codes to error types
        if status_code == 401:
            return RouterOSAuthenticationError(
                message=f"Authentication failed for device {device_id}",
                routeros_error=routeros_error,
                device_id=device_id,
                endpoint=endpoint
            )

        if status_code == 403:
            return RouterOSAuthorizationError(
                message=f"Insufficient permissions for {endpoint}",
                routeros_error=routeros_error,
                device_id=device_id,
                endpoint=endpoint
            )

        if status_code == 404:
            return RouterOSNotFoundError(
                message=f"Resource not found: {endpoint}",
                routeros_error=routeros_error,
                device_id=device_id,
                endpoint=endpoint
            )

        if status_code == 409:
            return RouterOSConflictError(
                message=f"Resource conflict at {endpoint}",
                routeros_error=routeros_error,
                device_id=device_id,
                endpoint=endpoint
            )

        if status_code == 429:
            return RouterOSRateLimitError(
                message=f"Rate limit exceeded for device {device_id}",
                routeros_error=routeros_error,
                device_id=device_id,
                endpoint=endpoint
            )

        if 500 <= status_code < 600:
            return RouterOSServerError(
                message=f"RouterOS server error ({status_code})",
                routeros_error=routeros_error,
                device_id=device_id,
                endpoint=endpoint
            )

        if 400 <= status_code < 500:
            return RouterOSClientError(
                message=f"Invalid request to {endpoint} ({status_code})",
                routeros_error=routeros_error,
                device_id=device_id,
                endpoint=endpoint
            )

    # Fallback for unknown errors
    return RouterOSError(
        message=f"Unexpected error: {str(exc)}",
        device_id=device_id,
        endpoint=endpoint
    )
```

### Using Error Mapping in MCP Tools

```python
from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id")

@mcp.tool()
async def system_get_status(device_id: str) -> dict:
    """Get system status for a RouterOS device."""
    try:
        # Business logic
        client = get_routeros_client(device_id)
        resource = await client.get("/rest/system/resource")
        identity = await client.get("/rest/system/identity")

        return {
            "device_id": device_id,
            "system_identity": identity["name"],
            "uptime_seconds": parse_duration(resource["uptime"]),
            "cpu_usage_percent": float(resource["cpu-load"]),
            "memory_free_bytes": int(resource["free-memory"])
        }

    except RouterOSError as e:
        # Convert to MCP JSON-RPC error
        correlation_id = correlation_id_var.get(None)
        raise MCPToolError(
            error=e.to_mcp_error(correlation_id)
        ) from e

    except Exception as e:
        # Unexpected error
        correlation_id = correlation_id_var.get(None)
        raise MCPToolError(
            error={
                "code": MCPErrorCode.INTERNAL_ERROR,
                "message": "Unexpected error executing tool",
                "data": {
                    "device_id": device_id,
                    "correlation_id": correlation_id,
                    "error_type": type(e).__name__
                }
            }
        ) from e
```

### Error Recovery Strategies

**For retryable errors:**

```python
async def execute_with_retry(
    func: Callable,
    max_attempts: int = 3,
    backoff_base: float = 2.0
) -> Any:
    """Execute function with exponential backoff retry.

    Args:
        func: Async function to execute
        max_attempts: Maximum retry attempts
        backoff_base: Exponential backoff base (seconds)

    Returns:
        Function result

    Raises:
        RouterOSError: If all retries exhausted
    """
    last_error = None

    for attempt in range(max_attempts):
        try:
            return await func()

        except RouterOSError as e:
            last_error = e

            # Don't retry non-retryable errors
            if not e.retryable:
                raise

            # Last attempt - don't backoff
            if attempt == max_attempts - 1:
                raise

            # Exponential backoff
            backoff_seconds = backoff_base ** attempt
            logger.warning(
                f"Retryable error, attempt {attempt + 1}/{max_attempts}, "
                f"retrying in {backoff_seconds}s",
                extra={
                    "error_type": type(e).__name__,
                    "device_id": e.device_id,
                    "endpoint": e.endpoint
                }
            )
            await asyncio.sleep(backoff_seconds)

    # Should never reach here, but safeguard
    raise last_error
```

---

## SSH/CLI Integration Strategy

### When SSH is Used

**SSH as last resort** for operations not available via REST API:

- **Export operations**: `/export` command for full config backups (Note: Large configs may generate 10,000-100,000 tokens)
- **Specific diagnostics**: Commands not exposed via `/rest/tool`
- **Feature gaps**: RouterOS features without REST API parity (rare in v7.10+)
- **One-off monitoring commands**: Commands that require a `once` argument to return single snapshot instead of streaming data
  - Example: `/interface/monitor-traffic` is normally a continuous command, but `/interface/monitor-traffic {interface} once` returns a single snapshot of traffic statistics and exits immediately

**SSH should never be used as a general "escape hatch" for arbitrary commands.**

**Resource/identity health probes (fallback path)**

- SSH fallback uses standard `/system/resource/print` and `/system/identity/print` commands.

### Parameterized Commands

**Some SSH commands require parameters to function correctly:**

- **Continuous vs. One-Off Output**: RouterOS CLI commands may support a `once` argument to convert from streaming/continuous output to a single snapshot
  - `/interface/monitor-traffic` alone continuously streams real-time stats
  - `/interface/monitor-traffic {interface} once` returns a single snapshot and exits
  - **Implementation**: For one-off operations, always append the `once` argument to the command to ensure execution completes and returns in a bounded time
- **Command Validation**: The SSH client supports prefix-matching for parameterized commands
  - Whitelist: `/interface/monitor-traffic` (base command)
  - Allowed: `/interface/monitor-traffic ether1 once` (with parameters)
  - Validation: Command is allowed if it exactly matches whitelist OR starts with a whitelisted base command followed by space

**CRITICAL POLICY: DO NOT USE `as-value` ARGUMENT**

- The `as-value` argument (e.g., `/system/resource/print as-value`) is **NOT A VALID RouterOS argument** - it is unreliable and not officially supported across RouterOS builds.
- Many devices return **empty output** or **ignore the format directive** entirely when `as-value` is specified.
- **MCP POLICY**: Use ONLY standard `print` format consistently. Never use `as-value` in any RouterOS command.
- Plain output (`key: value`) is parsed with unit-aware coercion (e.g., `MiB`, `GiB`, `%`) so CPU, memory, uptime, architecture, board-name, and version fields remain meaningful over SSH fallback.
- All parsers must handle the standard colon-separated format: `key: value`

### Phase 1: Code-Based Command Templates

**For Phase 1, SSH command templates are defined in code, not via web GUI:**

```python
# routeros_mcp/infra/routeros/ssh_templates.py

from typing import Dict, Any
from pydantic import BaseModel, Field

class SSHCommandTemplate(BaseModel):
    """SSH command template definition."""

    id: str = Field(..., description="Unique command identifier")
    name: str = Field(..., description="Human-readable command name")
    description: str = Field(..., description="What this command does")
    template: str = Field(..., description="Command template with {placeholders}")
    tier: str = Field(..., description="fundamental/advanced/professional")
    allowed_environments: list[str] = Field(..., description="lab/staging/prod")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameter definitions")
    timeout_seconds: int = Field(default=30, description="Command timeout")


# Pre-defined templates (Phase 1)
SSH_COMMAND_TEMPLATES = {
    "export_full_config": SSHCommandTemplate(
        id="export_full_config",
        name="Export Full Configuration",
        description="Export complete RouterOS configuration to .rsc format",
        template="/export file={filename}",
        tier="fundamental",
        allowed_environments=["lab", "staging", "prod"],
        parameters={
            "filename": {
                "type": "str",
                "pattern": r"^[a-zA-Z0-9_-]+$",  # Alphanumeric, underscore, hyphen only
                "max_length": 64,
                "description": "Output filename (without .rsc extension)"
            }
        },
        timeout_seconds=60
    ),

    "export_compact_config": SSHCommandTemplate(
        id="export_compact_config",
        name="Export Compact Configuration",
        description="Export configuration in compact format (minimal output)",
        template="/export compact file={filename}",
        tier="fundamental",
        allowed_environments=["lab", "staging", "prod"],
        parameters={
            "filename": {
                "type": "str",
                "pattern": r"^[a-zA-Z0-9_-]+$",
                "max_length": 64
            }
        },
        timeout_seconds=60
    ),

    "system_backup": SSHCommandTemplate(
        id="system_backup",
        name="Create System Backup",
        description="Create binary system backup file",
        template="/system backup save name={filename}",
        tier="advanced",
        allowed_environments=["lab", "staging", "prod"],
        parameters={
            "filename": {
                "type": "str",
                "pattern": r"^[a-zA-Z0-9_-]+$",
                "max_length": 64,
                "description": "Backup filename (without .backup extension)"
            }
        },
        timeout_seconds=120
    ),

    "fetch_url": SSHCommandTemplate(
        id="fetch_url",
        name="Fetch File from URL",
        description="Download file from HTTP/HTTPS URL (lab/staging only)",
        template="/tool fetch url={url} dst-path={dst_path}",
        tier="advanced",
        allowed_environments=["lab", "staging"],  # NOT allowed in prod
        parameters={
            "url": {
                "type": "str",
                "pattern": r"^https?://[a-zA-Z0-9.-]+(/.*)?$",  # HTTP/HTTPS only
                "max_length": 256,
                "description": "Source URL (http:// or https://)"
            },
            "dst_path": {
                "type": "str",
                "pattern": r"^[a-zA-Z0-9_/-]+\.[a-z]+$",
                "max_length": 128,
                "description": "Destination path on router"
            }
        },
        timeout_seconds=300
    )
}
```

### Command Template Validation

**Before executing any SSH command, validate parameters:**

```python
import re
from typing import Any

def validate_ssh_parameters(
    template: SSHCommandTemplate,
    params: dict[str, Any]
) -> dict[str, Any]:
    """Validate and sanitize SSH command parameters.

    Args:
        template: Command template definition
        params: User-provided parameters

    Returns:
        Validated and sanitized parameters

    Raises:
        ValueError: If validation fails
    """
    validated = {}

    for param_name, param_def in template.parameters.items():
        # Check required parameters
        if param_name not in params:
            raise ValueError(f"Missing required parameter: {param_name}")

        value = params[param_name]

        # Type check
        if param_def["type"] == "str" and not isinstance(value, str):
            raise ValueError(f"Parameter {param_name} must be string")

        # Pattern validation (prevent injection)
        if "pattern" in param_def:
            if not re.match(param_def["pattern"], value):
                raise ValueError(
                    f"Parameter {param_name} does not match required pattern"
                )

        # Length validation
        if "max_length" in param_def:
            if len(value) > param_def["max_length"]:
                raise ValueError(
                    f"Parameter {param_name} exceeds max length "
                    f"{param_def['max_length']}"
                )

        validated[param_name] = value

    return validated


def render_ssh_command(
    template: SSHCommandTemplate,
    params: dict[str, Any]
) -> str:
    """Render SSH command from template with validated parameters.

    Args:
        template: Command template
        params: Validated parameters

    Returns:
        Rendered command string
    """
    # Validate parameters first
    validated_params = validate_ssh_parameters(template, params)

    # Render template (safe - params are validated)
    return template.template.format(**validated_params)
```

### Command Execution Flow

```python
async def execute_ssh_command(
    device: Device,
    command_id: str,
    params: dict[str, Any]
) -> str:
    """Execute whitelisted SSH command on device.

    Args:
        device: Target RouterOS device
        command_id: SSH command template ID
        params: Command parameters

    Returns:
        Command output

    Raises:
        ValueError: If command not found or parameters invalid
        AuthorizationError: If command not allowed for device
        SSHError: If command execution fails
    """
    # 1. Get template
    template = SSH_COMMAND_TEMPLATES.get(command_id)
    if not template:
        raise ValueError(f"Unknown SSH command: {command_id}")

    # 2. Check authorization
    check_ssh_command_access(device, template)

    # 3. Validate and render command
    command = render_ssh_command(template, params)

    # 4. Execute via SSH client
    ssh_client = get_ssh_client(device)
    result = await ssh_client.execute(command, timeout=template.timeout_seconds)

    # 5. Audit log
    audit_ssh_command(device, template, command, result)

    return result
```

---

## Phase 1: Code-Based Template Management

**For Phase 1 (single-user), SSH command templates are code-based:**

✅ **Advantages:**

- **Security**: Templates reviewed in code review process
- **Version control**: All changes tracked in git
- **No runtime modification**: Prevents accidental template corruption
- **Type safety**: Pydantic validation at load time

**Implemented in Later Phases:**

- Web GUI for adding/modifying templates (Phase 4)
- Runtime template modification (Phase 2-3)
- User-defined custom commands (Phase 3)

### Future: Phase 2-3 Template Management

**Phase 2-3 may add configuration-file-based templates:**

```yaml
# config/ssh_templates.yaml (Phase 2+)
ssh_templates:
  - id: export_dns_config
    name: Export DNS Configuration
    template: "/ip dns export file={filename}"
    tier: fundamental
    allowed_environments: [lab, staging, prod]
    parameters:
      filename:
        type: str
        pattern: "^[a-zA-Z0-9_-]+$"
        max_length: 64
```

**Phase 4 may add web GUI for admin users:**

- CRUD operations on SSH templates
- Template testing in lab environment
- Approval workflow for new templates
- Template usage audit trail

**But for Phase 1**: Templates are hardcoded in `ssh_templates.py` and require code changes to add/modify.

---

## SSH Command Audit Strategy

### Audit Logging (Phase 1)

**Every SSH operation is logged:**

```python
def audit_ssh_command(
    device: Device,
    template: SSHCommandTemplate,
    rendered_command: str,
    result: str
) -> None:
    """Log SSH command execution for audit trail.

    Args:
        device: Target device
        template: Command template used
        rendered_command: Actual command executed
        result: Command output (may be truncated)
    """
    from contextvars import ContextVar

    # Get correlation ID from context (propagated from MCP request)
    correlation_id_var: ContextVar[str] = ContextVar("correlation_id")
    correlation_id = correlation_id_var.get(None)

    audit_event = AuditEvent(
        id=generate_id(),
        timestamp=datetime.utcnow(),
        correlation_id=correlation_id,  # Link to MCP request
        device_id=device.id,
        environment=device.environment,
        action="SSH_COMMAND",
        tool_name=f"ssh/{template.id}",
        tool_tier=template.tier,
        result="SUCCESS" if result else "FAILURE",
        metadata={
            "command_id": template.id,
            "command_name": template.name,
            "rendered_command": rendered_command,  # May mask sensitive params
            "output_length": len(result),
            "timeout_seconds": template.timeout_seconds
        }
    )

    # Save to audit_events table
    save_audit_event(audit_event)

    # Also log to structured logger with correlation ID
    logger.info(
        "SSH command executed",
        extra={
            "correlation_id": correlation_id,
            "device_id": device.id,
            "command_id": template.id,
            "result": audit_event.result
        }
    )
```

### SSH Command Restrictions

**Additional safety measures:**

1. **Environment restrictions**: Some commands only allowed in lab/staging
2. **Device capability flags**: SSH commands require `allow_ssh_commands` flag (default: false)
3. **Tier-based access**: Advanced/Professional SSH commands follow same tier rules
4. **No shell access**: Commands are executed via `/system script run`, not interactive shell
5. **Output limits**: Command output truncated to 10MB to prevent resource exhaustion

---

## Summary: SSH Integration (Phase 1)

✅ **What Phase 1 Has:**

- Pre-defined SSH command templates in code
- Parameter validation and injection prevention
- Environment and tier-based restrictions
- Comprehensive audit logging
- Support for config export and backups

**Deferred to Later Phases:**

- Web GUI for template management (Phase 4)
- Runtime template modification (Phase 2-3)
- User-defined custom commands (Phase 3)
- Interactive SSH shell access (never - security risk)

**Rationale**: Code-based templates provide maximum security and auditability for single-user deployments. Template management features are implemented in Phase 4 when multi-user access control is in place.

---

## Idempotency, change detection, and read-modify-write patterns

- **Idempotent tools**:

  - Tools must be designed so that repeatedly applying the same desired state yields the same result (no unintended side effects).
  - For example, setting a system identity to the same value should return `changed=false`.

- **Read-modify-write**:

  - Before changing configuration, the integration:
    - Reads the current state from RouterOS.
    - Computes the desired changes relative to the current state.
    - Applies the minimal set of changes required.

- **Change detection**:
  - Tools must explicitly report whether a change was applied (`changed=true/false`).
  - Out-of-band changes on RouterOS are handled by always re-reading and not assuming previous writes succeeded.

This pattern is critical for safe multi-device orchestration and drift handling.

---

## Handling version differences and feature detection per device

- **Minimum supported version**:

  - The MCP service assumes RouterOS v7 with a configured minimum minor version (e.g. ≥ 7.xx LTS).

- **Feature detection**:

  - At registration or on-demand, the service queries device capabilities (version, installed packages, available endpoints).
  - Certain tools or features may be disabled for devices that do not meet requirements.

- **Degraded behavior**:
  - If a feature is missing:
    - Tools may degrade to read-only mode (e.g., read DNS config but not modify).
    - Or return a clear “unsupported” error.

---

## Performance considerations (batching, pagination, rate limiting per device)

- **Batching**:

  - Where possible, combine related reads into fewer REST calls (e.g., fetch multiple interfaces in one request).
  - Avoid over-batching for large fleets; per-device and global limits still apply.

- **Pagination**:

  - Large result sets (e.g., logs, large routing tables) should be paginated by the MCP tools and integration layer, not dumped wholesale.

- **Rate limiting**:
  - Per-device:
    - Capped QPS and concurrency, with backoff on repeated failures.
  - Global:
    - Limits to protect the MCP service and upstream dependencies from overload.

These considerations are especially important for metrics collection and multi-device plan/apply workflows.

---

## Testing against lab devices and simulation / “dry-run” patterns

- **Lab devices**:

  - A small, representative set of RouterOS devices in `lab` environment must be available for:
    - Integration testing.
    - Validating new tools and features.
    - Exercising high-risk operations under controlled conditions.

- **Simulation / mocks**:

  - For CI and unit tests, use simulated RouterOS responses or mocks that mirror REST/SSH behavior.
  - Simulated scenarios should include:
    - Success paths.
    - Common error cases.
    - Timeouts and rate-limiting behaviors.

- **Dry-run mode**:
  - Where feasible, tools should support “dry-run” or “plan” operations:
    - Compute and report intended RouterOS changes without applying them.
    - This dovetails with the plan/apply pattern in MCP tools.
