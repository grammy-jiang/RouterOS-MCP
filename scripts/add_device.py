#!/usr/bin/env python3
"""Add a new RouterOS device to the MCP database (developer utility).

**DEPRECATED**: This script is deprecated. Use the new admin CLI instead:

    python -m routeros_mcp.cli.admin device add --help

Purpose:
    Convenience CLI for quickly registering a device and its REST credential in the
    MCP database using the same config precedence as the main app. Intended for
    development and lab setups; usable in staging/prod with proper RBAC and audit.

When to use:
    - Lab onboarding of test devices
    - Initial seeding of devices in a fresh environment
    - Quick demos or e2e tests where a device and REST credential are required

Safety notes:
    - Credentials are stored encrypted-at-rest (see docs/02 and docs/18). Ensure an encryption key
      is configured via environment or settings in non-lab environments.
    - For production, prefer audited admin APIs and change plans when available.

Requirements:
    - Python 3.11+
    - A valid config file (YAML/TOML) passed via --config
    - Optional: ``sshpass`` binary if you want automatic identity discovery via SSH

Parameters:
    --config: Path to config file (required)
    --id: Device ID (UUID or string). If omitted and SSH identity discovery succeeds, a UUID is generated
    --name: Human-friendly device name. If omitted, script tries to fetch RouterOS identity via SSH
    --ip: Management IP (required)
    --port: REST port (default 443)
    --username / --password: REST API credentials (required)
    --tags: JSON object of tags (e.g., '{"site":"home"}')
    --allow-advanced-writes / --allow-professional-workflows: Capability flags

Exit codes:
    0 on success; non-zero on validation or connection errors.

Examples:
    python scripts/add_device.py --config config/lab.yaml --id dev-lab-01 \
        --name "Router Lab 01" --ip 192.168.1.1 --port 443 \
        --username admin --password secret

    # With optional flags:
    python scripts/add_device.py --config config/lab.yaml --id dev-lab-01 \
        --name "Router Lab 01" --ip 192.168.1.1 \
        --username admin --password secret \
        --tags '{"site": "home", "role": "core"}' \
        --allow-advanced-writes --allow-professional-workflows
"""

import argparse
import asyncio
import json
import subprocess
import sys
import uuid
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routeros_mcp.config import Settings, load_settings_from_file
from routeros_mcp.domain.models import CredentialCreate, DeviceCreate
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.db.session import get_session_factory


async def add_device(
    settings: Settings,
    device_id: str,
    name: str,
    ip: str,
    port: int,
    username: str,
    password: str,
    tags: dict[str, str] | None = None,
    allow_advanced_writes: bool = False,
    allow_professional_workflows: bool = False,
) -> None:
    """Add a new device to the MCP database."""
    session_factory = get_session_factory(settings)

    # Initialize the session manager before use
    await session_factory.init()

    async with session_factory.session() as session:
        service = DeviceService(session, settings)

        # Register device
        device_data = DeviceCreate(
            id=device_id,
            name=name,
            management_ip=ip,
            management_port=port,
            environment=settings.environment,  # Use current environment from config
            tags=tags or {},
            allow_advanced_writes=allow_advanced_writes,
            allow_professional_workflows=allow_professional_workflows,
        )

        device = await service.register_device(device_data)
        print(f"✅ Device registered: {device.id} ({device.name})")
        print(f"   IP: {device.management_ip}")
        print(f"   Port: {device.management_port}")
        print(f"   Environment: {device.environment}")
        print(f"   Status: {device.status}")

        # Add credentials
        credential_data = CredentialCreate(
            device_id=device_id,
            credential_type="rest",
            username=username,
            password=password,
        )

        await service.add_credential(credential_data)
        print(f"✅ Credentials added for user: {username}")

        print(f"\n🎉 Device '{device_id}' is ready to use!")
        print("   Try: mcp_routeros-mcp_list_devices or mcp_routeros-mcp_check_connectivity")


