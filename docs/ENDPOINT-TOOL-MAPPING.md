# Endpoint-to-Tool Mapping Analysis

## Date
2025-01-15

## Purpose

Cross-reference between Doc 03 (RouterOS REST endpoint mappings) and Doc 04 (MCP tool catalog) to ensure consistency and completeness.

---

## Mapping Table

| RouterOS REST Endpoint | Doc 03 Section | MCP Tool Name | Doc 04 Tier | Phase | Status |
|------------------------|----------------|---------------|-------------|-------|--------|
| **System Topic** |
| GET `/rest/system/resource` | System | `system.get_overview` | Fundamental | Phase 1 | ✅ Defined |
| GET `/rest/system/identity` | System | `system.get_overview` | Fundamental | Phase 1 | ✅ Defined |
| PUT/PATCH `/rest/system/identity` | System | `system.update_identity` | Advanced | Phase 2 | ✅ Defined |
| GET `/rest/system/routerboard` | System | `system.get_overview` | Fundamental | Phase 1 | ✅ Defined |
| GET `/rest/system/package` | System | `system.get_packages` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| GET `/rest/system/clock` | System | `system.get_clock` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| **Interface Topic** |
| GET `/rest/interface` | Interface | `interface.list_interfaces` | Fundamental | Phase 1 | ✅ Defined |
| GET `/rest/interface/{id}` | Interface | `interface.get_interface` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| PATCH `/rest/interface/{id}` | Interface | `interface.update_comment` | Advanced | Phase 2 | ✅ Defined |
| GET `/rest/interface/monitor-traffic` | Interface | `interface.get_stats` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| **IP Address Topic** |
| GET `/rest/ip/address` | IP Address | `ip.list_addresses` | Fundamental | Phase 1 | ✅ Defined |
| GET `/rest/ip/address/{id}` | IP Address | `ip.get_address` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| PUT `/rest/ip/address` | IP Address | `ip.add_secondary_address` | Advanced | Phase 2 | ✅ Defined |
| DELETE `/rest/ip/address/{id}` | IP Address | `ip.remove_secondary_address` | Advanced | Phase 2 | ✅ Defined |
| GET `/rest/ip/arp` | IP Address | `ip.get_arp_table` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| **DNS Topic** |
| GET `/rest/ip/dns` | DNS | `dns.get_status` | Fundamental | Phase 1 | ✅ Defined |
| PUT/PATCH `/rest/ip/dns` | DNS | `dns.update_servers` | Advanced | Phase 2 | ⚠️ Add to Doc 04 |
| GET `/rest/ip/dns/cache` | DNS | `dns.get_cache` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| POST `/rest/ip/dns/cache/flush` | DNS | `dns.flush_cache` | Advanced | Phase 2 | ⚠️ Add to Doc 04 |
| **NTP Topic** |
| GET `/rest/system/ntp/client` | NTP | `ntp.get_status` | Fundamental | Phase 1 | ✅ Defined |
| PUT/PATCH `/rest/system/ntp/client` | NTP | `ntp.update_servers` | Advanced | Phase 2 | ⚠️ Add to Doc 04 |
| GET `/rest/system/ntp/client/monitor` | NTP | `ntp.get_status` | Fundamental | Phase 1 | ✅ Defined |
| **Routing Topic** |
| GET `/rest/ip/route` | Routes | `routing.get_summary` | Fundamental | Phase 1 | ✅ Defined |
| GET `/rest/ip/route/{id}` | Routes | `routing.get_route` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| PUT `/rest/ip/route` | Routes | `routing.add_static_route` | Professional | Phase 4 | ⚠️ Add to Doc 04 |
| DELETE `/rest/ip/route/{id}` | Routes | `routing.remove_static_route` | Professional | Phase 4 | ⚠️ Add to Doc 04 |
| **Firewall Topic** |
| GET `/rest/ip/firewall/filter` | Firewall | `firewall.list_filter_rules` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| GET `/rest/ip/firewall/nat` | Firewall | `firewall.list_nat_rules` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| GET `/rest/ip/firewall/address-list` | Firewall | `firewall.list_address_lists` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| PUT `/rest/ip/firewall/address-list` | Firewall | `ip.update_address_list_entry` | Advanced | Phase 2 | ✅ Defined |
| DELETE `/rest/ip/firewall/address-list/{id}` | Firewall | `ip.update_address_list_entry` | Advanced | Phase 2 | ✅ Defined |
| **Logging Topic** |
| GET `/rest/log` | Logging | `logs.get_recent` | Fundamental | Phase 1/2 | ✅ Defined |
| GET `/rest/system/logging` | Logging | `logs.get_config` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| **Diagnostics Topic** |
| POST `/rest/tool/ping` | Tool | `tool.ping` | Fundamental | Phase 1 | ✅ Defined |
| POST `/rest/tool/traceroute` | Tool | `tool.traceroute` | Fundamental | Phase 1 | ✅ Defined |
| POST `/rest/tool/bandwidth-test` | Tool | `tool.bandwidth_test` | Fundamental | Phase 1 | ⚠️ Add to Doc 04 |
| **Device Management (MCP-only, no RouterOS endpoint)** |
| N/A | N/A | `device.list_devices` | Fundamental | Phase 1 | ✅ Defined |
| N/A | N/A | `device.check_connectivity` | Fundamental | Phase 1 | ✅ Defined |
| N/A | N/A | `device.register_device` | Advanced | Phase 1 | ⚠️ Add to Doc 04 |
| N/A | N/A | `device.update_device` | Advanced | Phase 1 | ⚠️ Add to Doc 04 |
| **Multi-Device Workflows (Professional Tier)** |
| Multiple | N/A | `config.plan_dns_ntp_rollout` | Professional | Phase 4 | ✅ Defined |
| Multiple | N/A | `config.apply_dns_ntp_rollout` | Professional | Phase 4 | ✅ Defined |
| Multiple | N/A | `config.plan_address_list_sync` | Professional | Phase 4 | ✅ Defined |
| Multiple | N/A | `config.apply_address_list_sync` | Professional | Phase 4 | ✅ Defined |

