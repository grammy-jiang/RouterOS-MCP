"""Firewall service for firewall configuration operations.

Provides operations for querying and managing RouterOS firewall configuration,
including filter rules, NAT rules, and address lists.
"""

import logging
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.observability import metrics

logger = logging.getLogger(__name__)


class FirewallService:
    """Service for RouterOS firewall operations.

    Responsibilities:
    - Query firewall configuration
    - Manage MCP-owned address lists
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = FirewallService(session, settings)

            # Update address list entry
            result = await service.update_address_list_entry(
                "dev-lab-01",
                "mcp-managed-hosts",
                "10.0.1.100",
                action="add"
            )
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize firewall service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def list_address_lists(
        self,
        device_id: str,
        list_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List firewall address-list entries.

        Args:
            device_id: Device identifier
            list_name: Optional list name filter

        Returns:
            List of address-list entry dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            address_lists = await client.get("/rest/ip/firewall/address-list")

            # Normalize address list data
            result: list[dict[str, Any]] = []
            if isinstance(address_lists, list):
                for entry in address_lists:
                    if isinstance(entry, dict):
                        # Filter by list name if provided
                        if list_name and entry.get("list") != list_name:
                            continue

                        result.append({
                            "id": entry.get(".id", ""),
                            "list_name": entry.get("list", ""),
                            "address": entry.get("address", ""),
                            "comment": entry.get("comment", ""),
                            "timeout": entry.get("timeout", ""),
                            "disabled": entry.get("disabled", False),
                            "dynamic": entry.get("dynamic", False),
                        })

            return result

        finally:
            await client.close()

    async def update_address_list_entry(
        self,
        device_id: str,
        list_name: str,
        address: str,
        action: str = "add",
        comment: str = "",
        timeout: str = "",
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update firewall address-list entry (add or remove).

        Args:
            device_id: Device identifier
            list_name: Address list name (must start with 'mcp-')
            address: IP address or network
            action: Action to perform ("add" or "remove")
            comment: Optional comment (for add)
            timeout: Optional timeout (for add, e.g., "1d")
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with update result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            InvalidListNameError: If list name doesn't start with 'mcp-'
            ValueError: If action is invalid
        """
        from routeros_mcp.security.safeguards import (
            create_dry_run_response,
            validate_ip_address_format,
            validate_mcp_owned_list,
        )

        # Validate list name is MCP-owned
        validate_mcp_owned_list(list_name)

        # Validate action
        if action not in ("add", "remove"):
            raise ValueError(
                f"Invalid action: {action}. Must be 'add' or 'remove'."
            )

        # Validate IP address format (for add action)
        if action == "add":
            validate_ip_address_format(address)

        await self.device_service.get_device(device_id)

        # For remove action, find the entry ID
        entry_id = None
        if action == "remove":
            existing_entries = await self.list_address_lists(device_id, list_name)
            for entry in existing_entries:
                if entry["address"] == address and entry["list_name"] == list_name:
                    entry_id = entry["id"]
                    break

            if not entry_id:
                # Entry doesn't exist, nothing to remove
                return {
                    "changed": False,
                    "action": action,
                    "list_name": list_name,
                    "address": address,
                    "dry_run": dry_run,
                    "message": "Entry not found, no action needed",
                }

        # Dry-run: return planned changes
        if dry_run:
            planned_changes = {
                "action": action,
                "list_name": list_name,
                "address": address,
            }
            if action == "add":
                planned_changes["comment"] = comment
                planned_changes["timeout"] = timeout
            else:
                # entry_id guaranteed non-None here since we checked for it above and returned early if None
                planned_changes["entry_id"] = cast(str, entry_id)

            return cast(dict[str, Any], create_dry_run_response(
                operation="firewall/update-address-list-entry",
                device_id=device_id,
                planned_changes=planned_changes,
            ))

        # Apply change
        client = await self.device_service.get_rest_client(device_id)

        try:
            if action == "add":
                payload = {
                    "list": list_name,
                    "address": address,
                }
                if comment:
                    payload["comment"] = comment
                if timeout:
                    payload["timeout"] = timeout

                result = await client.put("/rest/ip/firewall/address-list", payload)
                result_id = result.get(".id", "") if isinstance(result, dict) else ""

                logger.info(
                    f"Added {address} to address list '{list_name}'",
                    extra={"device_id": device_id, "entry_id": result_id},
                )

                # Invalidate firewall cache after successful update
                if self.settings.mcp_resource_cache_auto_invalidate:
                    await self._invalidate_firewall_cache(device_id)

                return {
                    "changed": True,
                    "action": action,
                    "list_name": list_name,
                    "address": address,
                    "entry_id": result_id,
                    "dry_run": False,
                }

            else:  # remove
                await client.delete(f"/rest/ip/firewall/address-list/{entry_id}")

                logger.info(
                    f"Removed {address} from address list '{list_name}'",
                    extra={"device_id": device_id, "entry_id": entry_id},
                )

                # Invalidate firewall cache after successful update
                if self.settings.mcp_resource_cache_auto_invalidate:
                    await self._invalidate_firewall_cache(device_id)

                return {
                    "changed": True,
                    "action": action,
                    "list_name": list_name,
                    "address": address,
                    "entry_id": entry_id,
                    "dry_run": False,
                }

        finally:
            await client.close()

    async def _invalidate_firewall_cache(self, device_id: str) -> None:
        """Invalidate firewall-related cache entries for a device.

        Args:
            device_id: Device identifier
        """
        try:
            from routeros_mcp.infra.observability.resource_cache import get_cache

            cache = get_cache()

            # Invalidate firewall address-list resources
            count = await cache.invalidate_pattern(f"device://{device_id}/firewall")

            if count > 0:
                metrics.record_cache_invalidation("firewall", "config_update")
                logger.info(
                    f"Invalidated firewall cache entries for device {device_id}",
                    extra={"device_id": device_id, "invalidated_count": count}
                )
        except RuntimeError:
            # Cache not initialized - skip invalidation
            logger.debug("Cache not initialized, skipping firewall cache invalidation")
