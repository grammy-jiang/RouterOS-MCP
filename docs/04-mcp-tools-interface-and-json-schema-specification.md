# MCP Tools Interface & JSON Schema Specification

## Purpose

Define the MCP-facing API—tool taxonomy, capability tiers (fundamental/advanced/professional), input/output JSON schemas, and safety guardrails that map cleanly to RouterOS operations. This document is the contract between MCP clients (including AI tools) and the RouterOS MCP service.

**Related Documents:**
- [Doc 03: RouterOS Integration & Endpoint Mappings](03-routeros-integration-and-platform-constraints-rest-and-ssh.md)
- [Doc 19: JSON-RPC Error Codes & MCP Protocol](19-json-rpc-error-codes-and-mcp-protocol-specification.md)
- [ENDPOINT-TOOL-MAPPING.md](ENDPOINT-TOOL-MAPPING.md) - Cross-reference analysis

---

## Conceptual capability model (topics and subtopics: system, interface, ip, dns, etc.)

Capabilities are organized by **topic** and **tier**:

- Topics mirror RouterOS areas, but are grouped for clarity:
  - `device` (MCP device management, no RouterOS endpoint)
  - `system` (identity, resources, health, packages, clock)
  - `interface` (Ethernet, VLAN, wireless interface metadata)
  - `bridge`
  - `ip` (addresses, ARP, address-lists)
  - `dns` (DNS configuration and cache)
  - `ntp` (NTP client configuration)
  - `dhcp`
  - `routing` (routes, protocol status)
  - `firewall` (filter rules, NAT, address-lists - read-only in Phase 1)
  - `logs` (system logs and logging configuration)
  - `wireless` (status and limited config)
  - `tool` (ping, traceroute, bandwidth-test diagnostics)
  - `config` (multi-device workflows - Phase 4+)

Each MCP tool:

- Belongs to exactly one primary topic (even if it touches multiple topics, its primary concern is defined).
- Declares a **tier** (`fundamental`, `advanced`, `professional`).
- Declares a **phase** for implementation (Phase 0-5).
- Declares the RouterOS versions and environments it supports.

---

## Feature tier definitions (fundamental read-only; advanced writes; professional workflows)

- **Fundamental**:
  - Read-only operations and non-mutating diagnostics.
  - Safe to expose broadly to `read_only` users (Phase 4) or all users (Phase 1).
  - Examples: list devices, fetch system health, read interface status, run limited ping/traceroute.

- **Advanced**:
  - Single-device configuration writes with low to moderate risk.
  - Exposed to `ops_rw` and `admin` users (Phase 4) on devices where `allow_advanced_writes=true`.
  - Examples: change system identity, update interface comments, modify DNS/NTP on lab devices.

- **Professional**:
  - Multi-step or multi-device workflows, often with higher risk.
  - Only for `admin` users (Phase 4), and only on devices where `allow_professional_workflows=true` and environment permits.
  - Must use a **plan/apply** pattern and require **human approval tokens** (Phase 4) for writes.
  - Examples: multi-device DNS rollout, shared address-list sync, staged configuration changes.

---

## MCP Protocol Integration

**All tools use JSON-RPC 2.0 format as specified in [Doc 19](19-json-rpc-error-codes-and-mcp-protocol-specification.md).**

### JSON-RPC 2.0 Request Format

```json
{
  "jsonrpc": "2.0",
  "id": "req-12345",
  "method": "tools/call",
  "params": {
    "name": "system/get-overview",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

### Success Response Format

```json
{
  "jsonrpc": "2.0",
  "id": "req-12345",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "System overview retrieved successfully"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "routeros_version": "7.10.1",
      "uptime_seconds": 86400,
      "cpu_usage_percent": 5.2
    }
  }
}
```

### Error Response Format

```json
{
  "jsonrpc": "2.0",
  "id": "req-12345",
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {
      "mcp_error_code": "INVALID_DEVICE_ID",
      "details": "Device 'dev-unknown' not found in registry",
      "device_id": "dev-unknown"
    }
  }
}
```

**For complete error code taxonomy, see [Doc 19](19-json-rpc-error-codes-and-mcp-protocol-specification.md#error-code-taxonomy).**

---

## Complete Tool Catalog with JSON-RPC Schemas

This section provides complete JSON-RPC request/response schemas for **all tools**, organized by phase and topic.

### Phase 1: Read-Only Operations (Fundamental Tier)

---

#### Device Management Topic

##### `device/list-devices`

**Description**: List all registered devices in MCP (does not contact RouterOS).

**Tier**: Fundamental
**Phase**: Phase 1
**MCP Method**: `tools/call`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tools/call",
  "params": {
    "name": "device/list-devices",
    "arguments": {
      "environment": "lab",  // Optional filter
      "tags": {"site": "main"}  // Optional filter
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 3 devices matching criteria"
      }
    ],
    "isError": false,
    "_meta": {
      "devices": [
        {
          "id": "dev-lab-01",
          "name": "router-lab-01",
          "management_address": "192.168.1.1:443",
          "environment": "lab",
          "status": "healthy",
          "routeros_version": "7.10.1",
          "tags": {"site": "main", "role": "edge"},
          "allow_advanced_writes": true,
          "allow_professional_workflows": false
        }
      ],
      "total_count": 3
    }
  }
}
```

---

##### `device/check-connectivity`

**Description**: Check connectivity to a device (lightweight health check).

