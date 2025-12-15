
"""Check reachability of a registered device via DeviceService.

Purpose:
    Quick developer sanity check that the DB is reachable, the device exists,
    and the RouterOS endpoint responds to a lightweight connectivity probe.

When to use:
    - After adding a device (e.g., via scripts/add_device.py)
    - During local development to verify settings and networking

Usage:
    python scripts/test_connectivity.py <device_id> [--config config/lab.yaml]

Exit codes:
    0 on success; non-zero if the device is unreachable or on errors.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routeros_mcp.config import load_settings_from_file
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import get_session_factory

async def check_device(device_id: str, config_path: str = "config/lab.yaml") -> None:
    """Run a connectivity check for a device by ID using provided settings file."""
    settings = load_settings_from_file(config_path)
    session_factory = get_session_factory(settings)
    await session_factory.init()

    async with session_factory.session() as session:
        service = DeviceService(session, settings)
        print(f"Checking connectivity for {device_id}...")
        reachable, meta = await service.check_connectivity(device_id)
        print(f"Reachable: {reachable}")
        print(f"Meta: {meta}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check device connectivity")
    parser.add_argument("device_id", help="Device ID to check")
    parser.add_argument("--config", default="config/lab.yaml", help="Path to config file")
    args = parser.parse_args()

    try:
        asyncio.run(check_device(args.device_id, args.config))
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
