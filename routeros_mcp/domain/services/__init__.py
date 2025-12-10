"""Domain services for RouterOS MCP.

Domain services encapsulate business logic and orchestrate operations
across persistence, RouterOS clients, and domain models. They provide
clean, typed interfaces for MCP tools and ensure proper error handling,
authorization, and environment semantics.

Services in this package:
- DeviceService: Device registry and credential management
- HealthService: Device and fleet health computation
- SystemService: System information and metrics collection
- InterfaceService: Network interface operations
- IPService: IP address configuration operations
- DNSNTPService: DNS and NTP configuration operations
- RoutingService: Routing table operations
- FirewallLogsService: Firewall rules and system logs operations
- DiagnosticsService: Network diagnostic operations (ping, traceroute)
- PlanService: Plan/apply workflow for multi-device changes
- JobService: Job execution and coordination
"""

from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.diagnostics import DiagnosticsService
from routeros_mcp.domain.services.dns_ntp import DNSNTPService
from routeros_mcp.domain.services.firewall_logs import FirewallLogsService
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.domain.services.interface import InterfaceService
from routeros_mcp.domain.services.ip import IPService
from routeros_mcp.domain.services.job import JobService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.domain.services.routing import RoutingService
from routeros_mcp.domain.services.system import SystemService

__all__ = [
    "DeviceService",
    "DiagnosticsService",
    "DNSNTPService",
    "FirewallLogsService",
    "HealthService",
    "InterfaceService",
    "IPService",
    "JobService",
    "PlanService",
    "RoutingService",
    "SystemService",
]