**Tier**: Fundamental
**Phase**: Phase 1
**MCP Method**: `tools/call`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "method": "tools/call",
  "params": {
    "name": "device/check-connectivity",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Device dev-lab-01 is reachable"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "reachable": true,
      "response_time_ms": 45,
      "routeros_version": "7.10.1"
    }
  }
}
```

---

#### System Topic

##### `system/get-overview`

**Description**: Get comprehensive system overview (resources, identity, routerboard info).

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoints**:
- `GET /rest/system/resource`
- `GET /rest/system/identity`
- `GET /rest/system/routerboard`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-003",
  "method": "tools/call",
  "params": {
    "name": "system/get-overview",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-003",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "System overview for router-lab-01"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "identity": "router-lab-01",
      "routeros_version": "7.10.1 (stable)",
      "uptime_seconds": 864000,
      "hardware_model": "RB5009UG+S+",
      "serial_number": "ABC12345678",
      "firmware_version": "7.10",
      "cpu": {
        "usage_percent": 5.2,
        "count": 4
      },
      "memory": {
        "total_bytes": 536870912,
        "used_bytes": 268435456,
        "free_bytes": 268435456
      },
      "health": {
        "temperature_celsius": 45.0,
        "voltage": 24.1
      }
    }
  }
}
```

---

##### `system/get-packages`

**Description**: Get installed packages and versions.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/system/package`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-004",
  "method": "tools/call",
  "params": {
    "name": "system/get-packages",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-004",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 12 installed packages"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "packages": [
        {
          "name": "routeros",
          "version": "7.10.1",
          "build_time": "2024-01-10 10:30:00",
          "disabled": false
        },
        {
          "name": "wireless",
          "version": "7.10.1",
          "build_time": "2024-01-10 10:30:00",
          "disabled": false
        }
      ],
      "total_count": 12
    }
  }
}
```

---

##### `system/get-clock`

**Description**: Get system time and timezone information.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/system/clock`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-005",
  "method": "tools/call",
  "params": {
    "name": "system/get-clock",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-005",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "System time: 2025-01-15 14:30:00 UTC"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "time": "2025-01-15T14:30:00Z",
      "timezone": "UTC",
      "time_zone_autodetect": false,
      "time_zone_name": "UTC"
    }
  }
}
```

---

#### Interface Topic

##### `interface/list-interfaces`

**Description**: List all interfaces with status and statistics.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/interface`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-006",
  "method": "tools/call",
  "params": {
    "name": "interface/list-interfaces",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-006",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 10 interfaces on router-lab-01"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "interfaces": [
        {
          "id": "*1",
          "name": "ether1",
          "type": "ether",
          "running": true,
          "disabled": false,
          "comment": "WAN uplink",
          "mtu": 1500,
          "mac_address": "AA:BB:CC:DD:EE:FF"
        },
        {
          "id": "*2",
          "name": "ether2",
          "type": "ether",
          "running": true,
          "disabled": false,
          "comment": "LAN",
          "mtu": 1500,
          "mac_address": "AA:BB:CC:DD:EE:00"
        }
      ],
      "total_count": 10
    }
  }
}
```

---

##### `interface/get-interface`

**Description**: Get detailed information about a specific interface.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/interface/{id}`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-007",
  "method": "tools/call",
  "params": {
    "name": "interface/get-interface",
    "arguments": {
      "device_id": "dev-lab-01",
      "interface_id": "*1"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-007",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Interface ether1 details"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "interface": {
        "id": "*1",
        "name": "ether1",
        "type": "ether",
        "running": true,
        "disabled": false,
        "comment": "WAN uplink",
        "mtu": 1500,
        "mac_address": "AA:BB:CC:DD:EE:FF",
        "last_link_up_time": "2024-12-01T10:00:00Z"
      }
    }
  }
}
```

---

##### `interface/get-stats`

**Description**: Get real-time traffic statistics for interfaces.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/interface/monitor-traffic`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-008",
  "method": "tools/call",
  "params": {
    "name": "interface/get-stats",
    "arguments": {
      "device_id": "dev-lab-01",
      "interface_names": ["ether1", "ether2"]  // Optional filter
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-008",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Traffic statistics for 2 interfaces"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "stats": [
        {
          "name": "ether1",
          "rx_bits_per_second": 15000000,
          "tx_bits_per_second": 8000000,
          "rx_packets_per_second": 1200,
          "tx_packets_per_second": 900
        },
        {
          "name": "ether2",
          "rx_bits_per_second": 50000000,
          "tx_bits_per_second": 30000000,
          "rx_packets_per_second": 4000,
          "tx_packets_per_second": 2500
        }
      ]
    }
  }
}
```

---

#### IP Address Topic

##### `ip/list-addresses`

**Description**: List all IP addresses configured on the device.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/address`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-009",
  "method": "tools/call",
  "params": {
    "name": "ip/list-addresses",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-009",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 5 IP addresses on router-lab-01"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "addresses": [
        {
          "id": "*2",
          "address": "192.168.1.1/24",
          "network": "192.168.1.0",
          "interface": "ether1",
          "disabled": false,
          "comment": "LAN gateway"
        },
        {
          "id": "*3",
          "address": "10.0.0.1/8",
          "network": "10.0.0.0",
          "interface": "ether2",
          "disabled": false,
          "comment": ""
        }
      ],
      "total_count": 5
    }
  }
}
```

---

##### `ip/get-address`

**Description**: Get details of a specific IP address.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/address/{id}`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-010",
  "method": "tools/call",
  "params": {
    "name": "ip/get-address",
    "arguments": {
      "device_id": "dev-lab-01",
      "address_id": "*2"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-010",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "IP address 192.168.1.1/24 on ether1"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "address": {
        "id": "*2",
        "address": "192.168.1.1/24",
        "network": "192.168.1.0",
        "interface": "ether1",
        "disabled": false,
        "comment": "LAN gateway",
        "dynamic": false,
        "invalid": false
      }
    }
  }
}
```

