# MCP Tools Interface & JSON Schema Specification

## Purpose

Define the MCP-facing API—tool taxonomy, capability tiers (fundamental/advanced/professional), input/output JSON schemas, and safety guardrails that map cleanly to RouterOS operations. This document is the contract between MCP clients (including AI tools) and the RouterOS MCP service.

## Phase 1-3 (current implementation) tool snapshot

The running service currently registers **62 tools** across 13 categories. This list is authoritative for Phase 1-3; the larger catalogs below remain forward-looking. SSH fallback commands used by these tools are documented in [Doc 15](15-mcp-resources-and-prompts-design.md#ssh-commands-used-by-phase-1-resourcestools-reference).

- **Platform/health helpers (2):** `echo`, `service_health`
- **Device registry (2):** `list_devices`, `check_connectivity`
- **System (4):** `get_system_overview`, `get_system_packages`, `get_system_clock`, `set_system_identity` (advanced)
- **Interface (3):** `list_interfaces`, `get_interface`, `get_interface_stats`
- **IP addressing (5):** `list_ip_addresses`, `get_ip_address`, `get_arp_table`, `add_secondary_ip_address` (advanced), `remove_secondary_ip_address` (advanced)
- **DNS / NTP (6):** `get_dns_status`, `get_dns_cache`, `get_ntp_status`, `update_dns_servers` (advanced), `flush_dns_cache` (advanced), `update_ntp_servers` (advanced)
- **Routing (6):** `get_routing_summary`, `get_route`, `plan_add_static_route`, `plan_modify_static_route`, `plan_remove_static_route`, `apply_routing_plan`
- **Firewall & logs (5):** `list_firewall_filter_rules`, `list_firewall_nat_rules`, `list_firewall_address_lists`, `get_recent_logs`, `get_logging_config`
- **Firewall write (5):** `update_firewall_address_list` (advanced), `plan_add_firewall_rule`, `plan_modify_firewall_rule`, `plan_remove_firewall_rule`, `apply_firewall_plan`
- **DHCP (6):** `get_dhcp_server_status`, `get_dhcp_leases`, `plan_create_dhcp_pool`, `plan_modify_dhcp_pool`, `plan_remove_dhcp_pool`, `apply_dhcp_plan`
- **Bridge (6):** `list_bridges`, `get_bridge`, `get_bridge_ports`, `plan_create_bridge`, `plan_modify_bridge_ports`, `apply_bridge_plan`
- **Wireless (9):** `get_wireless_interfaces`, `get_wireless_clients`, `get_capsman_remote_caps`, `get_capsman_registrations`, `plan_create_wireless_ssid`, `plan_modify_wireless_ssid`, `plan_remove_wireless_ssid`, `plan_wireless_rf_settings`, `apply_wireless_plan`
- **Config/Plan workflows (3):** `config_plan_dns_ntp_rollout`, `config_apply_dns_ntp_rollout`, `config_rollback_plan`
- **Diagnostics (2):** `ping`, `traceroute` (implemented but not registered in Phase 1-3; enabled in Phase 4+)

> Diagnostics (`ping`, `traceroute`) are implemented in code but **not registered** in Phase 1-3; they will be enabled in Phase 4+ once guardrails are finalized.

Prompts and resources currently exposed are listed in [Doc 15](15-mcp-resources-and-prompts-design.md#phase-1-current-implementation-snapshot).

**Related Documents:**

- [Doc 03: RouterOS Integration & Endpoint Mappings](03-routeros-integration-and-platform-constraints-rest-and-ssh.md) - Complete endpoint catalog with 41 REST API endpoints
- [Doc 19: JSON-RPC Error Codes & MCP Protocol](19-json-rpc-error-codes-and-mcp-protocol-specification.md) - Error taxonomy and protocol compliance

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

**Description:**

```
List all registered RouterOS devices in the MCP service.

Use when:
- User asks "what devices are available?" or "show me all routers"
- Beginning device selection workflows (user needs to choose a target)
- Filtering devices by environment (lab/staging/prod) or tags (site, role, region)
- Checking device health status across the fleet
- Auditing device inventory

Returns: List of devices with ID, name, management address, environment, status, RouterOS version, tags, and capability flags.

Tip: Use tags parameter to narrow results (e.g., {"site": "datacenter-1"}).
```

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
      "environment": "lab", // Optional filter
      "tags": { "site": "main" } // Optional filter
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
          "tags": { "site": "main", "role": "edge" },
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

**Description:**

```
Verify if a device is reachable and responsive.

Probe order:
1. REST API (`GET /rest/system/resource`)
2. SSH fallback (whitelisted `"/system/resource/print"`) if REST fails

On success, the response states whether REST or SSH was used. On failure,
the tool reports the classified reason and 2–3 safe remediation steps.

Use when:
- User asks "is device X reachable?" or "can you ping this router?"
- Troubleshooting connectivity issues before attempting configuration changes
- Validating device registration (checking if new device responds)
- Quick health check without full system overview
- Pre-flight check before plan execution

Returns: Reachability status, response time, RouterOS version.

Note: Lightweight connectivity probe (REST first, SSH fallback); not a full health check.
```

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

**Response (success)**:

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
      "routeros_version": "7.10.1",
      "failure_reason": null,
      "transport": "rest", // or "ssh" when fallback succeeds
      "fallback_used": false,
      "attempted_transports": ["rest"],
      "suggestions": []
    }
  }
}
```

**Response (failure with guidance)**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-002",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Device dev-lab-01 is not reachable (reason: timeout)"
      }
    ],
    "isError": true,
    "_meta": {
      "device_id": "dev-lab-01",
      "reachable": false,
      "response_time_ms": 3000,
      "failure_reason": "timeout",
      "transport": "ssh", // last attempted transport
      "fallback_used": true,
      "attempted_transports": ["rest", "ssh"],
      "suggestions": [
        "Verify device is powered on and reachable on the management IP/port",
        "Check firewall or NAT rules blocking HTTPS/SSH to the device",
        "Increase routeros_rest_timeout_seconds for slow links"
      ]
    }
  }
}
```

**Requirement:** On failure, the tool MUST include a classified `failure_reason`, structured meta (including retries/timeout when available), and 2–3 actionable remediation steps (suggestions) that are safe to surface to users.

---

#### System Topic

##### `system/get-overview`

**Description:**

```
Get comprehensive system information including identity, hardware, resource usage, and health metrics.

Use when:
- User asks "show me system status" or "what's the router's health?"
- Troubleshooting performance issues (CPU, memory usage)
- Gathering device information for documentation or inventory
- Checking hardware specs (model, serial number, firmware version)
- Verifying system uptime or recent reboots
- Initial device assessment before configuration changes

Returns: Identity, RouterOS version, uptime, hardware model, serial number, CPU usage, memory usage, temperature, voltage.

Tip: This is the primary "health dashboard" tool - use it as a starting point for most device interactions.
```

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

**Description:**

```
List all installed RouterOS packages and their versions.

Use when:
- User asks "what packages are installed?" or "what version is wireless package?"
- Verifying software capabilities before attempting feature-specific operations
- Troubleshooting missing features (checking if required package is installed)
- Auditing software inventory across fleet
- Planning package upgrades

Returns: List of packages with name, version, build time, and disabled status.

Note: Does not show available upgrades (use RouterOS upgrade tools for that).
```

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

