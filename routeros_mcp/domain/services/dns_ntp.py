"""DNS and NTP service for DNS and time synchronization operations.

Provides operations for querying RouterOS DNS and NTP configuration
and status.
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.observability import metrics
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSClientError,
    RouterOSNetworkError,
    RouterOSServerError,
    RouterOSTimeoutError,
)

logger = logging.getLogger(__name__)

# Safety limits
MAX_DNS_CACHE_ENTRIES = 1000


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"yes", "true", "1", "on", "enabled"}


def _parse_duration_to_ms(value: Any) -> float:
    """Convert RouterOS duration strings (s/ms/us) to milliseconds."""

    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip().lower()
    if not text:
        return 0.0

    sign = -1 if text.startswith("-") else 1
    if text[0] in {"-", "+"}:
        text = text[1:]

    def _safe_float(raw: str) -> float:
        try:
            return float(raw)
        except ValueError:
            return 0.0

    # Composite durations can appear in RouterOS output, e.g. `5ms945us`.
    # Support: [<seconds>s][<milliseconds>ms][<microseconds>us]
    import re

    m = re.match(
        r"^(?:(?P<s>[0-9]*\.?[0-9]+)s)?(?:(?P<ms>[0-9]*\.?[0-9]+)ms)?(?:(?P<us>[0-9]+)(?:us|µs))?$",
        text,
    )
    if m and (m.group("s") or m.group("ms") or m.group("us")):
        seconds = _safe_float(m.group("s") or "0")
        millis = _safe_float(m.group("ms") or "0")
        micros = _safe_float(m.group("us") or "0")
        return sign * ((seconds * 1000.0) + millis + (micros / 1000.0))

    if text.endswith("ms"):
        return sign * _safe_float(text[:-2])
    if text.endswith("us") or text.endswith("µs"):
        return sign * (_safe_float(text[:-2]) / 1000.0)
    if text.endswith("s"):
        return sign * (_safe_float(text[:-1]) * 1000.0)

    return sign * _safe_float(text)


class DNSNTPService:
    """Service for RouterOS DNS and NTP operations.

    Responsibilities:
    - Query DNS configuration and cache
    - Query NTP configuration and sync status
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = DNSNTPService(session, settings)

            # Get DNS status
            dns_status = await service.get_dns_status("dev-lab-01")

            # Get DNS cache
            cache = await service.get_dns_cache("dev-lab-01", limit=100)

            # Get NTP status
            ntp_status = await service.get_ntp_status("dev-lab-01")
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize DNS/NTP service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def get_dns_status(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Get DNS server configuration and cache statistics with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            DNS configuration dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            dns_status = await self._get_dns_status_via_rest(device_id)
            dns_status["transport"] = "rest"
            dns_status["fallback_used"] = False
            dns_status["rest_error"] = None
            return dns_status
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST get_dns_status failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            try:
                dns_status = await self._get_dns_status_via_ssh(device_id)
                dns_status["transport"] = "ssh"
                dns_status["fallback_used"] = True
                dns_status["rest_error"] = str(rest_exc)
                return dns_status
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH get_dns_status failed",
                    exc_info=ssh_exc,
                    extra={
                        "device_id": device_id,
                        "rest_error": str(rest_exc),
                    },
                )
                raise RuntimeError(
                    f"Get DNS status failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_dns_status_via_rest(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Fetch DNS status via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            dns_data = await client.get("/rest/ip/dns")

            # Parse DNS servers (comma-separated string or list to list)
            servers_val = dns_data.get("servers", "")
            if isinstance(servers_val, str):
                dns_servers = [s.strip() for s in servers_val.split(",") if s.strip()]
            elif isinstance(servers_val, list):
                dns_servers = [str(s).strip() for s in servers_val if str(s).strip()]
            else:
                dns_servers = []

            # Parse dynamic servers
            dynamic_val = dns_data.get("dynamic-servers", "")
            if isinstance(dynamic_val, str):
                dynamic_servers = [s.strip() for s in dynamic_val.split(",") if s.strip()]
            elif isinstance(dynamic_val, list):
                dynamic_servers = [str(s).strip() for s in dynamic_val if str(s).strip()]
            else:
                dynamic_servers = []

            result = {
                "dns_servers": dns_servers,
                "dynamic_servers": dynamic_servers,
                "allow_remote_requests": dns_data.get("allow-remote-requests", False),
                "cache_size_kb": dns_data.get("cache-size", 2048),
                "cache_used_kb": dns_data.get("cache-used", 0),
            }
            
            # Add optional fields if present
            if "use-doh-server" in dns_data:
                result["use_doh_server"] = dns_data.get("use-doh-server")
            if "verify-doh-cert" in dns_data:
                result["verify_doh_cert"] = dns_data.get("verify-doh-cert", False)
            if "doh-max-server-connections" in dns_data:
                result["doh_max_server_connections"] = dns_data.get("doh-max-server-connections")
            if "doh-max-concurrent-queries" in dns_data:
                result["doh_max_concurrent_queries"] = dns_data.get("doh-max-concurrent-queries")
            if "doh-timeout" in dns_data:
                result["doh_timeout"] = dns_data.get("doh-timeout")
            if "max-udp-packet-size" in dns_data:
                result["max_udp_packet_size"] = dns_data.get("max-udp-packet-size")
            if "query-server-timeout" in dns_data:
                result["query_server_timeout"] = dns_data.get("query-server-timeout")
            if "query-total-timeout" in dns_data:
                result["query_total_timeout"] = dns_data.get("query-total-timeout")
            if "max-concurrent-queries" in dns_data:
                result["max_concurrent_queries"] = dns_data.get("max-concurrent-queries")
            if "max-concurrent-tcp-sessions" in dns_data:
                result["max_concurrent_tcp_sessions"] = dns_data.get("max-concurrent-tcp-sessions")
            if "cache-max-ttl" in dns_data:
                result["cache_max_ttl"] = dns_data.get("cache-max-ttl")
            if "address-list-extra-time" in dns_data:
                result["address_list_extra_time"] = dns_data.get("address-list-extra-time")
            if "vrf" in dns_data:
                result["vrf"] = dns_data.get("vrf")
            if "mdns-repeat-ifaces" in dns_data:
                result["mdns_repeat_ifaces"] = dns_data.get("mdns-repeat-ifaces")
            
            return result

        finally:
            await client.close()

    async def _get_dns_status_via_ssh(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Fetch DNS status via SSH CLI.
        
        Handles RouterOS output format where servers can be on multiple lines:
            servers: 1.1.1.1
                     1.0.0.1
                     8.8.8.8
        """
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/dns/print")

            # Parse /ip/dns/print output (key: value format with multi-line continuation)
            dns_servers: list[str] = []
            dynamic_servers: list[str] = []
            result: dict[str, Any] = {
                "dns_servers": [],
                "dynamic_servers": [],
                "allow_remote_requests": False,
                "cache_size_kb": 2048,
                "cache_used_kb": 0,
            }
            current_key: str | None = None

            lines = output.strip().split("\n")
            for line in lines:
                if not line.strip() or line.startswith("Flags:") or line.startswith("#"):
                    continue

                # Check if this is a continuation line (starts with whitespace, no colon)
                if line[0].isspace() and ":" not in line and current_key:
                    # Continuation line - add to current key's value
                    value = line.strip()
                    if current_key == "servers" and value:
                        dns_servers.append(value)
                    elif current_key == "dynamic-servers" and value:
                        dynamic_servers.append(value)
                    continue

                # Parse key: value line
                if ":" in line:
                    parts = line.split(":", 1)
                    key = parts[0].strip().lower()
                    value = parts[1].strip()
                    current_key = key

                    if key == "servers":
                        # Reset and start collecting servers
                        dns_servers = []
                        if value:
                            if "," in value:
                                dns_servers = [s.strip() for s in value.split(",") if s.strip()]
                            else:
                                dns_servers = [value]
                    elif key == "dynamic-servers":
                        dynamic_servers = []
                        if value:
                            if "," in value:
                                dynamic_servers = [s.strip() for s in value.split(",") if s.strip()]
                            else:
                                dynamic_servers = [value]
                    elif key == "use-doh-server":
                        result["use_doh_server"] = value if value else None
                    elif key == "verify-doh-cert":
                        result["verify_doh_cert"] = value.lower() in ("yes", "true")
                    elif key == "doh-max-server-connections":
                        try:
                            result["doh_max_server_connections"] = int(value)
                        except ValueError:
                            result["doh_max_server_connections"] = None
                    elif key == "doh-max-concurrent-queries":
                        try:
                            result["doh_max_concurrent_queries"] = int(value)
                        except ValueError:
                            result["doh_max_concurrent_queries"] = None
                    elif key == "doh-timeout":
                        result["doh_timeout"] = value
                    elif key == "allow-remote-requests":
                        result["allow_remote_requests"] = value.lower() in ("yes", "true")
                    elif key == "max-udp-packet-size":
                        try:
                            result["max_udp_packet_size"] = int(value)
                        except ValueError:
                            result["max_udp_packet_size"] = None
                    elif key == "query-server-timeout":
                        result["query_server_timeout"] = value
                    elif key == "query-total-timeout":
                        result["query_total_timeout"] = value
                    elif key == "max-concurrent-queries":
                        try:
                            result["max_concurrent_queries"] = int(value)
                        except ValueError:
                            result["max_concurrent_queries"] = None
                    elif key == "max-concurrent-tcp-sessions":
                        try:
                            result["max_concurrent_tcp_sessions"] = int(value)
                        except ValueError:
                            result["max_concurrent_tcp_sessions"] = None
                    elif key == "cache-size":
                        try:
                            value_clean = value.replace("KiB", "").replace("KB", "").strip()
                            result["cache_size_kb"] = int(value_clean)
                        except ValueError:
                            pass
                    elif key == "cache-max-ttl":
                        result["cache_max_ttl"] = value
                    elif key == "address-list-extra-time":
                        result["address_list_extra_time"] = value
                    elif key == "vrf":
                        result["vrf"] = value
                    elif key == "mdns-repeat-ifaces":
                        result["mdns_repeat_ifaces"] = value if value else None
                    elif key == "cache-used":
                        try:
                            value_clean = value.replace("KiB", "").replace("KB", "").strip()
                            result["cache_used_kb"] = int(value_clean)
                        except ValueError:
                            pass

            result["dns_servers"] = dns_servers
            result["dynamic_servers"] = dynamic_servers
            return result

        finally:
            await ssh_client.close()

    async def get_dns_cache(
        self,
        device_id: str,
        limit: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        """View DNS cache entries (recently resolved domains) with REST→SSH fallback.

        Args:
            device_id: Device identifier
            limit: Maximum number of entries to return (max 1000)

        Returns:
            Tuple of (cache_entries, total_count)

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValidationError: If limit exceeds maximum
        """
        from routeros_mcp.mcp.errors import ValidationError

        await self.device_service.get_device(device_id)

        # Enforce safety limit
        if limit > MAX_DNS_CACHE_ENTRIES:
            raise ValidationError(
                f"DNS cache limit cannot exceed {MAX_DNS_CACHE_ENTRIES} entries",
                data={"requested_limit": limit, "max_limit": MAX_DNS_CACHE_ENTRIES},
            )

        try:
            result, total_count = await self._get_dns_cache_via_rest(device_id, limit)
            return (
                [dict(r, transport="rest", fallback_used=False, rest_error=None) for r in result],
                total_count,
            )
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST get_dns_cache failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id, "limit": limit},
            )
            try:
                result, total_count = await self._get_dns_cache_via_ssh(device_id, limit)
                return (
                    [
                        dict(r, transport="ssh", fallback_used=True, rest_error=str(rest_exc))
                        for r in result
                    ],
                    total_count,
                )
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH get_dns_cache failed",
                    exc_info=ssh_exc,
                    extra={
                        "device_id": device_id,
                        "limit": limit,
                        "rest_error": str(rest_exc),
                    },
                )
                raise RuntimeError(
                    f"Get DNS cache failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_dns_cache_via_rest(
        self,
        device_id: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Fetch DNS cache via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            cache_data = await client.get("/rest/ip/dns/cache")

            # Normalize cache data
            result: list[dict[str, Any]] = []
            if isinstance(cache_data, list):
                for i, entry in enumerate(cache_data):
                    if i >= limit:
                        break
                    if isinstance(entry, dict):
                        result.append({
                            "name": entry.get("name", ""),
                            "type": entry.get("type", ""),
                            "data": entry.get("data", ""),
                            "ttl": entry.get("ttl", 0),
                        })

            total_count = len(cache_data) if isinstance(cache_data, list) else 0
            return result, total_count

        finally:
            await client.close()

    async def _get_dns_cache_via_ssh(
        self,
        device_id: str,
        limit: int,
    ) -> tuple[list[dict[str, Any]], int]:
        """Fetch DNS cache via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/dns/cache/print")

            # Parse /ip/dns/cache/print output (table format)
            result: list[dict[str, Any]] = []
            lines = output.strip().split("\n")

            for line in lines:
                if not line.strip() or line.startswith("Flags:") or line.startswith("#"):
                    continue

                if len(result) >= limit:
                    break

                # Table format: [id] [flags?] [name] [type] [data] [ttl]
                parts = line.split()
                if not parts or not (parts[0][0] == "*" or parts[0][0].isdigit()):
                    continue

                try:
                    idx = 1
                    # Check if second part is flags
                    if len(parts) > 1 and len(parts[1]) <= 3 and not parts[1][0].isdigit():
                        idx = 2

                    if len(parts) > idx + 2:
                        name = parts[idx]
                        type_val = parts[idx + 1]
                        data = parts[idx + 2]
                        ttl = 0

                        if len(parts) > idx + 3:
                            try:
                                ttl = int(parts[idx + 3])
                            except ValueError:
                                pass

                        result.append({
                            "name": name,
                            "type": type_val,
                            "data": data,
                            "ttl": ttl,
                        })
                except (IndexError, ValueError) as e:
                    logger.debug(f"Failed to parse DNS cache line: {line}", exc_info=e)
                    continue

            return result, len(result)

        finally:
            await ssh_client.close()

    async def get_ntp_status(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Get NTP client configuration and synchronization status with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            NTP status dictionary

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            ntp_status = await self._get_ntp_status_via_rest(device_id)
            ntp_status["transport"] = "rest"
            ntp_status["fallback_used"] = False
            ntp_status["rest_error"] = None
            return ntp_status
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST get_ntp_status failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            try:
                ntp_status = await self._get_ntp_status_via_ssh(device_id)
                ntp_status["transport"] = "ssh"
                ntp_status["fallback_used"] = True
                ntp_status["rest_error"] = str(rest_exc)
                return ntp_status
            except Exception as ssh_exc:
                logger.error(
                    "Both REST and SSH get_ntp_status failed",
                    exc_info=ssh_exc,
                    extra={
                        "device_id": device_id,
                        "rest_error": str(rest_exc),
                    },
                )
                raise RuntimeError(
                    f"Get NTP status failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_ntp_status_via_rest(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Fetch NTP status via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get NTP client configuration
            ntp_config = await client.get("/rest/system/ntp/client")

            # Parse NTP servers (may be comma-separated or array)
            servers_str = ntp_config.get("servers", "")
            if isinstance(servers_str, str):
                ntp_servers = [s.strip() for s in servers_str.split(",") if s.strip()]
            elif isinstance(servers_str, list):
                ntp_servers = servers_str
            else:
                ntp_servers = []

            dynamic_servers_str = ntp_config.get("dynamic-servers", "")
            if isinstance(dynamic_servers_str, str):
                dynamic_servers = [s.strip() for s in dynamic_servers_str.split(",") if s.strip()]
            elif isinstance(dynamic_servers_str, list):
                dynamic_servers = dynamic_servers_str
            else:
                dynamic_servers = []

            monitor_data: dict[str, Any] = {}
            try:
                raw_monitor = await client.get("/rest/system/ntp/client/monitor")
                if isinstance(raw_monitor, list):
                    monitor_data = raw_monitor[0] if raw_monitor else {}
                elif isinstance(raw_monitor, dict):
                    monitor_data = raw_monitor
            except Exception:
                monitor_data = {}

            status = monitor_data.get("status")
            if status is None:
                synced_flag = monitor_data.get("synced")
                if synced_flag is not None:
                    status = "synchronized" if _parse_bool(synced_flag) else "not_synchronized"
            if status is None:
                status = "enabled" if ntp_config.get("enabled", False) else "disabled"

            stratum_val = monitor_data.get("stratum")
            try:
                stratum = int(stratum_val) if stratum_val is not None else 0
            except (TypeError, ValueError):
                stratum = 0

            offset_val = monitor_data.get("offset") or monitor_data.get("last-offset")
            offset_ms = _parse_duration_to_ms(offset_val)

            synced_server = monitor_data.get("server") or monitor_data.get("active-server")
            synced_stratum = monitor_data.get("active-stratum") or monitor_data.get("synced-stratum")
            try:
                synced_stratum_int = int(synced_stratum) if synced_stratum is not None else None
            except (TypeError, ValueError):
                synced_stratum_int = None

            result = {
                "enabled": ntp_config.get("enabled", False),
                "ntp_servers": ntp_servers,
                "dynamic_servers": dynamic_servers,
                "mode": ntp_config.get("mode", "unicast"),
                "status": status,
                "stratum": stratum,
                "offset_ms": offset_ms,
            }

            if synced_server:
                result["synced_server"] = synced_server
            if synced_stratum_int is not None:
                result["synced_stratum"] = synced_stratum_int
            if "vrf" in ntp_config:
                result["vrf"] = ntp_config.get("vrf")

            return result

        finally:
            await client.close()

    async def _get_ntp_status_via_ssh(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Fetch NTP status via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/system/ntp/client/print")

            # Parse /system/ntp/client/print output (key: value format and table rows)
            ntp_servers: list[str] = []
            dynamic_servers: list[str] = []
            table_servers: list[str] = []
            enabled = False
            mode = "unicast"
            status: str | None = None
            stratum: int | None = None
            synced_server: str | None = None
            synced_stratum: int | None = None
            offset_ms: float | None = None
            system_offset_ms: float | None = None
            last_offset_ms: float | None = None
            raw_fields: dict[str, Any] = {}
            current_key: str | None = None

            lines = output.strip().split("\n")
            for line in lines:
                if not line.strip() or line.startswith("Flags:") or line.startswith("#"):
                    continue

                # Continuation line for multi-value fields
                if line[0].isspace() and ":" not in line and current_key:
                    cont_value = line.strip()
                    if current_key == "servers" and cont_value:
                        ntp_servers.append(cont_value)
                    elif current_key == "dynamic-servers" and cont_value:
                        dynamic_servers.append(cont_value)
                    continue

                # Table rows (e.g., "0   pool.ntp.org  unicast  true")
                parts = line.split()
                if parts and parts[0][0].isdigit() and ":" not in line:
                    if len(parts) >= 2:
                        table_servers.append(parts[1])
                    if len(parts) >= 4:
                        sync_val = parts[3].lower()
                        if sync_val in ("true", "yes"):
                            status = "synchronized"
                    if len(parts) >= 3:
                        mode = parts[2]
                    continue

                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    current_key = key
                    raw_fields[key.replace("-", "_")] = value

                    if key == "servers":
                        ntp_servers = []
                        if value:
                            if "," in value:
                                ntp_servers = [s.strip() for s in value.split(",") if s.strip()]
                            else:
                                ntp_servers = [value]
                    elif key == "dynamic-servers":
                        dynamic_servers = []
                        if value:
                            if "," in value:
                                dynamic_servers = [s.strip() for s in value.split(",") if s.strip()]
                            else:
                                dynamic_servers = [value]
                    elif key == "enabled":
                        enabled = _parse_bool(value)
                    elif key == "mode":
                        mode = value
                    elif key in {"status", "state"}:
                        status = value or status
                    elif key in {"synced-server", "active-server", "primary-ntp"}:
                        synced_server = value
                    elif key == "stratum":
                        try:
                            stratum = int(value)
                        except (TypeError, ValueError):
                            stratum = stratum
                    elif key in {"synced-stratum", "active-stratum"}:
                        try:
                            synced_stratum = int(value)
                        except (TypeError, ValueError):
                            synced_stratum = synced_stratum
                        if stratum is None:
                            stratum = synced_stratum
                    elif key in {"offset", "primary-offset"}:
                        offset_ms = _parse_duration_to_ms(value)
                    elif key == "system-offset":
                        system_offset_ms = _parse_duration_to_ms(value)
                    elif key == "last-offset":
                        last_offset_ms = _parse_duration_to_ms(value)

            # Consolidate servers, preferring configured list then table-discovered
            combined_servers = ntp_servers or table_servers

            effective_status = status or ("enabled" if enabled else "disabled")
            effective_stratum = stratum if stratum is not None else 0
            effective_offset = (
                offset_ms
                if offset_ms is not None
                else (last_offset_ms if last_offset_ms is not None else (system_offset_ms or 0.0))
            )

            result: dict[str, Any] = {
                "enabled": enabled,
                "ntp_servers": combined_servers,
                "dynamic_servers": dynamic_servers,
                "mode": mode,
                "status": effective_status,
                "stratum": effective_stratum,
                "offset_ms": effective_offset,
            }

            if synced_server:
                result["synced_server"] = synced_server
            if synced_stratum is not None:
                result["synced_stratum"] = synced_stratum
            if system_offset_ms is not None:
                result["system_offset_ms"] = system_offset_ms
            if last_offset_ms is not None:
                result["last_offset_ms"] = last_offset_ms
            if raw_fields:
                result["raw_fields"] = raw_fields

            return result

        finally:
            await ssh_client.close()

    async def update_dns_servers(
        self,
        device_id: str,
        dns_servers: list[str],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update DNS server configuration.

        Args:
            device_id: Device identifier
            dns_servers: List of DNS server addresses
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with update result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValueError: If server addresses are invalid
        """
        from routeros_mcp.security.safeguards import (
            create_dry_run_response,
            validate_dns_servers,
        )

        # Validate DNS servers
        validate_dns_servers(dns_servers)

        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get current DNS configuration
            current_data = await client.get("/rest/ip/dns")
            current_servers_str = current_data.get("servers", "")
            current_servers = [
                s.strip() for s in current_servers_str.split(",") if s.strip()
            ]

            # Check if change is needed
            if set(current_servers) == set(dns_servers):
                return {
                    "changed": False,
                    "old_servers": current_servers,
                    "new_servers": dns_servers,
                    "dry_run": dry_run,
                }

            # Dry-run: return planned changes
            if dry_run:
                return create_dry_run_response(
                    operation="dns/update-servers",
                    device_id=device_id,
                    planned_changes={
                        "old_servers": current_servers,
                        "new_servers": dns_servers,
                    },
                )

            # Apply change
            servers_str = ",".join(dns_servers)
            await client.patch("/rest/ip/dns", {"servers": servers_str})

            logger.info(
                f"Updated DNS servers: {current_servers} -> {dns_servers}",
                extra={"device_id": device_id},
            )

            # Invalidate DNS cache after successful update
            if self.settings.mcp_resource_cache_auto_invalidate:
                await self._invalidate_dns_cache(device_id)

            return {
                "changed": True,
                "old_servers": current_servers,
                "new_servers": dns_servers,
                "dry_run": False,
            }

        finally:
            await client.close()

    async def flush_dns_cache(
        self,
        device_id: str,
    ) -> dict[str, Any]:
        """Flush (clear) DNS cache.

        Args:
            device_id: Device identifier

        Returns:
            Dictionary with flush result

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get cache size before flush (for reporting)
            try:
                cache_data = await client.get("/rest/ip/dns/cache")
                entries_before = len(cache_data) if isinstance(cache_data, list) else 0
            except Exception:
                entries_before = 0

            # Flush cache
            await client.post("/rest/ip/dns/cache/flush", {})

            logger.info(
                f"Flushed DNS cache ({entries_before} entries)",
                extra={"device_id": device_id},
            )

            # Invalidate DNS cache after flush
            if self.settings.mcp_resource_cache_auto_invalidate:
                await self._invalidate_dns_cache(device_id)

            return {
                "changed": True,
                "entries_flushed": entries_before,
            }

        finally:
            await client.close()

    async def update_ntp_servers(
        self,
        device_id: str,
        ntp_servers: list[str],
        enabled: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Update NTP server configuration.

        Args:
            device_id: Device identifier
            ntp_servers: List of NTP server addresses
            enabled: Enable NTP client
            dry_run: If True, only return planned changes without applying

        Returns:
            Dictionary with update result

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValueError: If server addresses are invalid
        """
        from routeros_mcp.security.safeguards import (
            create_dry_run_response,
            validate_ntp_servers,
        )

        # Validate NTP servers
        validate_ntp_servers(ntp_servers)

        await self.device_service.get_device(device_id)
        client = await self.device_service.get_rest_client(device_id)

        try:
            # Get current NTP configuration
            current_data = await client.get("/rest/system/ntp/client")
            current_servers_str = current_data.get("servers", "")
            if isinstance(current_servers_str, str):
                current_servers = [
                    s.strip() for s in current_servers_str.split(",") if s.strip()
                ]
            elif isinstance(current_servers_str, list):
                current_servers = current_servers_str
            else:
                current_servers = []
            current_enabled = current_data.get("enabled", False)

            # Check if change is needed
            if set(current_servers) == set(ntp_servers) and current_enabled == enabled:
                return {
                    "changed": False,
                    "old_servers": current_servers,
                    "new_servers": ntp_servers,
                    "enabled": enabled,
                    "dry_run": dry_run,
                }

            # Dry-run: return planned changes
            if dry_run:
                return create_dry_run_response(
                    operation="ntp/update-servers",
                    device_id=device_id,
                    planned_changes={
                        "old_servers": current_servers,
                        "new_servers": ntp_servers,
                        "old_enabled": current_enabled,
                        "new_enabled": enabled,
                    },
                )

            # Apply change
            servers_str = ",".join(ntp_servers)
            await client.patch(
                "/rest/system/ntp/client",
                {"servers": servers_str, "enabled": "yes" if enabled else "no"},
            )

            logger.info(
                f"Updated NTP servers: {current_servers} -> {ntp_servers}, enabled={enabled}",
                extra={"device_id": device_id},
            )

            # Invalidate NTP cache after successful update
            if self.settings.mcp_resource_cache_auto_invalidate:
                await self._invalidate_ntp_cache(device_id)

            return {
                "changed": True,
                "old_servers": current_servers,
                "new_servers": ntp_servers,
                "enabled": enabled,
                "dry_run": False,
            }

        finally:
            await client.close()

    async def _invalidate_dns_cache(self, device_id: str) -> None:
        """Invalidate DNS-related cache entries for a device.

        Args:
            device_id: Device identifier
        """
        try:
            from routeros_mcp.infra.observability.resource_cache import get_cache

            cache = get_cache()

            # Invalidate DNS status and cache resources
            count = 0
            count += int(await cache.invalidate(f"device://{device_id}/dns-status", device_id))
            count += int(await cache.invalidate(f"device://{device_id}/dns-cache", device_id))

            if count > 0:
                metrics.record_cache_invalidation("dns_ntp", "config_update")
                logger.info(
                    f"Invalidated DNS cache entries for device {device_id}",
                    extra={"device_id": device_id, "invalidated_count": count}
                )
        except RuntimeError:
            # Cache not initialized - skip invalidation
            logger.debug("Cache not initialized, skipping DNS cache invalidation")

    async def _invalidate_ntp_cache(self, device_id: str) -> None:
        """Invalidate NTP-related cache entries for a device.

        Args:
            device_id: Device identifier
        """
        try:
            from routeros_mcp.infra.observability.resource_cache import get_cache

            cache = get_cache()

            # Invalidate NTP status resources
            invalidated = await cache.invalidate(f"device://{device_id}/ntp-status", device_id)

            if invalidated:
                metrics.record_cache_invalidation("dns_ntp", "config_update")
                logger.info(
                    f"Invalidated NTP cache entries for device {device_id}",
                    extra={"device_id": device_id, "invalidated": invalidated}
                )
        except RuntimeError:
            # Cache not initialized - skip invalidation
            logger.debug("Cache not initialized, skipping NTP cache invalidation")
