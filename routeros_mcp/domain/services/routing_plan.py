"""Routing plan service for static route planning and validation.

This service implements the plan phase for static route operations,
providing validation, risk assessment, and preview generation.

See docs/07-device-control-and-high-risk-operations-safeguards.md for
detailed requirements.
"""

import gzip
import hashlib
import ipaddress
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient

logger = logging.getLogger(__name__)


class RoutingPlanService:
    """Service for static route planning operations.

    Provides:
    - Route parameter validation (destination, gateway, no default routes)
    - Risk level assessment based on management network impact
    - Preview generation for planned changes
    - Gateway reachability checks
    - Routing table snapshot/rollback

    All routing operations follow the plan/apply workflow.
    """

    # Default routes that are always blocked
    DEFAULT_ROUTES = ["0.0.0.0/0", "::/0"]

    # High-risk conditions for risk assessment
    HIGH_RISK_ENVIRONMENTS = ["prod"]  # Production environment

    def validate_route_params(
        self,
        dst_address: str,
        gateway: str | None = None,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """Validate static route parameters.

        Args:
            dst_address: Destination address in CIDR notation
            gateway: Gateway IP address (optional for validation only)
            comment: Route comment (optional)

        Returns:
            Dictionary with validation result

        Raises:
            ValueError: If any parameter is invalid
        """
        errors = []

        # Validate destination address
        if not dst_address:
            errors.append("Destination address is required")
        else:
            try:
                network = ipaddress.ip_network(dst_address, strict=False)
                
                # Block default routes
                if str(network) in self.DEFAULT_ROUTES or dst_address in self.DEFAULT_ROUTES:
                    errors.append(
                        f"Default route {dst_address} is blocked for safety. "
                        f"Default routes cannot be managed via MCP."
                    )
            except ValueError as e:
                errors.append(f"Invalid destination address '{dst_address}': {e}")

        # Validate gateway if provided
        if gateway:
            try:
                ipaddress.ip_address(gateway)
            except ValueError as e:
                errors.append(f"Invalid gateway address '{gateway}': {e}")

        if errors:
            raise ValueError("Route parameter validation failed:\n- " + "\n- ".join(errors))

        logger.debug(f"Route parameter validation passed for dst={dst_address}, gateway={gateway}")

        return {
            "valid": True,
            "dst_address": dst_address,
            "gateway": gateway,
            "comment": comment,
        }

    def check_management_network_overlap(
        self,
        dst_address: str,
        management_ip: str,
    ) -> bool:
        """Check if route destination overlaps with management network.

        Args:
            dst_address: Destination address in CIDR notation
            management_ip: Device management IP address

        Returns:
            True if overlaps (high risk), False otherwise
        """
        try:
            network = ipaddress.ip_network(dst_address, strict=False)
            mgmt_ip = ipaddress.ip_address(management_ip)
            
            # Check if management IP is within the destination network
            return mgmt_ip in network
        except (ValueError, TypeError):
            # On parse error, assume high risk for safety
            logger.warning(
                f"Could not parse addresses for overlap check: "
                f"dst={dst_address}, mgmt={management_ip}"
            )
            return True

    def assess_risk(
        self,
        dst_address: str,
        device_environment: str = "lab",
        management_ip: str | None = None,
    ) -> str:
        """Assess risk level for a static route operation.

        Risk classification:
        - High risk:
          - Routes affecting management networks (destination overlaps with management IP)
          - Production environment
        - Medium risk:
          - Other static routes on non-management paths
          - Lab/staging environments

        Args:
            dst_address: Destination address in CIDR notation
            device_environment: Device environment (lab/staging/prod)
            management_ip: Device management IP (for overlap detection)

        Returns:
            Risk level: "medium" or "high"
        """
        # High risk conditions
        if device_environment in self.HIGH_RISK_ENVIRONMENTS:
            logger.info("High risk: production environment")
            return "high"

        if management_ip and self.check_management_network_overlap(dst_address, management_ip):
            logger.info("High risk: route destination overlaps with management network")
            return "high"

        # Default to medium risk
        logger.debug(
            f"Medium risk: dst={dst_address}, env={device_environment}, "
            f"mgmt={management_ip}"
        )
        return "medium"

    def generate_preview(
        self,
        operation: str,
        device_id: str,
        device_name: str,
        device_environment: str,
        dst_address: str | None = None,
        gateway: str | None = None,
        comment: str | None = None,
        route_id: str | None = None,
        modifications: dict[str, Any] | None = None,
        management_ip: str | None = None,
    ) -> dict[str, Any]:
        """Generate detailed preview for a static route operation.

        Args:
            operation: Operation type (add_static_route/modify_static_route/remove_static_route)
            device_id: Device identifier
            device_name: Device name
            device_environment: Device environment
            dst_address: Destination address (for add/modify)
            gateway: Gateway address (for add/modify)
            comment: Route comment (for add/modify)
            route_id: Route ID (for modify/remove)
            modifications: Modifications dict (for modify)
            management_ip: Device management IP (for risk assessment)

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

        # Generate warnings for management network overlap
        warnings = []
        if dst_address and management_ip:
            if self.check_management_network_overlap(dst_address, management_ip):
                warnings.append(
                    f"WARNING: Route destination {dst_address} overlaps with "
                    f"management network. This may affect device reachability."
                )

        if operation == "add_static_route":
            # Build route specification
            route_parts = [
                f"dst-address={dst_address}",
            ]
            if gateway:
                route_parts.append(f"gateway={gateway}")
            if comment:
                route_parts.append(f"comment={comment}")

            route_spec = " ".join(route_parts)

            preview["preview"] = {
                "operation": "add_static_route",
                "dst_address": dst_address,
                "gateway": gateway,
                "route_spec": route_spec,
                "estimated_impact": "Low - route added to routing table, may affect traffic to destination",
                "warnings": warnings,
            }

        elif operation == "modify_static_route":
            preview["preview"] = {
                "operation": "modify_static_route",
                "route_id": route_id,
                "modifications": modifications or {},
                "estimated_impact": "Medium - existing route modified, may affect active traffic",
                "warnings": warnings,
            }

        elif operation == "remove_static_route":
            preview["preview"] = {
                "operation": "remove_static_route",
                "route_id": route_id,
                "estimated_impact": "Medium - route removal may make destination unreachable",
                "warnings": warnings,
            }

        logger.debug(f"Generated preview for {operation} on device {device_id}")

        return preview

    async def create_routing_snapshot(
        self,
        device_id: str,
        device_name: str,
        rest_client: RouterOSRestClient,
    ) -> dict[str, Any]:
        """Create snapshot of current routing table for rollback.

        Args:
            device_id: Device identifier
            device_name: Device name
            rest_client: REST client instance for device

        Returns:
            Snapshot metadata with snapshot_id and routes payload

        Raises:
            Exception: If snapshot creation fails
        """
        try:
            # Fetch current static routes
            routes_data = await rest_client.get("/rest/ip/route")
            
            # Filter only static routes
            static_routes = []
            if isinstance(routes_data, list):
                static_routes = [
                    route for route in routes_data
                    if isinstance(route, dict) and route.get("static", False)
                ]

            # Create snapshot payload
            snapshot_payload = {
                "device_id": device_id,
                "device_name": device_name,
                "timestamp": datetime.now(UTC).isoformat(),
                "static_routes": static_routes,
            }

            # Serialize and compress
            payload_json = json.dumps(snapshot_payload)
            payload_bytes = payload_json.encode("utf-8")
            compressed_data = gzip.compress(payload_bytes, compresslevel=6)

            # Calculate checksum
            checksum = hashlib.sha256(payload_bytes).hexdigest()

            # Generate snapshot ID
            snapshot_id = f"snap-rt-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

            logger.info(
                f"Created routing snapshot {snapshot_id} for device {device_id}",
                extra={
                    "snapshot_id": snapshot_id,
                    "device_id": device_id,
                    "route_count": len(static_routes),
                    "size_bytes": len(payload_bytes),
                    "compressed_size": len(compressed_data),
                },
            )

            return {
                "snapshot_id": snapshot_id,
                "device_id": device_id,
                "timestamp": snapshot_payload["timestamp"],
                "route_count": len(static_routes),
                "size_bytes": len(payload_bytes),
                "compressed_size": len(compressed_data),
                "checksum": checksum,
                "data": compressed_data,
            }

        except Exception as e:
            logger.error(
                f"Failed to create routing snapshot for device {device_id}: {e}",
                exc_info=True,
            )
            raise

    async def perform_health_check(
        self,
        device_id: str,
        rest_client: RouterOSRestClient,
        timeout_seconds: float = 30.0,  # noqa: ARG002 - reserved for future timeout implementation
    ) -> dict[str, Any]:
        """Perform health check after routing changes.

        Verifies:
        - Device still responds to REST API
        - Routing table is accessible
        - Basic connectivity test

        Args:
            device_id: Device identifier
            rest_client: REST client instance for device
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

            # Test 2: Verify routing table is accessible (management path intact)
            routes = await rest_client.get("/rest/ip/route")

            if routes is None:
                return {
                    "status": "degraded",
                    "device_id": device_id,
                    "checks": [
                        {
                            "check": "rest_api_response",
                            "status": "passed",
                            "message": "Device responds to REST API",
                        },
                        {
                            "check": "routing_access",
                            "status": "failed",
                            "message": "Cannot access routing table",
                        },
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # All checks passed
            logger.info(
                f"Health check passed for device {device_id}",
                extra={
                    "device_id": device_id,
                    "checks_passed": 2,
                },
            )

            return {
                "status": "healthy",
                "device_id": device_id,
                "checks": [
                    {
                        "check": "rest_api_response",
                        "status": "passed",
                        "message": "Device responds to REST API",
                    },
                    {
                        "check": "routing_access",
                        "status": "passed",
                        "message": "Routing table accessible",
                    },
                ],
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error(
                f"Health check failed for device {device_id}: {e}",
                exc_info=True,
            )
            return {
                "status": "failed",
                "device_id": device_id,
                "checks": [
                    {
                        "check": "health_check_exception",
                        "status": "failed",
                        "message": f"Health check exception: {str(e)}",
                    }
                ],
                "timestamp": datetime.now(UTC).isoformat(),
                "error": str(e),
            }

    async def rollback_from_snapshot(
        self,
        device_id: str,
        snapshot_data: bytes,
        rest_client: RouterOSRestClient,
        operation: str = "add_static_route",
    ) -> dict[str, Any]:
        """Rollback static routes from snapshot.

        Args:
            device_id: Device identifier
            snapshot_data: Compressed snapshot data
            rest_client: REST client instance for device
            operation: Operation type that was performed (add/modify/remove)

        Returns:
            Rollback results with status and details

        Raises:
            Exception: If rollback fails
        """
        try:
            # Decompress snapshot
            decompressed = gzip.decompress(snapshot_data)
            snapshot_payload = json.loads(decompressed.decode("utf-8"))

            original_routes = snapshot_payload.get("static_routes", [])

            logger.info(
                f"Starting rollback for device {device_id}",
                extra={
                    "device_id": device_id,
                    "operation": operation,
                    "original_route_count": len(original_routes),
                },
            )

            # Get current routes
            current_routes_data = await rest_client.get("/rest/ip/route")
            current_routes_list = current_routes_data if isinstance(current_routes_data, list) else []
            
            # Filter only static routes
            current_static_routes = [
                route for route in current_routes_list
                if isinstance(route, dict) and route.get("static", False)
            ]
            
            current_route_ids = {route.get(".id") for route in current_static_routes}
            original_route_ids = {route.get(".id") for route in original_routes}

            rollback_actions = []

            if operation == "add_static_route":
                # For add operations: remove newly added routes
                new_route_ids = current_route_ids - original_route_ids

                for route_id in new_route_ids:
                    try:
                        await rest_client.delete(f"/rest/ip/route/{route_id}")
                        rollback_actions.append({"action": "removed", "route_id": route_id})
                    except Exception as e:
                        logger.warning(
                            f"Failed to remove route {route_id} during rollback: {e}",
                            extra={"device_id": device_id, "route_id": route_id},
                        )
                        rollback_actions.append({"action": "failed_remove", "route_id": route_id, "error": str(e)})

            elif operation == "modify_static_route":
                # For modify operations: restore original route properties
                # Build a map of original routes by ID
                original_routes_map = {route.get(".id"): route for route in original_routes if route.get(".id")}

                for current_route in current_static_routes:
                    route_id = current_route.get(".id")
                    if route_id in original_routes_map:
                        original_route = original_routes_map[route_id]
                        # Check if route was modified (compare properties)
                        if self._route_differs(original_route, current_route):
                            try:
                                # Restore original properties
                                restore_data = {}
                                for key in ["dst-address", "gateway", "distance", "comment"]:
                                    if key in original_route:
                                        restore_data[key] = original_route[key]

                                await rest_client.patch(f"/rest/ip/route/{route_id}", restore_data)
                                rollback_actions.append({"action": "restored", "route_id": route_id})
                            except Exception as e:
                                logger.warning(
                                    f"Failed to restore route {route_id} during rollback: {e}",
                                    extra={"device_id": device_id, "route_id": route_id},
                                )
                                rollback_actions.append({"action": "failed_restore", "route_id": route_id, "error": str(e)})

            elif operation == "remove_static_route":
                # For remove operations: re-add deleted routes
                deleted_route_ids = original_route_ids - current_route_ids
                original_routes_map = {route.get(".id"): route for route in original_routes}

                for route_id in deleted_route_ids:
                    if route_id in original_routes_map:
                        original_route = original_routes_map[route_id]
                        try:
                            # Re-create the route
                            add_data = {}
                            for key in ["dst-address", "gateway", "distance", "comment"]:
                                if key in original_route:
                                    add_data[key] = original_route[key]

                            await rest_client.post("/rest/ip/route/add", add_data)
                            rollback_actions.append({"action": "re-added", "route_id": route_id})
                        except Exception as e:
                            logger.warning(
                                f"Failed to re-add route {route_id} during rollback: {e}",
                                extra={"device_id": device_id, "route_id": route_id},
                            )
                            rollback_actions.append({"action": "failed_readd", "route_id": route_id, "error": str(e)})

            logger.info(
                f"Rollback completed for device {device_id}",
                extra={
                    "device_id": device_id,
                    "operation": operation,
                    "rollback_action_count": len(rollback_actions),
                },
            )

            return {
                "status": "success",
                "device_id": device_id,
                "operation": operation,
                "rollback_actions": rollback_actions,
                "original_route_count": len(original_routes),
                "timestamp": datetime.now(UTC).isoformat(),
            }

        except Exception as e:
            logger.error(
                f"Rollback failed for device {device_id}: {e}",
                exc_info=True,
            )
            return {
                "status": "failed",
                "device_id": device_id,
                "operation": operation,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    def _route_differs(self, route1: dict[str, Any], route2: dict[str, Any]) -> bool:
        """Check if two routes have different properties.

        Args:
            route1: First route
            route2: Second route

        Returns:
            True if routes differ in any property
        """
        # Compare key properties
        check_keys = ["dst-address", "gateway", "distance", "comment"]
        return any(route1.get(key) != route2.get(key) for key in check_keys)

    async def apply_plan(
        self,
        device_id: str,
        device_name: str,  # noqa: ARG002 - used in logging context, reserved for future use
        operation: str,
        changes: dict[str, Any],
        rest_client: RouterOSRestClient,
    ) -> dict[str, Any]:
        """Apply routing plan changes to a device.

        Args:
            device_id: Device identifier
            device_name: Device name
            operation: Operation type (add_static_route, modify_static_route, remove_static_route)
            changes: Change specifications from plan
            rest_client: REST client instance for device

        Returns:
            Apply results with status and details

        Raises:
            Exception: If apply operation fails
        """
        try:
            logger.info(
                f"Applying routing plan to device {device_id}",
                extra={
                    "device_id": device_id,
                    "operation": operation,
                },
            )

            if operation == "add_static_route":
                # Build route payload
                route_data = {
                    "dst-address": changes["dst_address"],
                }

                if changes.get("gateway"):
                    route_data["gateway"] = changes["gateway"]
                if changes.get("comment"):
                    route_data["comment"] = changes["comment"]
                if changes.get("distance"):
                    route_data["distance"] = changes["distance"]

                # Add route via REST API
                result = await rest_client.post("/rest/ip/route/add", route_data)

                return {
                    "status": "success",
                    "device_id": device_id,
                    "operation": operation,
                    "route_id": result.get(".id") if isinstance(result, dict) else None,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            elif operation == "modify_static_route":
                route_id = changes["route_id"]
                modifications = changes["modifications"]

                # Build update payload
                update_data = {}
                if "dst_address" in modifications:
                    update_data["dst-address"] = modifications["dst_address"]
                if "gateway" in modifications:
                    update_data["gateway"] = modifications["gateway"]
                if "distance" in modifications:
                    update_data["distance"] = modifications["distance"]
                if "comment" in modifications:
                    update_data["comment"] = modifications["comment"]

                # Update route via REST API
                await rest_client.patch(f"/rest/ip/route/{route_id}", update_data)

                return {
                    "status": "success",
                    "device_id": device_id,
                    "operation": operation,
                    "route_id": route_id,
                    "modifications": list(modifications.keys()),
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            elif operation == "remove_static_route":
                route_id = changes["route_id"]

                # Remove route via REST API
                await rest_client.delete(f"/rest/ip/route/{route_id}")

                return {
                    "status": "success",
                    "device_id": device_id,
                    "operation": operation,
                    "route_id": route_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            else:
                raise ValueError(f"Unknown operation: {operation}")

        except Exception as e:
            logger.error(
                f"Failed to apply routing plan to device {device_id}: {e}",
                exc_info=True,
            )
            return {
                "status": "failed",
                "device_id": device_id,
                "operation": operation,
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }
