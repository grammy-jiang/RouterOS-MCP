"""DHCP service for DHCP server operations.

Provides operations for querying RouterOS DHCP server configuration,
pools, and active leases, plus plan/apply workflow for DHCP changes.
"""

import gzip
import hashlib
import ipaddress
import json
import logging
import shlex
import uuid
from datetime import UTC, datetime
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
from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient

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


class DHCPPlanService:
    """Service for DHCP server planning operations.

    Provides:
    - DHCP pool parameter validation (overlapping ranges, gateway in subnet)
    - Risk level assessment based on environment and scope
    - Preview generation for planned changes
    - Snapshot creation for rollback
    - Health check after DHCP changes

    All DHCP pool operations follow the plan/apply workflow.
    """

    # High-risk conditions for risk assessment
    HIGH_RISK_ENVIRONMENTS = ["prod"]  # Production environment

    def validate_pool_params(
        self,
        pool_name: str,
        address_range: str,
        gateway: str | None = None,
        dns_servers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Validate DHCP pool parameters.

        Args:
            pool_name: Name for the DHCP pool
            address_range: IP address range (e.g., "192.168.1.100-192.168.1.200")
            gateway: Gateway IP address (optional)
            dns_servers: List of DNS server IPs (optional)

        Returns:
            Dictionary with validation result

        Raises:
            ValueError: If any parameter is invalid
        """
        errors = []

        # Validate pool name
        if not pool_name or not pool_name.strip():
            errors.append("Pool name cannot be empty")

        # Validate address range format and parse
        if not address_range or "-" not in address_range:
            errors.append(
                f"Invalid address range '{address_range}'. "
                "Must be in format: 'start_ip-end_ip' (e.g., '192.168.1.100-192.168.1.200')"
            )
        else:
            try:
                start_str, end_str = address_range.split("-", 1)
                start_ip = ipaddress.ip_address(start_str.strip())
                end_ip = ipaddress.ip_address(end_str.strip())

                # Validate range order
                if start_ip >= end_ip:
                    errors.append(
                        f"Invalid address range: start IP {start_ip} must be less than end IP {end_ip}"
                    )

                # Store parsed IPs for subnet validation
                range_start = start_ip
                range_end = end_ip

            except ValueError as e:
                errors.append(f"Invalid IP address in range '{address_range}': {e}")
                range_start = None
                range_end = None

        # Validate gateway if provided
        gateway_ip = None
        if gateway:
            try:
                gateway_ip = ipaddress.ip_address(gateway.strip())

                # Check if gateway is compatible with and within the address range
                if range_start and range_end:
                    if gateway_ip.version != range_start.version:
                        errors.append(
                            f"Gateway {gateway_ip} IP version must match address range "
                            f"IP version ({range_start.version})"
                        )
                    elif not (range_start <= gateway_ip <= range_end):
                        errors.append(
                            f"Gateway {gateway_ip} should be within the DHCP address range "
                            f"{range_start}-{range_end}"
                        )
            except ValueError as e:
                errors.append(f"Invalid gateway address '{gateway}': {e}")

        # Validate DNS servers if provided
        if dns_servers:
            for dns in dns_servers:
                try:
                    ipaddress.ip_address(dns.strip())
                except ValueError as e:
                    errors.append(f"Invalid DNS server address '{dns}': {e}")

        if errors:
            raise ValueError("DHCP pool parameter validation failed:\n- " + "\n- ".join(errors))

        logger.debug(
            f"DHCP pool parameter validation passed for pool={pool_name}, "
            f"range={address_range}"
        )

        return {
            "valid": True,
            "pool_name": pool_name,
            "address_range": address_range,
            "gateway": gateway,
            "dns_servers": dns_servers or [],
        }

    def check_pool_overlap(
        self,
        new_range: str,
        existing_pools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Check if new pool overlaps with existing pools.

        Args:
            new_range: IP address range for new pool
            existing_pools: List of existing DHCP pools with address ranges

        Returns:
            Dictionary with overlap status and details

        Raises:
            ValueError: If overlap is detected
        """
        try:
            start_str, end_str = new_range.split("-", 1)
            new_start = ipaddress.ip_address(start_str.strip())
            new_end = ipaddress.ip_address(end_str.strip())
        except (ValueError, AttributeError) as e:
            raise ValueError(f"Invalid new pool range '{new_range}': {e}") from e

        overlapping_pools = []
        for pool in existing_pools:
            pool_range = pool.get("address_range") or pool.get("addresses", "")
            if not pool_range or "-" not in pool_range:
                continue

            try:
                pool_start_str, pool_end_str = pool_range.split("-", 1)
                pool_start = ipaddress.ip_address(pool_start_str.strip())
                pool_end = ipaddress.ip_address(pool_end_str.strip())

                # Check for overlap: ranges overlap if one starts before the other ends
                if not (new_end < pool_start or new_start > pool_end):
                    overlapping_pools.append({
                        "pool_name": pool.get("name", "unknown"),
                        "address_range": pool_range,
                    })
            except (ValueError, AttributeError):
                logger.warning(f"Could not parse existing pool range: {pool_range}")
                continue

        if overlapping_pools:
            overlap_details = "; ".join(
                f"{p['pool_name']} ({p['address_range']})" for p in overlapping_pools
            )
            raise ValueError(
                f"New pool range {new_range} overlaps with existing pools: {overlap_details}"
            )

        logger.debug(f"No overlap detected for new pool range {new_range}")
        return {
            "overlap_detected": False,
            "new_range": new_range,
        }

    def assess_risk(
        self,
        operation: str,
        device_environment: str = "lab",
        affects_production: bool = False,
    ) -> str:
        """Assess risk level for a DHCP operation.

        Risk classification:
        - High risk:
          - Production environment
          - Operations affecting production networks
          - Pool removal (may affect many clients)
        - Medium risk:
          - Lab/staging environments
          - Pool creation/modification
          - Non-production changes

        Args:
            operation: Operation type (create_pool/modify_pool/remove_pool)
            device_environment: Device environment (lab/staging/prod)
            affects_production: Whether operation affects production network

        Returns:
            Risk level: "medium" or "high"
        """
        # High risk conditions
        if device_environment in self.HIGH_RISK_ENVIRONMENTS:
            logger.info("High risk: production environment")
            return "high"

        if affects_production:
            logger.info("High risk: affects production network")
            return "high"

        if operation == "remove_dhcp_pool":
            logger.info("High risk: pool removal may affect many clients")
            return "high"

        # Default to medium risk
        logger.debug(
            f"Medium risk: operation={operation}, env={device_environment}, "
            f"prod_impact={affects_production}"
        )
        return "medium"

    def generate_preview(
        self,
        operation: str,
        device_id: str,
        device_name: str,
        device_environment: str,
        pool_name: str | None = None,
        address_range: str | None = None,
        gateway: str | None = None,
        dns_servers: list[str] | None = None,
        pool_id: str | None = None,
        modifications: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate detailed preview for a DHCP operation.

        Args:
            operation: Operation type (create_dhcp_pool/modify_dhcp_pool/remove_dhcp_pool)
            device_id: Device identifier
            device_name: Device name
            device_environment: Device environment
            pool_name: Pool name (for create/modify)
            address_range: Address range (for create)
            gateway: Gateway IP (for create/modify)
            dns_servers: DNS servers list (for create/modify)
            pool_id: Pool ID (for modify/remove)
            modifications: Modifications dict (for modify)

        Returns:
            Preview dictionary with operation details
        """
        preview: dict[str, Any] = {
            "device_id": device_id,
            "name": device_name,
            "environment": device_environment,
            "operation": operation,
            "pre_check_status": "passed",
        }

        if operation == "create_dhcp_pool":
            preview["preview"] = {
                "operation": "create_dhcp_pool",
                "pool_name": pool_name,
                "address_range": address_range,
                "gateway": gateway,
                "dns_servers": dns_servers or [],
                "estimated_impact": "Medium - new DHCP pool will begin serving leases to clients",
            }

        elif operation == "modify_dhcp_pool":
            preview["preview"] = {
                "operation": "modify_dhcp_pool",
                "pool_id": pool_id,
                "pool_name": pool_name,
                "modifications": modifications or {},
                "estimated_impact": "Medium - pool modification may affect active leases",
            }

        elif operation == "remove_dhcp_pool":
            preview["preview"] = {
                "operation": "remove_dhcp_pool",
                "pool_id": pool_id,
                "pool_name": pool_name,
                "estimated_impact": "High - pool removal will stop new leases, may affect clients",
            }

        logger.debug(f"Generated preview for {operation} on device {device_id}")

        return preview

    async def create_dhcp_snapshot(
        self,
        device_id: str,
        device_name: str,
        rest_client: RouterOSRestClient,
    ) -> dict[str, Any]:
        """Create snapshot of current DHCP configuration for rollback.

        Args:
            device_id: Device identifier
            device_name: Device name
            rest_client: REST client instance for device

        Returns:
            Snapshot metadata with snapshot_id and DHCP configuration payload

        Raises:
            Exception: If snapshot creation fails
        """
        try:
            # Fetch current DHCP server configuration
            dhcp_servers = await rest_client.get("/rest/ip/dhcp-server")

            # Fetch DHCP pools
            dhcp_pools = await rest_client.get("/rest/ip/pool")

            # Fetch DHCP server networks
            dhcp_networks = await rest_client.get("/rest/ip/dhcp-server/network")

            # Create snapshot payload
            snapshot_payload = {
                "device_id": device_id,
                "device_name": device_name,
                "timestamp": datetime.now(UTC).isoformat(),
                "dhcp_servers": dhcp_servers if isinstance(dhcp_servers, list) else [],
                "dhcp_pools": dhcp_pools if isinstance(dhcp_pools, list) else [],
                "dhcp_networks": dhcp_networks if isinstance(dhcp_networks, list) else [],
            }

            # Serialize and compress
            payload_json = json.dumps(snapshot_payload)
            payload_bytes = payload_json.encode("utf-8")
            compressed_data = gzip.compress(payload_bytes, compresslevel=6)

            # Calculate checksum
            checksum = hashlib.sha256(payload_bytes).hexdigest()

            # Generate snapshot ID
            snapshot_id = f"snap-dhcp-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

            logger.info(
                f"Created DHCP snapshot {snapshot_id} for device {device_id}",
                extra={
                    "snapshot_id": snapshot_id,
                    "device_id": device_id,
                    "server_count": len(snapshot_payload["dhcp_servers"]),
                    "pool_count": len(snapshot_payload["dhcp_pools"]),
                    "size_bytes": len(payload_bytes),
                    "compressed_size": len(compressed_data),
                },
            )

            return {
                "snapshot_id": snapshot_id,
                "device_id": device_id,
                "timestamp": snapshot_payload["timestamp"],
                "server_count": len(snapshot_payload["dhcp_servers"]),
                "pool_count": len(snapshot_payload["dhcp_pools"]),
                "size_bytes": len(payload_bytes),
                "compressed_size": len(compressed_data),
                "checksum": checksum,
                "data": compressed_data,
            }

        except Exception as e:
            logger.error(
                f"Failed to create DHCP snapshot for device {device_id}: {e}",
                exc_info=True,
            )
            raise

    async def perform_health_check(
        self,
        device_id: str,
        rest_client: RouterOSRestClient,
        expected_pool_name: str | None = None,
        timeout_seconds: float = 30.0,  # TODO: implement health check timeout handling; currently unused. noqa: ARG002
    ) -> dict[str, Any]:
        """Perform health check after DHCP changes.

        Verifies:
        - Device still responds to REST API
        - DHCP server is accessible
        - Expected pool exists (if specified)

        Args:
            device_id: Device identifier
            rest_client: REST client instance for device
            expected_pool_name: Pool name to verify (optional)
            timeout_seconds: Health check timeout (default: 30s)

        Returns:
            Health check results with status and details

        Raises:
            Exception: If health check fails critically
        """
        try:
            # Test 1: Check device responds to REST API
            system_resource = await rest_client.get("/rest/system/resource")

            if not system_resource:
                return {
                    "status": "failed",
                    "device_id": device_id,
                    "checks": [
                        {
                            "check": "rest_api_response",
                            "status": "failed",
                            "message": "Device did not respond to REST API",
                        }
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Test 2: Verify DHCP server configuration is accessible
            dhcp_servers = await rest_client.get("/rest/ip/dhcp-server")

            if dhcp_servers is None:
                return {
                    "status": "failed",
                    "device_id": device_id,
                    "checks": [
                        {
                            "check": "dhcp_config_accessible",
                            "status": "failed",
                            "message": "DHCP server configuration not accessible",
                        }
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            checks = [
                {
                    "check": "rest_api_response",
                    "status": "passed",
                    "message": "Device responding to REST API",
                },
                {
                    "check": "dhcp_config_accessible",
                    "status": "passed",
                    "message": "DHCP server configuration accessible",
                },
            ]

            # Test 3: Verify expected pool exists (if specified)
            if expected_pool_name:
                dhcp_pools = await rest_client.get("/rest/ip/pool")
                pool_list = dhcp_pools if isinstance(dhcp_pools, list) else []

                pool_exists = any(
                    pool.get("name") == expected_pool_name for pool in pool_list
                )

                if pool_exists:
                    checks.append({
                        "check": "expected_pool_exists",
                        "status": "passed",
                        "message": f"Pool '{expected_pool_name}' exists",
                    })
                else:
                    checks.append({
                        "check": "expected_pool_exists",
                        "status": "failed",
                        "message": f"Pool '{expected_pool_name}' not found",
                    })
                    return {
                        "status": "failed",
                        "device_id": device_id,
                        "checks": checks,
                        "timestamp": datetime.now(UTC).isoformat(),
                    }

            logger.info(
                f"DHCP health check passed for device {device_id}",
                extra={"device_id": device_id, "checks": len(checks)},
            )

            return {
                "status": "passed",
                "device_id": device_id,
                "checks": checks,
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error(
                f"DHCP health check failed for device {device_id}: {e}",
                exc_info=True,
            )
            return {
                "status": "failed",
                "device_id": device_id,
                "checks": [
                    {
                        "check": "health_check_execution",
                        "status": "failed",
                        "message": f"Health check failed with error: {str(e)}",
                    }
                ],
                "timestamp": datetime.now(UTC).isoformat(),
            }