**Description:**

```
Get current system time, timezone, and time configuration.

Use when:
- User asks "what time is it on the router?" or "what timezone is configured?"
- Troubleshooting time-related issues (logs, certificates, scheduled tasks)
- Verifying NTP synchronization indirectly (check if time is accurate)
- Diagnosing time drift problems
- Before/after NTP configuration changes

Returns: Current time (ISO 8601), timezone name, autodetect status.

Tip: Compare with ntp/get-status to verify time synchronization health.
```

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

**Description:**

```
List all network interfaces with operational status and metadata.

Use when:
- User asks "show me all interfaces" or "what's the interface status?"
- Finding interfaces by type (ether, vlan, bridge, wireless)
- Identifying disabled or down interfaces
- Discovering interface names for other operations
- Auditing interface inventory and comments
- Troubleshooting connectivity (checking running status)

Returns: List of interfaces with ID, name, type, running status, disabled status, comment, MTU, MAC address.

Tip: Use this first to discover interface names/IDs, then use interface/get-interface for details.
```

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

**Description:**

```
Get detailed information about a specific interface.

Use when:
- User asks about a specific interface ("tell me about ether1")
- Need complete interface configuration details
- Checking interface-specific settings before making changes
- Verifying last link up/down events
- Detailed troubleshooting of single interface

Returns: Complete interface configuration including all fields from interface list plus additional details.

Note: Requires interface ID (from interface/list-interfaces) or name.
```

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

**Description:**

```
Get real-time traffic statistics for network interfaces.

Use when:
- User asks "how much traffic on ether1?" or "show bandwidth usage"
- Monitoring current network load (bits/packets per second)
- Troubleshooting performance issues (identifying saturated links)
- Verifying traffic flow after configuration changes
- Capacity planning (understanding current utilization)

Returns: Real-time RX/TX rates in bits per second and packets per second.

Tip: This is a snapshot at the time of the call. For trends, compare multiple calls over time.
```

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
      "interface_names": ["ether1", "ether2"] // Optional filter
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

**Description:**

```
List all IP addresses configured on the device.

Use when:
- User asks "what IPs are configured?" or "show me all addresses"
- Finding which interfaces have which IP addresses
- Auditing IP address assignments
- Planning IP address additions (checking for conflicts)
- Troubleshooting IP connectivity issues
- Verifying address configuration after changes

Returns: List of IP addresses with CIDR notation, network, interface, disabled status, and comment.

Tip: Returns both primary and secondary addresses on all interfaces.
```

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

**Description:**

```
Get details of a specific IP address configuration.

Use when:
- User asks about a specific IP address
- Verifying address properties (network, interface binding)
- Checking if address is dynamic or static
- Detailed investigation of address configuration

Returns: Complete IP address details including network, interface, disabled/dynamic/invalid flags.

Note: Requires address ID (from ip/list-addresses).
```

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

**Description:**

```
Get ARP (Address Resolution Protocol) table entries.

Use when:
- User asks "what devices are on the network?" or "show me ARP table"
- Troubleshooting connectivity to specific hosts (verifying MAC address resolution)
- Identifying connected devices by MAC address
- Detecting IP/MAC conflicts
- Network discovery (seeing active hosts)

Returns: List of ARP entries with IP address, MAC address, interface, status, and comment.

Tip: Only shows devices that have recently communicated with the router.
```

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

**Description:**

```
Get DNS server configuration and cache statistics.

Use when:
- User asks "what DNS servers are configured?" or "is DNS working?"
- Troubleshooting DNS resolution issues
- Verifying DNS configuration after changes
- Checking DNS cache utilization
- Before planning DNS server updates
- Auditing DNS settings across fleet

Returns: DNS server list, remote request allowance, cache size/usage.

Tip: Use with tool/ping to verify DNS server reachability.
```

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

**Description:**

```
View DNS cache entries (recently resolved domains).

Use when:
- User asks "what's in the DNS cache?" or "has domain X been resolved?"
- Troubleshooting DNS resolution (verifying cache entries)
- Checking TTL values for cached records
- Investigating DNS-related connectivity issues
- Before/after flushing DNS cache

Returns: List of cached DNS records with name, type (A/AAAA/CNAME), data (IP), and TTL.

Note: Limited to 1000 entries max. Use limit parameter to control result size.
```

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
      "limit": 100 // Optional, max 1000
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

**Description:**

```
Get NTP client configuration and synchronization status.

Use when:
- User asks "is NTP working?" or "what time servers are configured?"
- Troubleshooting time synchronization issues
- Verifying NTP configuration after changes
- Checking sync status (synchronized vs not synchronized)
- Diagnosing time drift problems
- Before planning NTP server updates

Returns: Enabled status, NTP server list, mode, sync status, stratum, time offset.

Tip: Check offset_ms - large values indicate sync problems. Compare with system/get-clock.
```

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

**Description:**

```
Get routing table summary with route counts and key routes.

Use when:
- User asks "show me routes" or "what's the default gateway?"
- Overview of routing configuration
- Counting routes by type (static, connected, dynamic)
- Finding default route quickly
- Before planning routing changes
- Troubleshooting routing issues (verifying routes exist)

Returns: Total route count, counts by type (static/connected/dynamic), list of routes with destination, gateway, distance, comment.

Tip: For detailed single route info, use routing/get-route.
```

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

**Description:**

```
Get detailed information about a specific route.

Use when:
- User asks about a specific route destination
- Investigating route properties (scope, distance, active/inactive status)
- Verifying route configuration
- Detailed troubleshooting of routing behavior

Returns: Complete route details including destination, gateway, distance, scope, active status, dynamic flag.

Note: Requires route ID (from routing/get-summary).
```

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

**Description:**

```
List firewall filter rules (input/forward/output chains).

Use when:
- User asks "what firewall rules are configured?" or "show me filter rules"
- Auditing firewall security configuration
- Troubleshooting blocked connections (finding which rule blocks traffic)
- Verifying firewall rule order
- Before planning firewall changes
- Security compliance checks

Returns: List of filter rules with ID, chain, action, protocol, ports, comment, disabled status.

Note: Read-only in Phase 1. Modification requires Phase 2+.
```

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

**Description:**

```
List NAT (Network Address Translation) rules.

Use when:
- User asks "show me NAT config" or "what masquerade rules exist?"
- Troubleshooting NAT issues (port forwarding, masquerading)
- Auditing NAT configuration
- Verifying srcnat/dstnat rules
- Before planning NAT changes

Returns: List of NAT rules with ID, chain, action, interfaces, comment, disabled status.

Note: Read-only in Phase 1.
```

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

**Description:**

```
List firewall address-list entries (IP-based allow/deny lists).

Use when:
- User asks "show me address lists" or "what IPs are in list X?"
- Auditing firewall IP whitelists/blacklists
- Verifying address-list entries
- Troubleshooting access control (checking if IP is in list)
- Before adding/removing address-list entries
- Checking MCP-managed lists (prefix: mcp-)

Returns: List of address-list entries with ID, list name, address, comment, timeout.

Tip: Filter by list_name parameter to view specific list. Only MCP-managed lists (prefix: mcp-) can be modified.
```

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
      "list_name": "mcp-managed-hosts" // Optional filter
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