---

##### `ip/get-arp-table`

**Description**: Get ARP table entries.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/arp`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-011",
  "method": "tools/call",
  "params": {
    "name": "ip/get-arp-table",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-011",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 15 ARP entries"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "arp_entries": [
        {
          "address": "192.168.1.10",
          "mac_address": "11:22:33:44:55:66",
          "interface": "ether1",
          "status": "reachable",
          "comment": "Workstation"
        }
      ],
      "total_count": 15
    }
  }
}
```

---

#### DNS Topic

##### `dns/get-status`

**Description**: Get DNS configuration and cache status.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/dns`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-012",
  "method": "tools/call",
  "params": {
    "name": "dns/get-status",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-012",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "DNS servers: 8.8.8.8, 8.8.4.4"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "dns_servers": ["8.8.8.8", "8.8.4.4"],
      "allow_remote_requests": true,
      "cache_size_kb": 2048,
      "cache_used_kb": 156
    }
  }
}
```

---

##### `dns/get-cache`

**Description**: Get DNS cache entries.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/dns/cache`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-013",
  "method": "tools/call",
  "params": {
    "name": "dns/get-cache",
    "arguments": {
      "device_id": "dev-lab-01",
      "limit": 100  // Optional, max 1000
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-013",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "DNS cache contains 45 entries"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "cache_entries": [
        {
          "name": "example.com",
          "type": "A",
          "data": "93.184.216.34",
          "ttl": 3600
        }
      ],
      "total_count": 45,
      "returned_count": 45
    }
  }
}
```

---

#### NTP Topic

##### `ntp/get-status`

**Description**: Get NTP client configuration and sync status.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoints**:
- `GET /rest/system/ntp/client`
- `GET /rest/system/ntp/client/monitor`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-014",
  "method": "tools/call",
  "params": {
    "name": "ntp/get-status",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-014",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "NTP synchronized, stratum 2, offset -0.002s"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "enabled": true,
      "ntp_servers": ["time.cloudflare.com", "pool.ntp.org"],
      "mode": "unicast",
      "status": "synchronized",
      "stratum": 2,
      "offset_ms": -2.0
    }
  }
}
```

---

#### Routing Topic

##### `routing/get-summary`

**Description**: Get routing table summary and route counts.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/route`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-015",
  "method": "tools/call",
  "params": {
    "name": "routing/get-summary",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-015",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Routing table: 25 routes (2 static, 23 connected/dynamic)"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "total_routes": 25,
      "static_routes": 2,
      "connected_routes": 10,
      "dynamic_routes": 13,
      "routes": [
        {
          "id": "*3",
          "dst_address": "0.0.0.0/0",
          "gateway": "192.168.1.254",
          "distance": 1,
          "comment": "Default route"
        }
      ]
    }
  }
}
```

---

##### `routing/get-route`

**Description**: Get details of a specific route.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/route/{id}`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-016",
  "method": "tools/call",
  "params": {
    "name": "routing/get-route",
    "arguments": {
      "device_id": "dev-lab-01",
      "route_id": "*3"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-016",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Route: 0.0.0.0/0 via 192.168.1.254"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "route": {
        "id": "*3",
        "dst_address": "0.0.0.0/0",
        "gateway": "192.168.1.254",
        "distance": 1,
        "scope": 30,
        "target_scope": 10,
        "comment": "Default route",
        "active": true,
        "dynamic": false
      }
    }
  }
}
```

---

#### Firewall Topic

##### `firewall/list-filter-rules`

**Description**: List firewall filter rules (read-only).

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/firewall/filter`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-017",
  "method": "tools/call",
  "params": {
    "name": "firewall/list-filter-rules",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-017",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 15 firewall filter rules"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "filter_rules": [
        {
          "id": "*4",
          "chain": "input",
          "action": "accept",
          "protocol": "tcp",
          "dst_port": "22,8080",
          "comment": "Allow SSH and HTTP",
          "disabled": false
        }
      ],
      "total_count": 15
    }
  }
}
```

---

##### `firewall/list-nat-rules`

**Description**: List NAT rules (read-only).

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/firewall/nat`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-018",
  "method": "tools/call",
  "params": {
    "name": "firewall/list-nat-rules",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-018",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 3 NAT rules"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "nat_rules": [
        {
          "id": "*1",
          "chain": "srcnat",
          "action": "masquerade",
          "out_interface": "ether1",
          "comment": "Masquerade WAN",
          "disabled": false
        }
      ],
      "total_count": 3
    }
  }
}
```

---

##### `firewall/list-address-lists`

**Description**: List firewall address-list entries (read-only).

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/ip/firewall/address-list`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-019",
  "method": "tools/call",
  "params": {
    "name": "firewall/list-address-lists",
    "arguments": {
      "device_id": "dev-lab-01",
      "list_name": "mcp-managed-hosts"  // Optional filter
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-019",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Address list 'mcp-managed-hosts' contains 10 entries"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "address_lists": [
        {
          "id": "*5",
          "list_name": "mcp-managed-hosts",
          "address": "10.0.1.100",
          "comment": "MCP server",
          "timeout": "1d"
        }
      ],
      "total_count": 10
    }
  }
}
```

---

#### Logging Topic

##### `logs/get-recent`

**Description**: Get recent system logs (bounded query).

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/log`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-020",
  "method": "tools/call",
  "params": {
    "name": "logs/get-recent",
    "arguments": {
      "device_id": "dev-lab-01",
      "limit": 100,  // Max 1000
      "topics": ["system", "error"]  // Optional filter
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-020",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Retrieved 100 log entries"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "log_entries": [
        {
          "id": "*6",
          "time": "2025-01-15T10:30:45Z",
          "topics": ["system", "info"],
          "message": "System started"
        }
      ],
      "total_count": 100
    }
  }
}
```

---

##### `logs/get-config`

**Description**: Get logging configuration (topics and actions).

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `GET /rest/system/logging`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-021",
  "method": "tools/call",
  "params": {
    "name": "logs/get-config",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-021",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Logging configuration: 5 actions defined"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "logging_actions": [
        {
          "topics": ["system", "info"],
          "action": "memory",
          "prefix": ""
        }
      ],
      "total_count": 5
    }
  }
}
```

