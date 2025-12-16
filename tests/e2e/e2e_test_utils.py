"""Shared helpers for e2e MCP tool tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class DummyMCP:
    """Minimal MCP stub capturing registered tools."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self):  # type: ignore[override]
        def decorator(func: Any) -> Any:
            self.tools[func.__name__] = func
            return func

        return decorator


class FakeSessionFactory:
    """Async context manager that mimics DatabaseSessionManager.session()."""

    def session(self) -> FakeSessionFactory:
        return self

    async def __aenter__(self) -> FakeSessionFactory:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None


@dataclass
class FakeDeviceBase:
    """Common attributes for fake devices used in e2e tests."""

    id: str = "dev-lab-01"
    name: str = "router-lab-01"
    environment: str = "lab"
    allow_advanced_writes: bool = True
    allow_professional_workflows: bool = False


class MockRouterOSDevice:
    """Mock RouterOS device for E2E tests."""

    def __init__(self) -> None:
        self.dhcp_servers: list[dict[str, Any]] = []
        self.dhcp_leases: list[dict[str, Any]] = []

    def add_dhcp_server(
        self,
        name: str,
        interface: str,
        lease_time: str,
        address_pool: str,
        disabled: bool = False,
        **kwargs: Any,
    ) -> None:
        """Add a DHCP server to the mock device."""
        server = {
            "name": name,
            "interface": interface,
            "lease-time": lease_time,
            "address-pool": address_pool,
            "disabled": disabled,
        }
        server.update(kwargs)
        self.dhcp_servers.append(server)

    def add_dhcp_lease(
        self,
        address: str,
        mac_address: str,
        server: str,
        status: str = "bound",
        client_id: str = "",
        host_name: str = "",
        disabled: bool = False,
        **kwargs: Any,
    ) -> None:
        """Add a DHCP lease to the mock device."""
        lease = {
            "address": address,
            "mac-address": mac_address,
            "client-id": client_id,
            "host-name": host_name,
            "server": server,
            "status": status,
            "disabled": disabled,
        }
        lease.update(kwargs)
        self.dhcp_leases.append(lease)


def create_test_mcp_server() -> Any:
    """Create a test MCP server instance."""
    # Placeholder - implement as needed for full E2E tests
    pass

