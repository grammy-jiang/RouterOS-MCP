"""Safety guardrails for high-risk operations.

This module provides safety checks and validation for write operations:
- Management path protection (prevent breaking connectivity)
- MCP-owned list validation (firewall address lists)
- Environment-aware write validation
- Dry-run support utilities
"""

import ipaddress
import logging
from typing import Any

logger = logging.getLogger(__name__)


class UnsafeOperationError(Exception):
    """Raised when an operation would violate safety constraints."""

    pass


class ManagementPathProtectionError(UnsafeOperationError):
    """Raised when an operation would break management connectivity."""

    pass


class InvalidListNameError(UnsafeOperationError):
    """Raised when attempting to modify a non-MCP-owned address list."""

    pass


def validate_mcp_owned_list(list_name: str) -> None:
    """Validate that an address list is MCP-owned (starts with 'mcp-').

    Args:
        list_name: Firewall address list name

    Raises:
        InvalidListNameError: If list name doesn't start with 'mcp-'

    Example:
        validate_mcp_owned_list("mcp-managed-hosts")  # OK
        validate_mcp_owned_list("blacklist")  # Raises error
    """
    if not list_name.startswith("mcp-"):
        raise InvalidListNameError(
            f"Address list '{list_name}' is not MCP-owned. "
            "Only lists starting with 'mcp-' can be modified. "
            "This prevents accidental modification of system or user-managed lists."
        )

    logger.debug(f"List name validation passed: {list_name}")


def check_management_ip_protection(
    device_management_address: str,
    ip_to_remove: str,
) -> None:
    """Check if removing an IP would break management connectivity.

    Args:
        device_management_address: Device's management address (host:port)
        ip_to_remove: IP address being removed (CIDR format)

    Raises:
        ManagementPathProtectionError: If IP removal would break management

    Example:
        check_management_ip_protection(
            "192.168.1.1:443",
            "192.168.1.1/24"  # Would raise error
        )
    """
    # Extract host from management address (remove port)
    mgmt_host = device_management_address.split(":")[0]

    try:
        # Parse management IP
        mgmt_ip = ipaddress.ip_address(mgmt_host)

        # Parse IP being removed (CIDR notation)
        ip_network = ipaddress.ip_network(ip_to_remove, strict=False)

        # Check if management IP is in the network being removed
        if mgmt_ip in ip_network:
            raise ManagementPathProtectionError(
                f"Cannot remove IP address {ip_to_remove} - it contains the management IP "
                f"{mgmt_host} used to connect to this device. "
                "Removing this IP would break management connectivity."
            )

        logger.debug(
            f"Management IP protection passed: {mgmt_host} not in {ip_to_remove}"
        )

    except ValueError as e:
        # Invalid IP format - let it through, will fail at RouterOS
        logger.warning(
            f"Could not parse IPs for management protection check: {e}",
            extra={"mgmt_host": mgmt_host, "ip_to_remove": ip_to_remove},
        )


def validate_ip_address_format(address: str) -> None:
    """Validate IP address format (CIDR notation).

    Args:
        address: IP address in CIDR notation (e.g., "192.168.1.1/24")

    Raises:
        ValueError: If address format is invalid
    """
    try:
        ipaddress.ip_network(address, strict=False)
    except ValueError as e:
        raise ValueError(
            f"Invalid IP address format: {address}. "
            f"Expected CIDR notation (e.g., '192.168.1.1/24'). Error: {e}"
        ) from e


def check_ip_overlap(
    new_address: str,
    existing_addresses: list[dict[str, Any]],
    interface: str,
) -> None:
    """Check if a new IP address overlaps with existing addresses on the same interface.

    Args:
        new_address: New IP address in CIDR notation
        existing_addresses: List of existing address dicts with 'address' and 'interface'
        interface: Target interface name

    Raises:
        UnsafeOperationError: If address overlaps with existing address on same interface
    """
    try:
        new_network = ipaddress.ip_network(new_address, strict=False)

        for addr in existing_addresses:
            # Only check addresses on the same interface
            if addr.get("interface") != interface:
                continue

            # Skip dynamic addresses
            if addr.get("dynamic", False):
                continue

            existing_addr = addr.get("address", "")
            if not existing_addr:
                continue

            try:
                existing_network = ipaddress.ip_network(existing_addr, strict=False)

                # Check for overlap
                if new_network.overlaps(existing_network):
                    raise UnsafeOperationError(
                        f"IP address {new_address} overlaps with existing address "
                        f"{existing_addr} on interface '{interface}'. "
                        "Overlapping addresses on the same interface can cause routing issues."
                    )

            except ValueError:
                # Invalid existing address format - skip
                logger.warning(
                    f"Could not parse existing address: {existing_addr}",
                    extra={"address_id": addr.get("id")},
                )
                continue

        logger.debug(
            f"IP overlap check passed for {new_address} on {interface}",
            extra={"existing_count": len(existing_addresses)},
        )

    except ValueError as e:
        raise ValueError(
            f"Invalid IP address format: {new_address}. Error: {e}"
        ) from e


def validate_dns_servers(servers: list[str]) -> None:
    """Validate DNS server addresses.

    Args:
        servers: List of DNS server addresses (IP or hostname)

    Raises:
        ValueError: If any server address is invalid
    """
    if not servers:
        raise ValueError("DNS server list cannot be empty")

    if len(servers) > 10:
        raise ValueError(
            f"Too many DNS servers ({len(servers)}). Maximum 10 servers allowed."
        )

    for server in servers:
        if not server or not server.strip():
            raise ValueError("DNS server address cannot be empty")

        # Basic validation - try to parse as IP or accept as hostname
        try:
            ipaddress.ip_address(server)
        except ValueError:
            # Not an IP, check if it's a valid hostname format
            if not server.replace(".", "").replace("-", "").isalnum():
                raise ValueError(
                    f"Invalid DNS server address: {server}. "
                    "Must be a valid IP address or hostname."
                ) from None

    logger.debug(f"DNS server validation passed: {len(servers)} servers")


def validate_ntp_servers(servers: list[str]) -> None:
    """Validate NTP server addresses.

    Args:
        servers: List of NTP server addresses (IP or hostname)

    Raises:
        ValueError: If any server address is invalid
    """
    if not servers:
        raise ValueError("NTP server list cannot be empty")

    if len(servers) > 10:
        raise ValueError(
            f"Too many NTP servers ({len(servers)}). Maximum 10 servers allowed."
        )

    for server in servers:
        if not server or not server.strip():
            raise ValueError("NTP server address cannot be empty")

        # Basic validation - try to parse as IP or accept as hostname
        try:
            ipaddress.ip_address(server)
        except ValueError:
            # Not an IP, check if it's a valid hostname format
            if not server.replace(".", "").replace("-", "").isalnum():
                raise ValueError(
                    f"Invalid NTP server address: {server}. "
                    "Must be a valid IP address or hostname."
                ) from None

    logger.debug(f"NTP server validation passed: {len(servers)} servers")


def create_dry_run_response(
    operation: str,
    device_id: str,
    planned_changes: dict[str, Any],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    """Create standardized dry-run response.

    Args:
        operation: Operation name (e.g., "dns/update-servers")
        device_id: Device identifier
        planned_changes: Dictionary describing planned changes
        warnings: Optional list of warning messages

    Returns:
        Standardized dry-run response dictionary
    """
    return {
        "device_id": device_id,
        "changed": False,
        "dry_run": True,
        "operation": operation,
        "planned_changes": planned_changes,
        "warnings": warnings or [],
    }
