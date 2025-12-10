"""Domain services for RouterOS MCP.

Domain services encapsulate business logic and orchestrate operations
across persistence, RouterOS clients, and domain models. They provide
clean, typed interfaces for MCP tools and ensure proper error handling,
authorization, and environment semantics.

Services in this package:
- DeviceService: Device registry and credential management
- HealthService: Device and fleet health computation
- SystemService: System information and metrics collection
- (Topic-specific services for DNS, NTP, IP, firewall, diagnostics)
"""

from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.domain.services.system import SystemService

__all__ = [
    "DeviceService",
    "HealthService",
    "SystemService",
]
