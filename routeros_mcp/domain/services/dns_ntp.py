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