**Description:**

```
Retrieve recent system logs with optional filtering.

Use when:
- User asks "show me recent logs" or "check logs for errors"
- Troubleshooting issues (looking for error messages)
- Auditing system events
- Investigating security incidents
- Verifying recent configuration changes
- Checking specific topics (system, error, warning, firewall, etc.)

Returns: List of log entries with ID, timestamp, topics, and message.

Constraints:
- Max 1000 entries per call (use limit parameter)
- Filter by topics to narrow results (e.g., ["system", "error"])
- Bounded query - cannot stream unlimited logs

Tip: Start with small limit (e.g., 100) and specific topics to avoid overwhelming response.
```

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
      "limit": 100, // Max 1000
      "topics": ["system", "error"] // Optional filter
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

**Description:**

```
Get logging configuration (which topics log to which destinations).

Use when:
- User asks "what logging is configured?" or "where do logs go?"
- Auditing logging configuration
- Troubleshooting missing logs (verifying topic is logged)
- Understanding log architecture
- Before modifying logging configuration (Phase 2+)

Returns: List of logging actions with topics, action type (memory/disk/remote), and prefix.

Note: Configuration is read-only in Phase 1.
```

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

**Description:**

```
Run ICMP ping test from the router to a target address.

Use when:
- User asks "can you ping X?" or "is host Y reachable?"
- Testing network connectivity
- Verifying routing to destination
- Measuring latency/round-trip time
- Troubleshooting packet loss
- Verifying DNS resolution (can use hostname)

Returns: Packets sent/received, packet loss percentage, min/avg/max RTT.

Constraints:
- Max 10 pings per call (count parameter)
- Results are snapshot, not continuous monitoring

Tip: Use interval_ms parameter to control ping frequency.
```

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
      "count": 4, // Max 10
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

**Description:**

```
Run traceroute to show network path to destination.

Use when:
- User asks "trace route to X" or "show me path to Y"
- Troubleshooting routing issues (finding where packets go)
- Identifying network hops
- Measuring latency per hop
- Diagnosing routing loops or suboptimal paths

Returns: List of hops with hop number, IP address, and RTT.

Constraints:
- Max 30 hops
- Max 3 probes per hop (count parameter)

Tip: Some hops may not respond (shown as * in results).
```

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
      "count": 1 // Max 3 probes per hop
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

**Description:**

```
Run bandwidth test between router and target RouterOS device.

Use when:
- User asks "test bandwidth to X" or "how fast is the link?"
- Measuring actual throughput (not just interface speed)
- Troubleshooting performance issues
- Verifying link capacity
- Testing after configuration changes

Returns: TX/RX throughput in bits per second.

Constraints:
- Max 60 second duration
- Target must be another RouterOS device with bandwidth-test enabled
- Generates traffic load (use carefully in production)

Note: This is an active test that consumes bandwidth.
```

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
      "direction": "both", // send, receive, both
      "duration_seconds": 10 // Max 60
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

#### Phase-1 Resource Fallback Tools

**Purpose:** These tools provide Phase-1 compatibility for Phase-2 MCP resources. Tools-only clients (ChatGPT, Mistral) can use these tools to access resource data, while resource-aware clients (Claude Desktop, VS Code) can use the more efficient resource URIs directly.

**Best Practice:** Each fallback tool includes a `resource_uri` hint in its response to enable migration to resource-based workflows.

---

##### `device/get-health-data`

**Description:**

```
Get complete device health data including current metrics and historical trends.

Use when:
- User asks "show me device X health history" or "what's the health trend?"
- Need detailed health context for analysis
- Troubleshooting intermittent issues (checking historical data)
- Generating health reports

Returns: Health data with resource URI hint for Phase-2 clients.

Note: Phase-1 fallback for device://{device_id}/health resource.
In clients supporting Resources, use the resource URI directly for more efficient context loading.
```

**Tier**: Fundamental
**Phase**: 1 (Fallback for Phase 2 resource)

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-001",
  "method": "tools/call",
  "params": {
    "name": "device/get-health-data",
    "arguments": {
      "device_id": "dev-lab-01",
      "include_history": true,
      "history_hours": 24
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Device health data for router-lab-01"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "current_health": {
        "status": "healthy",
        "cpu_usage_percent": 5.2,
        "memory_usage_percent": 45.0,
        "temperature_celsius": 42.0,
        "uptime_seconds": 864000
      },
      "history": [
        {
          "timestamp": "2025-01-15T10:00:00Z",
          "status": "healthy",
          "cpu_usage_percent": 4.8,
          "memory_usage_percent": 43.0
        }
      ],
      "resource_uri": "device://dev-lab-01/health",
      "resource_hint": "In clients supporting MCP Resources, use resource_uri for efficient context access"
    }
  }
}
```

---

##### `device/get-config-snapshot`

**Description:**

```
Get device configuration snapshot (export).

Use when:
- User asks "show me device config" or "export configuration"
- Need configuration as context for analysis
- Comparing configurations across devices
- Backup/documentation purposes

Returns: Configuration export with resource URI hint.

Note: Phase-1 fallback for device://{device_id}/config resource.
```

**Tier**: Fundamental
**Phase**: 1 (Fallback)

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-002",
  "method": "tools/call",
  "params": {
    "name": "device/get-config-snapshot",
    "arguments": {
      "device_id": "dev-lab-01",
      "format": "compact"
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-002",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Configuration snapshot for router-lab-01"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "format": "compact",
      "config_text": "/system identity\nset name=router-lab-01\n/ip address\nadd address=192.168.1.1/24 interface=ether1\n...",
      "size_bytes": 2048,
      "snapshot_time": "2025-01-15T14:30:00Z",
      "resource_uri": "device://dev-lab-01/config",
      "resource_hint": "Use resource_uri in MCP Resources-compatible clients"
    }
  }
}
```

---

##### `fleet/get-summary`

**Description:**

```
Get fleet-wide summary and health status.

Use when:
- User asks "show me fleet status" or "how many devices are healthy?"
- Fleet-wide health dashboard
- Auditing device inventory
- Identifying unhealthy devices for investigation

Returns: Fleet summary with resource URI hint.

Note: Phase-1 fallback for fleet://{environment}/summary resource.
```

**Tier**: Fundamental
**Phase**: 1 (Fallback)

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-003",
  "method": "tools/call",
  "params": {
    "name": "fleet/get-summary",
    "arguments": {
      "environment": "lab"
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-003",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Fleet summary: 10 devices, 8 healthy, 2 degraded"
      }
    ],
    "isError": false,
    "_meta": {
      "environment": "lab",
      "total_devices": 10,
      "health_breakdown": {
        "healthy": 8,
        "degraded": 2,
        "unreachable": 0
      },
      "routeros_versions": {
        "7.10.1": 8,
        "7.9.2": 2
      },
      "devices_summary": [
        {
          "device_id": "dev-lab-01",
          "name": "router-lab-01",
          "status": "healthy",
          "routeros_version": "7.10.1"
        }
      ],
      "resource_uri": "fleet://lab/summary",
      "resource_hint": "Use resource_uri for efficient fleet context access"
    }
  }
}
```

---

##### `plan/get-details`

**Description:**

```
Get complete plan details including all target devices and proposed changes.

