"""DHCP service for DHCP server operations.

Provides operations for querying RouterOS DHCP server configuration,
pools, and active leases.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSClientError,
    RouterOSNetworkError,
    RouterOSServerError,
    RouterOSTimeoutError,
)

logger = logging.getLogger(__name__)


class DHCPService:
    """Service for RouterOS DHCP operations.

    Responsibilities:
    - Query DHCP server configuration and status
    - Query active DHCP leases
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = DHCPService(session, settings)

            # Get DHCP server status
            server_status = await service.get_dhcp_server_status("dev-lab-01")

            # Get active leases
            leases = await service.get_dhcp_leases("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize DHCP service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def get_dhcp_server_status(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Get DHCP server configuration and status with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            DHCP server configuration dictionary with list of servers

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            server_status = await self._get_dhcp_server_status_via_rest(device_id)
            server_status["transport"] = "rest"
            server_status["fallback_used"] = False
            server_status["rest_error"] = None
            return server_status
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                "REST get_dhcp_server_status failed, attempting SSH fallback: %s",
                rest_exc,
                extra={"device_id": device_id},
            )
            try:
                server_status = await self._get_dhcp_server_status_via_ssh(device_id)
                server_status["transport"] = "ssh"
                server_status["fallback_used"] = True
                server_status["rest_error"] = str(rest_exc)
                return server_status
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH get_dhcp_server_status failed",
                    exc_info=ssh_exc,
                    extra={
                        "device_id": device_id,
                        "rest_error": str(rest_exc),
                    },
                )
                raise RuntimeError(
                    f"Get DHCP server status failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_dhcp_server_status_via_rest(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Fetch DHCP server status via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get DHCP server configuration
            dhcp_servers = await client.get("/rest/ip/dhcp-server")

            # Normalize to list if single server returned
            if isinstance(dhcp_servers, dict):
                dhcp_servers = [dhcp_servers]
            elif not isinstance(dhcp_servers, list):
                dhcp_servers = []

            # Parse each server's configuration
            servers = []
            for server in dhcp_servers:
                server_data = {
                    "name": server.get("name", ""),
                    "interface": server.get("interface", ""),
                    "lease_time": server.get("lease-time", ""),
                    "address_pool": server.get("address-pool", ""),
                    "disabled": server.get("disabled", False),
                }
                
                # Add optional fields if present
                if "authoritative" in server:
                    server_data["authoritative"] = server.get("authoritative")
                if "bootp-support" in server:
                    server_data["bootp_support"] = server.get("bootp-support")
                if "lease-script" in server:
                    server_data["lease_script"] = server.get("lease-script")
                if ".id" in server:
                    server_data["id"] = server.get(".id")
                
                servers.append(server_data)

            return {
                "servers": servers,
                "total_count": len(servers),
            }

        finally:
            await client.close()

    async def _get_dhcp_server_status_via_ssh(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Fetch DHCP server status via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/dhcp-server/print")

            # Parse /ip/dhcp-server/print output (table format)
            servers = []
            lines = output.strip().split("\n")

            for line in lines:
                if not line.strip() or line.startswith("Flags:") or line.startswith("#"):
                    continue

                # Table format varies, but typically:
                # [flags] [id] [name] [interface] [lease-time] [address-pool]
                parts = line.split()
                if not parts or not (parts[0][0] in {"*", "X", "D"} or parts[0][0].isdigit()):
                    continue

                try:
                    # Parse based on flags presence
                    idx = 0
                    flags = ""
                    
                    # Check for flags (usually single char or short string)
                    if parts[idx] and len(parts[idx]) <= 3 and not parts[idx][0].isdigit():
                        flags = parts[idx]
                        idx += 1
                    
                    # Skip ID if present (numeric)
                    if idx < len(parts) and parts[idx][0].isdigit():
                        idx += 1
                    
                    # Remaining parts: name, interface, lease-time, address-pool
                    if idx + 3 < len(parts):
                        name = parts[idx]
                        interface = parts[idx + 1]
                        lease_time = parts[idx + 2]
                        address_pool = parts[idx + 3]
                        
                        disabled = "X" in flags
                        
                        server_data = {
                            "name": name,
                            "interface": interface,
                            "lease_time": lease_time,
                            "address_pool": address_pool,
                            "disabled": disabled,
                        }
                        
                        servers.append(server_data)
                        
                except (IndexError, ValueError) as e:
                    logger.debug("Failed to parse DHCP server line: %s", line, exc_info=e)
                    continue

            return {
                "servers": servers,
                "total_count": len(servers),
            }

        finally:
            await ssh_client.close()

    async def get_dhcp_leases(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Get active DHCP leases with REST→SSH fallback.

        Returns only active leases (filters out expired/released).

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with active leases list and count

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            leases_data = await self._get_dhcp_leases_via_rest(device_id)
            leases_data["transport"] = "rest"
            leases_data["fallback_used"] = False
            leases_data["rest_error"] = None
            return leases_data
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                "REST get_dhcp_leases failed, attempting SSH fallback: %s",
                rest_exc,
                extra={"device_id": device_id},
            )
            try:
                leases_data = await self._get_dhcp_leases_via_ssh(device_id)
                leases_data["transport"] = "ssh"
                leases_data["fallback_used"] = True
                leases_data["rest_error"] = str(rest_exc)
                return leases_data
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH get_dhcp_leases failed",
                    exc_info=ssh_exc,
                    extra={
                        "device_id": device_id,
                        "rest_error": str(rest_exc),
                    },
                )
                raise RuntimeError(
                    f"Get DHCP leases failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_dhcp_leases_via_rest(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Fetch DHCP leases via REST API.
        
        Filters to active leases only (status=bound).
        """
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get all DHCP leases
            all_leases = await client.get("/rest/ip/dhcp-server/lease")

            # Normalize to list
            if isinstance(all_leases, dict):
                all_leases = [all_leases]
            elif not isinstance(all_leases, list):
                all_leases = []

            # Filter to active leases only (status=bound)
            active_leases = []
            for lease in all_leases:
                # Check if lease is active (bound status)
                status = lease.get("status", "")
                disabled = lease.get("disabled", False)
                
                # Only include bound and non-disabled leases
                if status == "bound" and not disabled:
                    lease_data = {
                        "address": lease.get("address", ""),
                        "mac_address": lease.get("mac-address", ""),
                        "client_id": lease.get("client-id", ""),
                        "host_name": lease.get("host-name", ""),
                        "server": lease.get("server", ""),
                        "status": status,
                    }
                    
                    # Add optional fields
                    if "expires-after" in lease:
                        lease_data["expires_after"] = lease.get("expires-after")
                    if "last-seen" in lease:
                        lease_data["last_seen"] = lease.get("last-seen")
                    if "active-address" in lease:
                        lease_data["active_address"] = lease.get("active-address")
                    if "active-mac-address" in lease:
                        lease_data["active_mac_address"] = lease.get("active-mac-address")
                    if "active-client-id" in lease:
                        lease_data["active_client_id"] = lease.get("active-client-id")
                    if "active-server" in lease:
                        lease_data["active_server"] = lease.get("active-server")
                    if ".id" in lease:
                        lease_data["id"] = lease.get(".id")
                    
                    active_leases.append(lease_data)

            return {
                "leases": active_leases,
                "total_count": len(active_leases),
            }

        finally:
            await client.close()

    async def _get_dhcp_leases_via_ssh(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Fetch DHCP leases via SSH CLI.
        
        Filters to active leases only (bound status).
        """
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/dhcp-server/lease/print")

            # Parse /ip/dhcp-server/lease/print output (table format)
            active_leases = []
            lines = output.strip().split("\n")

            for line in lines:
                if not line.strip() or line.startswith("Flags:") or line.startswith("#"):
                    continue

                # Table format: [id] [flags] [address] [mac-address] [client-id] [host-name] [server]
                # Example: " 0 D 192.168.1.10   00:11:22:33:44:55  1:00:11:22:33:44:55 client1     dhcp1"
                parts = line.split()
                if not parts:
                    continue

                try:
                    idx = 0
                    flags = ""
                    
                    # Skip ID (numeric column, typically first)
                    if idx < len(parts) and parts[idx][0].isdigit():
                        idx += 1
                    
                    # Check for flags (single char or short string like D, X, DX, etc.)
                    if idx < len(parts) and len(parts[idx]) <= 3 and parts[idx][0] in {"*", "X", "D", "R", "B"}:
                        flags = parts[idx]
                        idx += 1
                    
                    # Only process bound leases (R flag or bound in flags)
                    # X = disabled, D = dynamic, R = radius, B = blocked
                    # Active lease typically has D flag without X
                    disabled = "X" in flags
                    is_bound = "D" in flags and not disabled
                    
                    if not is_bound:
                        continue
                    
                    # Parse lease fields: address, mac-address, client-id, host-name, server
                    # Extract up to 5 fields, pad with empty strings if missing
                    if idx < len(parts):
                        address, mac_address, client_id, host_name, server = (
                            (parts[idx:idx+5] + [""] * 5)[:5]
                        )
                        
                        lease_data = {
                            "address": address,
                            "mac_address": mac_address,
                            "client_id": client_id,
                            "host_name": host_name,
                            "server": server,
                            "status": "bound",
                        }
                        
                        active_leases.append(lease_data)
                        
                except (IndexError, ValueError) as e:
                    logger.debug("Failed to parse DHCP lease line: %s", line, exc_info=e)
                    continue

            return {
                "leases": active_leases,
                "total_count": len(active_leases),
            }

        finally:
            await ssh_client.close()
