"""DNS and NTP service for DNS and time synchronization operations.

Provides operations for querying RouterOS DNS and NTP configuration
and status.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService

logger = logging.getLogger(__name__)

# Safety limits
MAX_DNS_CACHE_ENTRIES = 1000


class DNSNTPService:
    """Service for RouterOS DNS and NTP operations.

    Responsibilities:
    - Query DNS configuration and cache
    - Query NTP configuration and sync status
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = DNSNTPService(session, settings)

            # Get DNS status
            dns_status = await service.get_dns_status("dev-lab-01")

            # Get DNS cache
            cache = await service.get_dns_cache("dev-lab-01", limit=100)

            # Get NTP status
            ntp_status = await service.get_ntp_status("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize DNS/NTP service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def get_dns_status(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Get DNS server configuration and cache statistics.

        Args:
            device_id: Device identifier

        Returns:
            DNS configuration dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            dns_data = await client.get("/rest/ip/dns")

            # Parse DNS servers (comma-separated string to list)
            servers_str = dns_data.get("servers", "")
            dns_servers = [s.strip() for s in servers_str.split(",") if s.strip()]

            return {
                "dns_servers": dns_servers,
                "allow_remote_requests": dns_data.get("allow-remote-requests", False),
                "cache_size_kb": dns_data.get("cache-size", 2048),
                "cache_used_kb": dns_data.get("cache-used", 0),
            }

        finally:
            await client.close()

    async def get_dns_cache(
        self,
        device_id: str,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        """View DNS cache entries (recently resolved domains).

        Args:
            device_id: Device identifier
            limit: Maximum number of entries to return (max 1000)

        Returns:
            Tuple of (cache_entries, total_count)

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValidationError: If limit exceeds maximum
        """
        from routeros_mcp.mcp.errors import ValidationError

        await self.device_service.get_device(device_id)

        # Enforce safety limit
        if limit > MAX_DNS_CACHE_ENTRIES:
            raise ValidationError(
                f"DNS cache limit cannot exceed {MAX_DNS_CACHE_ENTRIES} entries",
                data={"requested_limit": limit, "max_limit": MAX_DNS_CACHE_ENTRIES},
            )

        client = await self.device_service.get_rest_client(device_id)

        try:
            cache_data = await client.get("/rest/ip/dns/cache")

            # Normalize cache data
            result: list[dict[str, Any]] = []
            if isinstance(cache_data, list):
                for i, entry in enumerate(cache_data):
                    if i >= limit:
                        break
                    if isinstance(entry, dict):
                        result.append({
                            "name": entry.get("name", ""),
                            "type": entry.get("type", ""),
                            "data": entry.get("data", ""),
                            "ttl": entry.get("ttl", 0),
                        })

            total_count = len(cache_data) if isinstance(cache_data, list) else 0
            return result, total_count

        finally:
            await client.close()

    async def get_ntp_status(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Get NTP client configuration and synchronization status.

        Args:
            device_id: Device identifier

        Returns:
            NTP status dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get NTP client configuration
            ntp_config = await client.get("/rest/system/ntp/client")

            # Parse NTP servers (may be comma-separated or array)
            servers_str = ntp_config.get("servers", "")
            if isinstance(servers_str, str):
                ntp_servers = [s.strip() for s in servers_str.split(",") if s.strip()]
            elif isinstance(servers_str, list):
                ntp_servers = servers_str
            else:
                ntp_servers = []

            # Try to get monitor data for sync status
            try:
                monitor_data = await client.get("/rest/system/ntp/client/monitor")
                status = "synchronized" if monitor_data.get("synced", False) else "not_synchronized"
                stratum = monitor_data.get("stratum", 0)
                offset_ms = monitor_data.get("offset", 0.0)
            except Exception:
                # Monitor endpoint may not be available on all RouterOS versions
                status = "enabled" if ntp_config.get("enabled", False) else "disabled"
                stratum = 0
                offset_ms = 0.0

            return {
                "enabled": ntp_config.get("enabled", False),
                "ntp_servers": ntp_servers,
                "mode": ntp_config.get("mode", "unicast"),
                "status": status,
                "stratum": stratum,
                "offset_ms": offset_ms,
            }

        finally:
            await client.close()

    async def update_dns_servers(
        self,
        device_id: str,
        dns_servers: list[str],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update DNS server configuration.

        Args:
            device_id: Device identifier
            dns_servers: List of DNS server addresses
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with update result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValueError: If server addresses are invalid
        """
        from routeros_mcp.security.safeguards import (
            create_dry_run_response,
            validate_dns_servers,
        )

        # Validate DNS servers
        validate_dns_servers(dns_servers)

        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get current DNS configuration
            current_data = await client.get("/rest/ip/dns")
            current_servers_str = current_data.get("servers", "")
            current_servers = [
                s.strip() for s in current_servers_str.split(",") if s.strip()
            ]

            # Check if change is needed
            if set(current_servers) == set(dns_servers):
                return {
                    "changed": False,
                    "old_servers": current_servers,
                    "new_servers": dns_servers,
                    "dry_run": dry_run,
                }

            # Dry-run: return planned changes
            if dry_run:
                return create_dry_run_response(
                    operation="dns/update-servers",
                    device_id=device_id,
                    planned_changes={
                        "old_servers": current_servers,
                        "new_servers": dns_servers,
                    },
                )

            # Apply change
            servers_str = ",".join(dns_servers)
            await client.patch("/rest/ip/dns", {"servers": servers_str})

            logger.info(
                f"Updated DNS servers: {current_servers} -> {dns_servers}",
                extra={"device_id": device_id},
            )

            return {
                "changed": True,
                "old_servers": current_servers,
                "new_servers": dns_servers,
                "dry_run": False,
            }

        finally:
            await client.close()

    async def flush_dns_cache(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Flush (clear) DNS cache.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with flush result

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get cache size before flush (for reporting)
            try:
                cache_data = await client.get("/rest/ip/dns/cache")
                entries_before = len(cache_data) if isinstance(cache_data, list) else 0
            except Exception:
                entries_before = 0

            # Flush cache
            await client.post("/rest/ip/dns/cache/flush", {})

            logger.info(
                f"Flushed DNS cache ({entries_before} entries)",
                extra={"device_id": device_id},
            )

            return {
                "changed": True,
                "entries_flushed": entries_before,
            }

        finally:
            await client.close()

    async def update_ntp_servers(
        self,
        device_id: str,
        ntp_servers: list[str],
        enabled: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update NTP server configuration.

        Args:
            device_id: Device identifier
            ntp_servers: List of NTP server addresses
            enabled: Enable NTP client
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with update result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValueError: If server addresses are invalid
        """
        from routeros_mcp.security.safeguards import (
            create_dry_run_response,
            validate_ntp_servers,
        )

        # Validate NTP servers
        validate_ntp_servers(ntp_servers)

        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get current NTP configuration
            current_data = await client.get("/rest/system/ntp/client")
            current_servers_str = current_data.get("servers", "")
            if isinstance(current_servers_str, str):
                current_servers = [
                    s.strip() for s in current_servers_str.split(",") if s.strip()
                ]
            elif isinstance(current_servers_str, list):
                current_servers = current_servers_str
            else:
                current_servers = []
            current_enabled = current_data.get("enabled", False)

            # Check if change is needed
            if set(current_servers) == set(ntp_servers) and current_enabled == enabled:
                return {
                    "changed": False,
                    "old_servers": current_servers,
                    "new_servers": ntp_servers,
                    "enabled": enabled,
                    "dry_run": dry_run,
                }

            # Dry-run: return planned changes
            if dry_run:
                return create_dry_run_response(
                    operation="ntp/update-servers",
                    device_id=device_id,
                    planned_changes={
                        "old_servers": current_servers,
                        "new_servers": ntp_servers,
                        "old_enabled": current_enabled,
                        "new_enabled": enabled,
                    },
                )

            # Apply change
            servers_str = ",".join(ntp_servers)
            await client.patch(
                "/rest/system/ntp/client",
                {"servers": servers_str, "enabled": "yes" if enabled else "no"},
            )

            logger.info(
                f"Updated NTP servers: {current_servers} -> {ntp_servers}, enabled={enabled}",
                extra={"device_id": device_id},
            )

            return {
                "changed": True,
                "old_servers": current_servers,
                "new_servers": ntp_servers,
                "enabled": enabled,
                "dry_run": False,
            }

        finally:
            await client.close()
