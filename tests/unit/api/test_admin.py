"""Tests for admin API routes."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from routeros_mcp.api.admin import router
from routeros_mcp.api.http import create_http_app
from routeros_mcp.domain.models import PlanStatus


@pytest.fixture
def settings():
    """Create test settings with OIDC disabled."""
    from routeros_mcp.config import Settings
    return Settings(oidc_enabled=False, debug=True)


@pytest.fixture
def app(settings):
    """Create test FastAPI app."""
    return create_http_app(settings)


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_user():
    """Mock authenticated user."""
    return {
        "sub": "test-user",
        "email": "test@example.com",
        "name": "Test User",
        "role": "admin",
    }


@pytest.fixture
def mock_device_service():
    """Mock device service."""
    service = MagicMock()
    service.list_devices = AsyncMock(return_value=[])
    return service


@pytest.fixture
def mock_plan_service():
    """Mock plan service."""
    service = MagicMock()
    service.list_plans = AsyncMock(return_value=[])
    service.get_plan = AsyncMock(return_value={})
    service.approve_plan = AsyncMock(return_value={})
    service.update_plan_status = AsyncMock()
    return service


class TestAdminDashboard:
    """Tests for admin dashboard endpoint."""

    def test_dashboard_returns_html(self, client):
        """Test dashboard endpoint returns HTML."""
        response = client.get("/admin")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert b"RouterOS MCP Admin Console" in response.content


class TestDevicesList:
    """Tests for device list endpoint."""

    @patch("routeros_mcp.api.admin.get_device_service")
    def test_list_devices_empty(self, mock_get_service, client, mock_device_service):
        """Test listing devices when none exist."""
        mock_get_service.return_value = mock_device_service
        mock_device_service.list_devices.return_value = []

        response = client.get("/admin/api/devices")
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert len(data["devices"]) == 0

    @patch("routeros_mcp.api.admin.get_device_service")
    def test_list_devices_with_data(self, mock_get_service, client, mock_device_service):
        """Test listing devices with data."""
        mock_device = SimpleNamespace(
            id="dev-1",
            name="router-1",
            management_ip="192.168.1.1",
            management_port=443,
            environment="lab",
            tags={"location": "office"},
            capabilities={"allow_firewall_writes": True},
            last_seen=datetime.now(UTC),
        )
        mock_get_service.return_value = mock_device_service
        mock_device_service.list_devices.return_value = [mock_device]

        response = client.get("/admin/api/devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["id"] == "dev-1"
        assert data["devices"][0]["name"] == "router-1"
        assert data["devices"][0]["environment"] == "lab"
        assert data["devices"][0]["status"] == "online"

    @patch("routeros_mcp.api.admin.get_device_service")
    def test_list_devices_offline(self, mock_get_service, client, mock_device_service):
        """Test listing devices with offline status."""
        mock_device = SimpleNamespace(
            id="dev-2",
            name="router-2",
            management_ip="192.168.1.2",
            management_port=443,
            environment="staging",
            tags={},
            capabilities={},
            last_seen=None,
        )
        mock_get_service.return_value = mock_device_service
        mock_device_service.list_devices.return_value = [mock_device]

        response = client.get("/admin/api/devices")
        assert response.status_code == 200
        data = response.json()
        assert data["devices"][0]["status"] == "offline"


class TestPlansList:
    """Tests for plan list endpoint."""

    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_list_plans_empty(self, mock_get_service, client, mock_plan_service):
        """Test listing plans when none exist."""
        mock_get_service.return_value = mock_plan_service
        mock_plan_service.list_plans.return_value = []

        response = client.get("/admin/api/plans")
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert len(data["plans"]) == 0

    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_list_plans_with_data(self, mock_get_service, client, mock_plan_service):
        """Test listing plans with data."""
        now = datetime.now(UTC)
        mock_plan = {
            "id": "plan-1",
            "created_by": "user-1",
            "tool_name": "firewall_write",
            "status": "pending",
            "summary": "Add firewall rules",
            "device_ids": ["dev-1"],
            "created_at": now,
            "approved_by": None,
            "approved_at": None,
        }
        mock_get_service.return_value = mock_plan_service
        mock_plan_service.list_plans.return_value = [mock_plan]

        response = client.get("/admin/api/plans")
        assert response.status_code == 200
        data = response.json()
        assert len(data["plans"]) == 1
        assert data["plans"][0]["id"] == "plan-1"
        assert data["plans"][0]["status"] == "pending"

    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_list_plans_with_filter(self, mock_get_service, client, mock_plan_service):
        """Test listing plans with status filter."""
        mock_get_service.return_value = mock_plan_service
        mock_plan_service.list_plans.return_value = []

        response = client.get("/admin/api/plans?status_filter=approved")
        assert response.status_code == 200
        mock_plan_service.list_plans.assert_called_once()
        call_args = mock_plan_service.list_plans.call_args
        assert call_args[1]["filters"]["status"] == "approved"


class TestPlanDetail:
    """Tests for plan detail endpoint."""

    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_get_plan_detail(self, mock_get_service, client, mock_plan_service):
        """Test getting plan detail."""
        now = datetime.now(UTC)
        mock_plan = {
            "id": "plan-1",
            "created_by": "user-1",
            "tool_name": "firewall_write",
            "status": "pending",
            "summary": "Add firewall rules",
            "device_ids": ["dev-1"],
            "changes": {"rules": [{"action": "accept"}]},
            "created_at": now,
            "approved_by": None,
            "approved_at": None,
            "approval_token": None,
            "approval_token_expires_at": None,
        }
        mock_get_service.return_value = mock_plan_service
        mock_plan_service.get_plan.return_value = mock_plan

        response = client.get("/admin/api/plans/plan-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "plan-1"
        assert data["status"] == "pending"
        assert "changes" in data

    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_get_plan_not_found(self, mock_get_service, client, mock_plan_service):
        """Test getting non-existent plan."""
        mock_get_service.return_value = mock_plan_service
        mock_plan_service.get_plan.side_effect = ValueError("Plan not found")

        response = client.get("/admin/api/plans/invalid")
        assert response.status_code == 404


class TestPlanApproval:
    """Tests for plan approval endpoint."""

    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_approve_plan_success(self, mock_get_service, client, mock_plan_service):
        """Test approving a plan successfully."""
        now = datetime.now(UTC)
        mock_result = {
            "approval_token": "approve-abc123-xyz",
            "expires_at": now + timedelta(minutes=15),
        }
        mock_get_service.return_value = mock_plan_service
        mock_plan_service.approve_plan.return_value = mock_result

        response = client.post("/admin/api/plans/plan-1/approve", json={})
        assert response.status_code == 200
        data = response.json()
        assert "approval_token" in data
        assert data["approval_token"] == "approve-abc123-xyz"

    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_approve_plan_invalid_status(self, mock_get_service, client, mock_plan_service):
        """Test approving a plan with invalid status."""
        mock_get_service.return_value = mock_plan_service
        mock_plan_service.approve_plan.side_effect = ValueError("Invalid plan status")

        response = client.post("/admin/api/plans/plan-1/approve", json={})
        assert response.status_code == 400

    @patch("routeros_mcp.api.admin.get_current_user")
    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_approve_plan_insufficient_permissions(
        self, mock_get_service, mock_get_user, client, mock_plan_service
    ):
        """Test approving plan with read-only role."""
        # Override the dependency to return read-only user
        mock_get_user.return_value = {
            "sub": "test-user",
            "email": "test@example.com",
            "role": "read_only",
        }
        mock_get_service.return_value = mock_plan_service

        response = client.post("/admin/api/plans/plan-1/approve", json={})
        assert response.status_code == 403


class TestPlanRejection:
    """Tests for plan rejection endpoint."""

    @patch("routeros_mcp.api.admin.get_session")
    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_reject_plan_success(
        self, mock_get_service, mock_get_session, client, mock_plan_service
    ):
        """Test rejecting a plan successfully."""
        mock_session = AsyncMock()
        mock_get_session.return_value = mock_session
        mock_get_service.return_value = mock_plan_service

        response = client.post(
            "/admin/api/plans/plan-1/reject",
            json={"reason": "Not meeting requirements"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "Plan rejected successfully" in data["message"]

    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_reject_plan_without_reason(self, mock_get_service, client, mock_plan_service):
        """Test rejecting plan without reason."""
        mock_get_service.return_value = mock_plan_service

        # Missing reason field
        response = client.post("/admin/api/plans/plan-1/reject", json={})
        assert response.status_code == 422  # FastAPI validation error

    @patch("routeros_mcp.api.admin.get_current_user")
    @patch("routeros_mcp.api.admin.get_plan_service")
    def test_reject_plan_insufficient_permissions(
        self, mock_get_service, mock_get_user, client, mock_plan_service
    ):
        """Test rejecting plan with insufficient permissions."""
        mock_get_user.return_value = {
            "sub": "test-user",
            "email": "test@example.com",
            "role": "read_only",
        }
        mock_get_service.return_value = mock_plan_service

        response = client.post(
            "/admin/api/plans/plan-1/reject",
            json={"reason": "Not needed"},
        )
        assert response.status_code == 403


class TestAuthentication:
    """Tests for authentication requirements."""

    def test_admin_endpoints_require_auth(self):
        """Test that admin endpoints require authentication when OIDC enabled."""
        # Create app with OIDC enabled
        from routeros_mcp.config import Settings
        
        settings_with_auth = Settings(
            oidc_enabled=True,
            oidc_client_id="test-client",
            oidc_client_secret="test-secret",
            oidc_issuer="https://auth.example.com",
        )
        app = create_http_app(settings_with_auth)
        client = TestClient(app)

        # Without Bearer token should return 401
        response = client.get("/admin/api/devices")
        assert response.status_code == 401

        response = client.get("/admin/api/plans")
        assert response.status_code == 401
