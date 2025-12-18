"""DHCP service for DHCP server operations.

Provides operations for querying RouterOS DHCP server configuration,
pools, and active leases.
"""

import logging
import shlex
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

            # Parse /ip/dhcp-server/print output (standard table format)
            # Format:
            # Columns: NAME, INTERFACE, ADDRESS-POOL, LEASE-TIME
            # # NAME                 INTERFACE       ADDRESS-POOL         LEASE-TIME
            # 0 dhcp-vlan20-mgmt     vlan20-mgmt     pool-vlan20-mgmt     30m
            servers = []
            lines = output.strip().split("\n")

            for line in lines:
                # Skip empty lines, Columns header, and comment lines
                if not line.strip() or line.startswith("Columns:") or line.startswith("#") or line.startswith("Flags:"):
                    continue

                parts = line.split()
                if not parts:
                    continue

                try:
                    # Standard format: [id] [name] [interface] [address_pool] [lease_time]
                    # Example: 0 dhcp-vlan20-mgmt vlan20-mgmt pool-vlan20-mgmt 30m
                    # IDs are numeric (0, 1, 2, ...)
                    if not parts[0][0].isdigit():
                        # Might have flags (X for disabled, D for dynamic, etc.)
                        # Skip flags for now, parse from position 1
                        if len(parts) < 2 or not parts[1][0].isdigit():
                            continue
                        parts = parts[1:]

                    # After ensuring first part is ID
                    if len(parts) >= 5:
                        # id, name, interface, address_pool, lease_time
                        name = parts[1]
                        interface = parts[2]
                        address_pool = parts[3]
                        lease_time = parts[4]
                        disabled = False  # No explicit disabled flag in standard output

                        server_data = {
                            "name": name,
                            "interface": interface,
                            "address_pool": address_pool,
                            "lease_time": lease_time,
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
            # Over SSH, RouterOS may emit a shortened table which omits STATUS/LAST-SEEN columns.
            # Using 'detail' ensures we can reliably extract status=bound and last-seen values.
            # Use without-paging to avoid truncation.
            output = await ssh_client.execute("/ip/dhcp-server/lease/print detail without-paging")

            # Parse /ip/dhcp-server/lease/print detail output.
            # Example block:
            #   0   ;;; cAP ac (RBcAPGi-5acD2nD)
            #        address=192.168.20.251 mac-address=... server=... status=bound ... last-seen=13m43s
            #        host-name="ap-cAP-ac"
            #
            #   4 D address=192.168.20.248 mac-address=... status=bound ... last-seen=9m56s
            active_leases = []
            normalized = output.replace("\r", "")
            lines = normalized.splitlines()

            current: dict[str, Any] = {}
            current_flags = ""

            def flush_current() -> None:
                nonlocal current, current_flags
                if not current:
                    return

                status = current.get("status", "")
                if status == "bound":
                    lease_data = {
                        "address": current.get("address", ""),
                        "mac_address": current.get("mac-address", ""),
                        "host_name": current.get("host-name", ""),
                        "server": current.get("server", ""),
                        "status": status,
                        "last_seen": current.get("last-seen", ""),
                    }

                    comment = current.get("comment", "")
                    if comment:
                        lease_data["comment"] = comment

                    if "D" in current_flags:
                        lease_data["dynamic"] = True

                    # Ensure required fields exist before adding.
                    if lease_data["address"] and lease_data["mac_address"] and lease_data["server"]:
                        active_leases.append(lease_data)

                current = {}
                current_flags = ""

            for line in lines:
                stripped = line.strip()

                if not stripped:
                    flush_current()
                    continue

                # Detail header line example:
                #   0   ;;; Comment
                #   4 D address=... mac-address=...
                if stripped.startswith("Flags:"):
                    # Header line in detail output; ignore.
                    continue

                # New record begins with numeric id.
                if stripped[0].isdigit():
                    flush_current()

                    # Split the beginning into id + optional flags.
                    parts = stripped.split(None, 2)
                    if not parts:
                        continue

                    # parts[0] is record id (unused)
                    remainder = ""
                    if len(parts) >= 2 and len(parts[1]) <= 3 and parts[1][0] in {"*", "X", "D", "R", "B"}:
                        current_flags = parts[1]
                        remainder = parts[2] if len(parts) == 3 else ""
                    else:
                        current_flags = ""
                        remainder = parts[1] if len(parts) >= 2 else ""
                        if len(parts) == 3:
                            remainder = parts[1] + " " + parts[2]

                    # Extract comment if present on the header line.
                    if ";;;" in remainder:
                        comment_idx = remainder.find(";;;")
                        current["comment"] = remainder[comment_idx + 3 :].strip()
                        remainder = remainder[:comment_idx].strip()

                    # Parse any key=value tokens that also appear on the header line.
                    if remainder:
                        try:
                            tokens = shlex.split(remainder)
                        except ValueError:
                            tokens = remainder.split()
                        for token in tokens:
                            if "=" not in token:
                                continue
                            k, v = token.split("=", 1)
                            current[k] = v

                    continue

                # Continuation lines are key=value tokens (often indented).
                try:
                    tokens = shlex.split(stripped)
                except ValueError:
                    tokens = stripped.split()
                for token in tokens:
                    if "=" not in token:
                        continue
                    k, v = token.split("=", 1)
                    current[k] = v

            # Flush last block.
            flush_current()

            return {
                "leases": active_leases,
                "total_count": len(active_leases),
            }

        finally:
            await ssh_client.close()
