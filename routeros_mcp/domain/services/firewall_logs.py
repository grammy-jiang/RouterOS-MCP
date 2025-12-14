"""Firewall and logs service for firewall rules and system logging operations.

Provides operations for querying RouterOS firewall configuration and system logs.
"""

import logging
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.infra.routeros.exceptions import (
    RouterOSClientError,
    RouterOSNetworkError,
    RouterOSServerError,
    RouterOSTimeoutError,
)

logger = logging.getLogger(__name__)

# Safety limits
MAX_LOG_ENTRIES = 1000


class FirewallLogsService:
    """Service for RouterOS firewall and logging operations.

    Responsibilities:
    - Query firewall filter rules, NAT rules, and address lists
    - Retrieve system logs with filtering
    - Query logging configuration
    - Enforce safety limits on log queries
    - Normalize RouterOS responses to domain models

    Example:
        async with get_session() as session:
            service = FirewallLogsService(session, settings)

            # Get firewall rules
            filter_rules = await service.list_filter_rules("dev-lab-01")
            nat_rules = await service.list_nat_rules("dev-lab-01")

            # Get logs
            logs = await service.get_recent_logs("dev-lab-01", limit=100)
    """

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        """Initialize firewall/logs service.

        Args:
            session: Database session
            settings: Application settings
        """
        self.session = session
        self.settings = settings
        self.device_service = DeviceService(session, settings)

    async def list_filter_rules(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List firewall filter rules (input/forward/output chains) with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            List of filter rule dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            rules = await self._list_filter_rules_via_rest(device_id)
            for rule in rules:
                rule["transport"] = "rest"
                rule["fallback_used"] = False
                rule["rest_error"] = None
            return rules
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST filter rules listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            try:
                rules = await self._list_filter_rules_via_ssh(device_id)
                for rule in rules:
                    rule["transport"] = "ssh"
                    rule["fallback_used"] = True
                    rule["rest_error"] = str(rest_exc)
                return rules
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH filter rules listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Filter rules listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _list_filter_rules_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch filter rules via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            rules_data = await client.get("/rest/ip/firewall/filter")

            result: list[dict[str, Any]] = []
            if isinstance(rules_data, list):
                for rule in rules_data:
                    if isinstance(rule, dict):
                        result.append({
                            "id": rule.get(".id", ""),
                            "chain": rule.get("chain", ""),
                            "action": rule.get("action", ""),
                            "protocol": rule.get("protocol", ""),
                            "dst_port": rule.get("dst-port", ""),
                            "src_port": rule.get("src-port", ""),
                            "src_address": rule.get("src-address", ""),
                            "dst_address": rule.get("dst-address", ""),
                            "comment": rule.get("comment", ""),
                            "disabled": rule.get("disabled", False),
                        })

            return result

        finally:
            await client.close()

    async def _list_filter_rules_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch filter rules via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/firewall/filter/print")
            # DEBUG: Log first 500 chars of raw output
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Raw SSH output (first 500 chars): {repr(output[:500])}")
            logger.debug(f"First 5 lines:\n" + "\n".join(repr(line) for line in output.split("\n")[:5]))
            return self._parse_firewall_filter_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_firewall_filter_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /ip/firewall/filter/print output (supports mixed column and key=value formats)."""
        import shlex

        rules: list[dict[str, Any]] = []
        current_rule: dict[str, Any] | None = None

        def flush_current() -> None:
            if current_rule is None:
                return

            for key, default in (
                ("id", ""),
                ("chain", ""),
                ("action", ""),
                ("protocol", ""),
                ("dst_port", ""),
                ("src_port", ""),
                ("src_address", ""),
                ("dst_address", ""),
                ("comment", ""),
                ("disabled", False),
            ):
                current_rule.setdefault(key, default)

            current_rule.pop("_raw", None)
            rules.append(current_rule.copy())

        for raw_line in output.strip().split("\n"):
            line = raw_line.strip()
            if not line or line.startswith("Flags:") or line.startswith("#"):
                continue

            # Start of a new rule if line begins with id (digit or *)
            if line[0].isdigit() or line[0] == "*":
                flush_current()

                # Strip inline comment first
                comment = ""
                if ";;;" in line:
                    comment = line.split(";;;", 1)[1].strip()
                    line = line.split(";;;", 1)[0].strip()

                parts = line.split()
                rule_id = parts[0]
                flags = ""
                cursor = 1
                if len(parts) > 1 and re.fullmatch(r"[A-ZIXD]+", parts[1]):
                    flags = parts[1]
                    cursor = 2

                disabled = "X" in flags or "D" in flags or "d" in flags

                current_rule = {
                    "id": rule_id,
                    "disabled": disabled,
                    "comment": comment,
                    "chain": "",
                    "action": "",
                    "protocol": "",
                    "dst_port": "",
                    "src_port": "",
                    "src_address": "",
                    "dst_address": "",
                }

                remainder_tokens = parts[cursor:]
                kv_tokens = [t for t in remainder_tokens if "=" in t]

                if kv_tokens:
                    for token in kv_tokens:
                        key, value = token.split("=", 1)
                        FirewallLogsService._assign_token(current_rule, key, value)
                elif remainder_tokens:
                    # Column mode: CHAIN ACTION PROTOCOL DST-PORT SRC-PORT SRC-ADDRESS DST-ADDRESS
                    field_order = [
                        "chain",
                        "action",
                        "protocol",
                        "dst_port",
                        "src_port",
                        "src_address",
                        "dst_address",
                    ]
                    for idx, field in enumerate(field_order):
                        if idx < len(remainder_tokens):
                            current_rule[field] = remainder_tokens[idx]

                continue

            if current_rule is None:
                continue

            # Continuation line: expect key=value tokens
            try:
                tokens = shlex.split(line)
            except ValueError:
                tokens = line.split()
            for token in tokens:
                if "=" not in token:
                    continue
                key, value = token.split("=", 1)
                FirewallLogsService._assign_token(current_rule, key, value)

        flush_current()
        return rules

    @staticmethod
    def _assign_token(rule: dict[str, Any], key: str, value: str) -> None:
        """Map RouterOS key/value tokens into our normalized rule dict."""
        key_map = {
            "dst-port": "dst_port",
            "src-port": "src_port",
            "src-address": "src_address",
            "dst-address": "dst_address",
        }

        normalized_key = key_map.get(key, key)
        if normalized_key == "comment" and len(value) >= 2 and value[0] == value[-1] == '"':
            value = value[1:-1]

        if normalized_key in {"chain", "action", "protocol", "dst_port", "src_port", "src_address", "dst_address", "comment"}:
            rule[normalized_key] = value
        else:
            # Preserve additional attributes to aid debugging/observability
            extras = rule.setdefault("extras", {})
            extras[normalized_key] = value

    async def list_nat_rules(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """List NAT (Network Address Translation) rules with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            List of NAT rule dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            rules = await self._list_nat_rules_via_rest(device_id)
            for rule in rules:
                rule["transport"] = "rest"
                rule["fallback_used"] = False
                rule["rest_error"] = None
            return rules
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST NAT rules listing failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            try:
                rules = await self._list_nat_rules_via_ssh(device_id)
                for rule in rules:
                    rule["transport"] = "ssh"
                    rule["fallback_used"] = True
                    rule["rest_error"] = str(rest_exc)
                return rules
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH NAT rules listing failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"NAT rules listing failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _list_nat_rules_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch NAT rules via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            rules_data = await client.get("/rest/ip/firewall/nat")

            result: list[dict[str, Any]] = []
            if isinstance(rules_data, list):
                for rule in rules_data:
                    if isinstance(rule, dict):
                        result.append({
                            "id": rule.get(".id", ""),
                            "chain": rule.get("chain", ""),
                            "action": rule.get("action", ""),
                            "out_interface": rule.get("out-interface", ""),
                            "in_interface": rule.get("in-interface", ""),
                            "out_interface_list": rule.get("out-interface-list", ""),
                            "in_interface_list": rule.get("in-interface-list", ""),
                            "to_addresses": rule.get("to-addresses", ""),
                            "to_ports": rule.get("to-ports", ""),
                            "src_address": rule.get("src-address", ""),
                            "dst_address": rule.get("dst-address", ""),
                            "src_address_list": rule.get("src-address-list", ""),
                            "dst_address_list": rule.get("dst-address-list", ""),
                            "src_address_type": rule.get("src-address-type", ""),
                            "dst_address_type": rule.get("dst-address-type", ""),
                            "protocol": rule.get("protocol", ""),
                            "src_port": rule.get("src-port", ""),
                            "dst_port": rule.get("dst-port", ""),
                            "comment": rule.get("comment", ""),
                            "disabled": rule.get("disabled", False),
                        })

            return result

        finally:
            await client.close()

    async def _list_nat_rules_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch NAT rules via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/firewall/nat/print")
            return self._parse_firewall_nat_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_firewall_nat_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /ip/firewall/nat/print output."""
        rules: list[dict[str, Any]] = []

        # Group lines per rule (rules may span multiple indented lines)
        current: list[str] = []
        for line in output.strip().split("\n"):
            stripped = line.strip()
            if not stripped or stripped.startswith("Flags:") or stripped.startswith("#"):
                continue

            # New rule starts when line begins with id (digits or *id)
            if re.match(r"^[0-9*]", stripped):
                if current:
                    parsed = FirewallLogsService._parse_single_nat_rule(current)
                    if parsed:
                        rules.append(parsed)
                current = [stripped]
            else:
                if current:
                    current.append(stripped)

        if current:
            parsed = FirewallLogsService._parse_single_nat_rule(current)
            if parsed:
                rules.append(parsed)

        return rules

    @staticmethod
    def _parse_single_nat_rule(lines: list[str]) -> dict[str, Any] | None:
        """Parse a single NAT rule represented by one or more lines."""
        first = lines[0]

        # Extract id and optional flags
        m = re.match(r"^(?P<id>[0-9A-Za-z*]+)\s*(?P<flags>[A-ZIXD]*)\s*(?P<rest>.*)$", first)
        if not m:
            return None

        rule_id = m.group("id")
        flags = m.group("flags") or ""
        rest = m.group("rest")

        disabled = "X" in flags or "D" in flags or "d" in flags

        comment = ""
        if ";;;" in first:
            comment = first.split(";;;", 1)[1].strip()

        # Collect tokens key=value from all lines (including first remainder)
        tokens_text = " ".join([rest] + lines[1:])
        tokens = [t for t in tokens_text.split() if "=" in t]

        field_map = {
            "chain": "chain",
            "action": "action",
            "out-interface": "out_interface",
            "in-interface": "in_interface",
            "out-interface-list": "out_interface_list",
            "in-interface-list": "in_interface_list",
            "to-addresses": "to_addresses",
            "to-ports": "to_ports",
            "src-address": "src_address",
            "dst-address": "dst_address",
            "src-address-list": "src_address_list",
            "dst-address-list": "dst_address_list",
            "src-address-type": "src_address_type",
            "dst-address-type": "dst_address_type",
            "protocol": "protocol",
            "src-port": "src_port",
            "dst-port": "dst_port",
        }

        rule: dict[str, Any] = {v: "" for v in field_map.values()}
        rule.update({"id": rule_id, "comment": comment, "disabled": disabled})

        if tokens:
            for tok in tokens:
                key, val = tok.split("=", 1)
                target = field_map.get(key)
                if target:
                    rule[target] = val
        else:
            # Column-aligned output without key=value
            words = rest.split()
            field_order = [
                "chain",
                "action",
                "in_interface",
                "out_interface",
                "to_addresses",
            ]
            for idx, field in enumerate(field_order):
                if idx < len(words):
                    rule[field] = words[idx]

            if len(words) > len(field_order):
                trailing_comment = " ".join(words[len(field_order):]).strip()
                if trailing_comment:
                    rule["comment"] = trailing_comment

        return rule

    async def list_address_lists(
        self,
        device_id: str,
        list_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """List firewall address-list entries (IP-based allow/deny lists) with REST→SSH fallback.

        Args:
            device_id: Device identifier
            list_name: Optional filter by list name

        Returns:
            List of address-list entry dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            entries = await self._list_address_lists_via_rest(device_id, list_name)
            for entry in entries:
                entry["transport"] = "rest"
                entry["fallback_used"] = False
                entry["rest_error"] = None
            return entries
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST address lists failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            try:
                entries = await self._list_address_lists_via_ssh(device_id, list_name)
                for entry in entries:
                    entry["transport"] = "ssh"
                    entry["fallback_used"] = True
                    entry["rest_error"] = str(rest_exc)
                return entries
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH address lists failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Address lists failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _list_address_lists_via_rest(
        self,
        device_id: str,
        list_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch address lists via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            lists_data = await client.get("/rest/ip/firewall/address-list")

            result: list[dict[str, Any]] = []
            if isinstance(lists_data, list):
                for entry in lists_data:
                    if isinstance(entry, dict):
                        entry_list_name = entry.get("list", "")

                        if list_name and entry_list_name != list_name:
                            continue

                        result.append({
                            "id": entry.get(".id", ""),
                            "list_name": entry_list_name,
                            "address": entry.get("address", ""),
                            "comment": entry.get("comment", ""),
                            "timeout": entry.get("timeout", ""),
                        })

            return result

        finally:
            await client.close()

    async def _list_address_lists_via_ssh(
        self,
        device_id: str,
        list_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch address lists via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/ip/firewall/address-list/print")
            entries = self._parse_address_list_print_output(output)
            
            # Filter by list_name if provided
            if list_name:
                entries = [e for e in entries if e.get("list_name") == list_name]
            
            return entries
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_address_list_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /ip/firewall/address-list/print output."""
        entries: list[dict[str, Any]] = []

        lines = output.strip().split("\n")
        for line in lines:
            if not line.strip() or line.startswith("Flags:") or line.startswith("#"):
                continue

            parts = line.split()
            if not parts or not (parts[0][0] == "*" or parts[0][0].isdigit()):
                continue

            try:
                idx = 0
                flags = ""

                if len(parts) > 1 and len(parts[1]) == 1 and parts[1] in "DXdr":
                    flags = parts[1]
                    idx = 2
                else:
                    idx = 1

                # Parse: [id] [flags?] [list] [address]
                if len(parts) > idx + 1:
                    entry_id = parts[0]
                    list_name = parts[idx]
                    address = parts[idx + 1]

                    entries.append({
                        "id": entry_id,
                        "list": list_name,
                        "address": address,
                        "comment": "",
                        "timeout": "",
                        "disabled": "D" in flags or "d" in flags,
                    })
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse address list line: {line}", exc_info=e)
                continue

        return entries

    async def get_recent_logs(
        self,
        device_id: str,
        limit: int = 100,
        topics: list[str] | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        message: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Retrieve recent system logs with optional filtering with REST→SSH fallback.

        Args:
            device_id: Device identifier
            limit: Maximum number of entries to return (max 1000)
            topics: Optional list of topics to filter by

        Returns:
            Tuple of (log_entries, total_count)

        Raises:
            DeviceNotFoundError: If device doesn't exist
            ValidationError: If limit exceeds maximum
        """
        from routeros_mcp.mcp.errors import ValidationError

        await self.device_service.get_device(device_id)

        if limit > MAX_LOG_ENTRIES:
            raise ValidationError(
                f"Log entry limit cannot exceed {MAX_LOG_ENTRIES} entries",
                data={"requested_limit": limit, "max_limit": MAX_LOG_ENTRIES},
            )

        try:
            entries, total = await self._get_recent_logs_via_rest(device_id, limit, topics)
            for entry in entries:
                entry["transport"] = "rest"
                entry["fallback_used"] = False
                entry["rest_error"] = None
            entries = self._filter_logs(entries, start_time, end_time, message, limit)
            return entries, total
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST logs failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            try:
                entries, total = await self._get_recent_logs_via_ssh(device_id, limit, topics)
                for entry in entries:
                    entry["transport"] = "ssh"
                    entry["fallback_used"] = True
                    entry["rest_error"] = str(rest_exc)
                entries = self._filter_logs(entries, start_time, end_time, message, limit)
                return entries, total
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH logs failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Logs failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_recent_logs_via_rest(
        self,
        device_id: str,
        limit: int = 100,
        topics: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Fetch recent logs via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            logs_data = await client.get("/rest/log")

            result: list[dict[str, Any]] = []
            if isinstance(logs_data, list):
                for i, entry in enumerate(logs_data):
                    if i >= limit:
                        break
                    if isinstance(entry, dict):
                        entry_topics = entry.get("topics", "")
                        if isinstance(entry_topics, str):
                            entry_topics_list = [t.strip() for t in entry_topics.split(",") if t.strip()]
                        elif isinstance(entry_topics, list):
                            entry_topics_list = entry_topics
                        else:
                            entry_topics_list = []

                        if topics:
                            if not any(t in entry_topics_list for t in topics):
                                continue

                        result.append({
                            "id": entry.get(".id", ""),
                            "time": entry.get("time", ""),
                            "topics": entry_topics_list,
                            "message": entry.get("message", ""),
                        })

            total_count = len(logs_data) if isinstance(logs_data, list) else 0
            return result, total_count

        finally:
            await client.close()

    async def _get_recent_logs_via_ssh(
        self,
        device_id: str,
        limit: int = 100,
        topics: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        """Fetch recent logs via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/log/print")
            entries = self._parse_log_print_output(output, limit, topics)
            return entries, len(entries)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_log_print_output(
        output: str,
        limit: int = 100,
        topics: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Parse /log/print output."""
        entries: list[dict[str, Any]] = []
        date_regex = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        time_regex = re.compile(r"^\d{2}:\d{2}:\d{2}$")

        lines = output.strip().split("\n")
        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith("Flags:") or line.startswith("#"):
                continue

            if len(entries) >= limit:
                break

            try:
                entry_id = ""
                entry_time = ""
                entry_topics_str = ""
                message = ""

                # Variant 1: date + time present (e.g., 2025-12-11 22:52:33 system,info msg)
                parts = line.split(maxsplit=3)
                if (
                    len(parts) >= 3
                    and date_regex.match(parts[0])
                    and time_regex.match(parts[1])
                ):
                    entry_time = f"{parts[0]} {parts[1]}"
                    entry_id = entry_time
                    entry_topics_str = parts[2]
                    message = parts[3] if len(parts) > 3 else ""
                else:
                    # Variant 2: optional id then time (e.g., *l1 00:00:01 topics msg)
                    # Variant 3: time-only (e.g., 00:00:01 topics msg)
                    parts = line.split(maxsplit=2)
                    if len(parts) >= 2 and time_regex.match(parts[1]):
                        entry_id = parts[0]
                        entry_time = parts[1]
                        entry_topics_str = parts[2] if len(parts) > 2 else ""
                    elif time_regex.match(parts[0]):
                        entry_id = parts[0]
                        entry_time = parts[0]
                        entry_topics_str = parts[1] if len(parts) > 1 else ""
                        message = parts[2] if len(parts) > 2 else ""
                    else:
                        # Unknown format; skip
                        logger.debug("Skipping unparsable log line: %s", line)
                        continue

                    # If message not already set, split topics from message for variant 2
                    if not message and entry_topics_str:
                        topic_and_msg = entry_topics_str.split(maxsplit=1)
                        entry_topics_str = topic_and_msg[0]
                        message = topic_and_msg[1] if len(topic_and_msg) > 1 else ""

                entry_topics_list = [t.strip() for t in entry_topics_str.split(",") if t.strip()]

                # Filter by topics if provided
                if topics and not any(t in entry_topics_list for t in topics):
                    continue

                entries.append({
                    "id": entry_id,
                    "time": entry_time,
                    "topics": entry_topics_list,
                    "message": message.rstrip("\r"),
                })
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse log line: {line}", exc_info=e)
                continue

        return entries

    @staticmethod
    def _parse_time(value: str):
        """Attempt to parse a RouterOS log time string into datetime; return None if unknown."""
        from datetime import datetime

        if not value:
            return None

        candidates = [
            "%Y-%m-%d %H:%M:%S",
            "%b/%d/%Y %H:%M:%S",
            "%B/%d/%Y %H:%M:%S",
            "%H:%M:%S",
        ]
        for fmt in candidates:
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
        return None

    def _filter_logs(
        self,
        entries: list[dict[str, Any]],
        start_time: str | None,
        end_time: str | None,
        message: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Apply time-window and message substring filters to parsed log entries."""
        if not entries:
            return []

        start_dt = self._parse_time(start_time) if start_time else None
        end_dt = self._parse_time(end_time) if end_time else None
        message_filter = message.lower() if message else None

        filtered: list[dict[str, Any]] = []
        for entry in entries:
            if len(filtered) >= limit:
                break

            entry_time = entry.get("time", "")
            entry_dt = self._parse_time(entry_time)

            if start_dt and entry_dt and entry_dt < start_dt:
                continue
            if end_dt and entry_dt and entry_dt > end_dt:
                continue

            if message_filter:
                if message_filter not in entry.get("message", "").lower():
                    continue

            filtered.append(entry)

        return filtered

    async def get_logging_config(
        self,
        device_id: str,
    ) -> list[dict[str, Any]]:
        """Get logging configuration (which topics log to which destinations) with REST→SSH fallback.

        Args:
            device_id: Device identifier

        Returns:
            List of logging action dictionaries

        Raises:
            DeviceNotFoundError: If device doesn't exist
        """
        await self.device_service.get_device(device_id)

        try:
            configs = await self._get_logging_config_via_rest(device_id)
            for config in configs:
                config["transport"] = "rest"
                config["fallback_used"] = False
                config["rest_error"] = None
            return configs
        except (
            RouterOSTimeoutError,
            RouterOSNetworkError,
            RouterOSServerError,
            RouterOSClientError,
            Exception,
        ) as rest_exc:
            logger.warning(
                f"REST logging config failed, attempting SSH fallback: {rest_exc}",
                extra={"device_id": device_id},
            )
            try:
                configs = await self._get_logging_config_via_ssh(device_id)
                for config in configs:
                    config["transport"] = "ssh"
                    config["fallback_used"] = True
                    config["rest_error"] = str(rest_exc)
                return configs
            except Exception as ssh_exc:
                logger.error(
                    f"Both REST and SSH logging config failed",
                    exc_info=ssh_exc,
                    extra={"device_id": device_id, "rest_error": str(rest_exc)},
                )
                raise RuntimeError(
                    f"Logging config failed via REST and SSH: "
                    f"rest_error={rest_exc}, ssh_error={ssh_exc}"
                ) from ssh_exc

    async def _get_logging_config_via_rest(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch logging config via REST API."""
        client = await self.device_service.get_rest_client(device_id)

        try:
            logging_data = await client.get("/rest/system/logging")

            result: list[dict[str, Any]] = []
            if isinstance(logging_data, list):
                for action in logging_data:
                    if isinstance(action, dict):
                        topics = action.get("topics", "")
                        if isinstance(topics, str):
                            topics_list = [t.strip() for t in topics.split(",") if t.strip()]
                        elif isinstance(topics, list):
                            topics_list = topics
                        else:
                            topics_list = []

                        result.append({
                            "topics": topics_list,
                            "action": action.get("action", ""),
                            "prefix": action.get("prefix", ""),
                        })

            return result

        finally:
            await client.close()

    async def _get_logging_config_via_ssh(self, device_id: str) -> list[dict[str, Any]]:
        """Fetch logging config via SSH CLI."""
        ssh_client = await self.device_service.get_ssh_client(device_id)

        try:
            output = await ssh_client.execute("/system/logging/print")
            return self._parse_logging_config_print_output(output)
        finally:
            await ssh_client.close()

    @staticmethod
    def _parse_logging_config_print_output(output: str) -> list[dict[str, Any]]:
        """Parse /system/logging/print output."""
        configs: list[dict[str, Any]] = []

        lines = output.strip().split("\n")
        for line in lines:
            if not line.strip() or line.startswith("Flags:") or line.startswith("#"):
                continue

            parts = line.split()
            if not parts or not (parts[0][0] == "*" or parts[0][0].isdigit()):
                continue

            try:
                idx = 0
                flags = ""

                if len(parts) > 1 and len(parts[1]) == 1 and parts[1] in "DXdr":
                    flags = parts[1]
                    idx = 2
                else:
                    idx = 1

                # Parse: [id] [flags?] [topics] [action]
                if len(parts) > idx + 1:
                    topics_str = parts[idx]
                    action = parts[idx + 1]

                    topics_list = [t.strip() for t in topics_str.split(",") if t.strip()]

                    configs.append({
                        "topics": topics_list,
                        "action": action,
                        "prefix": "",  # Not shown in simple print
                    })
            except (IndexError, ValueError) as e:
                logger.debug(f"Failed to parse logging config line: {line}", exc_info=e)
                continue

        return configs
