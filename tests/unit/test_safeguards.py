"""Unit tests for safety guardrails.

Tests validation functions for:
- Management path protection
- MCP-owned list validation
- IP address validation
- DNS/NTP server validation
"""

import pytest

from routeros_mcp.security.safeguards import (
    InvalidListNameError,
    ManagementPathProtectionError,
    UnsafeOperationError,
    check_ip_overlap,
    check_management_ip_protection,
    create_dry_run_response,
    validate_dns_servers,
    validate_ip_address_format,
    validate_mcp_owned_list,
    validate_ntp_servers,
)


class TestMCPOwnedListValidation:
    """Test MCP-owned list name validation."""

    def test_valid_mcp_list(self):
        """MCP-owned list names should pass validation."""
        # Should not raise
        validate_mcp_owned_list("mcp-managed-hosts")
        validate_mcp_owned_list("mcp-whitelist")
        validate_mcp_owned_list("mcp-")

    def test_non_mcp_list_rejected(self):
        """Non-MCP list names should be rejected."""
        with pytest.raises(InvalidListNameError, match="not MCP-owned"):
            validate_mcp_owned_list("blacklist")

        with pytest.raises(InvalidListNameError, match="not MCP-owned"):
            validate_mcp_owned_list("whitelist")

        with pytest.raises(InvalidListNameError, match="not MCP-owned"):
            validate_mcp_owned_list("system-list")


class TestManagementPathProtection:
    """Test management IP protection."""

    def test_removing_management_ip_blocked(self):
        """Removing management IP should be blocked."""
        with pytest.raises(ManagementPathProtectionError, match="management IP"):
            check_management_ip_protection(
                device_management_ip="192.168.1.1",
                ip_to_remove="192.168.1.1/24",
            )

    def test_removing_non_management_ip_allowed(self):
        """Removing non-management IP should be allowed."""
        # Should not raise
        check_management_ip_protection(
            device_management_ip="192.168.1.1",
            ip_to_remove="10.0.0.1/24",
        )

    def test_removing_management_subnet_blocked(self):
        """Removing subnet containing management IP should be blocked."""
        with pytest.raises(ManagementPathProtectionError):
            check_management_ip_protection(
                device_management_ip="192.168.1.100",
                ip_to_remove="192.168.1.0/24",
            )

    def test_management_ip_invalid_format_logs_warning(self, caplog):
        """Invalid IP formats should emit warning rather than raising."""
        caplog.set_level("WARNING")

        # Invalid management address will trigger ValueError in ipaddress
        check_management_ip_protection(
            device_management_ip="not-an-ip",
            ip_to_remove="invalid-cidr",
        )

        assert any("Could not parse IPs" in record.message for record in caplog.records)


class TestIPAddressValidation:
    """Test IP address format validation."""

    def test_valid_cidr_notation(self):
        """Valid CIDR notation should pass."""
        # Should not raise
        validate_ip_address_format("192.168.1.1/24")
        validate_ip_address_format("10.0.0.0/8")
        validate_ip_address_format("172.16.0.0/12")

    def test_invalid_ip_format_rejected(self):
        """Invalid IP formats should be rejected."""
        with pytest.raises(ValueError, match="Invalid IP address format"):
            validate_ip_address_format("not-an-ip")

        with pytest.raises(ValueError, match="Invalid IP address format"):
            validate_ip_address_format("256.0.0.1/24")

        # Note: "192.168.1.1" without CIDR is accepted by ipaddress.ip_network
        # with strict=False (treats it as /32)


