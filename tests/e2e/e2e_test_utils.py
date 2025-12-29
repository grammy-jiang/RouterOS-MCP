"""Shared helpers for e2e MCP tool tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from routeros_mcp.config import Settings

if TYPE_CHECKING:
    from collections.abc import Callable
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


# Deterministic, valid Fernet key (base64 urlsafe, 32-byte key).
# Using a stable key avoids test flakiness and reduces warning noise.
TEST_ENCRYPTION_KEY = "F5N_V5vuw-uQLORwbDd5UBO5ckjh-STww5EHdmNbi0E="


def make_test_settings(**overrides: Any) -> Settings:
    """Create Settings for e2e tests with safe defaults.

    Defaults to a lab environment with a deterministic valid encryption key.
    Callers may override any Settings field via keyword args.
    """

    base: dict[str, Any] = {
        "environment": "lab",
        "encryption_key": TEST_ENCRYPTION_KEY,
    }
    base.update(overrides)
    return Settings(**base)


class DummyMCP:
    """Minimal MCP stub capturing registered tools."""

    def __init__(self) -> None:
        # Store callables as Any to avoid static type-checker false-positives in tests.
        self.tools: dict[str, Any] = {}

    def tool(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            self.tools[func.__name__] = func
            return func

        return decorator


class FakeSessionFactory:
    """Async context manager that mimics DatabaseSessionManager.session()."""

    def session(self) -> FakeSessionFactory:
        return self

    async def __aenter__(self) -> FakeSessionFactory:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        return None


class RealSessionFactory:
    """Session factory that wraps SQLAlchemy async_sessionmaker for Phase 3 e2e tests.
    
    This factory allows Phase 3 tests to use real database sessions with in-memory
    SQLite while maintaining compatibility with the DatabaseSessionManager interface.
    """

    def __init__(self, session_maker: "async_sessionmaker") -> None:
        """Initialize with SQLAlchemy async_sessionmaker.
        
        Args:
            session_maker: SQLAlchemy async_sessionmaker instance
        """
        self.session_maker = session_maker
    
    def session(self) -> "AsyncSession":
        """Return async session context manager.
        
        Returns:
            AsyncSession context manager from the session maker
        """
        return self.session_maker()


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