Use when:
- User asks "show me plan X" or "what does this plan do?"
- Reviewing plan before approval
- Auditing planned changes
- Understanding plan scope and impact

Returns: Complete plan data with resource URI hint.

Note: Phase-1 fallback for plan://{plan_id} resource.
```

**Tier**: Fundamental
**Phase**: 1 (Fallback)

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-004",
  "method": "tools/call",
  "params": {
    "name": "plan/get-details",
    "arguments": {
      "plan_id": "plan-20250115-001"
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-004",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Plan plan-20250115-001: Update DNS/NTP on 3 devices"
      }
    ],
    "isError": false,
    "_meta": {
      "plan_id": "plan-20250115-001",
      "status": "approved",
      "summary": "Update DNS/NTP to Cloudflare on 3 lab devices",
      "risk_level": "low",
      "created_at": "2025-01-15T14:00:00Z",
      "expires_at": "2025-01-16T14:00:00Z",
      "total_devices": 3,
      "devices": [
        {
          "device_id": "dev-lab-01",
          "environment": "lab",
          "changes": [
            {
              "topic": "dns",
              "action": "update_servers",
              "old_value": ["8.8.8.8", "8.8.4.4"],
              "new_value": ["1.1.1.1", "1.0.0.1"]
            }
          ]
        }
      ],
      "resource_uri": "plan://plan-20250115-001",
      "resource_hint": "Use resource_uri for efficient plan context access"
    }
  }
}
```

---

##### `audit/get-events`

**Description:**

```
Get audit events with optional filtering.

Use when:
- User asks "show me audit trail" or "what changes were made?"
- Security auditing and compliance
- Investigating who did what when
- Tracking configuration changes
- Troubleshooting issues (finding recent changes)

Returns: Audit events with resource URI hint.

Note: Phase-1 fallback for audit://{device_id}?start_time={ts}&action={action} resource.
```

**Tier**: Fundamental
**Phase**: 1 (Fallback)

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-005",
  "method": "tools/call",
  "params": {
    "name": "audit/get-events",
    "arguments": {
      "device_id": "dev-lab-01",
      "action": "WRITE",
      "start_time": "2025-01-14T00:00:00Z",
      "limit": 100
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-005",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Found 15 audit events for dev-lab-01"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "total_count": 15,
      "events": [
        {
          "id": "audit-001",
          "timestamp": "2025-01-15T10:30:00Z",
          "action": "WRITE",
          "tool_name": "dns/update-servers",
          "tool_tier": "advanced",
          "result": "success",
          "metadata": {
            "old_servers": ["8.8.8.8"],
            "new_servers": ["1.1.1.1"]
          }
        }
      ],
      "resource_uri": "audit://dev-lab-01?action=WRITE&start_time=2025-01-14T00:00:00Z",
      "resource_hint": "Use resource_uri for efficient audit context access"
    }
  }
}
```

---

##### `snapshot/get-content`

**Description:**

```
Get configuration snapshot content by snapshot ID.

Use when:
- User asks "show me snapshot X" or "what's in this backup?"
- Reviewing configuration snapshots
- Comparing pre/post-change configs
- Rollback planning (viewing old configuration)

Returns: Snapshot content with resource URI hint.

Note: Phase-1 fallback for snapshot://{snapshot_id} resource.
```

**Tier**: Fundamental
**Phase**: 1 (Fallback)

**Request**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-006",
  "method": "tools/call",
  "params": {
    "name": "snapshot/get-content",
    "arguments": {
      "snapshot_id": "snap-20250115-001"
    }
  }
}
```

**Response**:

```json
{
  "jsonrpc": "2.0",
  "id": "req-fb-006",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Snapshot snap-20250115-001: DNS configuration before change"
      }
    ],
    "isError": false,
    "_meta": {
      "snapshot_id": "snap-20250115-001",
      "device_id": "dev-lab-01",
      "kind": "dns_ntp",
      "timestamp": "2025-01-15T10:25:00Z",
      "size_bytes": 512,
      "content": {
        "dns_servers": ["8.8.8.8", "8.8.4.4"],
        "ntp_servers": ["pool.ntp.org"],
        "allow_remote_requests": true
      },
      "resource_uri": "snapshot://snap-20250115-001",
      "resource_hint": "Use resource_uri for efficient snapshot access"
    }
  }
}
```

---

###Phase 2: Single-Device Writes (Advanced Tier)

---

#### System Topic

##### `system/update-identity`

**Description:**

```
Update the system identity (device hostname).

Use when:
- User asks "rename this device to X" or "change hostname"
- Standardizing device naming across fleet
- Correcting misconfigured device names
- Preparing device for production deployment

Side effects:
- Changes device identity immediately
- May require reconnection (if using hostname for management)
- Audit logged
- Pre-change snapshot taken

Returns: Changed status, old identity, new identity.

Safety: Requires allow_advanced_writes=true on device. Use dry_run=true to preview.
```

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
      "dry_run": false // Optional, default false
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

**Description:**

```
Update interface comment (description field).

Use when:
- User asks "add comment to ether1" or "label interface as WAN"
- Documenting interface purposes
- Standardizing interface descriptions across fleet
- Adding context for troubleshooting

Side effects:
- Changes interface comment only (no operational impact)
- Audit logged

Returns: Changed status, old comment, new comment.

Safety: Low-risk operation. Requires allow_advanced_writes=true.
```

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

**Description:**

```
Add a secondary IP address to an interface.

Use when:
- User asks "add secondary IP X to interface Y"
- Configuring multiple IPs on single interface
- Adding temporary address for migration
- Setting up multi-subnet configurations

Side effects:
- Adds new IP address immediately
- Does not remove existing addresses
- Pre-change snapshot taken
- Audit logged

Returns: Changed status, new address ID, address, interface.

Safety:
- Validates no overlapping networks
- Requires allow_advanced_writes=true
- Use dry_run=true to preview
- Does not allow modifying primary management address
```

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

**Description:**

```
Remove a secondary IP address (with safety checks).

Use when:
- User asks "remove IP X" or "delete secondary address"
- Cleaning up unused addresses
- Decommissioning services

Side effects:
- Removes IP address immediately
- Pre-change snapshot taken
- Audit logged

Safety:
- Blocks removal of primary management address
- Blocks removal if only address on interface
- Requires allow_advanced_writes=true
- Use dry_run=true to preview

Returns: Changed status, removed address.
```

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

**Description:**

```
Add or remove entries from MCP-managed firewall address lists.

Use when:
- User asks "add IP X to whitelist Y" or "remove IP from blacklist"
- Managing dynamic access control lists
- Adding/removing hosts from firewall rules
- Implementing temporary access grants (with timeout)

Side effects:
- Adds or removes address-list entry immediately
- Affects firewall rule matching
- Pre-change snapshot taken
- Audit logged

Safety:
- Only allows modification of MCP-managed lists (prefix: mcp-)
- Blocks changes to system address lists
- Requires allow_advanced_writes=true
- Use dry_run=true to preview

Returns: Changed status, action (add/remove), list name, address, entry ID.

Tip: Use timeout parameter for temporary entries (e.g., "7d" for 7 days).
```

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
      "timeout": "7d", // Optional
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