class TestIPOverlapValidation:
    """Test IP overlap detection."""

    def test_overlapping_ips_rejected(self):
        """Overlapping IPs on same interface should be rejected."""
        existing = [{"interface": "ether1", "address": "192.168.1.1/24", "dynamic": False}]

        with pytest.raises(UnsafeOperationError, match="overlaps"):
            check_ip_overlap("192.168.1.10/24", existing, "ether1")

    def test_non_overlapping_ips_allowed(self):
        """Non-overlapping IPs should be allowed."""
        existing = [{"interface": "ether1", "address": "192.168.1.1/24", "dynamic": False}]

        # Different interface - should not raise
        check_ip_overlap("192.168.1.10/24", existing, "ether2")

        # Different network - should not raise
        check_ip_overlap("10.0.0.1/24", existing, "ether1")

    def test_dynamic_addresses_ignored(self):
        """Dynamic addresses should be ignored in overlap check."""
        existing = [{"interface": "ether1", "address": "192.168.1.1/24", "dynamic": True}]

        # Should not raise even though it overlaps (dynamic address)
        check_ip_overlap("192.168.1.10/24", existing, "ether1")

    def test_invalid_existing_address_skipped(self, caplog):
        """Invalid existing addresses should be skipped with warning."""
        caplog.set_level("WARNING")
        existing = [
            {"interface": "ether1", "address": "not-a-cidr", "dynamic": False},
        ]

        check_ip_overlap("10.0.0.0/24", existing, "ether1")

        assert any(
            "Could not parse existing address" in record.message for record in caplog.records
        )

    def test_empty_existing_address_skipped(self):
        """Entries without an address should be ignored."""
        existing = [{"interface": "ether1", "address": ""}]

        # Should not raise even though the entry is empty
        check_ip_overlap("10.0.0.0/24", existing, "ether1")

    def test_invalid_new_address_raises_value_error(self):
        """Invalid new address should raise ValueError with context."""
        with pytest.raises(ValueError, match="Invalid IP address format"):
            check_ip_overlap("bad-cidr", [], "ether1")


class TestDNSServerValidation:
    """Test DNS server validation."""

    def test_valid_dns_servers(self):
        """Valid DNS servers should pass."""
        # Should not raise
        validate_dns_servers(["8.8.8.8", "8.8.4.4"])
        validate_dns_servers(["1.1.1.1"])
        validate_dns_servers(["dns.google.com", "cloudflare-dns.com"])

    def test_empty_dns_servers_rejected(self):
        """Empty DNS server list should be rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_dns_servers([])

    def test_too_many_dns_servers_rejected(self):
        """Too many DNS servers should be rejected."""
        servers = [f"8.8.8.{i}" for i in range(11)]
        with pytest.raises(ValueError, match="Too many"):
            validate_dns_servers(servers)

    def test_invalid_dns_server_rejected(self):
        """Invalid DNS server addresses should be rejected."""
        with pytest.raises(ValueError, match="Invalid DNS server"):
            validate_dns_servers(["not a valid server!@#"])

    def test_empty_dns_entry_rejected(self):
        """Blank DNS server entries should fail validation."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_dns_servers(["", "8.8.8.8"])


class TestNTPServerValidation:
    """Test NTP server validation."""

    def test_valid_ntp_servers(self):
        """Valid NTP servers should pass."""
        # Should not raise
        validate_ntp_servers(["time.cloudflare.com"])
        validate_ntp_servers(["pool.ntp.org", "time.nist.gov"])

    def test_empty_ntp_servers_rejected(self):
        """Empty NTP server list should be rejected."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_ntp_servers([])

    def test_too_many_ntp_servers_rejected(self):
        """Too many NTP servers should be rejected."""
        servers = [f"ntp{i}.example.com" for i in range(11)]
        with pytest.raises(ValueError, match="Too many"):
            validate_ntp_servers(servers)

    def test_empty_ntp_entry_rejected(self):
        """Blank NTP server entries should fail validation."""
        with pytest.raises(ValueError, match="cannot be empty"):
            validate_ntp_servers(["", "pool.ntp.org"])

    def test_invalid_ntp_server_format(self):
        """Invalid NTP server strings should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid NTP server address"):
            validate_ntp_servers(["bad@@@server"])


class TestDryRunResponse:
    """Test dry-run response formatting."""

    def test_dry_run_response_structure(self):
        """Dry-run response should have correct structure."""
        result = create_dry_run_response(
            operation="test/operation",
            device_id="dev-test-01",
            planned_changes={"field": "value"},
            warnings=["warning1"],
        )

        assert result["device_id"] == "dev-test-01"
        assert result["changed"] is False
        assert result["dry_run"] is True
        assert result["operation"] == "test/operation"
        assert result["planned_changes"] == {"field": "value"}
        assert result["warnings"] == ["warning1"]

    def test_dry_run_response_no_warnings(self):
        """Dry-run response should handle no warnings."""
        result = create_dry_run_response(
            operation="test/operation",
            device_id="dev-test-01",
            planned_changes={},
        )

        assert result["warnings"] == []
