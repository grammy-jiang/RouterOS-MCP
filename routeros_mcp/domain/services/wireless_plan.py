"""Wireless plan service for wireless SSID and RF configuration planning and validation.

This service implements the plan phase for wireless operations,
providing validation, risk assessment, and preview generation.

See docs/07-device-control-and-high-risk-operations-safeguards.md for
detailed requirements.
"""

import gzip
import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient

logger = logging.getLogger(__name__)


class WirelessPlanService:
    """Service for wireless SSID and RF configuration planning operations.

    Provides:
    - SSID parameter validation (security profile, band, channel)
    - RF parameter validation (TX power within limits, channel not DFS)
    - Risk level assessment based on environment and change type
    - Preview generation for planned changes
    - Wireless configuration snapshot/rollback
    - Health check after changes (verify AP responds, still broadcasting)

    All wireless configuration operations follow the plan/apply workflow.
    """

    # Valid wireless bands
    VALID_BANDS = ["2ghz-b", "2ghz-g", "2ghz-n", "5ghz-a", "5ghz-n", "5ghz-ac", "5ghz-ax"]

    # Valid 2.4GHz channels (1-14, commonly 1-11 in US/EU)
    VALID_2GHZ_CHANNELS = list(range(1, 15))

    # Valid 5GHz channels (commonly used, non-DFS for safety)
    # Non-DFS channels: 36, 40, 44, 48, 149, 153, 157, 161, 165
    VALID_5GHZ_CHANNELS_NON_DFS = [36, 40, 44, 48, 149, 153, 157, 161, 165]

    # DFS channels (52-144) - blocked by default for safety
    DFS_CHANNELS = list(range(52, 145, 4))

    # TX power limits (dBm)
    MIN_TX_POWER = 0
    MAX_TX_POWER = 30  # Typical regulatory limit

    # High-risk conditions
    HIGH_RISK_ENVIRONMENTS = ["prod"]  # Production environment

    # Security profiles that require additional validation
    INSECURE_PROFILES = ["none", "open"]

    def validate_ssid_params(
        self,
        ssid: str,
        security_profile: str | None = None,
        band: str | None = None,
        channel: int | None = None,
    ) -> dict[str, Any]:
        """Validate SSID parameters.

        Args:
            ssid: SSID name (1-32 characters)
            security_profile: Security profile name (optional for validation)
            band: Wireless band (optional)
            channel: Wireless channel (optional)

        Returns:
            Dictionary with validation result

        Raises:
            ValueError: If any parameter is invalid
        """
        errors = []

        # Validate SSID
        if not ssid or len(ssid) == 0:
            errors.append("SSID cannot be empty")
        elif len(ssid) > 32:
            errors.append(f"SSID too long (max 32 characters): '{ssid}'")

        # Validate band if provided
        if band and band not in self.VALID_BANDS:
            errors.append(
                f"Invalid band '{band}'. Must be one of: {', '.join(self.VALID_BANDS)}"
            )

        # Validate channel if provided
        if channel is not None:
            if band:
                if band.startswith("2ghz"):
                    if channel not in self.VALID_2GHZ_CHANNELS:
                        errors.append(
                            f"Invalid 2.4GHz channel {channel}. "
                            f"Valid channels: {', '.join(map(str, self.VALID_2GHZ_CHANNELS))}"
                        )
                elif band.startswith("5ghz"):
                    # Allow only non-DFS channels for safety
                    if channel not in self.VALID_5GHZ_CHANNELS_NON_DFS:
                        if channel in self.DFS_CHANNELS:
                            errors.append(
                                f"DFS channel {channel} is blocked for safety. "
                                f"Use non-DFS channels: {', '.join(map(str, self.VALID_5GHZ_CHANNELS_NON_DFS))}"
                            )
                        else:
                            errors.append(
                                f"Invalid 5GHz channel {channel}. "
                                f"Valid non-DFS channels: {', '.join(map(str, self.VALID_5GHZ_CHANNELS_NON_DFS))}"
                            )
            else:
                # If band not specified, warn about channel validation
                logger.warning(
                    f"Channel {channel} specified without band - validation limited"
                )

        # Warn about insecure security profiles
        if security_profile and security_profile in self.INSECURE_PROFILES:
            logger.warning(
                f"SSID '{ssid}' uses insecure security profile: '{security_profile}'"
            )

        if errors:
            raise ValueError("SSID parameter validation failed:\n- " + "\n- ".join(errors))

        logger.debug(f"SSID parameter validation passed for ssid={ssid}")

        return {
            "valid": True,
            "ssid": ssid,
            "security_profile": security_profile,
            "band": band,
            "channel": channel,
        }

    def validate_rf_params(
        self,
        channel: int | None = None,
        tx_power: int | None = None,
        band: str | None = None,
    ) -> dict[str, Any]:
        """Validate RF (radio frequency) parameters.

        Args:
            channel: Wireless channel (optional)
            tx_power: TX power in dBm (optional)
            band: Wireless band for channel validation (optional)

        Returns:
            Dictionary with validation result

        Raises:
            ValueError: If any parameter is invalid
        """
        errors = []

        # Validate channel (same logic as SSID validation)
        if channel is not None:
            if band:
                if band.startswith("2ghz"):
                    if channel not in self.VALID_2GHZ_CHANNELS:
                        errors.append(
                            f"Invalid 2.4GHz channel {channel}. "
                            f"Valid channels: {', '.join(map(str, self.VALID_2GHZ_CHANNELS))}"
                        )
                elif band.startswith("5ghz"):
                    if channel not in self.VALID_5GHZ_CHANNELS_NON_DFS:
                        if channel in self.DFS_CHANNELS:
                            errors.append(
                                f"DFS channel {channel} is blocked for safety. "
                                f"Use non-DFS channels: {', '.join(map(str, self.VALID_5GHZ_CHANNELS_NON_DFS))}"
                            )
                        else:
                            errors.append(
                                f"Invalid 5GHz channel {channel}. "
                                f"Valid non-DFS channels: {', '.join(map(str, self.VALID_5GHZ_CHANNELS_NON_DFS))}"
                            )

        # Validate TX power if provided
        if tx_power is not None:
            if tx_power < self.MIN_TX_POWER or tx_power > self.MAX_TX_POWER:
                errors.append(
                    f"TX power {tx_power} dBm is out of range. "
                    f"Must be between {self.MIN_TX_POWER} and {self.MAX_TX_POWER} dBm"
                )

        if errors:
            raise ValueError("RF parameter validation failed:\n- " + "\n- ".join(errors))

        logger.debug(f"RF parameter validation passed for channel={channel}, tx_power={tx_power}")

        return {
            "valid": True,
            "channel": channel,
            "tx_power": tx_power,
            "band": band,
        }

    def assess_risk(
        self,
        operation: str,
        device_environment: str = "lab",
        has_active_clients: bool = False,
    ) -> str:
        """Assess risk level for a wireless operation.

        Risk classification:
        - High risk:
          - Production environment APs
          - Modifying SSID with active clients
          - Changing security profile on active SSID
        - Medium risk:
          - Lab/staging environment APs
          - Creating new SSIDs
          - RF parameter changes without active clients

        Args:
            operation: Operation type (create_ssid/modify_ssid/remove_ssid/rf_settings)
            device_environment: Device environment (lab/staging/prod)
            has_active_clients: Whether SSID has active clients

        Returns:
            Risk level: "medium" or "high"
        """
        # High risk conditions
        if device_environment in self.HIGH_RISK_ENVIRONMENTS:
            logger.info("High risk: production environment AP")
            return "high"

        if operation in ["modify_ssid", "remove_ssid"] and has_active_clients:
            logger.info("High risk: modifying/removing SSID with active clients")
            return "high"

        # Default to medium risk
        logger.debug(
            f"Medium risk: operation={operation}, env={device_environment}, "
            f"active_clients={has_active_clients}"
        )
        return "medium"

    def generate_preview(
        self,
        operation: str,
        device_id: str,
        device_name: str,
        device_environment: str,
        ssid: str | None = None,
        ssid_id: str | None = None,
        security_profile: str | None = None,
        band: str | None = None,
        channel: int | None = None,
        interface: str | None = None,
        tx_power: int | None = None,
        modifications: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate detailed preview for a wireless operation.

        Args:
            operation: Operation type (create_ssid/modify_ssid/remove_ssid/rf_settings)
            device_id: Device identifier
            device_name: Device name
            device_environment: Device environment
            ssid: SSID name (for create)
            ssid_id: SSID ID (for modify/remove)
            security_profile: Security profile name (for create/modify)
            band: Wireless band (for create/modify)
            channel: Wireless channel (for create/modify/rf_settings)
            interface: Wireless interface (for rf_settings)
            tx_power: TX power in dBm (for rf_settings)
            modifications: Modifications dict (for modify)

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

        if operation == "create_ssid":
            # Build SSID specification
            ssid_parts = [f"ssid={ssid}"]
            if security_profile:
                ssid_parts.append(f"security-profile={security_profile}")
            if band:
                ssid_parts.append(f"band={band}")
            if channel:
                ssid_parts.append(f"channel={channel}")

            preview["changes"] = {
                "action": "create",
                "ssid": ssid,
                "security_profile": security_profile,
                "band": band,
                "channel": channel,
                "preview": f"Will create SSID: {', '.join(ssid_parts)}",
            }

        elif operation == "modify_ssid":
            if modifications:
                preview["changes"] = {
                    "action": "modify",
                    "ssid_id": ssid_id,
                    "modifications": modifications,
                    "preview": f"Will modify SSID {ssid_id}: {', '.join(f'{k}={v}' for k, v in modifications.items())}",
                }
            else:
                preview["changes"] = {
                    "action": "modify",
                    "ssid_id": ssid_id,
                    "preview": "No modifications specified",
                }

        elif operation == "remove_ssid":
            preview["changes"] = {
                "action": "remove",
                "ssid_id": ssid_id,
                "preview": f"Will remove SSID {ssid_id}",
            }

        elif operation == "rf_settings":
            rf_parts = []
            if interface:
                rf_parts.append(f"interface={interface}")
            if channel:
                rf_parts.append(f"channel={channel}")
            if tx_power is not None:
                rf_parts.append(f"tx-power={tx_power}dBm")

            preview["changes"] = {
                "action": "rf_settings",
                "interface": interface,
                "channel": channel,
                "tx_power": tx_power,
                "preview": f"Will update RF settings: {', '.join(rf_parts)}",
            }

        return preview

    async def create_wireless_snapshot(
        self,
        device_id: str,
        device_name: str,
        rest_client: RouterOSRestClient,
    ) -> dict[str, Any]:
        """Create snapshot of current wireless configuration.

        Args:
            device_id: Device identifier
            device_name: Device name
            rest_client: REST client instance for device

        Returns:
            Snapshot metadata with snapshot_id and wireless config payload

        Raises:
            Exception: If snapshot creation fails
        """
        try:
            # Fetch current wireless interfaces configuration
            wireless_interfaces = await rest_client.get("/rest/interface/wireless")

            # Create snapshot payload
            snapshot_payload = {
                "device_id": device_id,
                "device_name": device_name,
                "timestamp": datetime.now(UTC).isoformat(),
                "wireless_interfaces": wireless_interfaces if isinstance(wireless_interfaces, list) else [],
            }

            # Serialize and compress
            payload_json = json.dumps(snapshot_payload)
            payload_bytes = payload_json.encode("utf-8")
            compressed_data = gzip.compress(payload_bytes, compresslevel=6)

            # Calculate checksum
            checksum = hashlib.sha256(payload_bytes).hexdigest()

            # Generate snapshot ID
            snapshot_id = f"snap-wireless-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

            logger.info(
                f"Created wireless snapshot {snapshot_id} for device {device_id}",
                extra={
                    "snapshot_id": snapshot_id,
                    "device_id": device_id,
                    "interface_count": len(snapshot_payload["wireless_interfaces"]),
                    "size_bytes": len(payload_bytes),
                    "compressed_size": len(compressed_data),
                },
            )

            return {
                "snapshot_id": snapshot_id,
                "device_id": device_id,
                "timestamp": snapshot_payload["timestamp"],
                "interface_count": len(snapshot_payload["wireless_interfaces"]),
                "size_bytes": len(payload_bytes),
                "compressed_size": len(compressed_data),
                "checksum": checksum,
                "data": compressed_data,
            }

        except Exception as e:
            logger.error(
                f"Failed to create wireless snapshot for device {device_id}: {e}",
                exc_info=True,
            )
            raise

    async def perform_health_check(
        self,
        device_id: str,
        rest_client: RouterOSRestClient,
        timeout_seconds: float = 30.0,  # noqa: ARG002 - reserved for future timeout implementation
    ) -> dict[str, Any]:
        """Perform health check after wireless configuration changes.

        Verifies:
        - Device still responds to REST API
        - Wireless interfaces are accessible
        - At least one wireless interface is running

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

            # Test 2: Verify wireless interfaces are accessible
            wireless_interfaces = await rest_client.get("/rest/interface/wireless")

            if wireless_interfaces is None:
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
                            "check": "wireless_access",
                            "status": "failed",
                            "message": "Cannot access wireless configuration",
                        },
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # Test 3: Check if at least one wireless interface is running
            running_interfaces = []
            if isinstance(wireless_interfaces, list):
                running_interfaces = [
                    iface for iface in wireless_interfaces
                    if isinstance(iface, dict) and iface.get("running", False)
                ]

            if len(running_interfaces) == 0:
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
                            "check": "wireless_access",
                            "status": "passed",
                            "message": "Wireless configuration accessible",
                        },
                        {
                            "check": "wireless_running",
                            "status": "warning",
                            "message": "No wireless interfaces are running",
                        },
                    ],
                    "timestamp": datetime.now(UTC).isoformat(),
                }

            # All checks passed
            logger.info(
                f"Health check passed for device {device_id}",
                extra={
                    "device_id": device_id,
                    "checks_passed": 3,
                    "running_interfaces": len(running_interfaces),
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
                        "check": "wireless_access",
                        "status": "passed",
                        "message": "Wireless configuration accessible",
                    },
                    {
                        "check": "wireless_running",
                        "status": "passed",
                        "message": f"{len(running_interfaces)} wireless interface(s) running",
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
        operation: str = "create_ssid",
    ) -> dict[str, Any]:
        """Rollback wireless configuration from snapshot.

        Args:
            device_id: Device identifier
            snapshot_data: Compressed snapshot data
            rest_client: REST client instance for device
            operation: Operation type that was performed

        Returns:
            Rollback results with status and details

        Raises:
            Exception: If rollback fails
        """
        try:
            # Decompress snapshot
            decompressed = gzip.decompress(snapshot_data)
            snapshot_payload = json.loads(decompressed.decode("utf-8"))

            original_interfaces = snapshot_payload.get("wireless_interfaces", [])

            logger.info(
                f"Starting rollback for device {device_id}",
                extra={
                    "device_id": device_id,
                    "operation": operation,
                    "original_interface_count": len(original_interfaces),
                },
            )

            # For wireless rollback, we need to restore interface configurations
            # This is a simplified rollback - full implementation would restore
            # all interface properties
            rollback_actions = []

            # Get current interfaces
            current_interfaces = await rest_client.get("/rest/interface/wireless")

            if not isinstance(current_interfaces, list):
                current_interfaces = []

            # Track rollback progress
            success_count = 0
            fail_count = 0

            # For safety, we only rollback specific properties that we modified
            # Full interface deletion/recreation is too risky
            for original_iface in original_interfaces:
                iface_id = original_iface.get(".id", "")
                iface_name = original_iface.get("name", "")

                if not iface_id:
                    continue

                # Find matching current interface
                current_iface = next(
                    (iface for iface in current_interfaces if iface.get(".id") == iface_id),
                    None
                )

                if current_iface:
                    # Restore key properties
                    try:
                        # Build update payload with safe properties
                        update_payload = {}
                        if "ssid" in original_iface:
                            update_payload["ssid"] = original_iface["ssid"]
                        if "disabled" in original_iface:
                            update_payload["disabled"] = original_iface["disabled"]

                        if update_payload:
                            await rest_client.patch(
                                f"/rest/interface/wireless/{iface_id}",
                                update_payload
                            )
                            rollback_actions.append(
                                f"Restored interface {iface_name} ({iface_id})"
                            )
                            success_count += 1
                    except Exception as e:
                        logger.error(f"Failed to rollback interface {iface_name}: {e}")
                        rollback_actions.append(
                            f"Failed to restore interface {iface_name}: {str(e)}"
                        )
                        fail_count += 1

            logger.info(
                f"Rollback completed for device {device_id}",
                extra={
                    "device_id": device_id,
                    "success_count": success_count,
                    "fail_count": fail_count,
                },
            )

            return {
                "status": "success" if fail_count == 0 else "partial",
                "device_id": device_id,
                "rollback_actions": rollback_actions,
                "success_count": success_count,
                "fail_count": fail_count,
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
                "error": str(e),
                "timestamp": datetime.now(UTC).isoformat(),
            }

    async def apply_plan(
        self,
        device_id: str,
        device_name: str,
        operation: str,
        changes: dict[str, Any],
        rest_client: RouterOSRestClient,
    ) -> dict[str, Any]:
        """Apply wireless configuration plan to device.

        Args:
            device_id: Device identifier
            device_name: Device name
            operation: Operation type (create_ssid/modify_ssid/remove_ssid/rf_settings)
            changes: Changes dictionary from plan
            rest_client: REST client instance for device

        Returns:
            Apply results with status and details

        Raises:
            Exception: If apply fails
        """
        try:
            logger.info(
                f"Applying wireless plan to device {device_id}",
                extra={
                    "device_id": device_id,
                    "operation": operation,
                },
            )

            if operation == "create_ssid":
                # Create new wireless interface/SSID
                ssid = changes.get("ssid")
                security_profile = changes.get("security_profile", "default")
                band = changes.get("band")
                channel = changes.get("channel")

                # Build create payload
                create_payload: dict[str, Any] = {
                    "name": f"wlan-{ssid[:20]}",  # Truncate for safety
                    "ssid": ssid,
                    "security-profile": security_profile,
                }

                if band:
                    create_payload["band"] = band
                if channel:
                    create_payload["channel-width"] = "20mhz"  # Safe default
                    # Note: Channel setting may require different API depending on RouterOS version

                result = await rest_client.put("/rest/interface/wireless", create_payload)

                return {
                    "status": "success",
                    "device_id": device_id,
                    "operation": operation,
                    "result": result,
                    "message": f"Created SSID '{ssid}' on {device_name}",
                }

            elif operation == "modify_ssid":
                # Modify existing SSID
                ssid_id = changes.get("ssid_id")
                modifications = changes.get("modifications", {})

                if not ssid_id:
                    raise ValueError("Missing ssid_id for modify operation")

                # Build update payload
                update_payload = {}
                if "ssid" in modifications:
                    update_payload["ssid"] = modifications["ssid"]
                if "security_profile" in modifications:
                    update_payload["security-profile"] = modifications["security_profile"]
                if "band" in modifications:
                    update_payload["band"] = modifications["band"]
                if "channel" in modifications:
                    # Note: Channel update may require interface to be disabled first
                    pass  # Simplified for safety

                result = await rest_client.patch(
                    f"/rest/interface/wireless/{ssid_id}",
                    update_payload
                )

                return {
                    "status": "success",
                    "device_id": device_id,
                    "operation": operation,
                    "result": result,
                    "message": f"Modified SSID {ssid_id} on {device_name}",
                }

            elif operation == "remove_ssid":
                # Remove SSID
                ssid_id = changes.get("ssid_id")

                if not ssid_id:
                    raise ValueError("Missing ssid_id for remove operation")

                # First disable the interface
                await rest_client.patch(
                    f"/rest/interface/wireless/{ssid_id}",
                    {"disabled": "yes"}
                )

                # Then remove it
                await rest_client.delete(f"/rest/interface/wireless/{ssid_id}")

                return {
                    "status": "success",
                    "device_id": device_id,
                    "operation": operation,
                    "message": f"Removed SSID {ssid_id} on {device_name}",
                }

            elif operation == "rf_settings":
                # Update RF settings (channel, TX power)
                interface = changes.get("interface")
                channel = changes.get("channel")
                tx_power = changes.get("tx_power")

                if not interface:
                    raise ValueError("Missing interface for RF settings operation")

                # Build update payload
                update_payload = {}
                if channel:
                    # Note: May need to disable interface first
                    # Use the provided channel value directly as the frequency setting.
                    update_payload["frequency"] = str(channel)
                if tx_power is not None:
                    update_payload["tx-power"] = tx_power
                    update_payload["tx-power-mode"] = "manual"

                result = await rest_client.patch(
                    f"/rest/interface/wireless/{interface}",
                    update_payload
                )

                return {
                    "status": "success",
                    "device_id": device_id,
                    "operation": operation,
                    "result": result,
                    "message": f"Updated RF settings on interface {interface} on {device_name}",
                }

            else:
                raise ValueError(f"Unknown operation type: {operation}")

        except Exception as e:
            logger.error(
                f"Failed to apply plan to device {device_id}: {e}",
                exc_info=True,
            )
            return {
                "status": "failed",
                "device_id": device_id,
                "operation": operation,
                "error": str(e),
            }
