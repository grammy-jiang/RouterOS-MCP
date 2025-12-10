"""Routing service for routing table operations.

Provides operations for querying RouterOS routing table information.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService

logger = logging.getLogger(__name__)


class RoutingService:
    """Service for RouterOS routing operations.

    Responsibilities:
    - Query routing table and routes
    - Analyze route types and statistics
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = RoutingService(session, settings)

            # Get routing summary
            summary = await service.get_routing_summary("dev-lab-01")

            # Get specific route
            route = await service.get_route("dev-lab-01", "*3")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize routing service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def get_routing_summary(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Get routing table summary with route counts and key routes.

        Args:
            device_id: Device identifier

        Returns:
            Routing summary dictionary with counts and routes

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            routes_data = await client.get("/rest/ip/route")

            # Analyze routes
            total_routes = 0
            static_routes = 0
            connected_routes = 0
            dynamic_routes = 0
            routes_list: list[dict[str, Any]] = []

            if isinstance(routes_data, list):
                total_routes = len(routes_data)
                
                for route in routes_data:
                    if isinstance(route, dict):
                        # Count by type
                        if route.get("static", False):
                            static_routes += 1
                        elif route.get("connect", False) or route.get("connected", False):
                            connected_routes += 1
                        elif route.get("dynamic", False):
                            dynamic_routes += 1

                        # Add to routes list
                        routes_list.append({
                            "id": route.get(".id", ""),
                            "dst_address": route.get("dst-address", ""),
                            "gateway": route.get("gateway", ""),
                            "distance": route.get("distance", 0),
                            "comment": route.get("comment", ""),
                        })

            return {
                "total_routes": total_routes,
                "static_routes": static_routes,
                "connected_routes": connected_routes,
                "dynamic_routes": dynamic_routes,
                "routes": routes_list,
            }

        finally:
            await client.close()

    async def get_route(
        self,
        device_id: str,
        route_id: str,
    ) -> dict[str, Any]:
        """Get detailed information about a specific route.

        Args:
            device_id: Device identifier
            route_id: Route ID

        Returns:
            Route information dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            route_data = await client.get(f"/rest/ip/route/{route_id}")

            # Normalize route data
            return {
                "id": route_data.get(".id", route_id),
                "dst_address": route_data.get("dst-address", ""),
                "gateway": route_data.get("gateway", ""),
                "distance": route_data.get("distance", 0),
                "scope": route_data.get("scope", 0),
                "target_scope": route_data.get("target-scope", 0),
                "comment": route_data.get("comment", ""),
                "active": route_data.get("active", False),
                "dynamic": route_data.get("dynamic", False),
            }

        finally:
            await client.close()
