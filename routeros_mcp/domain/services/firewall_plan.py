"""Firewall plan service for firewall rule planning and validation.

This service implements the plan phase for firewall rule operations,
providing validation, risk assessment, and preview generation.

See docs/07-device-control-and-high-risk-operations-safeguards.md for
detailed requirements.
"""

import ipaddress
import logging
from typing import Any

logger = logging.getLogger(__name__)


class FirewallPlanService:
    """Service for firewall rule planning operations.

    Provides:
    - Rule parameter validation
    - Risk level assessment based on chain and action
    - Preview generation for planned changes

    All firewall rule operations follow the plan/apply workflow.
    """

    # Valid firewall chains
    VALID_CHAINS = ["input", "forward", "output"]

    # Valid firewall actions
    VALID_ACTIONS = ["accept", "drop", "reject", "jump", "return", "passthrough", "log"]

    # Valid protocols
    VALID_PROTOCOLS = ["tcp", "udp", "icmp", "gre", "esp", "ah", "ipip", "ipsec-ah", "ipsec-esp"]

    # High-risk conditions for risk assessment
    HIGH_RISK_CHAIN = "input"  # Input chain affects device management
    HIGH_RISK_ACTIONS = ["reject"]  # More aggressive than drop
    HIGH_RISK_ENVIRONMENTS = ["prod"]  # Production environment

    def validate_rule_params(
        self,
        chain: str,
        action: str,
        src_address: str | None = None,
        dst_address: str | None = None,
        protocol: str | None = None,
        dst_port: str | None = None,
    ) -> dict[str, Any]:
        """Validate firewall rule parameters.

        Args:
            chain: Firewall chain (input/forward/output)
            action: Rule action (accept/drop/reject/etc.)
            src_address: Optional source address (IP or CIDR)
            dst_address: Optional destination address (IP or CIDR)
            protocol: Optional protocol (tcp/udp/icmp/etc.)
            dst_port: Optional destination port (single port or range)

        Returns:
            Dictionary with validation result

        Raises:
            ValueError: If any parameter is invalid
        """
        errors = []

        # Validate chain
        if chain not in self.VALID_CHAINS:
            errors.append(
                f"Invalid chain '{chain}'. Must be one of: {', '.join(self.VALID_CHAINS)}"
            )

        # Validate action
        if action not in self.VALID_ACTIONS:
            errors.append(
                f"Invalid action '{action}'. Must be one of: {', '.join(self.VALID_ACTIONS)}"
            )

        # Validate IP addresses if provided
        if src_address:
            try:
                ipaddress.ip_network(src_address, strict=False)
            except ValueError as e:
                errors.append(f"Invalid source address '{src_address}': {e}")

        if dst_address:
            try:
                ipaddress.ip_network(dst_address, strict=False)
            except ValueError as e:
                errors.append(f"Invalid destination address '{dst_address}': {e}")

        # Validate protocol if provided
        if protocol and protocol not in self.VALID_PROTOCOLS:
            errors.append(
                f"Invalid protocol '{protocol}'. Must be one of: {', '.join(self.VALID_PROTOCOLS)}"
            )

        # Validate destination port if provided
        if dst_port and not self._validate_port(dst_port):
            errors.append(
                f"Invalid destination port '{dst_port}'. Must be a number (1-65535) or range (e.g., '8000-9000')"
            )

        if errors:
            raise ValueError("Rule parameter validation failed:\n- " + "\n- ".join(errors))

        logger.debug(f"Rule parameter validation passed for chain={chain}, action={action}")

        return {
            "valid": True,
            "chain": chain,
            "action": action,
            "src_address": src_address,
            "dst_address": dst_address,
            "protocol": protocol,
            "dst_port": dst_port,
        }

    def _validate_port(self, port: str) -> bool:
        """Validate port number or port range.

        Args:
            port: Port number or range (e.g., "443" or "8000-9000")

        Returns:
            True if valid, False otherwise
        """
        try:
            # Check for range
            if "-" in port:
                start, end = port.split("-", 1)
                start_port = int(start)
                end_port = int(end)
                return 1 <= start_port <= 65535 and 1 <= end_port <= 65535 and start_port <= end_port
            else:
                port_num = int(port)
                return 1 <= port_num <= 65535
        except (ValueError, AttributeError):
            return False

    def assess_risk(
        self,
        chain: str,
        action: str,
        device_environment: str = "lab",
    ) -> str:
        """Assess risk level for a firewall rule operation.

        Risk classification:
        - High risk:
          - Rules in input chain (affects device management)
          - Action=reject (more aggressive than drop)
          - Production environment
        - Medium risk:
          - Rules in forward/output chains
          - Action=accept/drop
          - Lab/staging environments

        Args:
            chain: Firewall chain
            action: Rule action
            device_environment: Device environment (lab/staging/prod)

        Returns:
            Risk level: "medium" or "high"
        """
        # High risk conditions
        if chain == self.HIGH_RISK_CHAIN:
            logger.info("High risk: input chain affects device management")
            return "high"

        if action in self.HIGH_RISK_ACTIONS:
            logger.info("High risk: reject action is more aggressive")
            return "high"

        if device_environment in self.HIGH_RISK_ENVIRONMENTS:
            logger.info("High risk: production environment")
            return "high"

        # Default to medium risk
        logger.debug(f"Medium risk: chain={chain}, action={action}, env={device_environment}")
        return "medium"

    def generate_preview(
        self,
        operation: str,
        device_id: str,
        device_name: str,
        device_environment: str,
        chain: str,
        action: str,
        src_address: str | None = None,
        dst_address: str | None = None,
        protocol: str | None = None,
        dst_port: str | None = None,
        comment: str | None = None,
        rule_id: str | None = None,
        modifications: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate detailed preview for a firewall rule operation.

        Args:
            operation: Operation type (add_rule/modify_rule/remove_rule)
            device_id: Device identifier
            device_name: Device name
            device_environment: Device environment
            chain: Firewall chain
            action: Rule action
            src_address: Source address (for add/modify)
            dst_address: Destination address (for add/modify)
            protocol: Protocol (for add/modify)
            dst_port: Destination port (for add/modify)
            comment: Rule comment (for add/modify)
            rule_id: Rule ID (for modify/remove)
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

        if operation == "add_firewall_rule":
            # Build rule specification
            rule_parts = [
                f"chain={chain}",
                f"action={action}",
            ]
            if src_address:
                rule_parts.append(f"src-address={src_address}")
            if dst_address:
                rule_parts.append(f"dst-address={dst_address}")
            if protocol:
                rule_parts.append(f"protocol={protocol}")
            if dst_port:
                rule_parts.append(f"dst-port={dst_port}")
            if comment:
                rule_parts.append(f"comment={comment}")

            rule_spec = " ".join(rule_parts)

            preview["preview"] = {
                "operation": "add_firewall_rule",
                "chain": chain,
                "position": "auto",
                "rule_spec": rule_spec,
                "estimated_impact": "Low - rule added to end of chain, existing connections unaffected",
            }

        elif operation == "modify_firewall_rule":
            preview["preview"] = {
                "operation": "modify_firewall_rule",
                "rule_id": rule_id,
                "chain": chain,
                "modifications": modifications or {},
                "estimated_impact": "Medium - existing rule modified, may affect active connections",
            }

        elif operation == "remove_firewall_rule":
            preview["preview"] = {
                "operation": "remove_firewall_rule",
                "rule_id": rule_id,
                "chain": chain,
                "estimated_impact": "Medium - rule removal may allow previously blocked traffic",
            }

        logger.debug(f"Generated preview for {operation} on device {device_id}")

        return preview