**Description:**

```
Update DNS server configuration.

Use when:
- User asks "change DNS servers to X,Y" or "update DNS config"
- Migrating to new DNS infrastructure
- Fixing DNS resolution issues
- Standardizing DNS across fleet (use multi-device workflow for this)

Side effects:
- Updates DNS servers immediately
- May cause brief DNS resolution disruption
- Pre-change snapshot taken
- Audit logged

Safety:
- Validates server reachability before applying (ping test)
- Requires allow_advanced_writes=true
- Lab/staging environments only by default (prod requires explicit approval)
- Use dry_run=true to preview

Returns: Changed status, old servers, new servers.

Tip: For multi-device changes, use config/plan-dns-ntp-rollout (Professional tier).
```

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

**Description:**

```
Flush (clear) DNS cache.

Use when:
- User asks "flush DNS cache" or "clear DNS"
- Troubleshooting stale DNS entries
- After DNS server changes
- Forcing fresh DNS resolution
- Resolving DNS-related connectivity issues

Side effects:
- Clears all cached DNS entries immediately
- Next DNS query will require upstream resolution
- Slight increase in DNS resolution latency temporarily
- Audit logged

Returns: Changed status, number of entries flushed.

Safety: Low-risk operation. Requires allow_advanced_writes=true.
```

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

**Description:**

```
Update NTP server configuration.

Use when:
- User asks "change NTP servers to X" or "update time servers"
- Migrating to new NTP infrastructure
- Fixing time synchronization issues
- Standardizing NTP across fleet (use multi-device workflow for this)

Side effects:
- Updates NTP configuration immediately
- May cause brief time sync disruption
- System will re-sync with new servers
- Pre-change snapshot taken
- Audit logged

Safety:
- Validates server reachability before applying
- Requires allow_advanced_writes=true
- Lab/staging environments only by default
- Use dry_run=true to preview

Returns: Changed status, old servers, new servers.

Tip: For multi-device changes, use config/plan-dns-ntp-rollout (Professional tier).
```

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

**Description:**

```
Create execution plan for updating DNS/NTP servers across multiple devices.

Use when:
- User asks "update DNS/NTP on all lab devices" or "rollout new time servers"
- Standardizing DNS/NTP infrastructure across fleet
- Migrating to new DNS/NTP providers
- Need change preview before applying
- Multi-device coordination required

Pattern: This is the PLAN step (no changes applied).

Returns: Plan ID, summary, list of devices with proposed changes.

Next step: Review plan, then use config/apply-dns-ntp-rollout to execute.

Safety:
- No side effects (plan only)
- Requires allow_professional_workflows=true on all target devices
- Plan expires after 24 hours

Tip: Always review plan details before applying!
```

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

**Description:**

```
Execute approved DNS/NTP rollout plan.

Use when:
- After reviewing plan from config/plan-dns-ntp-rollout
- User confirms "apply the plan" or "execute rollout"
- Ready to make changes across multiple devices

Pattern: This is the APPLY step (executes changes).

Side effects:
- Updates DNS/NTP on all devices in plan
- Creates pre/post-change snapshots per device
- Job executes asynchronously
- Audit logged per device

Safety:
- Requires approval token (Phase 5: multi-user approval; Phase 1-4: self-approval)
- Plan must be valid and not expired
- Requires allow_professional_workflows=true on devices
- Rollback available via snapshots

Returns: Job ID, execution status, success/failure counts, per-device results.

Note: Execution is sequential across devices to minimize blast radius.
```

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
      "approval_token": "approval-token-xyz" // Phase 5: multi-user approval; Phase 1-4: self-approval allowed
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

**Description:**

```
Create plan for synchronizing firewall address-list entries across devices.

Use when:
- User asks "sync whitelist across fleet" or "update blacklist on all devices"
- Maintaining consistent address lists across multiple routers
- Deploying new access control rules fleet-wide
- Need preview before changing firewall rules

Pattern: This is the PLAN step.

Returns: Plan ID, summary, list of devices with proposed address-list changes.

Next step: Review, then use config/apply-address-list-sync.

Safety:
- No side effects (plan only)
- Only syncs MCP-managed lists (prefix: mcp-)
- Requires allow_professional_workflows=true

Tip: Useful for managing distributed firewall policies.
```

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
        { "address": "10.0.1.100", "comment": "MCP server" },
        { "address": "10.0.1.200", "comment": "Monitoring" }
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

**Description:**

```
Execute approved address-list synchronization plan.

Use when:
- After reviewing plan from config/plan-address-list-sync
- User confirms "sync address lists" or "apply firewall update"

Pattern: This is the APPLY step.

Side effects:
- Adds/removes address-list entries on all devices
- Creates pre/post-change snapshots
- May affect active firewall rules
- Audit logged per device

Safety:
- Requires approval token
- Only modifies MCP-managed lists
- Plan must be valid
- Rollback available via snapshots

Returns: Job ID, execution status, per-device results.

Note: Changes may affect active connections if firewall rules reference these lists.
```

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

**Description:**

```
Add a static route (high-risk operation).

Use when:
- User asks "add route to network X via gateway Y"
- Configuring routing to remote networks
- Setting up site-to-site connectivity
- Need custom routing beyond connected/dynamic routes

Side effects:
- Adds static route immediately
- Affects routing decisions and traffic flow
- May disrupt connectivity if misconfigured
- Pre-change snapshot taken
- Audit logged

Safety:
- Professional tier (requires allow_professional_workflows=true)
- Use dry_run=true for planning
- Validates gateway reachability
- Warns if conflicts with existing routes
- Phase 4: Requires plan/apply pattern for production

Returns: Changed status, planned route details.

Warning: Routing changes can cause connectivity loss. Always use dry_run first!
```

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
      "dry_run": true // Plan mode
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

**Description:**

```
Remove a static route (high-risk operation).

Use when:
- User asks "delete route to X" or "remove static route"
- Decommissioning network connectivity
- Cleaning up obsolete routes
- Correcting misconfigurations

Side effects:
- Removes route immediately
- May break connectivity to destination network
- Pre-change snapshot taken
- Audit logged

Safety:
- Professional tier (requires allow_professional_workflows=true)
- Use dry_run=true to preview
- Warns if route is currently active
- Blocks removal of default route without explicit confirmation

Returns: Changed status, removed route details.

Warning: Removing routes can cause connectivity loss. Verify alternate paths first!
```

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

**Description:**