---

#### Diagnostics (Tool) Topic

##### `tool/ping`

**Description**: Run ICMP ping diagnostic.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `POST /rest/tool/ping`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-022",
  "method": "tools/call",
  "params": {
    "name": "tool/ping",
    "arguments": {
      "device_id": "dev-lab-01",
      "address": "8.8.8.8",
      "count": 4,  // Max 10
      "interval_ms": 1000
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-022",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Ping to 8.8.8.8: 4 sent, 4 received, 0% loss"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "host": "8.8.8.8",
      "packets_sent": 4,
      "packets_received": 4,
      "packet_loss_percent": 0,
      "min_rtt_ms": 10.0,
      "avg_rtt_ms": 12.0,
      "max_rtt_ms": 15.0
    }
  }
}
```

---

##### `tool/traceroute`

**Description**: Run network traceroute diagnostic.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `POST /rest/tool/traceroute`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-023",
  "method": "tools/call",
  "params": {
    "name": "tool/traceroute",
    "arguments": {
      "device_id": "dev-lab-01",
      "address": "8.8.8.8",
      "count": 1  // Max 3 probes per hop
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-023",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Traceroute to 8.8.8.8 completed in 8 hops"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "target": "8.8.8.8",
      "hops": [
        {
          "hop": 1,
          "address": "192.168.1.254",
          "rtt_ms": 1.5
        },
        {
          "hop": 2,
          "address": "10.0.0.1",
          "rtt_ms": 5.2
        }
      ],
      "total_hops": 8
    }
  }
}
```

---

##### `tool/bandwidth-test`

**Description**: Run bandwidth test to measure throughput.

**Tier**: Fundamental
**Phase**: Phase 1
**RouterOS Endpoint**: `POST /rest/tool/bandwidth-test`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-024",
  "method": "tools/call",
  "params": {
    "name": "tool/bandwidth-test",
    "arguments": {
      "device_id": "dev-lab-01",
      "address": "192.168.1.254",
      "direction": "both",  // send, receive, both
      "duration_seconds": 10  // Max 60
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-024",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Bandwidth test: TX 950 Mbps, RX 940 Mbps"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "target": "192.168.1.254",
      "tx_bits_per_second": 950000000,
      "rx_bits_per_second": 940000000,
      "duration_seconds": 10
    }
  }
}
```

---

### Phase 2: Single-Device Writes (Advanced Tier)

---

#### System Topic

##### `system/update-identity`

**Description**: Update system identity and related fields.

**Tier**: Advanced
**Phase**: Phase 2
**RouterOS Endpoint**: `PATCH /rest/system/identity`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-025",
  "method": "tools/call",
  "params": {
    "name": "system/update-identity",
    "arguments": {
      "device_id": "dev-lab-01",
      "identity": "router-lab-01-new",
      "dry_run": false  // Optional, default false
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-025",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "System identity updated to 'router-lab-01-new'"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": true,
      "old_identity": "router-lab-01",
      "new_identity": "router-lab-01-new"
    }
  }
}
```

---

#### Interface Topic

##### `interface/update-comment`

**Description**: Update interface comment (description).

**Tier**: Advanced
**Phase**: Phase 2
**RouterOS Endpoint**: `PATCH /rest/interface/{id}`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-026",
  "method": "tools/call",
  "params": {
    "name": "interface/update-comment",
    "arguments": {
      "device_id": "dev-lab-01",
      "interface_id": "*1",
      "comment": "WAN uplink (primary)",
      "dry_run": false
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-026",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Interface ether1 comment updated"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "interface_id": "*1",
      "interface_name": "ether1",
      "changed": true,
      "old_comment": "WAN uplink",
      "new_comment": "WAN uplink (primary)"
    }
  }
}
```

---

#### IP Address Topic

##### `ip/add-secondary-address`

**Description**: Add secondary IP address to an interface.

**Tier**: Advanced
**Phase**: Phase 2
**RouterOS Endpoint**: `PUT /rest/ip/address`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-027",
  "method": "tools/call",
  "params": {
    "name": "ip/add-secondary-address",
    "arguments": {
      "device_id": "dev-lab-01",
      "address": "192.168.1.2/24",
      "interface": "ether1",
      "comment": "Secondary IP",
      "dry_run": false
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-027",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Added secondary IP 192.168.1.2/24 to ether1"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": true,
      "address_id": "*10",
      "address": "192.168.1.2/24",
      "interface": "ether1"
    }
  }
}
```

---

##### `ip/remove-secondary-address`

**Description**: Remove secondary IP address (with safety checks).