---

## Findings

### ✅ Consistent Mappings

These tools are properly defined in both documents:
- `system.get_overview` → `/rest/system/resource`, `/rest/system/identity`, `/rest/system/routerboard`
- `interface.list_interfaces` → `/rest/interface`
- `interface.update_comment` → `PATCH /rest/interface/{id}`
- `ip.list_addresses` → `/rest/ip/address`
- `dns.get_status` → `/rest/ip/dns`
- `ntp.get_status` → `/rest/system/ntp/client` + `/rest/system/ntp/client/monitor`
- `routing.get_summary` → `/rest/ip/route`
- `tool.ping` → `POST /rest/tool/ping`
- `tool.traceroute` → `POST /rest/tool/traceroute`
- `logs.get_recent` → `GET /rest/log`

### ⚠️ Missing Tools in Doc 04

These endpoints are documented in Doc 03 but need corresponding tools in Doc 04:

**Phase 1 (Fundamental - Read-Only):**
- `system.get_packages` → `GET /rest/system/package`
- `system.get_clock` → `GET /rest/system/clock`
- `interface.get_interface` → `GET /rest/interface/{id}`
- `interface.get_stats` → `GET /rest/interface/monitor-traffic`
- `ip.get_address` → `GET /rest/ip/address/{id}`
- `ip.get_arp_table` → `GET /rest/ip/arp`
- `dns.get_cache` → `GET /rest/ip/dns/cache`
- `routing.get_route` → `GET /rest/ip/route/{id}`
- `firewall.list_filter_rules` → `GET /rest/ip/firewall/filter`
- `firewall.list_nat_rules` → `GET /rest/ip/firewall/nat`
- `firewall.list_address_lists` → `GET /rest/ip/firewall/address-list`
- `logs.get_config` → `GET /rest/system/logging`
- `tool.bandwidth_test` → `POST /rest/tool/bandwidth-test`

**Phase 2 (Advanced - Single-Device Writes):**
- `dns.update_servers` → `PUT/PATCH /rest/ip/dns`
- `dns.flush_cache` → `POST /rest/ip/dns/cache/flush`
- `ntp.update_servers` → `PUT/PATCH /rest/system/ntp/client`

**Phase 4 (Professional - High-Risk):**
- `routing.add_static_route` → `PUT /rest/ip/route`
- `routing.remove_static_route` → `DELETE /rest/ip/route/{id}`

**Device Management (MCP-only):**
- `device.register_device` - Register new device in MCP
- `device.update_device` - Update device metadata

---

## Recommendations

1. **Add Missing Tools to Doc 04**: Update the tool catalog section to include all tools listed above
2. **Provide JSON-RPC Schemas**: Create complete request/response schemas for ALL tools (see Doc 19 for format)
3. **Clarify Phase Assignment**: Ensure each tool clearly specifies which phase it belongs to
4. **Update Tool Specifications Section**: Expand from 2 examples to comprehensive schemas for all tools

---

## Next Steps

1. Update Doc 04 with complete tool catalog
2. Add JSON-RPC request/response schemas for all tools
3. Reference Doc 19 for error code specifications
4. Ensure consistency with README phase roadmap
