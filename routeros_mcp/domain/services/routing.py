"""Routing service for routing table operations.

Provides operations for querying RouterOS routing table information.
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
        """Get routing table summary with route counts and key routes with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            Routing summary dictionary with counts and routes

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            summary = await self._get_routing_summary_via_rest(device_id)
            summary["transport"] = "rest"
            summary["fallback_used"] = False
            summary["rest_error"] = None
            return summary
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST routing summary failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            try:
                summary = await self._get_routing_summary_via_ssh(device_id)
                summary["transport"] = "ssh"
                summary["fallback_used"] = True
                summary["rest_error"] = str(rest_exc)
                return summary
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH routing summary failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Routing summary failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_routing_summary_via_rest(self, device_id: str) -> dict[str, Any]:
        """Fetch routing summary via REST API."""
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

    async def _get_routing_summary_via_ssh(self, device_id: str) -> dict[str, Any]:
        """Fetch routing summary via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/route/print")
            routes_list = self._parse_route_print_output(output)

            # Analyze routes by type
            static_routes = sum(1 for r in routes_list if r.get("static"))
            connected_routes = sum(1 for r in routes_list if r.get("connected"))
            dynamic_routes = sum(1 for r in routes_list if r.get("dynamic"))

            return {
                "total_routes": len(routes_list),
                "static_routes": static_routes,
                "connected_routes": connected_routes,
                "dynamic_routes": dynamic_routes,
                "routes": [
                    {
                        "id": r.get("id", ""),
                        "dst_address": r.get("dst_address", ""),
                        "gateway": r.get("gateway", ""),
                        "distance": r.get("distance", 0),
                        "comment": "",
                    }
                    for r in routes_list
                ],
            }
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_route_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /ip/route/print output."""
        routes: list[dict[str, Any]] = []

        header_tokens = {
            "dst-address",
            "pref-src",
            "gateway",
            "distance",
            "routing-table",
            "routingtable",
        }

        def _looks_like_header(parts: list[str]) -> bool:
            normalized: list[str] = []
            for token in parts:
                token_clean = token.strip().strip(",").strip(":")
                if not token_clean:
                    continue
                token_clean = token_clean.replace("/", " ")
                for piece in token_clean.split():
                    piece_clean = piece.strip().strip(",").strip(":").lower()
                    if piece_clean:
                        normalized.append(piece_clean)

            return bool(normalized) and all(piece in header_tokens for piece in normalized)

        lines = output.strip().split("\n")
        route_counter = 0  # Generate synthetic IDs if not in output
        for line in lines:
            stripped = line.strip()
            if (
                not stripped
                or stripped.startswith("Flags:")
                or stripped.startswith("#")
                or stripped.lower().startswith("columns:")
                or stripped.lower().startswith("dst-address")
                or (
                    "distance" in stripped.lower()
                    and "gateway" in stripped.lower()
                    and "/" not in stripped
                )
            ):
                continue

            parts = line.split()
            if not parts:
                continue

            if _looks_like_header(parts):
                continue

            try:
                route_id = ""
                flags = ""
                idx = 0

                parts_lower0 = parts[0].lower()
                if parts_lower0 in {"gateway", "dst-address", "distance", "routing-table"}:
                    continue

                # Pattern A: numeric or * index followed by optional flags
                if parts[0][0].isdigit() or parts[0].startswith("*"):
                    route_id = parts[0]
                    idx = 1
                    if idx < len(parts) and any(ch.isalpha() for ch in parts[idx]):
                        flags = parts[idx]
                        idx += 1
                # Pattern B: flags-only (common in compact /ip/route/print)
                elif any(ch.isalpha() for ch in parts[0]) and "/" not in parts[0]:
                    flags = parts[0]
                    idx = 1

                # Generate synthetic ID if not present
                if not route_id:
                    route_id = f"*{route_counter}"
                    route_counter += 1
                elif parts[0][0].isdigit() or parts[0].startswith("*"):
                    # Extract numeric part for counter
                    try:
                        num = int(parts[0].lstrip("*"))
                        route_counter = max(route_counter, num + 1)
                    except ValueError:
                        pass

                # Now expect: dst-address gateway [routing-table] distance
                if len(parts) <= idx + 1:
                    continue

                dst_address = parts[idx]

                # Take tokens after dst for further parsing
                remainder = parts[idx + 1 :]
                distance_token = remainder[-1] if remainder else "0"
                try:
                    distance_val = int(distance_token)
                    remainder = remainder[:-1]
                except ValueError:
                    distance_val = 0

                routing_table = ""
                if remainder and any(ch.isalpha() for ch in remainder[-1]):
                    routing_table = remainder[-1]
                    remainder = remainder[:-1]

                gateway = remainder[-1] if remainder else ""

                routes.append({
                    "id": route_id,
                    "dst_address": dst_address,
                    "gateway": gateway,
                    "routing_table": routing_table,
                    "distance": distance_val,
                    "static": "S" in flags or "s" in flags,
                    "dynamic": "D" in flags or "d" in flags,
                    "connected": "C" in flags or "c" in flags,
                })
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse route line: {line}", exc_info=e)
                continue

        return routes

    async def get_route(
        self,
        device_id: str,
        route_id: str,
    ) -> dict[str, Any]:
        """Get detailed information about a specific route with REST→SSH fallback.

        Args:
            device_id: Device identifier
            route_id: Route ID

        Returns:
            Route information dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            route = await self._get_route_via_rest(device_id, route_id)
            route["transport"] = "rest"
            route["fallback_used"] = False
            route["rest_error"] = None
            return route
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST get_route failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id, "route_id": route_id},
            )
            try:
                route = await self._get_route_via_ssh(device_id, route_id)
                route["transport"] = "ssh"
                route["fallback_used"] = True
                route["rest_error"] = str(rest_exc)
                return route
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH get_route failed",
                    exc_info=ssh_exc,
                    extra={
                        "device_id": device_id,
                        "route_id": route_id,
                        "rest_error": str(rest_exc),
                    },
                )
                raise RuntimeError(
                    f"Get route failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_route_via_rest(
        self,
        device_id: str,
        route_id: str,
    ) -> dict[str, Any]:
        """Fetch route details via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            route_data = await client.get(f"/rest/ip/route/{route_id}")

            # Handle empty or None responses
            if not route_data or not isinstance(route_data, dict):
                return {}

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

    async def _get_route_via_ssh(
        self,
        device_id: str,
        route_id: str,
    ) -> dict[str, Any]:
        """Fetch route details via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/route/print")
            routes = self._parse_route_print_output(output)

            # Try to match by ID first
            for route in routes:
                if route.get("id") == route_id:
                    return {
                        "id": route.get("id", route_id),
                        "dst_address": route.get("dst_address", ""),
                        "gateway": route.get("gateway", ""),
                        "distance": route.get("distance", 0),
                        "scope": 0,
                        "target_scope": 0,
                        "comment": "",
                        "active": True,
                        "dynamic": route.get("dynamic", False),
                    }

            # Try matching by index if no ID match found
            # If route_id looks like an index (e.g., "2", "3", etc.)
            try:
                route_index = int(route_id.lstrip("*"))
                if 0 <= route_index < len(routes):
                    route = routes[route_index]
                    return {
                        "id": route.get("id", f"*{route_index}"),
                        "dst_address": route.get("dst_address", ""),
                        "gateway": route.get("gateway", ""),
                        "distance": route.get("distance", 0),
                        "scope": 0,
                        "target_scope": 0,
                        "comment": "",
                        "active": True,
                        "dynamic": route.get("dynamic", False),
                    }
            except (ValueError, IndexError):
                pass

            return {}

        finally:
            await ssh_client.close()
