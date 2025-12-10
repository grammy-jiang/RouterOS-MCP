"""Firewall and logs service for firewall rules and system logging operations.

Provides operations for querying RouterOS firewall configuration and system logs.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService

logger = logging.getLogger(__name__)

# Safety limits
MAX_LOG_ENTRIES = 1000


class FirewallLogsService:
    """Service for RouterOS firewall and logging operations.

    Responsibilities:
    - Query firewall filter rules, NAT rules, and address lists
    - Retrieve system logs with filtering
    - Query logging configuration
    - Enforce safety limits on log queries
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = FirewallLogsService(session, settings)

            # Get firewall rules
            filter_rules = await service.list_filter_rules("dev-lab-01")
            nat_rules = await service.list_nat_rules("dev-lab-01")

            # Get logs
            logs = await service.get_recent_logs("dev-lab-01", limit=100)
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize firewall/logs service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def list_filter_rules(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List firewall filter rules (input/forward/output chains).

        Args:
            device_id: Device identifier

        Returns:
            List of filter rule dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            rules_data = await client.get("/rest/ip/firewall/filter")

            # Normalize rules data
            result: list[dict[str, Any]] = []
            if isinstance(rules_data, list):
                for rule in rules_data:
                    if isinstance(rule, dict):
                        result.append({
                            "id": rule.get(".id", ""),
                            "chain": rule.get("chain", ""),
                            "action": rule.get("action", ""),
                            "protocol": rule.get("protocol", ""),
                            "dst_port": rule.get("dst-port", ""),
                            "src_port": rule.get("src-port", ""),
                            "src_address": rule.get("src-address", ""),
                            "dst_address": rule.get("dst-address", ""),
                            "comment": rule.get("comment", ""),
                            "disabled": rule.get("disabled", False),
                        })

            return result

        finally:
            await client.close()

    async def list_nat_rules(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List NAT (Network Address Translation) rules.

        Args:
            device_id: Device identifier

        Returns:
            List of NAT rule dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            rules_data = await client.get("/rest/ip/firewall/nat")

            # Normalize rules data
            result: list[dict[str, Any]] = []
            if isinstance(rules_data, list):
                for rule in rules_data:
                    if isinstance(rule, dict):
                        result.append({
                            "id": rule.get(".id", ""),
                            "chain": rule.get("chain", ""),
                            "action": rule.get("action", ""),
                            "out_interface": rule.get("out-interface", ""),
                            "in_interface": rule.get("in-interface", ""),
                            "to_addresses": rule.get("to-addresses", ""),
                            "to_ports": rule.get("to-ports", ""),
                            "comment": rule.get("comment", ""),
                            "disabled": rule.get("disabled", False),
                        })

            return result

        finally:
            await client.close()

    async def list_address_lists(
        self,
        device_id: str,
        list_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List firewall address-list entries (IP-based allow/deny lists).

        Args:
            device_id: Device identifier
            list_name: Optional filter by list name

        Returns:
            List of address-list entry dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            lists_data = await client.get("/rest/ip/firewall/address-list")

            # Normalize lists data
            result: list[dict[str, Any]] = []
            if isinstance(lists_data, list):
                for entry in lists_data:
                    if isinstance(entry, dict):
                        entry_list_name = entry.get("list", "")

                        # Filter by list name if provided
                        if list_name and entry_list_name != list_name:
                            continue

                        result.append({
                            "id": entry.get(".id", ""),
                            "list_name": entry_list_name,
                            "address": entry.get("address", ""),
                            "comment": entry.get("comment", ""),
                            "timeout": entry.get("timeout", ""),
                        })

            return result

        finally:
            await client.close()

    async def get_recent_logs(
        self,
        device_id: str,
        limit: int = 100,
        topics: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Retrieve recent system logs with optional filtering.

        Args:
            device_id: Device identifier
            limit: Maximum number of entries to return (max 1000)
            topics: Optional list of topics to filter by

        Returns:
            Tuple of (log_entries, total_count)

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValidationError: If limit exceeds maximum
        """
        from routeros_mcp.mcp.errors import ValidationError

        await self.device_service.get_device(device_id)

        # Enforce safety limit
        if limit > MAX_LOG_ENTRIES:
            raise ValidationError(
                f"Log entry limit cannot exceed {MAX_LOG_ENTRIES} entries",
                data={"requested_limit": limit, "max_limit": MAX_LOG_ENTRIES},
            )

        client = await self.device_service.get_rest_client(device_id)

        try:
            logs_data = await client.get("/rest/log")

            # Normalize logs data
            result: list[dict[str, Any]] = []
            if isinstance(logs_data, list):
                for i, entry in enumerate(logs_data):
                    if i >= limit:
                        break
                    if isinstance(entry, dict):
                        entry_topics = entry.get("topics", "")
                        if isinstance(entry_topics, str):
                            entry_topics_list = [t.strip() for t in entry_topics.split(",") if t.strip()]
                        elif isinstance(entry_topics, list):
                            entry_topics_list = entry_topics
                        else:
                            entry_topics_list = []

                        # Filter by topics if provided
                        if topics:
                            if not any(t in entry_topics_list for t in topics):
                                continue

                        result.append({
                            "id": entry.get(".id", ""),
                            "time": entry.get("time", ""),
                            "topics": entry_topics_list,
                            "message": entry.get("message", ""),
                        })

            total_count = len(logs_data) if isinstance(logs_data, list) else 0
            return result, total_count

        finally:
            await client.close()

    async def get_logging_config(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """Get logging configuration (which topics log to which destinations).

        Args:
            device_id: Device identifier

        Returns:
            List of logging action dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            logging_data = await client.get("/rest/system/logging")

            # Normalize logging data
            result: list[dict[str, Any]] = []
            if isinstance(logging_data, list):
                for action in logging_data:
                    if isinstance(action, dict):
                        topics = action.get("topics", "")
                        if isinstance(topics, str):
                            topics_list = [t.strip() for t in topics.split(",") if t.strip()]
                        elif isinstance(topics, list):
                            topics_list = topics
                        else:
                            topics_list = []

                        result.append({
                            "topics": topics_list,
                            "action": action.get("action", ""),
                            "prefix": action.get("prefix", ""),
                        })

            return result

        finally:
            await client.close()