```
Register a new RouterOS device in the MCP service.

Use when:
- User asks "add new device" or "register router X"
- Onboarding new hardware
- Expanding managed device inventory
- Setting up fresh RouterOS installation

Side effects:
- Creates device record in MCP database
- Encrypts and stores credentials
- Schedules initial health check
- Audit logged

Safety:
- Validates connectivity before registration
- Encrypts credentials at rest
- Requires valid RouterOS credentials
- Default capability flags are conservative (writes disabled)

Returns: Device ID, registration status, initial connectivity check.

Next steps:
1. Verify connectivity with device/check-connectivity
2. Get system info with system/get-overview
3. Update capability flags if needed with device/update-device
```

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
      "tags": { "site": "main", "role": "access" },
      "allow_advanced_writes": true,
      "allow_professional_workflows": false,
      "credentials": {
        "username": "admin",
        "password": "secret123" // Will be encrypted
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

**Description:**

```
Update device metadata, tags, or capability flags.

Use when:
- User asks "enable advanced writes on device X" or "update device tags"
- Changing device capability flags (allow_advanced_writes, allow_professional_workflows)
- Updating device tags for organization (site, role, region)
- Modifying device metadata without touching RouterOS

Side effects:
- Updates device record in MCP database
- Changes authorization behavior (if modifying capability flags)
- Audit logged

Safety:
- MCP-only operation (no RouterOS changes)
- Capability flag changes affect tool authorization
- Be cautious enabling professional workflows on production devices

Returns: Changed status, updated fields, new capability flags.

Tip: Use tags for flexible device grouping (e.g., {"site": "dc1", "role": "edge", "region": "us-west"}).
```

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
      "tags": { "site": "main", "role": "edge", "region": "us-west" },
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

| Tool Name                        | Topic     | Tier         | Phase | RouterOS Endpoint                     |
| -------------------------------- | --------- | ------------ | ----- | ------------------------------------- |
| `device/list-devices`            | Device    | Fundamental  | 1     | N/A (MCP-only)                        |
| `device/check-connectivity`      | Device    | Fundamental  | 1     | `GET /rest/system/identity`           |
| `device/register-device`         | Device    | Advanced     | 1     | N/A (MCP-only)                        |
| `device/update-device`           | Device    | Advanced     | 1     | N/A (MCP-only)                        |
| `system/get-overview`            | System    | Fundamental  | 1     | Multiple `/rest/system/*`             |
| `system/get-packages`            | System    | Fundamental  | 1     | `GET /rest/system/package`            |
| `system/get-clock`               | System    | Fundamental  | 1     | `GET /rest/system/clock`              |
| `system/update-identity`         | System    | Advanced     | 2     | `PATCH /rest/system/identity`         |
| `interface/list-interfaces`      | Interface | Fundamental  | 1     | `GET /rest/interface`                 |
| `interface/get-interface`        | Interface | Fundamental  | 1     | `GET /rest/interface/{id}`            |
| `interface/get-stats`            | Interface | Fundamental  | 1     | `GET /rest/interface/monitor-traffic` |
| `interface/update-comment`       | Interface | Advanced     | 2     | `PATCH /rest/interface/{id}`          |
| `ip/list-addresses`              | IP        | Fundamental  | 1     | `GET /rest/ip/address`                |
| `ip/get-address`                 | IP        | Fundamental  | 1     | `GET /rest/ip/address/{id}`           |
| `ip/get-arp-table`               | IP        | Fundamental  | 1     | `GET /rest/ip/arp`                    |
| `ip/add-secondary-address`       | IP        | Advanced     | 2     | `PUT /rest/ip/address`                |
| `ip/remove-secondary-address`    | IP        | Advanced     | 2     | `DELETE /rest/ip/address/{id}`        |
| `ip/update-address-list-entry`   | IP        | Advanced     | 2     | Multiple firewall endpoints           |
| `dns/get-status`                 | DNS       | Fundamental  | 1     | `GET /rest/ip/dns`                    |
| `dns/get-cache`                  | DNS       | Fundamental  | 1     | `GET /rest/ip/dns/cache`              |
| `dns/update-servers`             | DNS       | Advanced     | 2     | `PATCH /rest/ip/dns`                  |
| `dns/flush-cache`                | DNS       | Advanced     | 2     | `POST /rest/ip/dns/cache/flush`       |
| `ntp/get-status`                 | NTP       | Fundamental  | 1     | Multiple NTP endpoints                |
| `ntp/update-servers`             | NTP       | Advanced     | 2     | `PATCH /rest/system/ntp/client`       |
| `routing/get-summary`            | Routing   | Fundamental  | 1     | `GET /rest/ip/route`                  |
| `routing/get-route`              | Routing   | Fundamental  | 1     | `GET /rest/ip/route/{id}`             |
| `routing/add-static-route`       | Routing   | Professional | 4     | `PUT /rest/ip/route`                  |
| `routing/remove-static-route`    | Routing   | Professional | 4     | `DELETE /rest/ip/route/{id}`          |
| `firewall/list-filter-rules`     | Firewall  | Fundamental  | 1     | `GET /rest/ip/firewall/filter`        |
| `firewall/list-nat-rules`        | Firewall  | Fundamental  | 1     | `GET /rest/ip/firewall/nat`           |
| `firewall/list-address-lists`    | Firewall  | Fundamental  | 1     | `GET /rest/ip/firewall/address-list`  |
| `logs/get-recent`                | Logs      | Fundamental  | 1     | `GET /rest/log`                       |
| `logs/get-config`                | Logs      | Fundamental  | 1     | `GET /rest/system/logging`            |
| `tool/ping`                      | Tool      | Fundamental  | 1     | `POST /rest/tool/ping`                |
| `tool/traceroute`                | Tool      | Fundamental  | 1     | `POST /rest/tool/traceroute`          |
| `tool/bandwidth-test`            | Tool      | Fundamental  | 1     | `POST /rest/tool/bandwidth-test`      |
| `config/plan-dns-ntp-rollout`    | Config    | Professional | 4     | N/A (plan step)                       |
| `config/apply-dns-ntp-rollout`   | Config    | Professional | 4     | Multiple endpoints                    |
| `config/plan-address-list-sync`  | Config    | Professional | 4     | N/A (plan step)                       |
| `config/apply-address-list-sync` | Config    | Professional | 4     | Multiple endpoints                    |

**Note:** The table above is a Phase 1–2 REST endpoint snapshot and does **not** list all 62 currently implemented tools (Phase 3 wireless, DHCP, bridge, and additional routing/firewall plan/apply tools are documented in the sections above).

---

## Tool Metadata Specification

**Every tool must declare the following metadata for optimal MCP client integration:**

### Required Metadata Fields

```python
class ToolMetadata(BaseModel):
    """Complete tool metadata for MCP introspection."""

    # Identity
    name: str                        # Tool name (e.g., "system/get-overview")
    description: str                 # Human-readable description
    topic: str                       # Topic category

    # Security & Access
    tier: str                        # fundamental/advanced/professional
    phase: int                       # Phase number (1-5)
    required_role: str               # read_only/ops_rw/admin (Phase 4)
    environments: list[str]          # Allowed environments
    requires_approval: bool          # Approval token required (Phase 4)

    # Execution Characteristics
    timeout_seconds: int             # Maximum execution time
    idempotent: bool                 # Can be safely retried
    supports_dry_run: bool           # Supports dry_run parameter

    # Response Characteristics
    cacheable: bool                  # Response can be cached
    cache_ttl_seconds: int | None    # Cache TTL (if cacheable)
    estimated_tokens: int            # Estimated response size (tokens)
    supports_pagination: bool        # Supports limit/offset

    # Streaming Support
    supports_streaming: bool         # Supports progress notifications

    # Schemas
    input_schema: dict               # JSON Schema for request arguments
    output_schema: dict              # JSON Schema for response _meta

    # Deprecation
    deprecated: bool                 # Tool is deprecated
    replacement_tool: str | None     # Replacement tool name
    deprecation_date: str | None     # ISO 8601 date
```

### Example Tool Metadata

```python
SYSTEM_GET_OVERVIEW_METADATA = ToolMetadata(
    name="system/get-overview",
    description="Get comprehensive system overview (resources, identity, routerboard info)",
    topic="system",
    tier="fundamental",
    phase=1,
    required_role="read_only",
    environments=["lab", "staging", "prod"],
    requires_approval=False,
    timeout_seconds=10,
    idempotent=True,
    supports_dry_run=False,
    cacheable=True,
    cache_ttl_seconds=60,
    estimated_tokens=500,
    supports_pagination=False,
    supports_streaming=False,
    input_schema={
        "type": "object",
        "properties": {
            "device_id": {"type": "string"},
            "correlation_id": {"type": "string"}
        },
        "required": ["device_id"]
    },
    output_schema={...},
    deprecated=False,
    replacement_tool=None,
    deprecation_date=None
)
```

### Metadata by Tool Category

**Read-Only Fundamental Tools:**

- `timeout_seconds`: 10-30s
- `idempotent`: true
- `supports_dry_run`: false (no writes)
- `cacheable`: true (30-300s TTL)
- `estimated_tokens`: 200-2000

**Single-Device Write Tools (Advanced):**

- `timeout_seconds`: 15-30s
- `idempotent`: true (read-modify-write pattern)
- `supports_dry_run`: true
- `cacheable`: false
- `estimated_tokens`: 100-500

**Multi-Device Workflows (Professional):**

- `timeout_seconds`: 60-300s
- `idempotent`: false (plan/apply pattern)
- `supports_dry_run`: N/A (plan step is dry-run)
- `cacheable`: false
- `estimated_tokens`: 1000-10000

**Diagnostic Tools:**

- `timeout_seconds`: 30-120s
- `idempotent`: false (network-dependent)
- `supports_dry_run`: false
- `cacheable`: false
- `supports_streaming`: true (ping, traceroute)
- `estimated_tokens`: 200-1000

---

## Pagination Standard

**Tools returning lists MUST support standardized pagination:**

### Pagination Parameters

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "method": "tools/call",
  "params": {
    "name": "logs/get-recent",
    "arguments": {
      "device_id": "dev-lab-01",
      "limit": 100, // Max items to return (default: 100, max: 1000)
      "offset": 0, // Skip N items (default: 0)
      "topics": ["system", "error"]
    }
  }
}
```

### Pagination Response

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "Retrieved 100 of 450 log entries"
      }
    ],
    "isError": false,
    "_meta": {
      "device_id": "dev-lab-01",
      "log_entries": [ ... ],
      "pagination": {
        "limit": 100,
        "offset": 0,
        "returned_count": 100,
        "total_count": 450,
        "has_more": true,
        "next_offset": 100
      }
    }
  }
}
```