**Tier**: Advanced
**Phase**: Phase 2
**RouterOS Endpoint**: `DELETE /rest/ip/address/{id}`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-028",
  "method": "tools/call",
  "params": {
    "name": "ip/remove-secondary-address",
    "arguments": {
      "device_id": "dev-lab-01",
      "address_id": "*10",
      "dry_run": false
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-028",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Removed IP address 192.168.1.2/24"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": true,
      "address_id": "*10",
      "removed_address": "192.168.1.2/24"
    }
  }
}
```

---

##### `ip/update-address-list-entry`

**Description**: Add or remove entries from MCP-managed address lists.

**Tier**: Advanced
**Phase**: Phase 2
**RouterOS Endpoints**:
- `PUT /rest/ip/firewall/address-list` (add)
- `DELETE /rest/ip/firewall/address-list/{id}` (remove)

**Request (Add)**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-029",
  "method": "tools/call",
  "params": {
    "name": "ip/update-address-list-entry",
    "arguments": {
      "device_id": "dev-lab-01",
      "action": "add",
      "list_name": "mcp-managed-hosts",
      "address": "10.0.1.200",
      "comment": "New server",
      "timeout": "7d",  // Optional
      "dry_run": false
    }
  }
}
```

**Response (Add)**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-029",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Added 10.0.1.200 to address list 'mcp-managed-hosts'"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": true,
      "action": "add",
      "list_name": "mcp-managed-hosts",
      "address": "10.0.1.200",
      "entry_id": "*20"
    }
  }
}
```

---

#### DNS Topic

##### `dns/update-servers`

**Description**: Update DNS server configuration.

**Tier**: Advanced
**Phase**: Phase 2
**RouterOS Endpoint**: `PATCH /rest/ip/dns`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-030",
  "method": "tools/call",
  "params": {
    "name": "dns/update-servers",
    "arguments": {
      "device_id": "dev-lab-01",
      "dns_servers": ["1.1.1.1", "1.0.0.1"],
      "dry_run": false
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-030",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "DNS servers updated to 1.1.1.1, 1.0.0.1"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": true,
      "old_servers": ["8.8.8.8", "8.8.4.4"],
      "new_servers": ["1.1.1.1", "1.0.0.1"]
    }
  }
}
```

---

##### `dns/flush-cache`

**Description**: Flush DNS cache.

**Tier**: Advanced
**Phase**: Phase 2
**RouterOS Endpoint**: `POST /rest/ip/dns/cache/flush`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-031",
  "method": "tools/call",
  "params": {
    "name": "dns/flush-cache",
    "arguments": {
      "device_id": "dev-lab-01"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-031",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "DNS cache flushed"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": true,
      "entries_flushed": 45
    }
  }
}
```

---

#### NTP Topic

##### `ntp/update-servers`

**Description**: Update NTP server configuration.

**Tier**: Advanced
**Phase**: Phase 2
**RouterOS Endpoint**: `PATCH /rest/system/ntp/client`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-032",
  "method": "tools/call",
  "params": {
    "name": "ntp/update-servers",
    "arguments": {
      "device_id": "dev-lab-01",
      "ntp_servers": ["time.cloudflare.com"],
      "enabled": true,
      "dry_run": false
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-032",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "NTP servers updated to time.cloudflare.com"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": true,
      "old_servers": ["pool.ntp.org"],
      "new_servers": ["time.cloudflare.com"]
    }
  }
}
```

---

### Phase 4: Multi-Device Workflows (Professional Tier)

---

#### Configuration (Multi-Device) Topic

##### `config/plan-dns-ntp-rollout`

**Description**: Create plan for multi-device DNS/NTP configuration update.

**Tier**: Professional
**Phase**: Phase 4
**Pattern**: Plan step (no RouterOS changes)

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-033",
  "method": "tools/call",
  "params": {
    "name": "config/plan-dns-ntp-rollout",
    "arguments": {
      "device_ids": ["dev-lab-01", "dev-lab-02", "dev-lab-03"],
      "dns_servers": ["1.1.1.1", "1.0.0.1"],
      "ntp_servers": ["time.cloudflare.com"],
      "description": "Update DNS/NTP to Cloudflare"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-033",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Created plan plan-20250115-001 for 3 devices"
      }
    ],
    "isError": false,
    "_meta": {
      "plan_id": "plan-20250115-001",
      "summary": "Update DNS/NTP to Cloudflare on 3 devices",
      "total_devices": 3,
      "devices": [
        {
          "device_id": "dev-lab-01",
          "environment": "lab",
          "risk_level": "low",
          "changes": [
            {
              "topic": "dns",
              "description": "Update DNS servers from 8.8.8.8,8.8.4.4 to 1.1.1.1,1.0.0.1"
            },
            {
              "topic": "ntp",
              "description": "Update NTP servers from pool.ntp.org to time.cloudflare.com"
            }
          ]
        }
      ]
    }
  }
}
```

---

##### `config/apply-dns-ntp-rollout`

**Description**: Execute approved DNS/NTP rollout plan.

**Tier**: Professional
**Phase**: Phase 4
**Pattern**: Apply step (requires approval token in Phase 4)

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-034",
  "method": "tools/call",
  "params": {
    "name": "config/apply-dns-ntp-rollout",
    "arguments": {
      "plan_id": "plan-20250115-001",
      "approval_token": "approval-token-xyz"  // Phase 4: multi-user approval; Phase 1: self-approval allowed
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-034",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Applied plan plan-20250115-001: 3/3 devices successful"
      }
    ],
    "isError": false,
    "_meta": {
      "plan_id": "plan-20250115-001",
      "job_id": "job-20250115-001",
      "total_devices": 3,
      "successful": 3,
      "failed": 0,
      "results": [
        {
          "device_id": "dev-lab-01",
          "status": "success",
          "changed": true,
          "execution_time_ms": 450
        }
      ]
    }
  }
}
```

