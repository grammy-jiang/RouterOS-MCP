"""System service for system information and metrics collection.

Provides operations for querying RouterOS system information,
including resource metrics, identity, and package information.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import SystemResource
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.utils import parse_routeros_uptime
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSClientError,
    RouterOSNetworkError,
    RouterOSServerError,
    RouterOSTimeoutError,
)
from routeros_mcp.mcp.errors import AuthenticationError

logger = logging.getLogger(__name__)


class SystemService:
    """Service for RouterOS system information operations.

    Responsibilities:
    - Query system resource metrics (CPU, memory, uptime)
    - Retrieve system identity and hardware information
    - List installed packages
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = SystemService(session, settings)

            # Get system overview
            overview = await service.get_system_overview("dev-lab-01")

            # Get resource metrics
            resource = await service.get_system_resource("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize system service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def get_system_overview(
        self,
        device_id: str,
    ) -> dict:
        """Get comprehensive system overview for a device.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with system overview data

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        device = await self.device_service.get_device(device_id)

        rest_error: str | None = None
        transport_used = "rest"
        fallback_used = False

        try:
            resource_data, identity = await self._get_overview_via_rest(device_id)
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSClientError,
            RouterOSServerError,
            AuthenticationError,
            Exception,
        ) as rest_exc:
            rest_error = str(rest_exc)
            transport_used = "ssh"
            fallback_used = True

            # Try SSH fallback using the whitelisted health probe
            try:
                resource_data, identity = await self._get_overview_via_ssh(device)
            except Exception as ssh_exc:
                # Preserve REST failure context while surfacing SSH error
                raise RuntimeError(
                    f"System overview failed via REST and SSH: rest_error={rest_error}, ssh_error={ssh_exc}"
                ) from ssh_exc

        overview = self._build_overview(
            device=device,
            resource_data=resource_data,
            identity=identity,
            transport=transport_used,
            fallback_used=fallback_used,
            rest_error=rest_error,
        )

        return overview

    async def get_system_resource(
        self,
        device_id: str,
    ) -> SystemResource:
        """Get system resource metrics as domain model.

        Args:
            device_id: Device identifier

        Returns:
            SystemResource domain model

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        device = await self.device_service.get_device(device_id)
        resource_data, identity = await self._get_overview_via_rest(device_id)

        # Parse metrics
        cpu_usage = float(resource_data.get("cpu-load", 0))
        cpu_count = resource_data.get("cpu-count", 1)

        memory_total = resource_data.get("total-memory", 0)
        memory_free = resource_data.get("free-memory", 0)
        memory_used = memory_total - memory_free
        memory_usage_pct = (
            (memory_used / memory_total * 100) if memory_total > 0 else 0.0
        )

        uptime = parse_routeros_uptime(resource_data.get("uptime", "0s"))

        return SystemResource(
            device_id=device_id,
            timestamp=datetime.now(UTC),
            routeros_version=resource_data.get("version", "Unknown"),
            system_identity=identity or device.system_identity,
            hardware_model=resource_data.get("board-name"),
            uptime_seconds=uptime,
            cpu_usage_percent=cpu_usage,
            cpu_count=cpu_count,
            memory_total_bytes=memory_total,
            memory_free_bytes=memory_free,
            memory_used_bytes=memory_used,
            memory_usage_percent=memory_usage_pct,
        )

    async def _get_overview_via_rest(self, device_id: str) -> tuple[dict[str, Any], str | None]:
        """Fetch system overview via REST.

        Returns resource data and identity (may be None).
        """

        client = await self.device_service.get_rest_client(device_id)

        try:
            resource_data = await client.get("/rest/system/resource")
            try:
                identity_data = await client.get("/rest/system/identity")
                identity = identity_data.get("name") if isinstance(identity_data, dict) else None
            except Exception:
                identity = None

            return resource_data, identity
        finally:
            await client.close()

    async def _get_packages_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        client = await self.device_service.get_rest_client(device_id)

        try:
            packages = await client.get("/rest/system/package")
            # REST typically returns only installed packages; we still normalize
            # to a consistent schema and mark them as installed.
            return self._normalize_packages(packages)
        finally:
            await client.close()

    async def _get_packages_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            # RouterOS standard table output is the most information-dense format
            # (includes AVAILABLE packages and SIZE). Use it directly.
            plain_output = await ssh_client.execute("/system/package/print")
            packages = self._normalize_packages(
                self._parse_system_package_print_table(plain_output)
            )

            if not packages:
                logger.warning(
                    "SSH package output was unparseable",
                    extra={
                        "device_id": device_id,
                        "plain_excerpt": (plain_output or "")[:500],
                    },
                )
                return []

            return packages
        finally:
            await ssh_client.close()

    def _normalize_packages(self, packages: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []

        if not isinstance(packages, list):
            return normalized

        for pkg in packages:
            if not isinstance(pkg, dict):
                continue

            name = pkg.get("name", "Unknown")

            # Extract common fields across REST/SSH parsers.
            version = pkg.get("version", pkg.get("ver", None))
            build_time = pkg.get("build-time", pkg.get("build_time", None))
            size = pkg.get("size", pkg.get("package-size", pkg.get("package_size", None)))

            flags = pkg.get("flags")
            available_flag = pkg.get("available")

            disabled_value = pkg.get("disabled", None)
            if disabled_value is None and isinstance(flags, str):
                disabled = "X" in flags
            elif isinstance(disabled_value, str):
                disabled = disabled_value.lower() in {"true", "yes", "on"}
            else:
                disabled = bool(disabled_value) if disabled_value is not None else False

            # Infer installed status; do not discard uninstalled packages.
            installed = bool(version and build_time)

            if available_flag is None and isinstance(flags, str):
                available = "A" in flags
            else:
                available = bool(available_flag) if available_flag is not None else False

            normalized.append(
                {
                    "name": name,
                    "installed": installed,
                    "available": available,
                    "version": version,
                    "build_time": build_time,
                    "size": size,
                    "disabled": disabled,
                    "flags": flags,
                }
            )

        return normalized

    async def _get_clock_via_rest(self, device_id: str) -> dict[str, Any]:
        client = await self.device_service.get_rest_client(device_id)

        try:
            data = await client.get("/rest/system/clock")
            return dict(data) if isinstance(data, dict) else {}
        finally:
            await client.close()

    async def _get_clock_via_ssh(self, device_id: str) -> dict[str, Any]:
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/system/clock/print")
            return self._parse_clock_print_output(output)
        finally:
            await ssh_client.close()
    
    @staticmethod
    def _parse_clock_print_output(output: str) -> dict[str, Any]:
        """Parse /system/clock/print output (key: value format)."""
        result = {}
        for line in output.splitlines():
            line = line.strip()
            if ':' not in line:
                continue
            key, _, value = line.partition(':')
            key = key.strip()
            value = value.strip()
            if key and value:
                result[key] = value
        return result

    @staticmethod
    def _parse_as_value_blocks(output: str) -> list[dict[str, Any]]:
        """Parse RouterOS `as-value` output that may contain multiple blocks.

        **DEPRECATED**: as-value is not a reliable RouterOS argument - some builds
        return empty output. This method is kept only for backward compatibility
        with existing tests. Production code should use standard print format
        with `_parse_ssh_kv_output()` or table parsers instead.

        Example format:
        key1=value1
        key2=value2

        key1=value3
        key2=value4
        """

        def _strip_quotes(value: str) -> str:
            v = value.strip()
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                return v[1:-1]
            return v

        def _parse_kv_pairs_from_line(line: str) -> dict[str, str]:
            """Parse a single RouterOS CLI line that may contain multiple key=value pairs.

            RouterOS frequently emits one of these shapes:
            - multi-line: `key=value` per line (one record)
            - single-line per row: `0 name=routeros version=7.20.6 build-time=2025-12-04 12:00:39`

            Values may contain spaces (e.g., build-time), so we treat tokens without
            `=` as continuations of the previous value.
            """
            pairs: dict[str, str] = {}
            tokens = line.strip().split()
            current_key: str | None = None
            current_val_tokens: list[str] = []

            def flush_pair() -> None:
                nonlocal current_key, current_val_tokens
                if current_key is None:
                    return
                pairs[current_key] = _strip_quotes(" ".join(current_val_tokens).strip())
                current_key = None
                current_val_tokens = []

            for tok in tokens:
                if "=" in tok:
                    # Start of a new key=value; close previous if present.
                    flush_pair()
                    key, val = tok.split("=", 1)
                    # Ignore positional index tokens which sometimes appear as `0`.
                    if key.isdigit():
                        continue
                    current_key = key
                    current_val_tokens = [val]
                else:
                    if current_key is not None:
                        current_val_tokens.append(tok)

            flush_pair()
            return pairs

        blocks: list[dict[str, Any]] = []
        current: dict[str, Any] = {}

        def flush_current() -> None:
            nonlocal current
            if current:
                blocks.append(current)
                current = {}

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                flush_current()
                continue
            if "=" not in line:
                continue

            kvs = _parse_kv_pairs_from_line(line)
            if not kvs:
                continue

            current.update(kvs)

            # Heuristic: if a single line produced multiple key/value pairs,
            # it's very likely a complete record (e.g., one table row).
            if len(kvs) > 1:
                flush_current()

        flush_current()
        return blocks

    @staticmethod
    def _parse_system_package_print_table(output: str) -> list[dict[str, Any]]:
        """Parse `/system/package/print` table output into package dictionaries.

        This is a best-effort parser for the human-readable table output.
        Unlike REST, this output includes both installed packages and AVAILABLE
        packages (not installed). We preserve as much information as we can,
        including flags and size.
        """

        packages: list[dict[str, Any]] = []

        for raw_line in output.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # Skip headers.
            if line.startswith("Flags:") or line.startswith("Columns:"):
                continue
            if line.startswith("#"):
                continue

            # Find build time like: 2025-12-04 12:00:39 (installed packages)
            import re

            m = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})", line)
            # Size is usually the last token (e.g., 864.1KiB, 8.8MiB)
            size: str | None = None
            if line.split():
                last = line.split()[-1]
                # Rough heuristic: size tokens usually contain a unit suffix.
                if any(u in last for u in ("KiB", "MiB", "GiB", "B")):
                    size = last

            # Two formats exist:
            # - Installed: "0 wireless 7.20.6 2025-12-04 12:00:39 864.1KiB"
            # - Available (not installed): "5 XA calea 20.1KiB"
            if m:
                build_time = f"{m.group(1)} {m.group(2)}"
                before = line[: m.start()].strip()
                tokens = before.split()
                if len(tokens) < 3:
                    continue

                flags_token: str | None = None
                name_idx = 1
                if len(tokens) >= 4 and set(tokens[1]).issubset({"X", "A"}):
                    flags_token = tokens[1]
                    name_idx = 2

                name = tokens[name_idx] if len(tokens) > name_idx else None
                version = tokens[name_idx + 1] if len(tokens) > name_idx + 1 else None
                if not name:
                    continue

                packages.append(
                    {
                        "name": name,
                        "version": version,
                        "build-time": build_time,
                        "size": size,
                        "flags": flags_token,
                        "available": bool(flags_token and "A" in flags_token),
                        "disabled": bool(flags_token and "X" in flags_token),
                    }
                )
            else:
                tokens = line.split()
                if len(tokens) < 3:
                    continue

                flags_token: str | None = None
                name_idx = 1
                if len(tokens) >= 4 and set(tokens[1]).issubset({"X", "A"}):
                    flags_token = tokens[1]
                    name_idx = 2

                name = tokens[name_idx] if len(tokens) > name_idx else None
                if not name:
                    continue

                packages.append(
                    {
                        "name": name,
                        "version": None,
                        "build-time": None,
                        "size": size,
                        "flags": flags_token,
                        "available": bool(flags_token and "A" in flags_token),
                        "disabled": bool(flags_token and "X" in flags_token),
                    }
                )

        return packages

    async def _get_overview_via_ssh(self, device) -> tuple[dict[str, Any], str | None]:
        """Fallback path: fetch minimal system resource via SSH health probe."""

        ssh_client = await self.device_service.get_ssh_client(device.id)

        try:
            # Use standard print format (key: value) consistently
            output = await ssh_client.execute("/system/resource/print")
            resource_raw = self._parse_ssh_resource_output(output)
            resource_data = self._coerce_resource_values(resource_raw)

            if not resource_data:
                raise RuntimeError("SSH resource output was empty")

            # Try to retrieve identity over SSH; fall back to stored device identity
            identity = device.system_identity or "Unknown"
            try:
                identity_output = await ssh_client.execute("/system/identity/print")
                identity_kv = self._parse_ssh_kv_output(identity_output)
                identity = identity_kv.get("name", identity) or device.system_identity or "Unknown"
            except Exception as identity_exc:  # pragma: no cover - best-effort
                logger.warning(
                    "SSH identity fetch failed; using stored identity",
                    exc_info=identity_exc,
                    extra={"device_id": device.id},
                )

            return resource_data, identity
        finally:
            await ssh_client.close()

    def _build_overview(
        self,
        device,
        resource_data: dict[str, Any],
        identity: str | None,
        transport: str,
        fallback_used: bool,
        rest_error: str | None,
    ) -> dict[str, Any]:
        """Normalize overview fields into a consistent shape."""

        # Ensure numeric fields are numbers even when coming from SSH text output
        resource_data = self._coerce_resource_values(resource_data)

        cpu_usage = float(resource_data.get("cpu-load", 0))
        memory_total = resource_data.get("total-memory", 0)
        memory_free = resource_data.get("free-memory", 0)
        memory_used = memory_total - memory_free
        memory_usage_pct = (
            (memory_used / memory_total * 100) if memory_total > 0 else 0.0
        )

        uptime = parse_routeros_uptime(resource_data.get("uptime", "0s"))

        overview = {
            "device_id": device.id,
            "device_name": device.name,
            "system_identity": identity or device.system_identity or "Unknown",
            "routeros_version": resource_data.get("version", "Unknown"),
            "hardware_model": resource_data.get("board-name", "Unknown"),
            "architecture": resource_data.get("architecture-name", "Unknown"),
            "cpu_count": resource_data.get("cpu-count", 1),
            "cpu_usage_percent": cpu_usage,
            "memory_total_bytes": memory_total,
            "memory_used_bytes": memory_used,
            "memory_free_bytes": memory_free,
            "memory_usage_percent": memory_usage_pct,
            "uptime_seconds": uptime,
            "uptime_formatted": resource_data.get("uptime", "0s"),
            "timestamp": datetime.now(UTC).isoformat(),
            "transport": transport,
            "fallback_used": fallback_used,
            "rest_error": rest_error,
        }

        return overview

    @staticmethod
    def _parse_ssh_kv_output(output: str, delimiters: tuple[str, ...] = ("=", ":")) -> dict[str, Any]:
        """Parse RouterOS CLI key/value output using supported delimiters.

        Supports both `key=value` (DEPRECATED as-value format) and `key: value` (standard format).
        Note: as-value is not a valid RouterOS argument and should never be used.
        """

        data: dict[str, Any] = {}
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            for delim in delimiters:
                if delim in line:
                    key, value = line.split(delim, 1)
                    data[key.strip()] = value.strip()
                    break

        return data

    @staticmethod
    def _parse_ssh_resource_output(output: str) -> dict[str, Any]:
        """Parse `/system/resource/print` output (standard colon-separated format) into a dict."""

        return SystemService._parse_ssh_kv_output(output)

    @staticmethod
    def _coerce_resource_values(resource_data: dict[str, Any]) -> dict[str, Any]:
        """Ensure numeric fields are numbers; leave others untouched."""

        def _parse_size_bytes(value: Any, default: int = 0) -> int:
            if isinstance(value, (int, float)):
                return int(value)
            if not isinstance(value, str):
                return default

            raw = value.strip()
            units = {
                "kib": 1024,
                "kb": 1000,
                "mib": 1024**2,
                "mb": 1000**2,
                "gib": 1024**3,
                "gb": 1000**3,
            }

            # Split numeric prefix and unit suffix
            num_part = ""
            unit_part = ""
            for ch in raw:
                if (ch.isdigit() or ch in {".", ","}) and unit_part == "":
                    num_part += ch
                else:
                    unit_part += ch

            unit_part = unit_part.strip().lower()
            if num_part == "":
                return default

            # Normalize decimal comma
            num_part = num_part.replace(",", ".")
            try:
                num_val = float(num_part)
            except ValueError:
                return default

            if unit_part in units:
                return int(num_val * units[unit_part])

            # Fallback: no recognized unit
            try:
                return int(num_val)
            except ValueError:
                return default

        def _to_int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        def _to_float(value: Any, default: float = 0.0) -> float:
            if isinstance(value, str) and value.endswith("%"):
                value = value[:-1]
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        coerced = dict(resource_data)
        coerced["total-memory"] = _parse_size_bytes(coerced.get("total-memory", 0))
        coerced["free-memory"] = _parse_size_bytes(coerced.get("free-memory", 0))
        coerced["cpu-count"] = _to_int(coerced.get("cpu-count", 1), default=1)
        coerced["cpu-load"] = _to_float(coerced.get("cpu-load", 0.0))

        return coerced

    async def get_system_packages(
        self,
        device_id: str,
    ) -> list[dict]:
        """Get list of installed packages.

        Args:
            device_id: Device identifier

        Returns:
            List of package information dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            packages = await self._get_packages_via_rest(device_id)
            transport = "rest"
            fallback_used = False
            rest_error = None
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSClientError,
            RouterOSServerError,
            AuthenticationError,
            Exception,
        ) as rest_exc:
            transport = "ssh"
            fallback_used = True
            rest_error = str(rest_exc)
            packages = await self._get_packages_via_ssh(device_id)

        for pkg in packages:
            pkg.setdefault("transport", transport)
            pkg.setdefault("fallback_used", fallback_used)
            pkg.setdefault("rest_error", rest_error)

        return packages

    async def get_system_clock(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Get current system time and timezone with REST→SSH fallback."""

        await self.device_service.get_device(device_id)

        try:
            clock = await self._get_clock_via_rest(device_id)
            transport = "rest"
            fallback_used = False
            rest_error = None
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSClientError,
            RouterOSServerError,
            AuthenticationError,
            Exception,
        ) as rest_exc:
            transport = "ssh"
            fallback_used = True
            rest_error = str(rest_exc)
            clock = await self._get_clock_via_ssh(device_id)

        clock.update(
            {
                "transport": transport,
                "fallback_used": fallback_used,
                "rest_error": rest_error,
            }
        )

        return clock

    async def update_system_identity(
        self,
        device_id: str,
        new_identity: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update system identity (hostname).

        Args:
            device_id: Device identifier
            new_identity: New identity name
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with update result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValueError: If identity is invalid
        """
        # Validate identity
        if not new_identity or not new_identity.strip():
            raise ValueError("System identity cannot be empty")

        if len(new_identity) > 255:
            raise ValueError(
                f"System identity too long ({len(new_identity)} chars). "
                "Maximum 255 characters allowed."
            )

        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get current identity
            current_data = await client.get("/rest/system/identity")
            current_identity = current_data.get("name", "Unknown")

            # Check if change is needed
            if current_identity == new_identity:
                return {
                    "changed": False,
                    "old_identity": current_identity,
                    "new_identity": new_identity,
                    "dry_run": dry_run,
                }

            # Dry-run: return planned changes
            if dry_run:
                from routeros_mcp.security.safeguards import create_dry_run_response

                return create_dry_run_response(
                    operation="system/set-identity",
                    device_id=device_id,
                    planned_changes={
                        "old_identity": current_identity,
                        "new_identity": new_identity,
                    },
                )

            # Apply change
            await client.patch("/rest/system/identity", {"name": new_identity})

            logger.info(
                f"Updated system identity: {current_identity} -> {new_identity}",
                extra={"device_id": device_id},
            )

            return {
                "changed": True,
                "old_identity": current_identity,
                "new_identity": new_identity,
                "dry_run": False,
            }

        finally:
            await client.close()