### Tools Supporting Pagination

| Tool Name                     | Default Limit | Max Limit | Total Count Source          |
| ----------------------------- | ------------- | --------- | --------------------------- |
| `device/list-devices`         | 100           | 1000      | MCP database                |
| `interface/list-interfaces`   | 50            | 500       | RouterOS `/rest/interface`  |
| `ip/list-addresses`           | 50            | 500       | RouterOS `/rest/ip/address` |
| `ip/get-arp-table`            | 100           | 1000      | RouterOS `/rest/ip/arp`     |
| `firewall/list-filter-rules`  | 50            | 500       | RouterOS firewall API       |
| `firewall/list-nat-rules`     | 50            | 500       | RouterOS firewall API       |
| `firewall/list-address-lists` | 100           | 1000      | RouterOS firewall API       |
| `logs/get-recent`             | 100           | 1000      | RouterOS `/rest/log`        |
| `routing/get-summary`         | 100           | 1000      | RouterOS `/rest/ip/route`   |

---

## Token Budget Estimates

**Estimated token counts for LLM context management:**

### By Tool Category

**Device Management:**

- `device/list-devices`: 200-2000 tokens (depends on device count)
- `device/check-connectivity`: 100-200 tokens

**System Status:**

- `system/get-overview`: 400-600 tokens
- `system/get-packages`: 300-1500 tokens (12-50 packages)
- `system/get-clock`: 100-150 tokens

**Network Interfaces:**

- `interface/list-interfaces`: 500-5000 tokens (10-100 interfaces)
- `interface/get-interface`: 200-300 tokens
- `interface/get-stats`: 150-250 tokens per interface

**IP Configuration:**

- `ip/list-addresses`: 300-3000 tokens (5-50 addresses)
- `ip/get-arp-table`: 500-5000 tokens (10-100 entries)

**DNS/NTP:**

- `dns/get-status`: 150-250 tokens
- `dns/get-cache`: 1000-10000 tokens (10-1000 entries)
- `ntp/get-status`: 150-250 tokens

**Routing:**

- `routing/get-summary`: 800-8000 tokens (25-250 routes)
- `routing/get-route`: 150-250 tokens

**Firewall:**

- `firewall/list-filter-rules`: 800-8000 tokens (15-150 rules)
- `firewall/list-nat-rules`: 300-3000 tokens (3-30 rules)
- `firewall/list-address-lists`: 500-5000 tokens (10-100 entries)

**Logs:**

- `logs/get-recent`: 5000-200000 tokens (**WARNING**: 100-1000 entries × 50-200 tokens/entry)
  - **Recommendation**: Default limit=100, max=1000
  - **Token budget**: ~5000-20000 tokens for 100 entries

**Diagnostics:**

- `tool/ping`: 200-400 tokens
- `tool/traceroute`: 400-1200 tokens (8-30 hops)
- `tool/bandwidth-test`: 200-300 tokens

**Multi-Device Workflows:**

- `config/plan-dns-ntp-rollout`: 1000-10000 tokens (depends on device count)
- `config/apply-dns-ntp-rollout`: 1000-10000 tokens

### Token Budget Recommendations

1. **Always use pagination** for list operations
2. **Default limit=100** for logs and large lists
3. **Warn users** when response exceeds 10,000 tokens
4. **Truncate logs** older than 24 hours
5. **Cache read-only responses** to reduce RouterOS load

---

## Common Request/Response Fields

### All Tools

**Common Request Fields:**

- `device_id` (string, required for device-specific tools): MCP device identifier
- `dry_run` (boolean, optional, default false): Plan mode without applying changes
- `correlation_id` (string, optional): Request correlation ID for tracing

**Common Response Fields in `_meta`:**

- `device_id` (string): Device identifier
- `changed` (boolean, for write operations): Whether configuration changed
- `execution_time_ms` (number, optional): Tool execution time
- `correlation_id` (string, optional): Request correlation ID (echoed from request)

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

### Phase 5 (Multi-User RBAC)

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

## MCP Resources Primitive (Phase 2)

**Phase 2 adds MCP Resources primitive for config exports and file access.**

### What are MCP Resources?

Resources are URI-addressable content that MCP clients can read. Unlike tools (which execute operations), resources provide direct access to configuration data.

