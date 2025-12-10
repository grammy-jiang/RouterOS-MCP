"""Device service for device registry and credential management.

Provides business logic for device CRUD operations, credential management,
and connectivity checks. Abstracts database and RouterOS client details.
"""

import logging
from datetime import UTC, datetime

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
from routeros_mcp.infra.routeros.rest_client import RouterOSRestClient
from routeros_mcp.mcp.errors import (
    AuthenticationError,
    DeviceNotFoundError,
    EnvironmentMismatchError,
    ValidationError,
)
from routeros_mcp.security.crypto import decrypt_string, encrypt_string

logger = logging.getLogger(__name__)


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
                management_address="192.168.1.1:443",
                environment="lab",
            ))

            # Add credentials
            await service.add_credential(CredentialCreate(
                device_id="dev-lab-01",
                kind="routeros_rest",
                username="admin",
                password="secret",
            ))

            # Check connectivity
            is_reachable = await service.check_connectivity("dev-lab-01")
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
            name=device_data.name,
            management_address=device_data.management_address,
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
                "name": device_orm.name,
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
            id=f"cred-{credential_data.device_id}-{credential_data.kind}",
            device_id=credential_data.device_id,
            kind=credential_data.kind,
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
                "kind": credential_data.kind,
                "username": credential_data.username,
            },
        )

    async def get_rest_client(
        self,
        device_id: str,
    ) -> RouterOSRestClient:
        """Get REST client for device with decrypted credentials.

        Args:
            device_id: Device identifier

        Returns:
            Configured RouterOS REST client

        Raises:
            DeviceNotFoundError: If device or credentials don't exist
            AuthenticationError: If credentials can't be decrypted
        """
        device = await self.get_device(device_id)

        # Get REST credentials
        result = await self.session.execute(
            select(CredentialORM).where(
                CredentialORM.device_id == device_id,
                CredentialORM.kind == "routeros_rest",
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

        # Parse management address
        host_port = device.management_address.rsplit(":", 1)
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 443

        # Create client
        client = RouterOSRestClient(
            host=host,
            port=port,
            username=credential.username,
            password=password,
            timeout_seconds=self.settings.routeros_rest_timeout_seconds,
            max_retries=self.settings.routeros_retry_attempts,
            verify_ssl=False,  # RouterOS often uses self-signed certs
        )

        return client

    async def check_connectivity(
        self,
        device_id: str,
    ) -> bool:
        """Check if device is reachable via REST API.

        Args:
            device_id: Device identifier

        Returns:
            True if device is reachable

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        try:
            client = await self.get_rest_client(device_id)

            # Try to get system resource
            await client.get("/rest/system/resource")

            # Update device status and last_seen_at
            await self.update_device(
                device_id,
                DeviceUpdate(
                    status="healthy",
                ),
            )

            # Update last_seen_at directly (not part of DeviceUpdate)
            result = await self.session.execute(
                select(DeviceORM).where(DeviceORM.id == device_id)
            )
            device_orm = result.scalar_one()
            device_orm.last_seen_at = datetime.now(UTC)
            await self.session.commit()

            await client.close()
            return True

        except Exception as e:
            logger.warning(
                "Device connectivity check failed",
                extra={"device_id": device_id, "error": str(e)},
            )

            # Update device status to unreachable
            await self.update_device(
                device_id,
                DeviceUpdate(status="unreachable"),
            )

            return False
