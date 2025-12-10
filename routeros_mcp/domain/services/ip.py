"""IP address service for IP configuration operations.

Provides operations for querying RouterOS IP address configuration,
including addresses, ARP table, and address lists.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService

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
        """List all IP addresses configured on the device.

        Args:
            device_id: Device identifier

        Returns:
            List of IP address information dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
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

    async def get_address(
        self,
        device_id: str,
        address_id: str,
    ) -> dict[str, Any]:
        """Get details of a specific IP address configuration.

        Args:
            device_id: Device identifier
            address_id: Address ID

        Returns:
            IP address information dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
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

    async def get_arp_table(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """Get ARP (Address Resolution Protocol) table entries.

        Args:
            device_id: Device identifier

        Returns:
            List of ARP entry dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
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
            device.management_address, address_details["address"]
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
