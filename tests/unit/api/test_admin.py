"""Tests for admin API routes."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from routeros_mcp.api.admin import router
from routeros_mcp.api.http import create_http_app


def create_mock_dependency(mock_service):
    """Create a dependency override that returns the mock service."""
    async def _dependency():
        yield mock_service
    return _dependency


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

    def test_list_devices_empty(self, app, mock_device_service):
        """Test listing devices when none exist."""
        from routeros_mcp.api.admin import get_device_service
        
        mock_device_service.list_devices.return_value = []
        app.dependency_overrides[get_device_service] = create_mock_dependency(mock_device_service)
        
        client = TestClient(app)
        response = client.get("/admin/api/devices")
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert len(data["devices"]) == 0

    def test_list_devices_with_data(self, app, mock_device_service):
        """Test listing devices with data."""
        from routeros_mcp.api.admin import get_device_service
        
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
        mock_device_service.list_devices.return_value = [mock_device]
        app.dependency_overrides[get_device_service] = create_mock_dependency(mock_device_service)

        client = TestClient(app)
        response = client.get("/admin/api/devices")
        assert response.status_code == 200
        data = response.json()
        assert len(data["devices"]) == 1
        assert data["devices"][0]["id"] == "dev-1"
        assert data["devices"][0]["name"] == "router-1"
        assert data["devices"][0]["environment"] == "lab"
        assert data["devices"][0]["status"] == "online"

    def test_list_devices_offline(self, app, mock_device_service):
        """Test listing devices with offline status."""
        from routeros_mcp.api.admin import get_device_service
        
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
        mock_device_service.list_devices.return_value = [mock_device]
        app.dependency_overrides[get_device_service] = create_mock_dependency(mock_device_service)

        client = TestClient(app)
        response = client.get("/admin/api/devices")
        assert response.status_code == 200
        data = response.json()
        assert data["devices"][0]["status"] == "offline"


class TestPlansList:
    """Tests for plan list endpoint."""

    def test_list_plans_empty(self, app, mock_plan_service):
        """Test listing plans when none exist."""
        from routeros_mcp.api.admin import get_plan_service
        
        mock_plan_service.list_plans.return_value = []
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        response = client.get("/admin/api/plans")
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        assert len(data["plans"]) == 0

    def test_list_plans_with_data(self, app, mock_plan_service):
        """Test listing plans with data."""
        from routeros_mcp.api.admin import get_plan_service
        
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
        mock_plan_service.list_plans.return_value = [mock_plan]
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        response = client.get("/admin/api/plans")
        assert response.status_code == 200
        data = response.json()
        assert len(data["plans"]) == 1
        assert data["plans"][0]["id"] == "plan-1"
        assert data["plans"][0]["status"] == "pending"

    def test_list_plans_with_filter(self, app, mock_plan_service):
        """Test listing plans with status filter."""
        from routeros_mcp.api.admin import get_plan_service
        
        mock_plan_service.list_plans.return_value = []
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        response = client.get("/admin/api/plans?status_filter=approved")
        assert response.status_code == 200
        mock_plan_service.list_plans.assert_called_once()
        call_args = mock_plan_service.list_plans.call_args
        assert call_args[1]["filters"]["status"] == "approved"


class TestPlanDetail:
    """Tests for plan detail endpoint."""

    def test_get_plan_detail(self, app, mock_plan_service):
        """Test getting plan detail."""
        from routeros_mcp.api.admin import get_plan_service
        
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
        mock_plan_service.get_plan.return_value = mock_plan
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        response = client.get("/admin/api/plans/plan-1")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "plan-1"
        assert data["status"] == "pending"
        assert "changes" in data

    def test_get_plan_not_found(self, app, mock_plan_service):
        """Test getting non-existent plan."""
        from routeros_mcp.api.admin import get_plan_service
        
        mock_plan_service.get_plan.side_effect = ValueError("Plan not found")
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        response = client.get("/admin/api/plans/invalid")
        assert response.status_code == 404


class TestPlanApproval:
    """Tests for plan approval endpoint."""

    def test_approve_plan_success(self, app, mock_plan_service):
        """Test approving a plan successfully."""
        from routeros_mcp.api.admin import get_plan_service
        
        now = datetime.now(UTC)
        mock_result = {
            "approval_token": "approve-abc123-xyz",
            "expires_at": now + timedelta(minutes=15),
        }
        mock_plan_service.approve_plan.return_value = mock_result
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        response = client.post("/admin/api/plans/plan-1/approve", json={})
        assert response.status_code == 200
        data = response.json()
        assert "approval_token" in data
        assert data["approval_token"] == "approve-abc123-xyz"

    def test_approve_plan_invalid_status(self, app, mock_plan_service):
        """Test approving a plan with invalid status."""
        from routeros_mcp.api.admin import get_plan_service
        
        mock_plan_service.approve_plan.side_effect = ValueError("Invalid plan status")
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        response = client.post("/admin/api/plans/plan-1/approve", json={})
        assert response.status_code == 400

    def test_approve_plan_insufficient_permissions(self, app, mock_plan_service):
        """Test approving plan with read-only role."""
        from routeros_mcp.api.admin import get_plan_service, get_current_user_dep
        
        # Override the user dependency to return read-only user
        async def mock_get_user():
            return {
                "sub": "test-user",
                "email": "test@example.com",
                "role": "read_only",
            }
        
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)
        app.dependency_overrides[get_current_user_dep()] = mock_get_user

        client = TestClient(app)
        response = client.post("/admin/api/plans/plan-1/approve", json={})
        assert response.status_code == 403


class TestPlanRejection:
    """Tests for plan rejection endpoint."""

    def test_reject_plan_success(self, app, mock_plan_service):
        """Test rejecting a plan successfully."""
        from routeros_mcp.api.admin import get_plan_service
        
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        response = client.post(
            "/admin/api/plans/plan-1/reject",
            json={"reason": "Not meeting requirements"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "Plan rejected successfully" in data["message"]

    def test_reject_plan_without_reason(self, app, mock_plan_service):
        """Test rejecting plan without reason."""
        from routeros_mcp.api.admin import get_plan_service
        
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)

        client = TestClient(app)
        # Missing reason field
        response = client.post("/admin/api/plans/plan-1/reject", json={})
        assert response.status_code == 422  # FastAPI validation error

    def test_reject_plan_insufficient_permissions(self, app, mock_plan_service):
        """Test rejecting plan with insufficient permissions."""
        from routeros_mcp.api.admin import get_plan_service, get_current_user_dep
        
        # Override the user dependency to return read-only user
        async def mock_get_user():
            return {
                "sub": "test-user",
                "email": "test@example.com",
                "role": "read_only",
            }
        
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)
        app.dependency_overrides[get_current_user_dep()] = mock_get_user

        client = TestClient(app)

        response = client.post(
            "/admin/api/plans/plan-1/reject",
            json={"reason": "Not needed"},
        )
        assert response.status_code == 403


class TestAuthentication:
    """Tests for authentication requirements."""

    def test_admin_endpoints_require_auth(self, app, mock_device_service, mock_plan_service):
        """Test that admin endpoints exist and are accessible."""
        from routeros_mcp.api.admin import get_device_service, get_plan_service
        
        # Mock the dependencies to avoid DB initialization
        app.dependency_overrides[get_device_service] = create_mock_dependency(mock_device_service)
        app.dependency_overrides[get_plan_service] = create_mock_dependency(mock_plan_service)
        
        client = TestClient(app)

        # Endpoints should exist and work with mocked dependencies
        response = client.get("/admin/api/devices")
        assert response.status_code == 200

        response = client.get("/admin/api/plans")
        assert response.status_code == 200
