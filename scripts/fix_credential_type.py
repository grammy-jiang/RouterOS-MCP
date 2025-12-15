
"""One-off helper to correct credential_type for a device's credentials.

Purpose:
    Fix historical data where a credential may have been stored with the wrong
    ``credential_type`` (e.g., 'rest' instead of 'ssh'). This script updates all
    credentials for a given device_id matching a source type to a target type.

When to use:
    - After early development or migration when types were inconsistent
    - To normalize data before enabling features that rely on correct types

Safety notes:
    - This directly mutates database rows. Use only in lab/staging unless you know
      the production impact and have a backup.
    - All changes are auditable via DB history/commits; consider taking a snapshot.

Usage:
    # Using defaults (config/lab.yaml, from 'rest' to 'ssh')
    python scripts/fix_credential_type.py --device-id dev-lab-01

    # Specify config and custom type mapping
    python scripts/fix_credential_type.py --device-id dev-lab-01 \
        --config config/staging.yaml --from-type rest --to-type ssh

Exit codes:
    0 on success; non-zero on validation or DB errors.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from sqlalchemy import select

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from routeros_mcp.config import load_settings_from_file
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.infra.db.models import Credential as CredentialORM


async def fix_credential(
    device_id: str,
    config_path: str = "config/lab.yaml",
    from_type: str = "rest",
    to_type: str = "ssh",
) -> None:
    """Update credential_type from ``from_type`` to ``to_type`` for a device.

    Args:
        device_id: Target device ID whose credentials will be scanned.
        config_path: Path to settings file (YAML/TOML). Defaults to lab config.
        from_type: Credential type to match and update from (default 'rest').
        to_type: New credential type to set (default 'ssh').
    """
    settings = load_settings_from_file(config_path)
    session_factory = get_session_factory(settings)
    await session_factory.init()

    async with session_factory.session() as session:
        # Find the credential
        stmt = select(CredentialORM).where(CredentialORM.device_id == device_id)
        result = await session.execute(stmt)
        creds = result.scalars().all()

        for cred in creds:
            print(f"Found credential: {cred.id}, Type: {cred.credential_type}, Username: {cred.username}")
            if cred.credential_type == from_type:
                print(f"Updating credential {cred.id} type: '{from_type}' -> '{to_type}' ...")
                cred.credential_type = to_type
                session.add(cred)

        await session.commit()
        print("Update complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fix credential_type for a device's credentials")
    parser.add_argument("--device-id", required=True, help="Device ID to update")
    parser.add_argument("--config", default="config/lab.yaml", help="Path to config file")
    parser.add_argument("--from-type", dest="from_type", default="rest", help="Current type to match (default: rest)")
    parser.add_argument("--to-type", dest="to_type", default="ssh", help="New type to set (default: ssh)")
    args = parser.parse_args()

    try:
        asyncio.run(
            fix_credential(
                device_id=args.device_id,
                config_path=args.config,
                from_type=args.from_type,
                to_type=args.to_type,
            )
        )
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
