"""IP address service for IP configuration operations.

Provides operations for querying RouterOS IP address configuration,
including addresses, ARP table, and address lists.
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


class IPService:
    """Service for RouterOS IP address operations.

    Responsibilities:
    - Query IP address configuration
    - Retrieve ARP table entries
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = IPService(session, settings)

            # Get IP addresses
            addresses = await service.list_addresses("dev-lab-01")

            # Get ARP table
            arp = await service.get_arp_table("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize IP service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def list_addresses(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List all IP addresses configured on the device with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            List of IP address information dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            addresses = await self._list_addresses_via_rest(device_id)
            # Add transport metadata
            for addr in addresses:
                addr["transport"] = "rest"
                addr["fallback_used"] = False
                addr["rest_error"] = None
            return addresses
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST address listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                addresses = await self._list_addresses_via_ssh(device_id)
                # Add transport metadata
                for addr in addresses:
                    addr["transport"] = "ssh"
                    addr["fallback_used"] = True
                    addr["rest_error"] = str(rest_exc)
                return addresses
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH address listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Address listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _list_addresses_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch IP addresses via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            addresses_data = await client.get("/rest/ip/address")

            # Normalize address data
            result: list[dict[str, Any]] = []
            if isinstance(addresses_data, list):
                for addr in addresses_data:
                    if isinstance(addr, dict):
                        result.append({
                            "id": addr.get(".id", ""),
                            "address": addr.get("address", ""),
                            "network": addr.get("network", ""),
                            "interface": addr.get("interface", ""),
                            "disabled": addr.get("disabled", False),
                            "comment": addr.get("comment", ""),
                            "dynamic": addr.get("dynamic", False),
                            "invalid": addr.get("invalid", False),
                        })

            return result

        finally:
            await client.close()

    async def _list_addresses_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch IP addresses via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/address/print")
            return self._parse_ip_address_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_ip_address_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /ip/address/print output into address list.

        Handles RouterOS standard table format with key: value pairs.
        Expects output like:
        Flags: D - disabled, X - invalid, I - interface, A - arp
         #    ADDRESS            NETWORK         INTERFACE
         *1   192.168.1.10/24    192.168.1.0/24  ether1
         *2 D 10.0.0.5/8         10.0.0.0/8      ether2
        """
        addresses: list[dict[str, Any]] = []

        lines = output.strip().split("\n")
        for line in lines:
            # Skip header/metadata lines
            if not line.strip() or line.startswith("Flags:") or line.startswith("#"):
                continue

            # Parse data lines (RouterOS IDs start with * or are numbers)
            parts = line.split()
            if not parts:
                continue

            # Check if first part is an ID (starts with * or digit)
            first_char = parts[0][0]
            if not (first_char == "*" or first_char.isdigit()):
                continue

            try:
                idx = 0
                flags = ""

                # First part is always ID (*1, *2, or 0, 1, etc.)
                # Second part might be flags (single letters like D, X, etc.)
                # or might be address if no flags
                addr_id = parts[0]

                # Check if second part is flags (single letter flag chars)
                if len(parts) > 1 and len(parts[1]) == 1 and parts[1] in "DXIAdrxia":
                    flags = parts[1]
                    idx = 2  # Address is at idx 2
                else:
                    idx = 1  # Address is at idx 1

                # Extract fields: [id] [flags?] [address] [network] [interface]
                if len(parts) > idx + 2:
                    address = parts[idx]
                    network = parts[idx + 1]
                    interface = parts[idx + 2]

                    addresses.append({
                        "id": addr_id,
                        "address": address,
                        "network": network,
                        "interface": interface,
                        "disabled": "D" in flags or "d" in flags,
                        "comment": "",  # Not shown in simple print
                        "dynamic": False,  # Can't determine from simple print
                        "invalid": "I" in flags or "X" in flags or "i" in flags or "x" in flags,
                    })
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse IP address line: {line}", exc_info=e)
                continue

        return addresses

    async def get_address(
        self,
        device_id: str,
        address_id: str,
    ) -> dict[str, Any]:
        """Get details of a specific IP address configuration with REST→SSH fallback.

        Args:
            device_id: Device identifier
            address_id: Address ID

        Returns:
            IP address information dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            address = await self._get_address_via_rest(device_id, address_id)
            address["transport"] = "rest"
            address["fallback_used"] = False
            address["rest_error"] = None
            return address
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST get_address failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id, "address_id": address_id},
            )
            # Try SSH fallback
            try:
                address = await self._get_address_via_ssh(device_id, address_id)
                address["transport"] = "ssh"
                address["fallback_used"] = True
                address["rest_error"] = str(rest_exc)
                return address
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH get_address failed",
                    exc_info=ssh_exc,
                    extra={
                        "device_id": device_id,
                        "address_id": address_id,
                        "rest_error": str(rest_exc),
                    },
                )
                raise RuntimeError(
                    f"Get address failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_address_via_rest(
        self,
        device_id: str,
        address_id: str,
    ) -> dict[str, Any]:
        """Fetch address details via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            address_data = await client.get(f"/rest/ip/address/{address_id}")

            # Normalize address data
            return {
                "id": address_data.get(".id", address_id),
                "address": address_data.get("address", ""),
                "network": address_data.get("network", ""),
                "interface": address_data.get("interface", ""),
                "disabled": address_data.get("disabled", False),
                "comment": address_data.get("comment", ""),
                "dynamic": address_data.get("dynamic", False),
                "invalid": address_data.get("invalid", False),
            }

        finally:
            await client.close()

    async def _get_address_via_ssh(
        self,
        device_id: str,
        address_id: str,
    ) -> dict[str, Any]:
        """Fetch address details via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            # Get all addresses and find by ID
            output = await ssh_client.execute("/ip/address/print")
            addresses = self._parse_ip_address_print_output(output)

            for addr in addresses:
                if addr.get("id") == address_id:
                    return addr

            # Not found - raise exception instead of returning empty dict
            raise ValueError(
                f"IP address with ID '{address_id}' not found on device '{device_id}'"
            )

        finally:
            await ssh_client.close()

    async def get_arp_table(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """Get ARP (Address Resolution Protocol) table entries with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            List of ARP entry dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            arp_entries = await self._get_arp_table_via_rest(device_id)
            # Add transport metadata
            for entry in arp_entries:
                entry["transport"] = "rest"
                entry["fallback_used"] = False
                entry["rest_error"] = None
            return arp_entries
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST ARP table failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            # Try SSH fallback
            try:
                arp_entries = await self._get_arp_table_via_ssh(device_id)
                # Add transport metadata
                for entry in arp_entries:
                    entry["transport"] = "ssh"
                    entry["fallback_used"] = True
                    entry["rest_error"] = str(rest_exc)
                return arp_entries
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH ARP table failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"ARP table failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_arp_table_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch ARP table via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            arp_data = await client.get("/rest/ip/arp")

            # Normalize ARP data
            result: list[dict[str, Any]] = []
            if isinstance(arp_data, list):
                for entry in arp_data:
                    if isinstance(entry, dict):
                        result.append({
                            "address": entry.get("address", ""),
                            "mac_address": entry.get("mac-address", ""),
                            "interface": entry.get("interface", ""),
                            "status": entry.get("status", ""),
                            "comment": entry.get("comment", ""),
                        })

            return result

        finally:
            await client.close()

    async def _get_arp_table_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch ARP table via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/arp/print")
            return self._parse_arp_table_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_arp_table_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /ip/arp/print output into ARP table.

        Handles RouterOS standard table format.
        Expects output like:
        Flags: D - DYNAMIC; C - COMPLETE
        Columns: ADDRESS, MAC-ADDRESS, INTERFACE, STATUS
        #    ADDRESS         MAC-ADDRESS        INTERFACE    STATUS   
        0 DC 192.168.20.251  18:FD:74:7C:7B:4F  vlan20-mgmt  stale    
        1 DC 192.168.20.248  00:E0:4C:34:5D:51  vlan20-mgmt  reachable
        
        Format: [id] [flags] [address] [mac-address] [interface] [status]
        """
        arp_entries: list[dict[str, Any]] = []

        lines = output.strip().split("\n")
        for line in lines:
            # Skip header/metadata lines
            if not line.strip() or line.startswith("Flags:") or line.startswith("#") or line.startswith("Columns:"):
                continue

            # Parse data lines (RouterOS IDs start with * or are numbers)
            parts = line.split()
            if not parts:
                continue

            # Check if first part is an ID (starts with * or digit)
            first_char = parts[0][0]
            if not (first_char == "*" or first_char.isdigit()):
                continue

            try:
                # Format: [id] [flags] [address] [mac-address] [interface] [status]
                # parts[0] = id (e.g., "0", "*1")
                # parts[1] = flags (e.g., "DC", "D", "C")
                # parts[2] = address (IP)
                # parts[3] = mac-address
                # parts[4] = interface
                # parts[5] = status (optional)
                
                idx = 1  # Start after ID
                
                # Check if second part looks like flags (all uppercase letters)
                if len(parts) > 1 and parts[1].isalpha() and parts[1].isupper():
                    idx = 2  # Skip flags, start from address
                
                # Extract fields: [id] [flags?] [address] [mac-address] [interface] [status?]
                if len(parts) > idx + 2:
                    address = parts[idx]
                    mac_address = parts[idx + 1]
                    interface = parts[idx + 2]
                    status = parts[idx + 3] if len(parts) > idx + 3 else ""

                    arp_entries.append({
                        "address": address,
                        "mac_address": mac_address,
                        "interface": interface,
                        "status": status,
                        "comment": "",  # Not shown in simple print
                    })
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse ARP line: {line}", exc_info=e)
                continue

        return arp_entries

    async def add_secondary_address(
        self,
        device_id: str,
        address: str,
        interface: str,
        comment: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Add a secondary IP address to an interface.

        Args:
            device_id: Device identifier
            address: IP address in CIDR notation (e.g., "192.168.1.10/24")
            interface: Interface name
            comment: Optional comment
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with add result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValueError: If address format is invalid
            UnsafeOperationError: If address overlaps with existing address
        """
        from routeros_mcp.security.safeguards import (
            check_ip_overlap,
            create_dry_run_response,
            validate_ip_address_format,
        )

        # Validate IP address format
        validate_ip_address_format(address)

        await self.device_service.get_device(device_id)

        # Get existing addresses to check for overlaps
        existing_addresses = await self.list_addresses(device_id)

        # Check for overlap
        check_ip_overlap(address, existing_addresses, interface)

        # Dry-run: return planned changes
        if dry_run:
            return create_dry_run_response(
                operation="ip/add-secondary-address",
                device_id=device_id,
                planned_changes={
                    "action": "add",
                    "address": address,
                    "interface": interface,
                    "comment": comment,
                },
            )

        # Apply change
        client = await self.device_service.get_rest_client(device_id)

        try:
            payload = {
                "address": address,
                "interface": interface,
            }
            if comment:
                payload["comment"] = comment

            result = await client.put("/rest/ip/address", payload)

            # Extract ID from result
            address_id = result.get(".id", "") if isinstance(result, dict) else ""

            logger.info(
                f"Added secondary IP address {address} to interface {interface}",
                extra={"device_id": device_id, "address_id": address_id},
            )

            return {
                "changed": True,
                "address": address,
                "interface": interface,
                "comment": comment,
                "address_id": address_id,
                "dry_run": False,
            }

        finally:
            await client.close()

    async def remove_secondary_address(
        self,
        device_id: str,
        address_id: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Remove a secondary IP address.

        Args:
            device_id: Device identifier
            address_id: Address ID to remove
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with remove result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ManagementPathProtectionError: If removing management IP
        """
        from routeros_mcp.security.safeguards import (
            check_management_ip_protection,
            create_dry_run_response,
        )

        device = await self.device_service.get_device(device_id)

        # Get address details
        address_details = await self.get_address(device_id, address_id)

        # Check management IP protection
        check_management_ip_protection(
            device.management_ip, address_details["address"]
        )

        # Dry-run: return planned changes
        if dry_run:
            return create_dry_run_response(
                operation="ip/remove-secondary-address",
                device_id=device_id,
                planned_changes={
                    "action": "remove",
                    "address_id": address_id,
                    "address": address_details["address"],
                    "interface": address_details["interface"],
                },
            )

        # Apply change
        client = await self.device_service.get_rest_client(device_id)

        try:
            await client.delete(f"/rest/ip/address/{address_id}")

            logger.info(
                f"Removed IP address {address_details['address']} from interface {address_details['interface']}",
                extra={"device_id": device_id, "address_id": address_id},
            )

            return {
                "changed": True,
                "address_id": address_id,
                "address": address_details["address"],
                "interface": address_details["interface"],
                "dry_run": False,
            }

        finally:
            await client.close()
