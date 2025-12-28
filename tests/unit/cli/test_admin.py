"""Unit tests for admin CLI module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from routeros_mcp.cli.admin import admin


@pytest.fixture
def cli_runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_settings():
    """Mock Settings object."""
    with patch("routeros_mcp.cli.admin.load_settings") as mock_load:
        mock_settings = MagicMock()
        mock_settings.environment = "lab"
        mock_settings.database_url = "sqlite+aiosqlite:///:memory:"
        mock_load.return_value = mock_settings
        yield mock_settings


@pytest.fixture
def mock_session_factory():
    """Mock session factory."""
    with patch("routeros_mcp.cli.admin.get_session_factory") as mock_factory:
        # Create async context manager mock
        mock_session = MagicMock()
        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        # Create session factory mock
        factory = MagicMock()
        factory.init = AsyncMock()
        factory.session = MagicMock(return_value=mock_session_cm)

        mock_factory.return_value = factory
        yield factory


class TestDeviceCommands:
    """Tests for device management commands."""

    def test_device_add_success(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test successful device addition."""
        # Mock DeviceService
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_device = MagicMock()
            mock_device.id = "dev-lab-01"
            mock_service.register_device = AsyncMock(return_value=mock_device)
            mock_service.add_credential = AsyncMock()
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "add",
                    "--id", "dev-lab-01",
                    "--name", "Test Device",
                    "--ip", "192.168.1.1",
                    "--username", "admin",
                    "--password", "secret",
                    "--non-interactive",
                ],
            )

            assert result.exit_code == 0
            assert "Device registered" in result.output
            assert "dev-lab-01" in result.output

    def test_device_add_missing_password_non_interactive(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test device add fails without password in non-interactive mode."""
        result = cli_runner.invoke(
            admin,
            [
                "--config", "config/lab.yaml",
                "device", "add",
                "--id", "dev-lab-01",
                "--name", "Test Device",
                "--ip", "192.168.1.1",
                "--username", "admin",
                "--non-interactive",
            ],
        )

        assert result.exit_code == 1
        assert "password required" in result.output.lower()

    def test_device_add_with_capabilities(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test device add with capability flags."""
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_device = MagicMock()
            mock_device.id = "dev-lab-01"
            mock_service.register_device = AsyncMock(return_value=mock_device)
            mock_service.add_credential = AsyncMock()
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "add",
                    "--id", "dev-lab-01",
                    "--name", "Test Device",
                    "--ip", "192.168.1.1",
                    "--username", "admin",
                    "--password", "secret",
                    "--allow-professional-workflows",
                    "--allow-firewall-writes",
                    "--non-interactive",
                ],
            )

            assert result.exit_code == 0
            # Verify register_device was called with correct capability flags
            call_args = mock_service.register_device.call_args
            device_create = call_args[0][0]
            assert device_create.allow_professional_workflows is True
            assert device_create.allow_firewall_writes is True

    def test_device_add_with_tags(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test device add with JSON tags."""
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_device = MagicMock()
            mock_device.id = "dev-lab-01"
            mock_service.register_device = AsyncMock(return_value=mock_device)
            mock_service.add_credential = AsyncMock()
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "add",
                    "--id", "dev-lab-01",
                    "--name", "Test Device",
                    "--ip", "192.168.1.1",
                    "--username", "admin",
                    "--password", "secret",
                    "--tags", '{"site": "home", "role": "core"}',
                    "--non-interactive",
                ],
            )

            assert result.exit_code == 0
            # Verify tags were parsed correctly
            call_args = mock_service.register_device.call_args
            device_create = call_args[0][0]
            assert device_create.tags == {"site": "home", "role": "core"}

    def test_device_add_invalid_tags(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test device add with invalid JSON tags."""
        result = cli_runner.invoke(
            admin,
            [
                "--config", "config/lab.yaml",
                "device", "add",
                "--id", "dev-lab-01",
                "--name", "Test Device",
                "--ip", "192.168.1.1",
                "--username", "admin",
                "--password", "secret",
                "--tags", 'invalid json',
                "--non-interactive",
            ],
        )

        assert result.exit_code == 1
        assert "Invalid JSON" in result.output

    def test_device_list_table_format(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test device list with table format."""
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_device1 = MagicMock()
            mock_device1.id = "dev-lab-01"
            mock_device1.name = "Router 1"
            mock_device1.management_ip = "192.168.1.1"
            mock_device1.management_port = 443
            mock_device1.environment = "lab"
            mock_device1.status = "healthy"
            mock_device1.allow_professional_workflows = True

            mock_service.list_devices = AsyncMock(return_value=[mock_device1])
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "list",
                ],
            )

            assert result.exit_code == 0
            assert "dev-lab-01" in result.output
            assert "Router 1" in result.output
            assert "192.168.1.1" in result.output

    def test_device_list_json_format(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test device list with JSON format."""
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_device1 = MagicMock()
            mock_device1.id = "dev-lab-01"
            mock_device1.name = "Router 1"
            mock_device1.management_ip = "192.168.1.1"
            mock_device1.management_port = 443
            mock_device1.environment = "lab"
            mock_device1.status = "healthy"
            mock_device1.allow_professional_workflows = True

            mock_service.list_devices = AsyncMock(return_value=[mock_device1])
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "list",
                    "--format", "json",
                ],
            )

            assert result.exit_code == 0
            assert '"id": "dev-lab-01"' in result.output
            assert '"name": "Router 1"' in result.output

    def test_device_list_with_filters(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test device list with environment and status filters."""
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_devices = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "list",
                    "--environment", "lab",
                    "--status", "healthy",
                ],
            )

            assert result.exit_code == 0
            # Verify filters were passed to service
            call_args = mock_service.list_devices.call_args
            assert call_args[1]["environment"] == "lab"
            assert call_args[1]["status"] == "healthy"

    def test_device_update_success(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test successful device update."""
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update_device = AsyncMock()
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "update",
                    "dev-lab-01",
                    "--name", "Updated Name",
                    "--allow-professional-workflows", "true",
                ],
            )

            assert result.exit_code == 0
            assert "updated successfully" in result.output

    def test_device_update_no_changes(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test device update with no changes specified."""
        result = cli_runner.invoke(
            admin,
            [
                "--config", "config/lab.yaml",
                "device", "update",
                "dev-lab-01",
            ],
        )

        assert result.exit_code == 0
        assert "No updates specified" in result.output

    def test_device_test_success(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test successful device connectivity test."""
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.check_connectivity = AsyncMock(
                return_value=(True, {"version": "7.11", "identity": "test-router"})
            )
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "test",
                    "dev-lab-01",
                ],
            )

            assert result.exit_code == 0
            assert "is reachable" in result.output
            assert "version" in result.output.lower()

    def test_device_test_failure(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test failed device connectivity test."""
        with patch("routeros_mcp.cli.admin.DeviceService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.check_connectivity = AsyncMock(
                return_value=(False, {"error": "Connection timeout"})
            )
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "device", "test",
                    "dev-lab-01",
                ],
            )

            assert result.exit_code == 1
            assert "not reachable" in result.output
            assert "Connection timeout" in result.output


class TestPlanCommands:
    """Tests for plan management commands."""

    def test_plan_list_table_format(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test plan list with table format."""
        with patch("routeros_mcp.cli.admin.PlanService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_plans = AsyncMock(
                return_value=[
                    {
                        "plan_id": "plan-12345",
                        "tool_name": "config/plan-dns-ntp",
                        "status": "pending",
                        "device_count": 3,
                        "created_by": "test-user",
                        "created_at": "2024-01-15T10:30:00Z",
                    }
                ]
            )
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "plan", "list",
                ],
            )

            assert result.exit_code == 0
            assert "plan-12345" in result.output
            assert "pending" in result.output

    def test_plan_list_json_format(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test plan list with JSON format."""
        with patch("routeros_mcp.cli.admin.PlanService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_plans = AsyncMock(
                return_value=[
                    {
                        "plan_id": "plan-12345",
                        "tool_name": "config/plan-dns-ntp",
                        "status": "pending",
                        "device_count": 3,
                        "created_by": "test-user",
                        "created_at": "2024-01-15T10:30:00Z",
                    }
                ]
            )
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "plan", "list",
                    "--format", "json",
                ],
            )

            assert result.exit_code == 0
            assert '"plan_id": "plan-12345"' in result.output

    def test_plan_list_with_filters(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test plan list with filters."""
        with patch("routeros_mcp.cli.admin.PlanService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.list_plans = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "plan", "list",
                    "--status", "pending",
                    "--created-by", "test-user",
                    "--limit", "100",
                ],
            )

            assert result.exit_code == 0
            # Verify filters were passed
            call_args = mock_service.list_plans.call_args
            assert call_args[1]["status"] == "pending"
            assert call_args[1]["created_by"] == "test-user"
            assert call_args[1]["limit"] == 100

    def test_plan_show_text_format(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test plan show with text format."""
        with patch("routeros_mcp.cli.admin.PlanService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_plan = AsyncMock(
                return_value={
                    "plan_id": "plan-12345",
                    "status": "pending",
                    "tool_name": "config/plan-dns-ntp",
                    "created_by": "test-user",
                    "created_at": "2024-01-15T10:30:00Z",
                    "risk_level": "medium",
                    "device_ids": ["dev-lab-01", "dev-lab-02"],
                    "summary": "Update DNS servers",
                    "changes": {"dns_servers": ["8.8.8.8"]},
                }
            )
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "plan", "show",
                    "plan-12345",
                ],
            )

            assert result.exit_code == 0
            assert "plan-12345" in result.output
            assert "pending" in result.output
            assert "Update DNS servers" in result.output

    def test_plan_show_json_format(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test plan show with JSON format."""
        with patch("routeros_mcp.cli.admin.PlanService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_plan = AsyncMock(
                return_value={
                    "plan_id": "plan-12345",
                    "status": "pending",
                    "tool_name": "config/plan-dns-ntp",
                    "created_by": "test-user",
                    "created_at": "2024-01-15T10:30:00Z",
                    "risk_level": "medium",
                    "device_ids": ["dev-lab-01"],
                    "summary": "Update DNS servers",
                    "changes": {"dns_servers": ["8.8.8.8"]},
                }
            )
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "plan", "show",
                    "plan-12345",
                    "--format", "json",
                ],
            )

            assert result.exit_code == 0
            assert '"plan_id": "plan-12345"' in result.output

    def test_plan_approve_non_interactive(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test plan approval token retrieval in non-interactive mode."""
        with patch("routeros_mcp.cli.admin.PlanService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.get_plan = AsyncMock(
                return_value={
                    "plan_id": "plan-12345",
                    "changes": {
                        "approval_token": "approve-abc123-xyz",
                        "approval_expires_at": "2024-01-15T10:45:00Z",
                    }
                }
            )
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "plan", "approve",
                    "plan-12345",
                    "--non-interactive",
                ],
            )

            assert result.exit_code == 0
            assert "Approval token retrieved" in result.output
            assert "approve-abc123-xyz" in result.output

    def test_plan_reject_success(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test plan rejection."""
        with patch("routeros_mcp.cli.admin.PlanService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.update_plan_status = AsyncMock()
            mock_service_class.return_value = mock_service

            result = cli_runner.invoke(
                admin,
                [
                    "--config", "config/lab.yaml",
                    "plan", "reject",
                    "plan-12345",
                    "--reason", "Invalid configuration",
                ],
            )

            assert result.exit_code == 0
            assert "rejected" in result.output
            assert "Invalid configuration" in result.output

    def test_plan_reject_missing_reason(
        self, cli_runner, mock_settings, mock_session_factory
    ):
        """Test plan rejection without reason fails."""
        result = cli_runner.invoke(
            admin,
            [
                "--config", "config/lab.yaml",
                "plan", "reject",
                "plan-12345",
            ],
        )

        assert result.exit_code != 0
        # Click will show "Missing option" error


class TestCLIHelp:
    """Tests for CLI help messages."""

    def test_main_help(self, cli_runner):
        """Test main CLI help."""
        result = cli_runner.invoke(admin, ["--help"])

        assert result.exit_code == 0
        assert "Device onboarding and plan management" in result.output
        assert "device" in result.output
        assert "plan" in result.output

    def test_device_help(self, cli_runner):
        """Test device command help."""
        result = cli_runner.invoke(admin, ["device", "--help"])

        assert result.exit_code == 0
        assert "Manage RouterOS devices" in result.output
        assert "add" in result.output
        assert "list" in result.output
        assert "update" in result.output
        assert "test" in result.output

    def test_plan_help(self, cli_runner):
        """Test plan command help."""
        result = cli_runner.invoke(admin, ["plan", "--help"])

        assert result.exit_code == 0
        assert "Manage configuration change plans" in result.output
        assert "list" in result.output
        assert "show" in result.output
        assert "approve" in result.output
        assert "reject" in result.output

    def test_device_add_help(self, cli_runner):
        """Test device add command help."""
        result = cli_runner.invoke(admin, ["device", "add", "--help"])

        assert result.exit_code == 0
        assert "--id" in result.output
        assert "--name" in result.output
        assert "--ip" in result.output
        assert "--username" in result.output
        assert "--password" in result.output
        assert "--allow-professional-workflows" in result.output
