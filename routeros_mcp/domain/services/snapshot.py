"""Snapshot service for capturing and managing device configuration snapshots.

This service implements configuration snapshot capture, compression, and retention
for RouterOS devices. Snapshots are captured periodically and stored in the database.

Design principles:
- Prefer REST API /export endpoint (when available)
- Fallback to SSH /export compact command
- Compress snapshots using gzip
- Enforce max size limits
- Implement retention policies (keep latest + configurable history)
- Redact sensitive information where supported

See docs/15-mcp-resources-and-prompts-design.md (Phase 2.1 implementation details)
"""

import gzip
import hashlib
import logging
import time
import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import Device as DeviceDomain
from routeros_mcp.infra.db.models import Snapshot as SnapshotORM
from routeros_mcp.infra.observability import metrics
from routeros_mcp.infra.routeros.exceptions import RouterOSNetworkError
from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient
from routeros_mcp.infra.routeros.ssh_client import RouterOSSSHClient
from routeros_mcp.mcp.errors import ValidationError
from routeros_mcp.security.crypto import decrypt_string

logger = logging.getLogger(__name__)


class SnapshotService:
    """Service for capturing and managing device configuration snapshots.

    Responsibilities:
    - Capture RouterOS configuration exports (REST preferred, SSH fallback)
    - Compress and persist snapshot data
    - Set snapshot metadata (checksum, compression, redaction, source)
    - Implement retention policies
    - Decode and retrieve snapshots

    Example:
        async with get_session() as session:
            service = SnapshotService(session, settings)

            # Capture snapshot for device
            snapshot_id = await service.capture_device_snapshot(device_id)

            # Get latest snapshot
            snapshot = await service.get_latest_snapshot(device_id, kind="config")

            # Prune old snapshots
            await service.prune_old_snapshots(device_id, keep_count=5)
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize snapshot service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings

    async def capture_device_snapshot(
        self,
        device: DeviceDomain,
        kind: str = "config",
        use_ssh_fallback: bool = True,
    ) -> str:
        """Capture configuration snapshot for a device.

        Args:
            device: Device domain model
            kind: Snapshot type (default: "config")
            use_ssh_fallback: Whether to fallback to SSH if REST fails

        Returns:
            Snapshot ID

        Raises:
            ValidationError: If snapshot exceeds size limit
            RouterOSNetworkError: If device is unreachable
        """
        # Track capture start time for duration metrics
        capture_start_time = time.time()
        
        # Get device credentials
        credentials = await self._get_device_credentials(device.id)
        if not credentials:
            # Record failure and update metrics
            capture_duration = time.time() - capture_start_time
            metrics.record_snapshot_capture(
                device_id=device.id,
                kind=kind,
                duration=capture_duration,
                success=False,
            )
            raise ValidationError(
                f"No credentials found for device {device.id}",
                data={"device_id": device.id},
            )

        rest_creds = credentials.get("rest")
        ssh_creds = credentials.get("ssh")

        # Try REST API first
        config_text = None
        source = None
        error_message = None
        redacted = False

        if rest_creds:
            try:
                config_text = await self._capture_via_rest(
                    device=device,
                    username=rest_creds["username"],
                    password=rest_creds["password"],
                )
                source = "rest"
                logger.info(
                    f"Captured config snapshot via REST for device {device.id}",
                    extra={
                        "device_id": device.id,
                        "source": "rest",
                        "kind": kind,
                    },
                )
            except Exception as e:
                error_message = str(e)
                logger.warning(
                    f"REST config export failed for device {device.id}: {e}",
                    extra={
                        "device_id": device.id,
                        "kind": kind,
                        "source": "rest",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

        # Fallback to SSH if REST failed and fallback is enabled
        if config_text is None and use_ssh_fallback and ssh_creds:
            try:
                config_text = await self._capture_via_ssh(
                    device=device,
                    username=ssh_creds["username"],
                    password=ssh_creds["password"],
                )
                source = "ssh"
                redacted = True
                logger.info(
                    f"Captured config snapshot via SSH for device {device.id}",
                    extra={
                        "device_id": device.id,
                        "source": "ssh",
                        "kind": kind,
                    },
                )
            except Exception as e:
                error_message = str(e)
                logger.error(
                    f"SSH config export failed for device {device.id}: {e}",
                    extra={
                        "device_id": device.id,
                        "kind": kind,
                        "source": "ssh",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )

        # Check if we got config
        if config_text is None:
            # Record failure and update metrics
            capture_duration = time.time() - capture_start_time
            metrics.record_snapshot_capture(
                device_id=device.id,
                kind=kind,
                duration=capture_duration,
                success=False,
            )
            raise RouterOSNetworkError(
                f"Failed to capture config snapshot for device {device.id}: {error_message}"
            )

        # Enforce size limit
        config_bytes = config_text.encode("utf-8")
        if len(config_bytes) > self.settings.snapshot_max_size_bytes:
            # Record failure and update metrics
            capture_duration = time.time() - capture_start_time
            metrics.record_snapshot_capture(
                device_id=device.id,
                kind=kind,
                duration=capture_duration,
                success=False,
            )
            raise ValidationError(
                f"Snapshot size ({len(config_bytes)} bytes) exceeds limit "
                f"({self.settings.snapshot_max_size_bytes} bytes)",
                data={
                    "device_id": device.id,
                    "size_bytes": len(config_bytes),
                    "max_size_bytes": self.settings.snapshot_max_size_bytes,
                },
            )

        # Compress snapshot data
        compressed_data = gzip.compress(
            config_bytes, compresslevel=self.settings.snapshot_compression_level
        )

        # Calculate checksum (of uncompressed data)
        checksum = hashlib.sha256(config_bytes).hexdigest()

        # Create metadata
        metadata = {
            "size_bytes": len(config_bytes),
            "compressed_size_bytes": len(compressed_data),
            "compression": "gzip",
            "compression_level": self.settings.snapshot_compression_level,
            "checksum": checksum,
            "checksum_algorithm": "sha256",
            "source": source,
            "redacted": redacted,
        }

        # Generate snapshot ID and capture timestamp
        now_utc = datetime.now(UTC)
        snapshot_id = f"snap-{now_utc.strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"

        # Create snapshot record
        snapshot = SnapshotORM(
            id=snapshot_id,
            device_id=device.id,
            timestamp=now_utc,
            kind=kind,
            data=compressed_data,
            meta=metadata,
        )

        self.session.add(snapshot)
        await self.session.flush()

        logger.info(
            f"Snapshot {snapshot_id} created for device {device.id}",
            extra={
                "snapshot_id": snapshot_id,
                "device_id": device.id,
                "kind": kind,
                "size_bytes": len(config_bytes),
                "compressed_size_bytes": len(compressed_data),
                "source": source,
            },
        )

        # Update metrics
        # Record capture duration
        capture_duration = time.time() - capture_start_time
        metrics.record_snapshot_capture(
            device_id=device.id,
            kind=kind,
            duration=capture_duration,
            success=True,
        )
        
        metrics.snapshot_capture_total.labels(
            device_id=device.id,
            kind=kind,
            source=source or "unknown",
            status="success",
        ).inc()

        metrics.snapshot_size_bytes.labels(
            device_id=device.id,
            kind=kind,
        ).observe(len(config_bytes))

        # Observe compression ratio (compressed size / original size) when original size is non-zero
        if len(config_bytes) > 0:
            metrics.snapshot_compression_ratio.labels(
                device_id=device.id,
                kind=kind,
            ).observe(len(compressed_data) / len(config_bytes))

        # Update snapshot age (0 seconds for newly captured)
        metrics.update_snapshot_age(
            device_id=device.id,
            kind=kind,
            age_seconds=0.0,
        )

        return snapshot_id

    async def get_latest_snapshot(
        self,
        device_id: str,
        kind: str = "config",
    ) -> SnapshotORM | None:
        """Get the latest snapshot for a device.

        Args:
            device_id: Device ID
            kind: Snapshot kind (default: "config")

        Returns:
            Snapshot ORM or None if no snapshots exist
        """
        result = await self.session.execute(
            select(SnapshotORM)
            .where(SnapshotORM.device_id == device_id, SnapshotORM.kind == kind)
            .order_by(desc(SnapshotORM.timestamp))
            .limit(1)
        )
        snapshot = result.scalar_one_or_none()
        
        # Update snapshot age metrics
        if snapshot:
            age_seconds = (datetime.now(UTC) - snapshot.timestamp).total_seconds()
            metrics.update_snapshot_age(
                device_id=device_id,
                kind=kind,
                age_seconds=age_seconds,
            )
        else:
            # No snapshot found - record missing snapshot
            metrics.record_snapshot_missing(
                device_id=device_id,
                kind=kind,
            )
        
        return snapshot

    async def decode_snapshot(
        self,
        snapshot: SnapshotORM,
    ) -> str:
        """Decode compressed snapshot data to text.

        Args:
            snapshot: Snapshot ORM instance

        Returns:
            Decoded configuration text

        Raises:
            ValidationError: If decompression fails
        """
        try:
            # Check if compressed
            if snapshot.meta.get("compression") == "gzip":
                decompressed = gzip.decompress(snapshot.data)
                return decompressed.decode("utf-8")
            else:
                # Not compressed
                return snapshot.data.decode("utf-8")
        except Exception as e:
            logger.error(
                f"Failed to decode snapshot {snapshot.id}: {e}",
                exc_info=True,
            )
            raise ValidationError(
                f"Failed to decode snapshot: {e}",
                data={"snapshot_id": snapshot.id},
            )

    async def prune_old_snapshots(
        self,
        device_id: str,
        kind: str = "config",
        keep_count: int = 5,
    ) -> int:
        """Prune old snapshots keeping only the most recent N.

        Args:
            device_id: Device ID
            kind: Snapshot kind
            keep_count: Number of snapshots to keep (default: 5)

        Returns:
            Number of snapshots deleted
        """
        # Get all snapshots for device/kind, ordered by timestamp descending
        result = await self.session.execute(
            select(SnapshotORM)
            .where(SnapshotORM.device_id == device_id, SnapshotORM.kind == kind)
            .order_by(desc(SnapshotORM.timestamp))
        )
        snapshots = result.scalars().all()

        # Delete snapshots beyond keep_count
        if len(snapshots) > keep_count:
            to_delete = snapshots[keep_count:]
            deleted_count = len(to_delete)

            for snapshot in to_delete:
                await self.session.delete(snapshot)

            await self.session.flush()

            logger.info(
                f"Pruned {deleted_count} old snapshots for device {device_id}",
                extra={
                    "device_id": device_id,
                    "kind": kind,
                    "deleted_count": deleted_count,
                    "kept_count": keep_count,
                },
            )

            return deleted_count
        else:
            return 0

    async def _get_device_credentials(
        self,
        device_id: str,
    ) -> dict[str, dict[str, str]]:
        """Get device credentials (decrypted).

        Args:
            device_id: Device ID

        Returns:
            Dict with "rest" and "ssh" credential dictionaries
        """
        from routeros_mcp.infra.db.models import Credential as CredentialORM

        result = await self.session.execute(
            select(CredentialORM).where(
                CredentialORM.device_id == device_id,
                CredentialORM.active == True,  # noqa: E712
            )
        )
        creds_orm = result.scalars().all()

        credentials: dict[str, dict[str, str]] = {}

        for cred in creds_orm:
            password = decrypt_string(
                cred.encrypted_secret,
                self.settings.encryption_key,
            )

            credentials[cred.credential_type] = {
                "username": cred.username,
                "password": password,
            }

        return credentials

    async def _capture_via_rest(
        self,
        device: DeviceDomain,
        username: str,
        password: str,
    ) -> str:
        """Capture config via REST API.

        Args:
            device: Device domain model
            username: REST API username
            password: REST API password

        Returns:
            Configuration text

        Raises:
            RouterOSClientError: If REST API call fails
        """
        client = RouterOSRestClient(
            host=device.management_ip,
            port=device.management_port,
            username=username,
            password=password,
            verify_ssl=False,  # RouterOS typically uses self-signed certs
        )

        try:
            # Note: RouterOS REST API doesn't provide a direct /export endpoint in v7.
            # Future enhancement: explore /system/script or other methods for REST export.
            # For now, raising NotImplementedError to trigger SSH fallback.
            raise NotImplementedError(
                "REST API configuration export not available in RouterOS v7. "
                "Using SSH /export fallback."
            )
        finally:
            await client.close()

    async def _capture_via_ssh(
        self,
        device: DeviceDomain,
        username: str,
        password: str,
    ) -> str:
        """Capture config via SSH.

        Args:
            device: Device domain model
            username: SSH username
            password: SSH password

        Returns:
            Configuration text

        Raises:
            RouterOSSSHError: If SSH command fails
        """
        client = RouterOSSSHClient(
            host=device.management_ip,
            port=22,  # Standard SSH port
            username=username,
            password=password,
            timeout_seconds=60.0,  # Exports can take time on large configs
        )

        try:
            # Use compact export with sensitive data redacted
            # This command is whitelisted in ssh_client.py
            config = await client.execute("/export hide-sensitive compact")
            return config
        finally:
            await client.close()