**Benefits:**

- Full MCP clients (Claude Desktop, VS Code) can browse resources
- Enables context attachment for LLM conversations
- Supports large config files without tool token limits

### Planned Resources (Phase 2)

#### RouterOS Configuration Export

**Resource URI Pattern**: `routeros://{device_id}/config/export`

**Example URIs:**

- `routeros://dev-lab-01/config/export` - Full configuration
- `routeros://dev-lab-01/config/export?compact=true` - Compact format
- `routeros://dev-lab-01/config/export?topic=firewall` - Firewall config only

**MCP Resource Schema:**

```json
{
  "jsonrpc": "2.0",
  "method": "resources/read",
  "params": {
    "uri": "routeros://dev-lab-01/config/export"
  }
}
```

**Response:**

```json
{
  "jsonrpc": "2.0",
  "result": {
    "contents": [
      {
        "uri": "routeros://dev-lab-01/config/export",
        "mimeType": "text/x-routeros-script",
        "text": "# jan/15/2025 14:30:00 by RouterOS 7.10.1\n/system identity\nset name=router-lab-01\n..."
      }
    ]
  }
}
```

**Token Considerations:**

- Full config export: 10,000-100,000 tokens
- Compact export: 5,000-50,000 tokens
- Topic-filtered export: 1,000-10,000 tokens

#### System Package Information

**Resource URI**: `routeros://{device_id}/system/packages`

**Response**: JSON array of installed packages

#### Device Inventory

**Resource URI**: `mcp://devices`

**Response**: JSON array of all registered devices

### Resource vs Tool Decision Matrix

| Use Case                                | Use Tool | Use Resource   |
| --------------------------------------- | -------- | -------------- |
| Execute operation (ping, change config) | ✅       | ❌             |
| Get current status (small response)     | ✅       | ❌             |
| Export large config file                | ❌       | ✅             |
| Browse device inventory                 | Both     | ✅ (better UX) |
| Attach context to LLM conversation      | ❌       | ✅             |
| Stream real-time data                   | ✅       | ❌             |

**Implementation Priority**: Phase 2 (after Phase 1 tools are stable)

---

## Streaming Support for Long-Running Tools (Phase 3)

**Phase 4 may add JSON-RPC streaming for long-running diagnostics.**

### Streaming-Compatible Tools

1. `tool/ping` - Progress notifications per packet
2. `tool/traceroute` - Progress notifications per hop
3. `tool/bandwidth-test` - Periodic throughput updates
4. `config/apply-dns-ntp-rollout` - Per-device completion notifications

### Streaming Protocol (JSON-RPC 2.0 Notifications)

**Initial Request:**

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
      "count": 10,
      "stream_progress": true // Enable streaming
    }
  }
}
```

**Progress Notifications (no id - these are notifications):**

```json
{
  "jsonrpc": "2.0",
  "method": "tools/progress",
  "params": {
    "request_id": "req-022",
    "progress": {
      "current": 3,
      "total": 10,
      "message": "Ping #3: 12.5ms"
    }
  }
}
```

**Final Response:**

```json
{
  "jsonrpc": "2.0",
  "id": "req-022",
  "result": {
    "content": [{ "type": "text", "text": "Ping completed: 10/10 packets" }],
    "_meta": {
      "packets_sent": 10,
      "packets_received": 10,
      "avg_rtt_ms": 12.0
    }
  }
}
```

**Implementation Priority**: Phase 3 (after Resources are implemented)

---

## Tool Composition Patterns

**Common workflows combining multiple tools:**

### Pattern 1: Device Discovery & Health Check

```python
# 1. List all lab devices
devices = await call_tool("device/list-devices", {
    "environment": "lab"
})

# 2. Check connectivity for each device (parallel)
connectivity_checks = await asyncio.gather(*[
    call_tool("device/check-connectivity", {"device_id": d["id"]})
    for d in devices["_meta"]["devices"]
])

# 3. Get overview for reachable devices
reachable_ids = [
    c["_meta"]["device_id"]
    for c in connectivity_checks
    if c["_meta"]["reachable"]
]

overviews = await asyncio.gather(*[
    call_tool("system/get-overview", {"device_id": device_id})
    for device_id in reachable_ids
])
```

### Pattern 2: Configuration Audit

```python
# 1. Get current DNS configuration
dns_status = await call_tool("dns/get-status", {
    "device_id": "dev-lab-01"
})

# 2. Get NTP configuration
ntp_status = await call_tool("ntp/get-status", {
    "device_id": "dev-lab-01"
})

# 3. Compare with desired state
compliance = check_compliance(dns_status, ntp_status, desired_state)
```

### Pattern 3: Safe Configuration Change

```python
# 1. Plan the change (dry-run)
plan = await call_tool("dns/update-servers", {
    "device_id": "dev-lab-01",
    "dns_servers": ["1.1.1.1", "1.0.0.1"],
    "dry_run": True
})

# 2. Review plan with user
if plan["_meta"]["changed"]:
    user_approval = await get_user_approval(plan)

# 3. Apply change
if user_approval:
    result = await call_tool("dns/update-servers", {
        "device_id": "dev-lab-01",
        "dns_servers": ["1.1.1.1", "1.0.0.1"],
        "dry_run": False
    })

# 4. Verify change
verification = await call_tool("dns/get-status", {
    "device_id": "dev-lab-01"
})
```

### Pattern 4: Multi-Device Rollout (Professional)

```python
# 1. Create rollout plan
plan = await call_tool("config/plan-dns-ntp-rollout", {
    "device_ids": ["dev-lab-01", "dev-lab-02", "dev-lab-03"],
    "dns_servers": ["1.1.1.1", "1.0.0.1"],
    "ntp_servers": ["time.cloudflare.com"]
})

# 2. Review plan
plan_id = plan["_meta"]["plan_id"]
print(f"Plan {plan_id} affects {plan['_meta']['total_devices']} devices")

# 3. Get approval token (Phase 4)
approval_token = await get_approval_token(plan_id)

# 4. Execute plan
result = await call_tool("config/apply-dns-ntp-rollout", {
    "plan_id": plan_id,
    "approval_token": approval_token
})

# 5. Monitor execution
print(f"Success: {result['_meta']['successful']}/{result['_meta']['total_devices']}")
```

---

## Related Documents

- **[Doc 03: RouterOS Integration & Endpoint Mappings](03-routeros-integration-and-platform-constraints-rest-and-ssh.md)** - REST API endpoint details
- **[Doc 19: JSON-RPC Error Codes & MCP Protocol](19-json-rpc-error-codes-and-mcp-protocol-specification.md)** - Complete error taxonomy
- **[ENDPOINT-TOOL-MAPPING.md](ENDPOINT-TOOL-MAPPING.md)** - Cross-reference analysis between endpoints and tools
- **[README.md](../README.md)** - Phase roadmap and project overview

---

**Document Status**: ✅ Complete with 62 tools (Phase 1-3 implemented: fundamental read-only, advanced single-device writes including firewall/DHCP/bridge/wireless; Phase 4 planned: diagnostics, multi-device coordination), full JSON-RPC schemas, intent-based descriptions, and phase assignments