---

##### `config/plan-address-list-sync`

**Description**: Create plan for multi-device address-list synchronization.

**Tier**: Professional
**Phase**: Phase 4
**Pattern**: Plan step

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-035",
  "method": "tools/call",
  "params": {
    "name": "config/plan-address-list-sync",
    "arguments": {
      "device_ids": ["dev-lab-01", "dev-lab-02"],
      "list_name": "mcp-managed-hosts",
      "addresses": [
        {"address": "10.0.1.100", "comment": "MCP server"},
        {"address": "10.0.1.200", "comment": "Monitoring"}
      ],
      "description": "Sync managed hosts list"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-035",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Created plan plan-20250115-002 for address-list sync"
      }
    ],
    "isError": false,
    "_meta": {
      "plan_id": "plan-20250115-002",
      "summary": "Sync managed hosts list across 2 devices",
      "list_name": "mcp-managed-hosts",
      "total_devices": 2,
      "devices": [
        {
          "device_id": "dev-lab-01",
          "environment": "lab",
          "risk_level": "low",
          "changes": [
            {
              "topic": "firewall",
              "description": "Add 2 entries to address-list 'mcp-managed-hosts'"
            }
          ]
        }
      ]
    }
  }
}
```

---

##### `config/apply-address-list-sync`

**Description**: Execute approved address-list sync plan.

**Tier**: Professional
**Phase**: Phase 4
**Pattern**: Apply step

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-036",
  "method": "tools/call",
  "params": {
    "name": "config/apply-address-list-sync",
    "arguments": {
      "plan_id": "plan-20250115-002",
      "approval_token": "approval-token-abc"
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-036",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Applied plan plan-20250115-002: 2/2 devices successful"
      }
    ],
    "isError": false,
    "_meta": {
      "plan_id": "plan-20250115-002",
      "job_id": "job-20250115-002",
      "total_devices": 2,
      "successful": 2,
      "failed": 0,
      "results": [
        {
          "device_id": "dev-lab-01",
          "status": "success",
          "changed": true,
          "entries_added": 2
        }
      ]
    }
  }
}
```

---

### Phase 4-5: High-Risk Operations (Professional Tier)

---

#### Routing Topic

##### `routing/add-static-route`

**Description**: Add static route (high-risk, requires plan/approval in Phase 4).

**Tier**: Professional
**Phase**: Phase 4
**RouterOS Endpoint**: `PUT /rest/ip/route`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-037",
  "method": "tools/call",
  "params": {
    "name": "routing/add-static-route",
    "arguments": {
      "device_id": "dev-lab-01",
      "dst_address": "10.1.0.0/16",
      "gateway": "192.168.1.254",
      "distance": 1,
      "comment": "Route to remote site",
      "dry_run": true  // Plan mode
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-037",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Plan: Would add static route 10.1.0.0/16 via 192.168.1.254"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": false,
      "dry_run": true,
      "planned_changes": {
        "dst_address": "10.1.0.0/16",
        "gateway": "192.168.1.254",
        "distance": 1
      }
    }
  }
}
```

---

##### `routing/remove-static-route`

**Description**: Remove static route (high-risk).

**Tier**: Professional
**Phase**: Phase 4
**RouterOS Endpoint**: `DELETE /rest/ip/route/{id}`

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-038",
  "method": "tools/call",
  "params": {
    "name": "routing/remove-static-route",
    "arguments": {
      "device_id": "dev-lab-01",
      "route_id": "*15",
      "dry_run": true
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-038",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Plan: Would remove route 10.1.0.0/16 via 192.168.1.254"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": false,
      "dry_run": true,
      "route_to_remove": {
        "id": "*15",
        "dst_address": "10.1.0.0/16",
        "gateway": "192.168.1.254"
      }
    }
  }
}
```

---

#### Device Management (MCP-Only) Topic

##### `device/register-device`

**Description**: Register a new device in MCP.

**Tier**: Advanced
**Phase**: Phase 1
**MCP Operation**: Internal database operation

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-039",
  "method": "tools/call",
  "params": {
    "name": "device/register-device",
    "arguments": {
      "name": "router-lab-04",
      "management_address": "192.168.1.4:443",
      "environment": "lab",
      "tags": {"site": "main", "role": "access"},
      "allow_advanced_writes": true,
      "allow_professional_workflows": false,
      "credentials": {
        "username": "admin",
        "password": "secret123"  // Will be encrypted
      }
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-039",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Registered device router-lab-04 as dev-lab-04"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-04",
      "name": "router-lab-04",
      "management_address": "192.168.1.4:443",
      "environment": "lab",
      "status": "pending",
      "created_at": "2025-01-15T14:30:00Z"
    }
  }
}
```

---

##### `device/update-device`

**Description**: Update device metadata or configuration.

**Tier**: Advanced
**Phase**: Phase 1
**MCP Operation**: Internal database operation

**Request**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-040",
  "method": "tools/call",
  "params": {
    "name": "device/update-device",
    "arguments": {
      "device_id": "dev-lab-01",
      "tags": {"site": "main", "role": "edge", "region": "us-west"},
      "allow_advanced_writes": true
    }
  }
}
```

**Response**:
```json
{
  "jsonrpc": "2.0",
  "id": "req-040",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Updated device dev-lab-01 metadata"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "changed": true,
      "updated_fields": ["tags", "allow_advanced_writes"],
      "updated_at": "2025-01-15T14:35:00Z"
    }
  }
}
```

