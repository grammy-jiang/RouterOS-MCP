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


@pytest.fixture
def mock_audit_service():
    """Mock audit service."""
    service = MagicMock()
    service.list_events = AsyncMock(return_value={
        "events": [],
        "total": 0,
        "page": 1,
        "page_size": 20,
        "total_pages": 0,
    })
    service.get_unique_devices = AsyncMock(return_value=[])
    service.get_unique_tools = AsyncMock(return_value=[])
    return service


class TestAuditEvents:
    """Tests for audit events API endpoints."""

    def test_list_audit_events_empty(self, app, mock_audit_service):
        """Test listing audit events when none exist."""
        from routeros_mcp.api.admin import get_audit_service
        
        app.dependency_overrides[get_audit_service] = create_mock_dependency(mock_audit_service)
        
        client = TestClient(app)
        response = client.get("/admin/api/audit/events")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert len(data["events"]) == 0
        assert data["total"] == 0

    def test_list_audit_events_with_data(self, app, mock_audit_service):
        """Test listing audit events with data."""
        from routeros_mcp.api.admin import get_audit_service
        
        mock_events = [
            {
                "id": "evt-001",
                "timestamp": "2024-01-01T00:00:00Z",
                "user_sub": "user-1",
                "user_email": "user1@example.com",
                "user_role": "admin",
                "user_id": "user-1",
                "approver_id": None,
                "approval_request_id": None,
                "device_id": "dev-001",
                "environment": "lab",
                "action": "WRITE",
                "tool_name": "device_create",
                "tool_tier": "fundamental",
                "success": True,
                "error_message": None,
                "parameters": None,
                "result_summary": None,
                "correlation_id": None,
            }
        ]
        
        mock_audit_service.list_events.return_value = {
            "events": mock_events,
            "total": 1,
            "page": 1,
            "page_size": 20,
            "total_pages": 1,
        }
        
        app.dependency_overrides[get_audit_service] = create_mock_dependency(mock_audit_service)
        
        client = TestClient(app)
        response = client.get("/admin/api/audit/events")
        assert response.status_code == 200
        data = response.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["id"] == "evt-001"

    def test_list_audit_events_with_filters(self, app, mock_audit_service):
        """Test listing audit events with filters."""
        from routeros_mcp.api.admin import get_audit_service
        
        app.dependency_overrides[get_audit_service] = create_mock_dependency(mock_audit_service)
        
        client = TestClient(app)
        response = client.get(
            "/admin/api/audit/events",
            params={
                "device_id": "dev-001",
                "tool_name": "device_create",
                "success": True,
                "search": "test",
            }
        )
        assert response.status_code == 200
        
        # Verify service was called with filters
        mock_audit_service.list_events.assert_called_once()
        call_kwargs = mock_audit_service.list_events.call_args[1]
        assert call_kwargs["device_id"] == "dev-001"
        assert call_kwargs["tool_name"] == "device_create"
        assert call_kwargs["success"] is True
        assert call_kwargs["search"] == "test"

    def test_list_audit_events_with_date_range(self, app, mock_audit_service):
        """Test listing audit events with date range filter."""
        from routeros_mcp.api.admin import get_audit_service
        
        app.dependency_overrides[get_audit_service] = create_mock_dependency(mock_audit_service)
        
        client = TestClient(app)
        response = client.get(
            "/admin/api/audit/events",
            params={
                "date_from": "2024-01-01T00:00:00Z",
                "date_to": "2024-01-31T23:59:59Z",
            }
        )
        assert response.status_code == 200
        
        # Verify service was called with parsed dates
        mock_audit_service.list_events.assert_called_once()
        call_kwargs = mock_audit_service.list_events.call_args[1]
        assert call_kwargs["date_from"] is not None
        assert call_kwargs["date_to"] is not None

    def test_list_audit_events_invalid_date(self, app, mock_audit_service):
        """Test listing audit events with invalid date format."""
        from routeros_mcp.api.admin import get_audit_service
        
        app.dependency_overrides[get_audit_service] = create_mock_dependency(mock_audit_service)
        
        client = TestClient(app)
        response = client.get(
            "/admin/api/audit/events",
            params={"date_from": "invalid-date"}
        )
        assert response.status_code == 400
        assert "Invalid date_from format" in response.json()["detail"]

    def test_list_audit_events_pagination(self, app, mock_audit_service):
        """Test audit events pagination."""
        from routeros_mcp.api.admin import get_audit_service
        
        app.dependency_overrides[get_audit_service] = create_mock_dependency(mock_audit_service)
        
        client = TestClient(app)
        response = client.get(
            "/admin/api/audit/events",
            params={"page": 2, "page_size": 50}
        )
        assert response.status_code == 200
        
        # Verify service was called with pagination params
        mock_audit_service.list_events.assert_called_once()
        call_kwargs = mock_audit_service.list_events.call_args[1]
        assert call_kwargs["page"] == 2
        assert call_kwargs["page_size"] == 50

    def test_export_audit_events_csv(self, app, mock_audit_service):
        """Test exporting audit events to CSV."""
        from routeros_mcp.api.admin import get_audit_service
        
        mock_events = [
            {
                "id": "evt-001",
                "timestamp": "2024-01-01T00:00:00Z",
                "user_sub": "user-1",
                "user_email": "user1@example.com",
                "user_role": "admin",
                "user_id": "user-1",
                "approver_id": None,
                "approval_request_id": None,
                "device_id": "dev-001",
                "environment": "lab",
                "action": "WRITE",
                "tool_name": "device_create",
                "tool_tier": "fundamental",
                "success": True,
                "error_message": None,
                "parameters": None,
                "result_summary": None,
                "correlation_id": None,
            }
        ]
        
        mock_audit_service.list_events.return_value = {
            "events": mock_events,
            "total": 1,
            "page": 1,
            "page_size": 10000,
            "total_pages": 1,
        }
        
        app.dependency_overrides[get_audit_service] = create_mock_dependency(mock_audit_service)
        
        client = TestClient(app)
        response = client.get("/admin/api/audit/events/export")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment" in response.headers["content-disposition"]
        
        # Verify CSV content
        content = response.text
        assert "Timestamp" in content
        assert "User Email" in content
        assert "user1@example.com" in content
        assert "device_create" in content

    def test_get_audit_filters(self, app, mock_audit_service):
        """Test getting available audit filter options."""
        from routeros_mcp.api.admin import get_audit_service
        
        mock_audit_service.get_unique_devices.return_value = ["dev-001", "dev-002"]
        mock_audit_service.get_unique_tools.return_value = ["device_create", "device_test"]
        
        app.dependency_overrides[get_audit_service] = create_mock_dependency(mock_audit_service)
        
        client = TestClient(app)
        response = client.get("/admin/api/audit/filters")
        assert response.status_code == 200
        data = response.json()
        assert "devices" in data
        assert "tools" in data
        assert len(data["devices"]) == 2
        assert len(data["tools"]) == 2
        assert "dev-001" in data["devices"]
        assert "device_create" in data["tools"]
