"""Test utilities for Phase 3 e2e tests.

Provides:
- Mock RouterOS REST clients with realistic responses
- Test fixtures for plan/apply workflows
- Mock response factories for firewall, routing, wireless, DHCP, bridge operations
"""

from __future__ import annotations

from typing import Any


class MockRouterOSRestClient:
    """Stateful mock RouterOS REST client for Phase 3 e2e tests.

    This client simulates RouterOS REST interactions and maintains in-memory
    device configuration state (firewall rules, routes, wireless interfaces,
    DHCP servers, bridge ports). It records all REST calls for later
    verification and models post-change health checks used by the e2e tests.

    Supports configurable failure modes:
    - rest_error: Simulate REST API errors on any REST call
    - health_check_failure: Simulate failed health checks after changes are applied
    - degraded_health: Simulate degraded device health after changes are applied
    """

    def __init__(
        self,
        device_id: str = "dev-lab-01",
        rest_error: str | None = None,
        health_check_failure: bool = False,
        degraded_health: bool = False,
    ) -> None:
        """Initialize mock REST client.
        
        Args:
            device_id: Device identifier
            rest_error: Error message to raise on REST calls (simulates connectivity failure)
            health_check_failure: If True, health check returns failed status (after changes applied)
            degraded_health: If True, health check returns degraded status (after changes applied)
        """
        self.device_id = device_id
        self.rest_error = rest_error
        self.health_check_failure = health_check_failure
        self.degraded_health = degraded_health
        self.closed = False
        
        # Track calls for verification
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        
        # State storage for simulating device configuration
        self.firewall_rules: list[dict[str, Any]] = []
        self.routes: list[dict[str, Any]] = []
        self.wireless_interfaces: list[dict[str, Any]] = []
        self.dhcp_servers: list[dict[str, Any]] = []
        self.bridge_ports: list[dict[str, Any]] = []
        
        # Track if changes have been applied (to trigger health check failures)
        self._changes_applied = False

    async def get(self, path: str) -> dict[str, Any] | list[dict[str, Any]]:
        """Simulate GET request to RouterOS REST API.
        
        Args:
            path: REST API path
            
        Returns:
            Mock response data
            
        Raises:
            Exception: If rest_error is configured
        """
        self.calls.append(("GET", path, None))
        
        if self.rest_error:
            raise Exception(self.rest_error)
        
        # System resource endpoint (for health checks)
        if path == "/rest/system/resource":
            # If changes applied and health check configured to fail, return empty response
            # This simulates device not responding properly to health check
            if self._changes_applied and self.health_check_failure:
                return {}
            return {
                "cpu-load": 15.5,
                "cpu-count": 4,
                "total-memory": 1073741824,  # 1GB
                "free-memory": 536870912,  # 512MB
                "uptime": "1d2h30m",
                "version": "7.10",
                "board-name": "RB5009",
                "architecture-name": "arm64",
            }
        
        # Firewall filter rules endpoint
        if path == "/rest/ip/firewall/filter":
            # Note: We don't fail firewall access even if health check is configured to fail
            # This allows rollback to work (rollback needs to access firewall rules)
            # The health check failure is triggered by empty system/resource response above
            if self.degraded_health:
                # Return partial response for degraded health
                return []
            return self.firewall_rules
        
        # Routing table endpoint
        if path == "/rest/ip/route":
            return self.routes
        
        # Wireless interfaces endpoint
        if path == "/rest/interface/wireless":
            return self.wireless_interfaces
        
        # DHCP server endpoint
        if path == "/rest/ip/dhcp-server":
            return self.dhcp_servers
        
        # Bridge ports endpoint
        if path == "/rest/interface/bridge/port":
            return self.bridge_ports
        
        # System identity endpoint
        if path == "/rest/system/identity":
            return {"name": f"router-{self.device_id}"}
        
        # Default empty response
        return {}

    async def post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Simulate POST request to RouterOS REST API.
        
        Args:
            path: REST API path
            data: POST data
            
        Returns:
            Mock response data
            
        Raises:
            Exception: If rest_error is configured
        """
        self.calls.append(("POST", path, data))
        
        if self.rest_error:
            raise Exception(self.rest_error)
        
        # Mark that changes have been applied
        self._changes_applied = True
        
        # Firewall rule creation
        if path == "/rest/ip/firewall/filter/add":
            new_rule = {
                ".id": f"*{len(self.firewall_rules) + 1}",
                **data,
            }
            self.firewall_rules.append(new_rule)
            return new_rule
        
        # Route creation
        if path == "/rest/ip/route/add":
            new_route = {
                ".id": f"*{len(self.routes) + 1}",
                **data,
            }
            self.routes.append(new_route)
            return new_route
        
        # Wireless interface creation
        if path == "/rest/interface/wireless/add":
            new_interface = {
                ".id": f"*{len(self.wireless_interfaces) + 1}",
                **data,
            }
            self.wireless_interfaces.append(new_interface)
            return new_interface
        
        # DHCP server creation
        if path == "/rest/ip/dhcp-server/add":
            new_server = {
                ".id": f"*{len(self.dhcp_servers) + 1}",
                **data,
            }
            self.dhcp_servers.append(new_server)
            return new_server
        
        # Bridge port creation
        if path == "/rest/interface/bridge/port/add":
            new_port = {
                ".id": f"*{len(self.bridge_ports) + 1}",
                **data,
            }
            self.bridge_ports.append(new_port)
            return new_port
        
        return {"status": "success"}

    async def patch(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        """Simulate PATCH request to RouterOS REST API.
        
        Args:
            path: REST API path
            data: PATCH data
            
        Returns:
            Mock response data
            
        Raises:
            Exception: If rest_error is configured
        """
        self.calls.append(("PATCH", path, data))
        
        if self.rest_error:
            raise Exception(self.rest_error)
        
        return {"status": "success"}

    async def delete(self, path: str) -> dict[str, Any]:
        """Simulate DELETE request to RouterOS REST API.
        
        Args:
            path: REST API path
            
        Returns:
            Mock response data
            
        Raises:
            Exception: If rest_error is configured
        """
        self.calls.append(("DELETE", path, None))
        
        if self.rest_error:
            raise Exception(self.rest_error)
        
        return {"status": "success"}

    async def close(self) -> None:
        """Close the mock REST client."""
        self.closed = True


class MockDeviceService:
    """Mock device service for Phase 3 e2e tests."""

    def __init__(
        self,
        devices: dict[str, dict[str, Any]],
        rest_clients: dict[str, MockRouterOSRestClient],
    ) -> None:
        """Initialize mock device service.
        
        Args:
            devices: Dictionary mapping device_id to device attributes
            rest_clients: Dictionary mapping device_id to mock REST clients
        """
        self.devices = devices
        self.rest_clients = rest_clients

    async def get_device(self, device_id: str) -> Any:
        """Get device by ID.
        
        Args:
            device_id: Device identifier
            
        Returns:
            Device object with attributes
            
        Raises:
            ValueError: If device not found
        """
        if device_id not in self.devices:
            raise ValueError(f"Device not found: {device_id}")
        
        # Return a simple object with device attributes
        class Device:
            def __init__(self, **kwargs: Any) -> None:
                for k, v in kwargs.items():
                    setattr(self, k, v)
        
        return Device(**self.devices[device_id])

    async def get_rest_client(self, device_id: str) -> MockRouterOSRestClient:
        """Get REST client for device.
        
        Args:
            device_id: Device identifier
            
        Returns:
            Mock REST client
            
        Raises:
            ValueError: If device not found
        """
        if device_id not in self.rest_clients:
            raise ValueError(f"Device not found: {device_id}")
        
        return self.rest_clients[device_id]


def create_mock_device(
    device_id: str = "dev-lab-01",
    environment: str = "lab",
    allow_professional_workflows: bool = True,
    allow_firewall_writes: bool = True,
    allow_routing_writes: bool = True,
    allow_wireless_writes: bool = True,
    allow_dhcp_writes: bool = True,
    allow_bridge_writes: bool = True,
    status: str = "healthy",
) -> dict[str, Any]:
    """Create a mock device configuration.
    
    Args:
        device_id: Device identifier
        environment: Device environment (lab/staging/prod)
        allow_professional_workflows: Enable professional workflows
        allow_firewall_writes: Enable firewall writes
        allow_routing_writes: Enable routing writes
        allow_wireless_writes: Enable wireless writes
        allow_dhcp_writes: Enable DHCP writes
        allow_bridge_writes: Enable bridge writes
        status: Device status (healthy/degraded/unreachable)
        
    Returns:
        Device attributes dictionary
    """
    return {
        "id": device_id,
        "name": f"router-{device_id}",
        "environment": environment,
        "management_ip": "192.168.1.1",
        "management_port": 443,
        "status": status,
        "allow_advanced_writes": True,
        "allow_professional_workflows": allow_professional_workflows,
        "allow_firewall_writes": allow_firewall_writes,
        "allow_routing_writes": allow_routing_writes,
        "allow_wireless_writes": allow_wireless_writes,
        "allow_dhcp_writes": allow_dhcp_writes,
        "allow_bridge_writes": allow_bridge_writes,
        "system_identity": f"router-{device_id}",
    }
