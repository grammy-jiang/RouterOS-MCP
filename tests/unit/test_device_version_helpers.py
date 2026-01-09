"""Tests for Device model version helper methods."""

from datetime import UTC, datetime

from routeros_mcp.domain.models import Device


class TestDeviceVersionHelpers:
    """Tests for Device model version detection and comparison methods."""

    def test_is_v6_returns_true_for_v6_version(self) -> None:
        """Test is_v6() returns True for RouterOS v6.x versions."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="6.48.6",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.is_v6() is True
        assert device.is_v7() is False

    def test_is_v7_returns_true_for_v7_version(self) -> None:
        """Test is_v7() returns True for RouterOS v7.x versions."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.10.2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.is_v7() is True
        assert device.is_v6() is False

    def test_is_v6_returns_false_when_version_none(self) -> None:
        """Test is_v6() returns False when version is None."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.is_v6() is False
        assert device.is_v7() is False

    def test_version_ge_exact_match(self) -> None:
        """Test version_ge() returns True for exact version match."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.10.2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.version_ge("7.10.2") is True

    def test_version_ge_greater_major(self) -> None:
        """Test version_ge() returns True when major version is greater."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.10.2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.version_ge("6.48") is True

    def test_version_ge_greater_minor(self) -> None:
        """Test version_ge() returns True when minor version is greater."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.10.2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.version_ge("7.9") is True

    def test_version_ge_greater_patch(self) -> None:
        """Test version_ge() returns True when patch version is greater."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.10.2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.version_ge("7.10.1") is True
        assert device.version_ge("7.10.0") is True

    def test_version_ge_less_than_target(self) -> None:
        """Test version_ge() returns False when version is less than target."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.10.2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.version_ge("7.10.3") is False
        assert device.version_ge("7.11") is False
        assert device.version_ge("8.0") is False

    def test_version_ge_none_version(self) -> None:
        """Test version_ge() returns False when version is None."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.version_ge("7.10") is False

    def test_version_ge_with_rc_suffix(self) -> None:
        """Test version_ge() handles RC/beta versions correctly."""
        # RC version should be considered less than stable version
        device_rc = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.11-rc1",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # RC version is NOT >= stable version of same number
        assert device_rc.version_ge("7.11") is False

        # But RC version IS >= earlier stable version
        assert device_rc.version_ge("7.10") is True

        # And RC version IS >= same RC version
        assert device_rc.version_ge("7.11-rc1") is True

    def test_version_ge_stable_greater_than_rc(self) -> None:
        """Test that stable version is >= RC version of same number."""
        device_stable = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.11",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Stable 7.11 should be >= RC 7.11-rc1
        assert device_stable.version_ge("7.11-rc1") is True
        assert device_stable.version_ge("7.11") is True

    def test_version_ge_two_digit_versions(self) -> None:
        """Test version_ge() works with two-digit version components."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.15.2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device.version_ge("7.9.1") is True
        assert device.version_ge("7.15.1") is True
        assert device.version_ge("7.15.2") is True
        assert device.version_ge("7.15.3") is False

    def test_version_ge_short_version_comparison(self) -> None:
        """Test version_ge() handles comparison with shorter version strings."""
        device = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.10.2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # 7.10.2 >= 7.10 should be True
        assert device.version_ge("7.10") is True

        # 7.10.2 >= 7 should be True
        assert device.version_ge("7") is True

    def test_version_ge_v6_to_v7_comparison(self) -> None:
        """Test version_ge() correctly compares v6 to v7."""
        device_v6 = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="6.48.6",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        assert device_v6.version_ge("6.48") is True
        assert device_v6.version_ge("6.48.6") is True
        assert device_v6.version_ge("6.49") is False
        assert device_v6.version_ge("7.0") is False

    def test_version_ge_both_rc_versions(self) -> None:
        """Test version_ge() when both versions have RC suffixes."""
        device_rc2 = Device(
            id="dev-001",
            name="test-router",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            status="healthy",
            tags={},
            allow_advanced_writes=False,
            allow_professional_workflows=False,
            routeros_version="7.11-rc2",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # When both have RC suffixes and numeric parts are equal, consider >= true
        # (We don't parse RC numbers, so rc2 >= rc1 returns True by design)
        assert device_rc2.version_ge("7.11-rc1") is True
        assert device_rc2.version_ge("7.11-rc2") is True
        assert device_rc2.version_ge("7.11-rc3") is True  # Can't distinguish RC numbers
