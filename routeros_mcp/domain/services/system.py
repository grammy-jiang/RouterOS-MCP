"""System service for system information and metrics collection.

Provides operations for querying RouterOS system information,
including resource metrics, identity, and package information.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import SystemResource
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.utils import parse_routeros_uptime

logger = logging.getLogger(__name__)


class SystemService:
    """Service for RouterOS system information operations.

    Responsibilities:
    - Query system resource metrics (CPU, memory, uptime)
    - Retrieve system identity and hardware information
    - List installed packages
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = SystemService(session, settings)

            # Get system overview
            overview = await service.get_system_overview("dev-lab-01")

            # Get resource metrics
            resource = await service.get_system_resource("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize system service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def get_system_overview(
        self,
        device_id: str,
    ) -> dict:
        """Get comprehensive system overview for a device.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with system overview data

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        device = await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get system resource
            resource_data = await client.get("/rest/system/resource")

            # Get system identity
            try:
                identity_data = await client.get("/rest/system/identity")
                identity = identity_data.get("name", "Unknown")
            except Exception:
                identity = device.system_identity or "Unknown"

            # Parse metrics
            cpu_usage = float(resource_data.get("cpu-load", 0))
            memory_total = resource_data.get("total-memory", 0)
            memory_free = resource_data.get("free-memory", 0)
            memory_used = memory_total - memory_free
            memory_usage_pct = (
                (memory_used / memory_total * 100) if memory_total > 0 else 0.0
            )

            uptime = parse_routeros_uptime(resource_data.get("uptime", "0s"))

            overview = {
                "device_id": device_id,
                "device_name": device.name,
                "system_identity": identity,
                "routeros_version": resource_data.get("version", "Unknown"),
                "hardware_model": resource_data.get("board-name", "Unknown"),
                "architecture": resource_data.get("architecture-name", "Unknown"),
                "cpu_count": resource_data.get("cpu-count", 1),
                "cpu_usage_percent": cpu_usage,
                "memory_total_bytes": memory_total,
                "memory_used_bytes": memory_used,
                "memory_free_bytes": memory_free,
                "memory_usage_percent": memory_usage_pct,
                "uptime_seconds": uptime,
                "uptime_formatted": resource_data.get("uptime", "0s"),
                "timestamp": datetime.now(UTC).isoformat(),
            }

            return overview

        finally:
            await client.close()

    async def get_system_resource(
        self,
        device_id: str,
    ) -> SystemResource:
        """Get system resource metrics as domain model.

        Args:
            device_id: Device identifier

        Returns:
            SystemResource domain model

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get system resource
            resource_data = await client.get("/rest/system/resource")

            # Parse metrics
            cpu_usage = float(resource_data.get("cpu-load", 0))
            cpu_count = resource_data.get("cpu-count", 1)

            memory_total = resource_data.get("total-memory", 0)
            memory_free = resource_data.get("free-memory", 0)
            memory_used = memory_total - memory_free
            memory_usage_pct = (
                (memory_used / memory_total * 100) if memory_total > 0 else 0.0
            )

            uptime = parse_routeros_uptime(resource_data.get("uptime", "0s"))

            # Try to get identity
            try:
                identity_data = await client.get("/rest/system/identity")
                identity = identity_data.get("name")
            except Exception:
                identity = None

            return SystemResource(
                device_id=device_id,
                timestamp=datetime.now(UTC),
                routeros_version=resource_data.get("version", "Unknown"),
                system_identity=identity,
                hardware_model=resource_data.get("board-name"),
                uptime_seconds=uptime,
                cpu_usage_percent=cpu_usage,
                cpu_count=cpu_count,
                memory_total_bytes=memory_total,
                memory_free_bytes=memory_free,
                memory_used_bytes=memory_used,
                memory_usage_percent=memory_usage_pct,
            )

        finally:
            await client.close()

    async def get_system_packages(
        self,
        device_id: str,
    ) -> list[dict]:
        """Get list of installed packages.

        Args:
            device_id: Device identifier

        Returns:
            List of package information dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            packages = await client.get("/rest/system/package")

            # Normalize package data
            result: list[dict[str, Any]] = []
            if isinstance(packages, list):
                for pkg in packages:
                    if isinstance(pkg, dict):
                        result.append({
                            "name": pkg.get("name", "Unknown"),
                            "version": pkg.get("version", "Unknown"),
                            "build_time": pkg.get("build-time", "Unknown"),
                            "disabled": pkg.get("disabled", False),
                        })

            return result

        finally:
            await client.close()

    async def update_system_identity(
        self,
        device_id: str,
        new_identity: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update system identity (hostname).

        Args:
            device_id: Device identifier
            new_identity: New identity name
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with update result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValueError: If identity is invalid
        """
        # Validate identity
        if not new_identity or not new_identity.strip():
            raise ValueError("System identity cannot be empty")

        if len(new_identity) > 255:
            raise ValueError(
                f"System identity too long ({len(new_identity)} chars). "
                "Maximum 255 characters allowed."
            )

        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get current identity
            current_data = await client.get("/rest/system/identity")
            current_identity = current_data.get("name", "Unknown")

            # Check if change is needed
            if current_identity == new_identity:
                return {
                    "changed": False,
                    "old_identity": current_identity,
                    "new_identity": new_identity,
                    "dry_run": dry_run,
                }

            # Dry-run: return planned changes
            if dry_run:
                from routeros_mcp.security.safeguards import create_dry_run_response

                return create_dry_run_response(
                    operation="system/set-identity",
                    device_id=device_id,
                    planned_changes={
                        "old_identity": current_identity,
                        "new_identity": new_identity,
                    },
                )

            # Apply change
            await client.patch("/rest/system/identity", {"name": new_identity})

            logger.info(
                f"Updated system identity: {current_identity} -> {new_identity}",
                extra={"device_id": device_id},
            )

            return {
                "changed": True,
                "old_identity": current_identity,
                "new_identity": new_identity,
                "dry_run": False,
            }

        finally:
            await client.close()