def main() -> None:
    # Print deprecation warning
    print("=" * 80)
    print("WARNING: This script is deprecated!")
    print("=" * 80)
    print()
    print("Please use the new admin CLI instead:")
    print()
    print("  python -m routeros_mcp.cli.admin device add --help")
    print()
    print("Example:")
    print("  python -m routeros_mcp.cli.admin --config config/lab.yaml device add \\")
    print("      --id dev-lab-01 --name 'Router Lab 01' \\")
    print("      --ip 192.168.1.1 --username admin --password secret")
    print()
    print("=" * 80)
    print()
    parser = argparse.ArgumentParser(
        description="Add a new device to the RouterOS MCP server (DEPRECATED - use admin CLI)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage (requires --config):
  python scripts/add_device.py --config config/lab.yaml \\
      --id dev-lab-01 --name "Router Lab 01" \\
      --ip 192.168.1.1 --port 443 --username admin --password secret

  # With default port (443):
  python scripts/add_device.py --config config/lab.yaml \\
      --id dev-lab-01 --name "Router Lab 01" \\
      --ip 192.168.1.1 --username admin --password secret

  # With tags and capability flags:
  python scripts/add_device.py --config config/lab.yaml \\
      --id dev-lab-01 --name "Router Lab 01" \\
      --ip 192.168.1.1 --username admin --password secret \\
      --tags '{"site": "home", "role": "core"}' \\
      --allow-advanced-writes
        """,
    )

    parser.add_argument(
        "--config",
        required=True,
        help="Path to config file (e.g., 'config/lab.yaml')",
    )
    parser.add_argument(
        "--id",
        required=False,
        help="Unique device ID (e.g., 'dev-lab-01'). If not provided, a UUID will be generated.",
    )
    parser.add_argument(
        "--name",
        required=False,
        help="Human-friendly device name (e.g., 'Router Lab 01'). If not provided, will attempt to fetch identity via SSH.",
    )
    parser.add_argument(
        "--ip",
        required=True,
        help="Management IP address (IPv4 or IPv6, e.g., '192.168.1.1')",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=443,
        help="Management port (1-65535, default: 443)",
    )
    parser.add_argument(
        "--username",
        required=True,
        help="RouterOS REST API username",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="RouterOS REST API password",
    )
    parser.add_argument(
        "--tags",
        default="{}",
        help="JSON object with device tags (e.g., '{\"site\": \"home\"}')",
    )
    parser.add_argument(
        "--allow-advanced-writes",
        action="store_true",
        help="Allow advanced tier write operations on this device",
    )
    parser.add_argument(
        "--allow-professional-workflows",
        action="store_true",
        help="Allow professional tier multi-device workflows on this device",
    )

    args = parser.parse_args()

    # Load settings from config file
    settings = load_settings_from_file(args.config)
    print(f"📁 Using config: {args.config}")
    print(f"   Environment: {settings.environment}")
    print(f"   Database: {settings.database_url}")

    # Parse tags JSON
    try:
        tags = json.loads(args.tags)
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON for --tags: {e}")
        sys.exit(1)

    device_id = args.id
    device_name = args.name

    if not device_id or not device_name:
        print("ℹ️  ID or Name not provided. Attempting to fetch identity via SSH...")
        try:
            # Try to fetch identity using sshpass and ssh
            # Note: This assumes sshpass is installed and available
            cmd = [
                "sshpass",
                "-p",
                args.password,
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=5",
                f"{args.username}@{args.ip}",
                "/system identity print",
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            output = result.stdout.strip()
            # Output format: "name: identity"
            if "name: " in output:
                identity = output.split("name: ")[1].strip()
                print(f"✅ Fetched identity: {identity}")

                if not device_name:
                    device_name = identity

                if not device_id:
                    device_id = str(uuid.uuid4())
                    print(f"ℹ️  Generated UUID for ID: {device_id}")
            else:
                print(f"⚠️  Could not parse identity from output: {output}")
                if not device_id or not device_name:
                     print("❌ ID and Name are required if identity cannot be fetched.")
                     sys.exit(1)

        except subprocess.CalledProcessError as e:
            print(f"❌ SSH connection failed: {e}")
            print(f"   Stderr: {e.stderr}")
            if not device_id or not device_name:
                print("❌ ID and Name are required if SSH fetch fails.")
                sys.exit(1)
        except FileNotFoundError:
             print("❌ sshpass not found. Please install sshpass or provide --id and --name.")
             sys.exit(1)

    # Run async function
    try:
        asyncio.run(
            add_device(
                settings=settings,
                device_id=device_id,
                name=device_name,
                ip=args.ip,
                port=args.port,
                username=args.username,
                password=args.password,
                tags=tags,
                allow_advanced_writes=args.allow_advanced_writes,
                allow_professional_workflows=args.allow_professional_workflows,
            )
        )
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