---

## Tool Catalog Summary Table

| Tool Name | Topic | Tier | Phase | RouterOS Endpoint |
|-----------|-------|------|-------|-------------------|
| `device/list-devices` | Device | Fundamental | 1 | N/A (MCP-only) |
| `device/check-connectivity` | Device | Fundamental | 1 | `GET /rest/system/identity` |
| `device/register-device` | Device | Advanced | 1 | N/A (MCP-only) |
| `device/update-device` | Device | Advanced | 1 | N/A (MCP-only) |
| `system/get-overview` | System | Fundamental | 1 | Multiple `/rest/system/*` |
| `system/get-packages` | System | Fundamental | 1 | `GET /rest/system/package` |
| `system/get-clock` | System | Fundamental | 1 | `GET /rest/system/clock` |
| `system/update-identity` | System | Advanced | 2 | `PATCH /rest/system/identity` |
| `interface/list-interfaces` | Interface | Fundamental | 1 | `GET /rest/interface` |
| `interface/get-interface` | Interface | Fundamental | 1 | `GET /rest/interface/{id}` |
| `interface/get-stats` | Interface | Fundamental | 1 | `GET /rest/interface/monitor-traffic` |
| `interface/update-comment` | Interface | Advanced | 2 | `PATCH /rest/interface/{id}` |
| `ip/list-addresses` | IP | Fundamental | 1 | `GET /rest/ip/address` |
| `ip/get-address` | IP | Fundamental | 1 | `GET /rest/ip/address/{id}` |
| `ip/get-arp-table` | IP | Fundamental | 1 | `GET /rest/ip/arp` |
| `ip/add-secondary-address` | IP | Advanced | 2 | `PUT /rest/ip/address` |
| `ip/remove-secondary-address` | IP | Advanced | 2 | `DELETE /rest/ip/address/{id}` |
| `ip/update-address-list-entry` | IP | Advanced | 2 | Multiple firewall endpoints |
| `dns/get-status` | DNS | Fundamental | 1 | `GET /rest/ip/dns` |
| `dns/get-cache` | DNS | Fundamental | 1 | `GET /rest/ip/dns/cache` |
| `dns/update-servers` | DNS | Advanced | 2 | `PATCH /rest/ip/dns` |
| `dns/flush-cache` | DNS | Advanced | 2 | `POST /rest/ip/dns/cache/flush` |
| `ntp/get-status` | NTP | Fundamental | 1 | Multiple NTP endpoints |
| `ntp/update-servers` | NTP | Advanced | 2 | `PATCH /rest/system/ntp/client` |
| `routing/get-summary` | Routing | Fundamental | 1 | `GET /rest/ip/route` |
| `routing/get-route` | Routing | Fundamental | 1 | `GET /rest/ip/route/{id}` |
| `routing/add-static-route` | Routing | Professional | 4 | `PUT /rest/ip/route` |
| `routing/remove-static-route` | Routing | Professional | 4 | `DELETE /rest/ip/route/{id}` |
| `firewall/list-filter-rules` | Firewall | Fundamental | 1 | `GET /rest/ip/firewall/filter` |
| `firewall/list-nat-rules` | Firewall | Fundamental | 1 | `GET /rest/ip/firewall/nat` |
| `firewall/list-address-lists` | Firewall | Fundamental | 1 | `GET /rest/ip/firewall/address-list` |
| `logs/get-recent` | Logs | Fundamental | 1 | `GET /rest/log` |
| `logs/get-config` | Logs | Fundamental | 1 | `GET /rest/system/logging` |
| `tool/ping` | Tool | Fundamental | 1 | `POST /rest/tool/ping` |
| `tool/traceroute` | Tool | Fundamental | 1 | `POST /rest/tool/traceroute` |
| `tool/bandwidth-test` | Tool | Fundamental | 1 | `POST /rest/tool/bandwidth-test` |
| `config/plan-dns-ntp-rollout` | Config | Professional | 4 | N/A (plan step) |
| `config/apply-dns-ntp-rollout` | Config | Professional | 4 | Multiple endpoints |
| `config/plan-address-list-sync` | Config | Professional | 4 | N/A (plan step) |
| `config/apply-address-list-sync` | Config | Professional | 4 | Multiple endpoints |

**Total: 40 tools** (13 Phase 1, 9 Phase 2, 18 Phase 4+)

---

## Common Request/Response Fields

### All Tools

**Common Request Fields:**
- `device_id` (string, required for device-specific tools): MCP device identifier
- `dry_run` (boolean, optional, default false): Plan mode without applying changes

**Common Response Fields in `_meta`:**
- `device_id` (string): Device identifier
- `changed` (boolean, for write operations): Whether configuration changed
- `execution_time_ms` (number, optional): Tool execution time

### Error Handling

**All tools return JSON-RPC 2.0 error format on failure. See [Doc 19](19-json-rpc-error-codes-and-mcp-protocol-specification.md) for complete error taxonomy.**

**Common Error Codes:**
- `-32602` / `INVALID_DEVICE_ID`: Device not found
- `-32002` / `FORBIDDEN`: Insufficient permissions (tier/capability)
- `-32010` / `DEVICE_UNREACHABLE`: Cannot connect to RouterOS
- `-32012` / `DEVICE_ERROR`: RouterOS returned error
- `-32021` / `UNSAFE_OPERATION`: Blocked by safety check

---

## Guardrails and safety constraints (validation, precondition checks, constraints per topic)

Each tool must embed its safety rules and validation logic:

