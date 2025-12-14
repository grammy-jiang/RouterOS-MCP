"""Device service for device registry and credential management.

Provides business logic for device CRUD operations, credential management,
and connectivity checks. Abstracts database and RouterOS client details.
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import (
    CredentialCreate,
    DeviceCreate,
    DeviceUpdate,
)
from routeros_mcp.domain.models import (
    Device as DeviceDomain,
)
from routeros_mcp.infra.db.models import Credential as CredentialORM
from routeros_mcp.infra.db.models import Device as DeviceORM
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSAuthenticationError,
    RouterOSAuthorizationError,
    RouterOSClientError,
    RouterOSNetworkError,
    RouterOSNotFoundError,
    RouterOSSSHAuthenticationError,
    RouterOSSSHCommandNotAllowedError,
    RouterOSSSHError,
    RouterOSSSHTimeoutError,
    RouterOSServerError,
    RouterOSTimeoutError,
)
from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient
from routeros_mcp.infra.routeros.ssh_client import RouterOSSSHClient
from routeros_mcp.mcp.errors import (
    AuthenticationError,
    DeviceNotFoundError,
    EnvironmentMismatchError,
    ValidationError,
)
from routeros_mcp.security.crypto import decrypt_string, encrypt_string

logger = logging.getLogger(__name__)

REST_KIND = "rest"
SSH_KIND = "ssh"


class DeviceService:
    """Service for device registry and credential management.

    Responsibilities:
    - Device CRUD operations with environment validation
    - Credential management with encryption
    - Connectivity checks via RouterOS REST client
    - Device metadata updates from RouterOS responses

    Example:
        async with get_session() as session:
            service = DeviceService(session, settings)

            # Register device
            device = await service.register_device(DeviceCreate(
                id="dev-lab-01",
                name="router-lab-01",
                management_ip="192.168.1.1",
                management_port=443,
                environment="lab",
            ))

            # Add credentials
            await service.add_credential(CredentialCreate(
                device_id="dev-lab-01",
                credential_type="rest",
                username="admin",
                password="secret",
            ))

            # Check connectivity
            is_reachable, meta = await service.check_connectivity("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize device service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings

    async def register_device(
        self,
        device_data: DeviceCreate,
    ) -> DeviceDomain:
        """Register a new device.

        Args:
            device_data: Device creation data

        Returns:
            Created device

        Raises:
            ValidationError: If device ID already exists
            EnvironmentMismatchError: If device environment doesn't match service
        """
        # Validate environment matches service environment
        if device_data.environment != self.settings.environment:
            raise EnvironmentMismatchError(
                f"Device environment '{device_data.environment}' does not match "
                f"service environment '{self.settings.environment}'",
                data={
                    "device_environment": device_data.environment,
                    "service_environment": self.settings.environment,
                },
            )

        # Check if device already exists
        result = await self.session.execute(
            select(DeviceORM).where(DeviceORM.id == device_data.id)
        )
        existing = result.scalar_one_or_none()
        if existing:
            raise ValidationError(
                f"Device with ID '{device_data.id}' already exists",
                data={"device_id": device_data.id},
            )

        # Create device ORM instance
        device_orm = DeviceORM(
            id=device_data.id,
            name=device_data.name or device_data.id,
            management_ip=device_data.management_ip,
            management_port=device_data.management_port,
            environment=device_data.environment,
            status="pending",
            tags=device_data.tags,
            allow_advanced_writes=device_data.allow_advanced_writes,
            allow_professional_workflows=device_data.allow_professional_workflows,
        )

        self.session.add(device_orm)
        await self.session.commit()
        await self.session.refresh(device_orm)

        logger.info(
            "Registered device",
            extra={
                "device_id": device_orm.id,
                "device_name": device_orm.name,
                "environment": device_orm.environment,
            },
        )

        return DeviceDomain.model_validate(device_orm)

    async def get_device(
        self,
        device_id: str,
    ) -> DeviceDomain:
        """Get device by ID.

        Args:
            device_id: Device identifier

        Returns:
            Device domain model

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        result = await self.session.execute(
            select(DeviceORM).where(DeviceORM.id == device_id)
        )
        device_orm = result.scalar_one_or_none()

        if not device_orm:
            raise DeviceNotFoundError(
                f"Device '{device_id}' not found",
                data={"device_id": device_id},
            )

        return DeviceDomain.model_validate(device_orm)

    async def list_devices(
        self,
        environment: str | None = None,
        status: str | None = None,
    ) -> list[DeviceDomain]:
        """List devices with optional filters.

        Args:
            environment: Filter by environment
            status: Filter by status

        Returns:
            List of devices
        """
        query = select(DeviceORM)

        if environment:
            query = query.where(DeviceORM.environment == environment)

        if status:
            query = query.where(DeviceORM.status == status)

        result = await self.session.execute(query)
        devices = result.scalars().all()

        return [DeviceDomain.model_validate(d) for d in devices]

    async def update_device(
        self,
        device_id: str,
        updates: DeviceUpdate,
    ) -> DeviceDomain:
        """Update device information.

        Args:
            device_id: Device identifier
            updates: Fields to update

        Returns:
            Updated device

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        result = await self.session.execute(
            select(DeviceORM).where(DeviceORM.id == device_id)
        )
        device_orm = result.scalar_one_or_none()

        if not device_orm:
            raise DeviceNotFoundError(
                f"Device '{device_id}' not found",
                data={"device_id": device_id},
            )

        # Apply updates
        update_data = updates.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(device_orm, field, value)

        await self.session.commit()
        await self.session.refresh(device_orm)

        logger.info(
            "Updated device",
            extra={"device_id": device_id, "updates": list(update_data.keys())},
        )

        return DeviceDomain.model_validate(device_orm)

    async def add_credential(
        self,
        credential_data: CredentialCreate,
    ) -> None:
        """Add encrypted credentials for a device.

        Args:
            credential_data: Credential data

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        # Verify device exists
        await self.get_device(credential_data.device_id)

        # Encrypt password
        encrypted_secret = encrypt_string(
            credential_data.password,
            self.settings.encryption_key,
        )

        # Create credential
        credential_orm = CredentialORM(
            id=f"cred-{credential_data.device_id}-{credential_data.credential_type}",
            device_id=credential_data.device_id,
            credential_type=credential_data.credential_type,
            username=credential_data.username,
            encrypted_secret=encrypted_secret,
            active=True,
        )

        self.session.add(credential_orm)
        await self.session.commit()

        logger.info(
            "Added credential",
            extra={
                "device_id": credential_data.device_id,
                "credential_type": credential_data.credential_type,
                "username": credential_data.username,
            },
        )

    async def get_rest_client(
        self,
        device_id: str,
    ) -> RouterOSRestClient:
        """Get REST client for device with decrypted credentials.

        **IMPORTANT**: The caller is responsible for closing the returned client
        by calling `await client.close()` when done. Consider using in a try/finally
        block or async context manager pattern.

        Args:
            device_id: Device identifier

        Returns:
            Configured RouterOS REST client (must be closed by caller)

        Raises:
            DeviceNotFoundError: If device or credentials don't exist
            AuthenticationError: If credentials can't be decrypted

        Example:
            client = await service.get_rest_client("dev-lab-01")
            try:
                data = await client.get("/rest/system/resource")
                # Process data...
            finally:
                await client.close()
        """
        device = await self.get_device(device_id)

        # Get REST credentials (no fallback)
        result = await self.session.execute(
            select(CredentialORM).where(
                CredentialORM.device_id == device_id,
                CredentialORM.credential_type == REST_KIND,
                CredentialORM.active == True,  # noqa: E712
            )
        )
        credential = result.scalar_one_or_none()

        if not credential:
            raise AuthenticationError(
                f"No active REST credentials found for device '{device_id}'",
                data={"device_id": device_id},
            )

        # Decrypt password
        try:
            password = decrypt_string(
                credential.encrypted_secret,
                self.settings.encryption_key,
            )
        except Exception as e:
            raise AuthenticationError(
                f"Failed to decrypt credentials for device '{device_id}': {e}",
                data={"device_id": device_id},
            )

        # Create client using separate IP and port fields
        client = RouterOSRestClient(
            host=device.management_ip,
            port=device.management_port,
            username=credential.username,
            password=password,
            timeout_seconds=self.settings.routeros_rest_timeout_seconds,
            max_retries=self.settings.routeros_retry_attempts,
            verify_ssl=self.settings.routeros_verify_ssl,
        )

        return client

    async def get_ssh_client(
        self,
        device_id: str,
    ) -> RouterOSSSHClient:
        """Get SSH client for device with decrypted credentials.

        Caller must close the returned client (`await client.close()`).
        """
        device = await self.get_device(device_id)

        result = await self.session.execute(
            select(CredentialORM).where(
                CredentialORM.device_id == device_id,
                CredentialORM.credential_type == SSH_KIND,
                CredentialORM.active == True,  # noqa: E712
            )
        )
        credential = result.scalar_one_or_none()

        if not credential:
            raise AuthenticationError(
                f"No active SSH credentials found for device '{device_id}'",
                data={"device_id": device_id},
            )

        try:
            password = decrypt_string(
                credential.encrypted_secret,
                self.settings.encryption_key,
            )
        except Exception as e:
            raise AuthenticationError(
                f"Failed to decrypt SSH credentials for device '{device_id}': {e}",
                data={"device_id": device_id},
            )

        client = RouterOSSSHClient(
            host=device.management_ip,
            port=22,
            username=credential.username,
            password=password,
            timeout_seconds=self.settings.routeros_rest_timeout_seconds,
            max_retries=self.settings.routeros_retry_attempts,
        )

        return client

    async def check_connectivity(
        self,
        device_id: str,
    ) -> tuple[bool, dict[str, Any]]:
        """Check device reachability.

        Attempts REST first; on REST failure, falls back to a whitelisted SSH
        read-only probe. Returns `(reachable, meta)` including which transport
        succeeded/failed and classified failure reasons.
        """
        rest_client: RouterOSRestClient | None = None
        ssh_client: RouterOSSSHClient | None = None
        rest_failure_reason: str | None = None
        ssh_failure_reason: str | None = None
        rest_time_ms: float | None = None
        ssh_time_ms: float | None = None
        rest_start: float | None = None
        ssh_start: float | None = None
        attempted_transports: list[str] = []
        meta: dict[str, Any] = {
            "device_id": device_id,
            "attempts": self.settings.routeros_retry_attempts,
            "timeout_seconds": self.settings.routeros_rest_timeout_seconds,
        }

        # --- REST attempt (primary, only if REST credential exists) ---
        rest_credential_exists = await self.session.execute(
            select(CredentialORM.id).where(
                CredentialORM.device_id == device_id,
                CredentialORM.credential_type == REST_KIND,
                CredentialORM.active == True,  # noqa: E712
            ).limit(1)
        )
        if rest_credential_exists.scalar_one_or_none():
            attempted_transports.append("rest")
            try:
                rest_client = await self.get_rest_client(device_id)
                rest_start = time.perf_counter()
                await rest_client.get("/rest/system/resource")
                rest_time_ms = (time.perf_counter() - rest_start) * 1000

                await self.update_device(device_id, DeviceUpdate(status="healthy"))
                result = await self.session.execute(
                    select(DeviceORM).where(DeviceORM.id == device_id)
                )
                device_orm = result.scalar_one()
                device_orm.last_seen_at = datetime.now(UTC)
                await self.session.commit()

                meta.update(
                    {
                        "reachable": True,
                        "failure_reason": None,
                        "transport": "rest",
                        "fallback_used": False,
                        "attempted_transports": attempted_transports,
                        "rest_time_ms": rest_time_ms,
                        "ssh_time_ms": ssh_time_ms,
                    }
                )
                return True, meta

            except RouterOSTimeoutError as e:
                rest_failure_reason = "timeout"
                meta["rest_error"] = str(e)
            except RouterOSNetworkError as e:
                rest_failure_reason = "network_error"
                meta["rest_error"] = str(e)
            except (RouterOSAuthenticationError, AuthenticationError) as e:
                rest_failure_reason = "auth_failed"
                meta["rest_error"] = str(e)
            except RouterOSAuthorizationError as e:
                rest_failure_reason = "authz_failed"
                meta["rest_error"] = str(e)
            except RouterOSNotFoundError as e:
                rest_failure_reason = "not_found"
                meta["rest_error"] = str(e)
            except RouterOSClientError as e:
                rest_failure_reason = "client_error"
                meta["rest_error"] = str(e)
                meta["status_code"] = getattr(e, "status_code", None)
            except RouterOSServerError as e:
                rest_failure_reason = "server_error"
                meta["rest_error"] = str(e)
                meta["status_code"] = getattr(e, "status_code", None)
            except Exception as e:  # pragma: no cover - safety net
                rest_failure_reason = "unknown"
                meta["rest_error"] = str(e)
            finally:
                if rest_time_ms is None and rest_start is not None:
                    rest_time_ms = (time.perf_counter() - rest_start) * 1000
                if rest_client:
                    try:
                        await rest_client.close()
                    except Exception:  # pragma: no cover - defensive
                        logger.debug("Failed to close RouterOS REST client", exc_info=True)

        # --- SSH fallback (secondary) ---
        try:
            attempted_transports.append("ssh")
            ssh_client = await self.get_ssh_client(device_id)
            ssh_start = time.perf_counter()
            await ssh_client.execute("/system/resource/print")
            ssh_time_ms = (time.perf_counter() - ssh_start) * 1000

            await self.update_device(device_id, DeviceUpdate(status="healthy"))
            result = await self.session.execute(
                select(DeviceORM).where(DeviceORM.id == device_id)
            )
            device_orm = result.scalar_one()
            device_orm.last_seen_at = datetime.now(UTC)
            await self.session.commit()

            meta.update(
                {
                    "reachable": True,
                    "failure_reason": None,
                    "transport": "ssh",
                    "fallback_used": True,
                    "attempted_transports": attempted_transports,
                    "rest_time_ms": rest_time_ms,
                    "ssh_time_ms": ssh_time_ms,
                }
            )
            return True, meta

        except AuthenticationError as e:
            ssh_failure_reason = "auth_failed"
            meta["ssh_error"] = str(e)
        except RouterOSSSHAuthenticationError as e:
            ssh_failure_reason = "auth_failed"
            meta["ssh_error"] = str(e)
        except RouterOSSSHTimeoutError as e:
            ssh_failure_reason = "timeout"
            meta["ssh_error"] = str(e)
        except RouterOSSSHCommandNotAllowedError as e:
            ssh_failure_reason = "client_error"
            meta["ssh_error"] = str(e)
        except RouterOSSSHError as e:
            ssh_failure_reason = "network_error"
            meta["ssh_error"] = str(e)
        except Exception as e:  # pragma: no cover - safety net
            ssh_failure_reason = "unknown"
            meta["ssh_error"] = str(e)
        finally:
            if ssh_time_ms is None and ssh_start is not None:
                ssh_time_ms = (time.perf_counter() - ssh_start) * 1000
            if ssh_client:
                try:
                    await ssh_client.close()
                except Exception:  # pragma: no cover - defensive
                    logger.debug("Failed to close RouterOS SSH client", exc_info=True)

        failure_reason = ssh_failure_reason or rest_failure_reason or "unknown"

        logger.warning(
            "Device connectivity check failed",
            extra={
                "device_id": device_id,
                "failure_reason": failure_reason,
                "rest_error": meta.get("rest_error"),
                "ssh_error": meta.get("ssh_error"),
            },
        )

        await self.update_device(device_id, DeviceUpdate(status="unreachable"))

        meta.update(
            {
                "reachable": False,
                "failure_reason": failure_reason,
                "transport": attempted_transports[-1] if attempted_transports else None,
                "fallback_used": "ssh" in attempted_transports,
                "attempted_transports": attempted_transports,
                "rest_time_ms": rest_time_ms,
                "ssh_time_ms": ssh_time_ms,
            }
        )

        return False, meta
