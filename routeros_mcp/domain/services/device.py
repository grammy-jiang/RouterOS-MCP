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
from routeros_mcp.domain.exceptions import (
    CapabilityNotAllowedError,
    EnvironmentNotAllowedError,
)
from routeros_mcp.domain.models import (
    CredentialCreate,
    DeviceCapability,
    DeviceCreate,
    DeviceUpdate,
    PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS,
)
from routeros_mcp.domain.models import (
    Device as DeviceDomain,
)
from routeros_mcp.infra.db.models import Credential as CredentialORM
from routeros_mcp.infra.db.models import Device as DeviceORM
from routeros_mcp.infra.observability import metrics
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
            allow_firewall_writes=device_data.allow_firewall_writes,
            allow_routing_writes=device_data.allow_routing_writes,
            allow_wireless_writes=device_data.allow_wireless_writes,
            allow_dhcp_writes=device_data.allow_dhcp_writes,
            allow_bridge_writes=device_data.allow_bridge_writes,
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

    async def create_device(
        self,
        device_id: str,
        name: str,
        management_ip: str,
        username: str,
        password: str,
        environment: str = "lab",
        management_port: int = 443,
    ) -> DeviceDomain:
        """Convenience wrapper to create a device with REST credentials.

        This method exists primarily for backwards compatibility with earlier
        tests and examples that created a device and its primary credentials in
        one call.

        Args:
            device_id: Unique device identifier
            name: Human-friendly device name
            management_ip: Management IP address
            username: REST username
            password: REST password
            environment: Environment name (lab/staging/prod)
            management_port: Management port (default: 443)

        Returns:
            Created device domain model
        """
        device = await self.register_device(
            DeviceCreate(
                id=device_id,
                name=name,
                management_ip=management_ip,
                management_port=management_port,
                environment=environment,
            )
        )

        await self.add_credential(
            CredentialCreate(
                device_id=device_id,
                credential_type=REST_KIND,
                username=username,
                password=password,
            )
        )

        return device

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

        # Track if status changed
        old_status = device_orm.status

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

        # Invalidate cache if status changed (health/availability update)
        new_status = device_orm.status
        if old_status != new_status and self.settings.mcp_resource_cache_auto_invalidate:
            await self._invalidate_device_cache(device_id, reason="status_change")

        return DeviceDomain.model_validate(device_orm)

    async def add_credential(
        self,
        credential_data: CredentialCreate,
    ) -> None:
        """Add encrypted credentials for a device.

        Supports password-based and SSH key-based credentials (Phase 4).

        Args:
            credential_data: Credential data

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValidationError: If SSH key is invalid or required fields are missing
        """
        from routeros_mcp.security.crypto import (
            SSHKeyValidationError,
            get_public_key_fingerprint,
            validate_ssh_private_key,
        )

        # Verify device exists
        await self.get_device(credential_data.device_id)

        # Validate credential data based on type
        if credential_data.credential_type == "routeros_ssh_key":
            # SSH key authentication
            if not credential_data.private_key:
                raise ValidationError(
                    "private_key is required for routeros_ssh_key credential type",
                    data={"device_id": credential_data.device_id},
                )
            
            # Validate SSH key format
            try:
                validate_ssh_private_key(credential_data.private_key)
            except SSHKeyValidationError as e:
                raise ValidationError(
                    f"Invalid SSH private key: {e}",
                    data={"device_id": credential_data.device_id},
                )
            
            # Generate fingerprint if not provided
            if not credential_data.public_key_fingerprint:
                try:
                    credential_data.public_key_fingerprint = get_public_key_fingerprint(
                        credential_data.private_key
                    )
                except SSHKeyValidationError as e:
                    raise ValidationError(
                        f"Failed to extract public key fingerprint: {e}",
                        data={"device_id": credential_data.device_id},
                    )
            
            # Encrypt private key
            encrypted_private_key = encrypt_string(
                credential_data.private_key,
                self.settings.encryption_key,
            )
            
            # Create credential with SSH key
            credential_orm = CredentialORM(
                id=f"cred-{credential_data.device_id}-{credential_data.credential_type}",
                device_id=credential_data.device_id,
                credential_type=credential_data.credential_type,
                username=credential_data.username,
                encrypted_secret="",  # Not used for key auth
                private_key=encrypted_private_key,
                public_key_fingerprint=credential_data.public_key_fingerprint,
                active=True,
            )
        else:
            # Password-based authentication (rest or ssh)
            if not credential_data.password:
                raise ValidationError(
                    f"password is required for {credential_data.credential_type} credential type",
                    data={"device_id": credential_data.device_id},
                )
            
            # Encrypt password
            encrypted_secret = encrypt_string(
                credential_data.password,
                self.settings.encryption_key,
            )

            # Create credential with password
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
        
        Phase 4: Supports both SSH key and password authentication.
        Tries routeros_ssh_key first, falls back to ssh password if not found.
        """
        device = await self.get_device(device_id)

        # Phase 4: Try SSH key credential first
        result = await self.session.execute(
            select(CredentialORM).where(
                CredentialORM.device_id == device_id,
                CredentialORM.credential_type == "routeros_ssh_key",
                CredentialORM.active == True,  # noqa: E712
            )
        )
        key_credential = result.scalar_one_or_none()
        
        if key_credential:
            # Use SSH key authentication
            try:
                private_key = decrypt_string(
                    key_credential.private_key,
                    self.settings.encryption_key,
                )
            except Exception as e:
                logger.warning(
                    f"Failed to decrypt SSH key for device '{device_id}': {e}, trying password fallback"
                )
                key_credential = None  # Fall through to password auth
            else:
                client = RouterOSSSHClient(
                    host=device.management_ip,
                    port=22,
                    username=key_credential.username,
                    private_key=private_key,
                    timeout_seconds=self.settings.routeros_rest_timeout_seconds,
                    max_retries=self.settings.routeros_retry_attempts,
                )
                logger.info(f"SSH client created with key authentication for device '{device_id}'")
                return client
        
        # Fallback to password-based SSH authentication
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

    async def check_device_capabilities(
        self,
        device_id: str,
        required_capabilities: list[DeviceCapability] | None = None,
        allowed_environments: list[str] | None = None,
        operation: str | None = None,
    ) -> DeviceDomain:
        """Check device capability flags and environment tags for Phase 3 safety guardrails.
        
        This method enforces two layers of safety:
        1. Environment validation: Ensure device is in an allowed environment
        2. Capability validation: Ensure required capability flags are enabled
        
        Args:
            device_id: Device identifier
            required_capabilities: List of capability flags required for the operation.
                                 If None or empty, only environment check is performed.
            allowed_environments: List of environments where operation is permitted.
                                If None, defaults to PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS
                                (lab/staging only).
            operation: Optional operation name for audit logging and error messages.
        
        Returns:
            Device domain model if all checks pass
        
        Raises:
            DeviceNotFoundError: If device doesn't exist
            EnvironmentNotAllowedError: If device environment is not in allowed list
            CapabilityNotAllowedError: If required capability flag is not enabled
        
        Example:
            # Check firewall write capability on lab/staging devices only
            device = await service.check_device_capabilities(
                device_id="dev-lab-01",
                required_capabilities=[DeviceCapability.FIREWALL_WRITES],
                allowed_environments=["lab", "staging"],
                operation="firewall_write"
            )
            
            # Check professional workflows (defaults to lab/staging only)
            device = await service.check_device_capabilities(
                device_id="dev-prod-01",
                required_capabilities=[DeviceCapability.PROFESSIONAL_WORKFLOWS],
                operation="plan_apply"
            )
        """
        # Get device
        device = await self.get_device(device_id)
        
        # Default to Phase 3 allowed environments (lab/staging only)
        if allowed_environments is None:
            allowed_environments = PHASE3_DEFAULT_ALLOWED_ENVIRONMENTS
        
        # 1. Environment validation (MANDATORY - cannot bypass)
        if device.environment not in allowed_environments:
            error_context = {
                "device_id": device_id,
                "device_name": device.name,
                "device_environment": device.environment,
                "allowed_environments": allowed_environments,
                "operation": operation or "unknown",
            }
            
            # Audit log for environment restriction
            logger.warning(
                "Device environment restriction enforced",
                extra={
                    **error_context,
                    "check_type": "environment_validation",
                    "result": "denied",
                },
            )
            
            raise EnvironmentNotAllowedError(
                f"Operation '{operation or 'unknown'}' not allowed on device in '{device.environment}' environment. "
                f"Allowed environments: {', '.join(allowed_environments)}",
                context=error_context,
            )
        
        # 2. Capability flag validation (if capabilities specified)
        if required_capabilities:
            for capability in required_capabilities:
                # Get capability flag value from device (defaults to False if not set)
                capability_flag_name = capability.value
                capability_enabled = getattr(device, capability_flag_name, False)
                
                if not capability_enabled:
                    error_context = {
                        "device_id": device_id,
                        "device_name": device.name,
                        "device_environment": device.environment,
                        "required_capability": capability_flag_name,
                        "current_value": capability_enabled,
                        "operation": operation or "unknown",
                    }
                    
                    # Audit log for capability restriction
                    logger.warning(
                        "Device capability flag restriction enforced",
                        extra={
                            **error_context,
                            "check_type": "capability_validation",
                            "result": "denied",
                        },
                    )
                    
                    raise CapabilityNotAllowedError(
                        f"Operation '{operation or 'unknown'}' requires capability flag '{capability_flag_name}' "
                        f"to be enabled on device '{device.name}' ({device_id}). "
                        f"Current value: {capability_enabled}. "
                        f"Please enable this capability flag to proceed.",
                        context=error_context,
                    )
        
        # All checks passed - audit log success
        logger.info(
            "Device capability check passed",
            extra={
                "device_id": device_id,
                "device_name": device.name,
                "device_environment": device.environment,
                "required_capabilities": [c.value for c in (required_capabilities or [])],
                "allowed_environments": allowed_environments,
                "operation": operation or "unknown",
                "check_type": "all",
                "result": "allowed",
            },
        )
        
        return device

    async def _invalidate_device_cache(self, device_id: str, reason: str = "state_change") -> None:
        """Invalidate device-related cache entries.

        Args:
            device_id: Device identifier
            reason: Reason for invalidation
        """
        try:
            from routeros_mcp.infra.observability.resource_cache import get_cache

            cache = get_cache()

            # Invalidate all device-related resources
            count = await cache.invalidate_device(device_id)

            if count > 0:
                metrics.record_cache_invalidation("device", reason)
                logger.info(
                    f"Invalidated device cache entries for device {device_id}",
                    extra={"device_id": device_id, "invalidated_count": count, "reason": reason}
                )
        except RuntimeError:
            # Cache not initialized - skip invalidation
            logger.debug("Cache not initialized, skipping device cache invalidation")
