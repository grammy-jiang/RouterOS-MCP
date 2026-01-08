#!/usr/bin/env python3
"""Example: RouterOS Version Detection

This example demonstrates how to use the version detection feature
to query RouterOS version and make version-aware decisions.

Phase 4 feature for v6/v7 compatibility.
"""

import asyncio

from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient


async def main():
    """Demonstrate version detection and comparison."""
    # Create REST client
    client = RouterOSRestClient(
        host="192.168.1.1",  # Replace with your RouterOS device IP
        port=443,
        username="admin",  # Replace with your credentials
        password="your-password",
        verify_ssl=False,  # Set True for production with valid certs
    )

    try:
        # Detect RouterOS version
        print("Detecting RouterOS version...")
        version = await client.detect_version()

        if version:
            print(f"✓ Detected RouterOS version: {version}")

            # Example: Make version-aware decisions
            if version.startswith("7."):
                print("  → Device is running RouterOS v7.x")
                print("  → Using v7 REST API endpoints")
            elif version.startswith("6."):
                print("  → Device is running RouterOS v6.x")
                print("  → Using v6-compatible endpoints")
            else:
                print(f"  → Unknown version format: {version}")

            # Example: Check for specific version requirements
            # Note: For this to work, you'd need a Device model instance
            # This is just for demonstration of the API
            print("\nVersion comparison examples:")
            print(f"  Version {version} >= 7.10: {compare_version(version, '7.10')}")
            print(f"  Version {version} >= 6.48: {compare_version(version, '6.48')}")
            print(f"  Version {version} >= 7.11: {compare_version(version, '7.11')}")

        else:
            print("✗ Could not detect RouterOS version")
            print("  (Device may be too old or endpoint not available)")

    except Exception as e:
        print(f"✗ Error: {e}")

    finally:
        # Clean up
        await client.close()


def compare_version(current: str, target: str) -> bool:
    """Simple version comparison (matches Device.version_ge logic)."""
    def parse_version(v: str) -> tuple[list[int], str]:
        parts = v.split("-", 1)
        version_str = parts[0]
        suffix = parts[1] if len(parts) > 1 else ""

        numeric_parts = []
        for part in version_str.split("."):
            try:
                numeric_parts.append(int(part))
            except ValueError:
                break

        return numeric_parts, suffix

    current_parts, current_suffix = parse_version(current)
    target_parts, target_suffix = parse_version(target)

    for i in range(max(len(current_parts), len(target_parts))):
        current_val = current_parts[i] if i < len(current_parts) else 0
        target_val = target_parts[i] if i < len(target_parts) else 0

        if current_val > target_val:
            return True
        elif current_val < target_val:
            return False

    if current_suffix and not target_suffix:
        return False

    return True


if __name__ == "__main__":
    # Run the example
    asyncio.run(main())