### Validation Rules

- **Required parameters**: Check all required fields are present
- **Type correctness**: Validate field types match schema
- **Range validation**: Enforce min/max values (ping count ≤ 10, log limit ≤ 1000)
- **Format validation**: IP addresses, CIDR notation, domain names
- **Dangerous values**: Reject obviously unsafe inputs

### Precondition Checks

**For all write operations:**
1. Device environment matches service environment (lab/staging/prod)
2. Device capability flags allow the tool tier:
   - Advanced tier requires `allow_advanced_writes=true`
   - Professional tier requires `allow_professional_workflows=true`
3. RouterOS version meets minimum requirements
4. Target is not a critical resource (e.g., management interface)

### Topic-Specific Constraints

**Diagnostics** (`tool/ping`, `tool/traceroute`):
- Hard caps: ping count ≤ 10, traceroute hops ≤ 30
- Timeout limits: max 60 seconds per operation

**Logs** (`logs/get-recent`):
- Mandatory time window: max 24 hours
- Line count cap: max 1000 entries

**IP Addresses** (`ip/add-secondary-address`, `ip/remove-secondary-address`):
- Prevent overlapping networks
- Block management interface modifications
- Require interface existence check

**DNS/NTP** (`dns/update-servers`, `ntp/update-servers`):
- Validate server reachability before applying
- Require health check verification post-change
- Multi-device changes require plan/apply pattern (Phase 4)

**Routing** (`routing/add-static-route`, `routing/remove-static-route`):
- Professional tier only
- Plan/apply pattern required
- Prevent default route modifications without explicit approval

**Address Lists** (`ip/update-address-list-entry`):
- Only allow MCP-managed lists (prefix: `mcp-`)
- Reject modifications to system address lists

---

## Tool-level authorization and scoping

### Phase 1 (Single-User)

**Authorization Model:**
- OS-level access control (filesystem permissions)
- Single implicit admin user
- Device-level capability checks only

**Enforcement:**
1. Check device environment matches service environment
2. Check device capability flags for tool tier
3. No user role checks (all operations allowed at OS level)

### Phase 4 (Multi-User)

**Authorization Model:**
- OAuth/OIDC authentication
- Role-based access control (RBAC)
- Device scoping per user
- Approval tokens for professional tier

**Tool Metadata:**
- `tier`: fundamental/advanced/professional
- `required_role`: `read_only`, `ops_rw`, or `admin`
- `environment_constraints`: allowed environments
- `requires_approval`: true for professional writes

**Enforcement:**
1. Verify OAuth token validity
2. Check user role meets `required_role`
3. Check device is in user's `device_scope`
4. Check device environment and capability flags
5. For professional tier: validate approval token

**Example Authorization Check:**
```python
def check_authorization(
    user: User,
    tool: ToolMetadata,
    device: Device
) -> None:
    """Check if user can invoke tool on device (Phase 4)."""
    # Role check
    if not user.role_allows(tool.required_role):
        raise UnauthorizedError(f"Role {user.role} cannot access {tool.tier} tier")

    # Device scope check
    if device.id not in user.device_scope:
        raise ForbiddenError(f"Device {device.id} not in user scope")

    # Environment check
    if device.environment not in tool.environment_constraints:
        raise ForbiddenError(f"Tool not allowed in {device.environment}")

    # Capability check
    if tool.tier == "advanced" and not device.allow_advanced_writes:
        raise ForbiddenError("Device does not allow advanced writes")

    if tool.tier == "professional" and not device.allow_professional_workflows:
        raise ForbiddenError("Device does not allow professional workflows")
```

---

## Versioning, deprecation strategy, and discoverability for MCP clients

### Versioning

- **Tool names**: Use `/` separator (e.g., `system/get-overview`)
- **Backward-compatible changes**: Add optional fields without version bump
- **Breaking changes**: Create new tool version (e.g., `system/get-overview-v2`)
- **Version window**: Maintain old version for 6 months after deprecation

### Deprecation

- **Deprecation flag**: Mark tool with `deprecated=true` in metadata
- **Replacement tool**: Specify `replacement_tool` name
- **Grace period**: 6 months warning, then removal
- **Client warnings**: Include deprecation warning in response `_meta`

### Discoverability

**MCP provides tool introspection endpoint:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-discover",
  "method": "tools/list",
  "params": {}
}
```

**Returns tool catalog with metadata:**
```json
{
  "jsonrpc": "2.0",
  "id": "req-discover",
  "result": {
    "tools": [
      {
        "name": "system/get-overview",
        "description": "Get comprehensive system overview",
        "topic": "system",
        "tier": "fundamental",
        "phase": 1,
        "required_role": "read_only",
        "environments": ["lab", "staging", "prod"],
        "requires_approval": false,
        "deprecated": false,
        "input_schema": { ... },
        "output_schema": { ... }
      }
    ]
  }
}
```

---

## Related Documents

- **[Doc 03: RouterOS Integration & Endpoint Mappings](03-routeros-integration-and-platform-constraints-rest-and-ssh.md)** - REST API endpoint details
- **[Doc 19: JSON-RPC Error Codes & MCP Protocol](19-json-rpc-error-codes-and-mcp-protocol-specification.md)** - Complete error taxonomy
- **[ENDPOINT-TOOL-MAPPING.md](ENDPOINT-TOOL-MAPPING.md)** - Cross-reference analysis between endpoints and tools
- **[README.md](../README.md)** - Phase roadmap and project overview

---

**Document Status**: ✅ Complete with 40 tools, full JSON-RPC schemas, and phase assignments
