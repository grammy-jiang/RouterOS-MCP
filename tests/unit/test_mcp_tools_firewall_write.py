"""Tests for firewall write MCP tools (plan phase)."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import Mock, patch

from routeros_mcp.config import Settings
from routeros_mcp.domain.models import PlanStatus
from routeros_mcp.mcp_tools import firewall_write as firewall_write_module
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


class FakeDevice:
    """Fake device for testing."""

    def __init__(
        self,
        device_id: str = "dev-lab-01",
        environment: str = "lab",
        allow_professional_workflows: bool = True,
        allow_firewall_writes: bool = True,
    ) -> None:
        self.id = device_id
        self.name = f"router-{device_id}"
        self.environment = environment
        self.allow_professional_workflows = allow_professional_workflows
        self.allow_advanced_writes = True
        self.allow_firewall_writes = allow_firewall_writes
        self.status = "healthy"


class FakeDeviceService:
    """Fake device service for testing."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.devices = {
            "dev-lab-01": FakeDevice("dev-lab-01", "lab"),
            "dev-lab-02": FakeDevice("dev-lab-02", "lab"),
            "dev-staging-01": FakeDevice("dev-staging-01", "staging"),
            "dev-prod-01": FakeDevice("dev-prod-01", "prod"),
        }

    async def get_device(self, device_id: str) -> FakeDevice:
        if device_id not in self.devices:
            raise ValueError(f"Device not found: {device_id}")
        return self.devices[device_id]


class FakePlanService:
    """Fake plan service for testing."""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def create_plan(
        self,
        tool_name: str,
        created_by: str,
        device_ids: list[str],
        summary: str,
        changes: dict,
        risk_level: str = "medium",
    ) -> dict:
        return {
            "plan_id": "plan-test-001",
            "approval_token": "approve-test-abc123",
            "approval_expires_at": "2025-12-20T16:00:00Z",
            "risk_level": risk_level,
            "device_count": len(device_ids),
            "devices": device_ids,
            "summary": summary,
            "status": PlanStatus.PENDING.value,
            "pre_check_results": {"status": "passed"},
        }


class TestFirewallPlanTools(unittest.TestCase):
    """Tests for firewall plan MCP tools."""

    def _register_tools(self) -> DummyMCP:
        """Register firewall write tools for testing."""
        mcp = DummyMCP()
        settings = Settings()
        firewall_write_module.register_firewall_write_tools(mcp, settings)
        return mcp

    def _get_content_text(self, result: dict) -> str:
        """Extract content text from tool result.

        Args:
            result: Tool result dictionary

        Returns:
            Content text string
        """
        content = result["content"]
        if isinstance(content, list) and len(content) > 0:
            return content[0].get("text", "")
        return str(content)

    def _create_mock_authz(self) -> Mock:
        """Create a mock for check_tool_authorization.

        Returns:
            Mock object with return_value=None
        """
        return Mock(return_value=None)

    def test_plan_add_firewall_rule_success(self) -> None:
        """Test successful firewall rule addition plan."""

        async def _run() -> None:
            mock_authz = self._create_mock_authz()
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    mock_authz,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_add_firewall_rule"]
                result = await fn(
                    device_ids=["dev-lab-01", "dev-lab-02"],
                    chain="forward",
                    action="accept",
                    src_address="192.168.1.0/24",
                    dst_address="10.0.0.0/8",
                    protocol="tcp",
                    dst_port="443",
                    comment="Allow HTTPS",
                )

                # Check success
                self.assertFalse(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("plan created successfully", content_text)

                # Check metadata
                meta = result["_meta"]
                self.assertEqual(meta["plan_id"], "plan-test-001")
                self.assertEqual(meta["approval_token"], "approve-test-abc123")
                self.assertEqual(meta["device_count"], 2)
                self.assertEqual(meta["tool_name"], "firewall/plan-add-rule")
                self.assertIn(meta["risk_level"], ["medium", "high"])

                # Check device previews
                self.assertEqual(len(meta["devices"]), 2)
                for device_preview in meta["devices"]:
                    self.assertIn("device_id", device_preview)
                    self.assertIn("preview", device_preview)
                    self.assertEqual(device_preview["preview"]["operation"], "add_firewall_rule")
                    self.assertEqual(device_preview["preview"]["chain"], "forward")

        asyncio.run(_run())

    def test_plan_add_firewall_rule_invalid_chain(self) -> None:
        """Test plan with invalid chain."""

        async def _run() -> None:
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_add_firewall_rule"]
                result = await fn(
                    device_ids=["dev-lab-01"],
                    chain="invalid_chain",
                    action="accept",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("Invalid chain", content_text)

        asyncio.run(_run())

    def test_plan_add_firewall_rule_invalid_action(self) -> None:
        """Test plan with invalid action."""

        async def _run() -> None:
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_add_firewall_rule"]
                result = await fn(
                    device_ids=["dev-lab-01"],
                    chain="forward",
                    action="invalid_action",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("Invalid action", content_text)

        asyncio.run(_run())

    def test_plan_add_firewall_rule_invalid_ip(self) -> None:
        """Test plan with invalid IP address."""

        async def _run() -> None:
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_add_firewall_rule"]
                result = await fn(
                    device_ids=["dev-lab-01"],
                    chain="forward",
                    action="accept",
                    src_address="invalid-ip",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("Invalid source address", content_text)

        asyncio.run(_run())

    def test_plan_add_firewall_rule_prod_environment(self) -> None:
        """Test plan rejects production environment by default."""

        async def _run() -> None:
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_add_firewall_rule"]
                result = await fn(
                    device_ids=["dev-prod-01"],
                    chain="forward",
                    action="accept",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("prod environment", content_text)
                self.assertIn("only allowed in", content_text)

        asyncio.run(_run())

    def test_plan_add_firewall_rule_missing_capability(self) -> None:
        """Test plan requires firewall write capability."""

        async def _run() -> None:
            # Create device without firewall write capability
            device_service = FakeDeviceService()
            device_service.devices["dev-lab-01"].allow_firewall_writes = False

            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    lambda *args, **kwargs: device_service,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_add_firewall_rule"]
                result = await fn(
                    device_ids=["dev-lab-01"],
                    chain="forward",
                    action="accept",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("firewall write capability", content_text)

        asyncio.run(_run())

    def test_plan_modify_firewall_rule_success(self) -> None:
        """Test successful firewall rule modification plan."""

        async def _run() -> None:
            mock_authz = self._create_mock_authz()
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    mock_authz,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_modify_firewall_rule"]
                result = await fn(
                    device_ids=["dev-lab-01"],
                    rule_id="*5",
                    action="drop",
                    comment="Updated rule",
                )

                # Check success
                self.assertFalse(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("modification plan created", content_text)

                # Check metadata
                meta = result["_meta"]
                self.assertEqual(meta["plan_id"], "plan-test-001")
                self.assertEqual(meta["tool_name"], "firewall/plan-modify-rule")
                self.assertEqual(meta["risk_level"], "high")  # Modification is always high risk

        asyncio.run(_run())

    def test_plan_modify_firewall_rule_no_modifications(self) -> None:
        """Test plan modify requires at least one modification."""

        async def _run() -> None:
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_modify_firewall_rule"]
                result = await fn(
                    device_ids=["dev-lab-01"],
                    rule_id="*5",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("At least one modification", content_text)

        asyncio.run(_run())

    def test_plan_remove_firewall_rule_success(self) -> None:
        """Test successful firewall rule removal plan."""

        async def _run() -> None:
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_remove_firewall_rule"]
                result = await fn(
                    device_ids=["dev-lab-01", "dev-lab-02"],
                    rule_id="*5",
                )

                # Check success
                self.assertFalse(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("removal plan created", content_text)
                self.assertIn("WARNING", content_text)

                # Check metadata
                meta = result["_meta"]
                self.assertEqual(meta["plan_id"], "plan-test-001")
                self.assertEqual(meta["tool_name"], "firewall/plan-remove-rule")
                self.assertEqual(meta["risk_level"], "high")  # Removal is always high risk
                self.assertEqual(meta["device_count"], 2)

        asyncio.run(_run())

    def test_plan_remove_firewall_rule_device_not_found(self) -> None:
        """Test plan remove with nonexistent device."""

        async def _run() -> None:
            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    FakeDeviceService,
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    FakePlanService,
                ),
                patch.object(
                    firewall_write_module,
                    "check_tool_authorization",
                    lambda **_kwargs: None,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["plan_remove_firewall_rule"]
                result = await fn(
                    device_ids=["nonexistent-device"],
                    rule_id="*5",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("Device not found", content_text)

        asyncio.run(_run())


class TestFirewallPlanService(unittest.TestCase):
    """Tests for FirewallPlanService."""

    def test_validate_rule_params_valid(self) -> None:
        """Test validation with valid parameters."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        result = service.validate_rule_params(
            chain="forward",
            action="accept",
            src_address="192.168.1.0/24",
            dst_address="10.0.0.0/8",
            protocol="tcp",
            dst_port="443",
        )

        self.assertTrue(result["valid"])
        self.assertEqual(result["chain"], "forward")
        self.assertEqual(result["action"], "accept")

    def test_validate_rule_params_invalid_chain(self) -> None:
        """Test validation with invalid chain."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        with self.assertRaises(ValueError) as cm:
            service.validate_rule_params(chain="invalid", action="accept")

        self.assertIn("Invalid chain", str(cm.exception))

    def test_validate_rule_params_invalid_action(self) -> None:
        """Test validation with invalid action."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        with self.assertRaises(ValueError) as cm:
            service.validate_rule_params(chain="forward", action="invalid")

        self.assertIn("Invalid action", str(cm.exception))

    def test_validate_rule_params_invalid_ip(self) -> None:
        """Test validation with invalid IP address."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        with self.assertRaises(ValueError) as cm:
            service.validate_rule_params(
                chain="forward", action="accept", src_address="invalid-ip"
            )

        self.assertIn("Invalid source address", str(cm.exception))

    def test_validate_rule_params_invalid_port(self) -> None:
        """Test validation with invalid port."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        with self.assertRaises(ValueError) as cm:
            service.validate_rule_params(
                chain="forward", action="accept", dst_port="99999"
            )

        self.assertIn("Invalid destination port", str(cm.exception))

    def test_validate_rule_params_invalid_protocol(self) -> None:
        """Test validation with invalid protocol."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        with self.assertRaises(ValueError) as cm:
            service.validate_rule_params(
                chain="forward", action="accept", protocol="invalid_protocol"
            )

        self.assertIn("Invalid protocol", str(cm.exception))

    def test_validate_port_valid_single(self) -> None:
        """Test port validation with valid single port."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        self.assertTrue(service._validate_port("443"))
        self.assertTrue(service._validate_port("80"))
        self.assertTrue(service._validate_port("65535"))

    def test_validate_port_valid_range(self) -> None:
        """Test port validation with valid port range."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        self.assertTrue(service._validate_port("8000-9000"))
        self.assertTrue(service._validate_port("1-65535"))

    def test_validate_port_invalid_number(self) -> None:
        """Test port validation with invalid port number."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        self.assertFalse(service._validate_port("70000"))
        self.assertFalse(service._validate_port("0"))
        self.assertFalse(service._validate_port("-1"))

    def test_validate_port_invalid_range(self) -> None:
        """Test port validation with invalid port range."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        self.assertFalse(service._validate_port("9000-8000"))  # reversed range
        self.assertFalse(service._validate_port("0-1000"))  # starts with 0

    def test_validate_port_invalid_format(self) -> None:
        """Test port validation with invalid format."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        self.assertFalse(service._validate_port("abc"))
        self.assertFalse(service._validate_port("80-"))
        self.assertFalse(service._validate_port("-80"))

    def test_validate_port_whitespace_handling(self) -> None:
        """Test port validation with whitespace."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        self.assertTrue(service._validate_port(" 443 "))
        self.assertTrue(service._validate_port("8000 - 9000"))
        self.assertTrue(service._validate_port(" 8000-9000 "))

    def test_assess_risk_high_input_chain(self) -> None:
        """Test risk assessment for input chain (high risk)."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        risk = service.assess_risk(chain="input", action="accept", device_environment="lab")

        self.assertEqual(risk, "high")

    def test_assess_risk_high_reject_action(self) -> None:
        """Test risk assessment for reject action (high risk)."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        risk = service.assess_risk(chain="forward", action="reject", device_environment="lab")

        self.assertEqual(risk, "high")

    def test_assess_risk_high_prod_environment(self) -> None:
        """Test risk assessment for prod environment (high risk)."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        risk = service.assess_risk(chain="forward", action="accept", device_environment="prod")

        self.assertEqual(risk, "high")

    def test_assess_risk_medium(self) -> None:
        """Test risk assessment for medium risk scenario."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        risk = service.assess_risk(chain="forward", action="accept", device_environment="lab")

        self.assertEqual(risk, "medium")

    def test_generate_preview_add_rule(self) -> None:
        """Test preview generation for add rule operation."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        preview = service.generate_preview(
            operation="add_firewall_rule",
            device_id="dev-lab-01",
            device_name="router-lab-01",
            device_environment="lab",
            chain="forward",
            action="accept",
            src_address="192.168.1.0/24",
            dst_address="10.0.0.0/8",
            protocol="tcp",
            dst_port="443",
            comment="Test rule",
        )

        self.assertEqual(preview["device_id"], "dev-lab-01")
        self.assertEqual(preview["operation"], "add_firewall_rule")
        self.assertIn("preview", preview)
        self.assertEqual(preview["preview"]["chain"], "forward")
        self.assertIn("rule_spec", preview["preview"])
        self.assertIn("chain=forward", preview["preview"]["rule_spec"])

    def test_generate_preview_modify_rule(self) -> None:
        """Test preview generation for modify rule operation."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        preview = service.generate_preview(
            operation="modify_firewall_rule",
            device_id="dev-lab-01",
            device_name="router-lab-01",
            device_environment="lab",
            chain="forward",
            action="drop",
            rule_id="*5",
            modifications={"action": "drop"},
        )

        self.assertEqual(preview["operation"], "modify_firewall_rule")
        self.assertEqual(preview["preview"]["rule_id"], "*5")
        self.assertIn("modifications", preview["preview"])

    def test_generate_preview_remove_rule(self) -> None:
        """Test preview generation for remove rule operation."""
        from routeros_mcp.domain.services.firewall_plan import FirewallPlanService

        service = FirewallPlanService()
        preview = service.generate_preview(
            operation="remove_firewall_rule",
            device_id="dev-lab-01",
            device_name="router-lab-01",
            device_environment="lab",
            chain="forward",
            action="accept",
            rule_id="*5",
        )

        self.assertEqual(preview["operation"], "remove_firewall_rule")
        self.assertEqual(preview["preview"]["rule_id"], "*5")
        self.assertIn("estimated_impact", preview["preview"])


class TestFirewallApplyTool(unittest.TestCase):
    """Tests for firewall apply MCP tool."""

    def _register_tools(self) -> DummyMCP:
        """Register firewall write tools for testing."""
        mcp = DummyMCP()
        settings = Settings()
        firewall_write_module.register_firewall_write_tools(mcp, settings)
        return mcp

    def _get_content_text(self, result: dict) -> str:
        """Extract content text from tool result."""
        content = result["content"]
        if isinstance(content, list) and len(content) > 0:
            return content[0].get("text", "")
        return str(content)

    def test_apply_firewall_plan_success(self) -> None:
        """Test successful firewall plan apply workflow."""

        async def _run() -> None:
            from datetime import UTC, datetime, timedelta
            from unittest.mock import AsyncMock

            # Mock REST client
            mock_rest_client = AsyncMock()
            mock_rest_client.get = AsyncMock(
                side_effect=[
                    # Snapshot: get filter rules
                    [{"id": "*1", "chain": "input", "action": "accept"}],
                    # Health check: system resource
                    {"uptime": "1d2h3m"},
                    # Health check: filter rules
                    [{"id": "*1", "chain": "input", "action": "accept"}],
                ]
            )
            mock_rest_client.post = AsyncMock(
                return_value={".id": "*2"}  # New rule ID
            )
            mock_rest_client.close = AsyncMock(return_value=None)

            # Mock plan service
            fake_plan_service = AsyncMock()
            fake_plan_service.get_plan = AsyncMock(
                return_value={
                    "plan_id": "plan-test-001",
                    "created_by": "test-user",
                    "status": "pending",
                    "device_ids": ["dev-lab-01"],
                    "changes": {
                        "operation": "add_firewall_rule",
                        "chain": "forward",
                        "action": "accept",
                        "src_address": "192.168.1.0/24",
                        "approval_token_timestamp": datetime.now(UTC).isoformat(),
                        "approval_expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
                    },
                }
            )
            fake_plan_service._validate_approval_token = Mock(return_value=None)
            fake_plan_service.update_plan_status = AsyncMock(return_value=None)

            # Mock device service
            fake_device_service = AsyncMock()
            fake_device_service.get_device = AsyncMock(
                return_value=FakeDevice("dev-lab-01", "lab")
            )
            fake_device_service.get_rest_client = AsyncMock(
                return_value=mock_rest_client
            )

            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    return_value=fake_plan_service,
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    return_value=fake_device_service,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["apply_firewall_plan"]
                result = await fn(
                    plan_id="plan-test-001",
                    approval_token="approve-test-abc123",
                )

                # Check success
                self.assertFalse(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("successfully", content_text.lower())

                # Check metadata
                meta = result["_meta"]
                self.assertEqual(meta["plan_id"], "plan-test-001")
                self.assertEqual(meta["successful_count"], 1)
                self.assertEqual(meta["failed_count"], 0)
                self.assertEqual(meta["final_status"], "completed")

                # Verify plan status was updated
                fake_plan_service.update_plan_status.assert_any_call(
                    "plan-test-001", "executing", "mcp-user"
                )
                fake_plan_service.update_plan_status.assert_any_call(
                    "plan-test-001", "completed", "mcp-user"
                )

        asyncio.run(_run())

    def test_apply_firewall_plan_expired_token(self) -> None:
        """Test apply with expired approval token."""

        async def _run() -> None:
            from datetime import UTC, datetime, timedelta
            from unittest.mock import AsyncMock

            # Mock plan service with expired token
            fake_plan_service = AsyncMock()
            fake_plan_service.get_plan = AsyncMock(
                return_value={
                    "plan_id": "plan-test-001",
                    "created_by": "test-user",
                    "status": "pending",
                    "device_ids": ["dev-lab-01"],
                    "changes": {
                        "operation": "add_firewall_rule",
                        "approval_token_timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                        "approval_expires_at": (datetime.now(UTC) - timedelta(minutes=45)).isoformat(),
                    },
                }
            )
            fake_plan_service._validate_approval_token = Mock(
                side_effect=ValueError("Approval token has expired")
            )

            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    return_value=fake_plan_service,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["apply_firewall_plan"]
                result = await fn(
                    plan_id="plan-test-001",
                    approval_token="approve-test-expired",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("expired", content_text.lower())

        asyncio.run(_run())

    def test_apply_firewall_plan_health_check_failure_with_rollback(self) -> None:
        """Test apply with health check failure triggering rollback."""

        async def _run() -> None:
            from datetime import UTC, datetime, timedelta
            from unittest.mock import AsyncMock

            # Mock REST client with health check failure
            mock_rest_client = AsyncMock()
            mock_rest_client.get = AsyncMock(
                side_effect=[
                    # Snapshot: get filter rules
                    [{"id": "*1", "chain": "input", "action": "accept"}],
                    # Health check: system resource fails (returns None)
                    None,
                    # Rollback: get current rules
                    [
                        {"id": "*1", "chain": "input", "action": "accept"},
                        {"id": "*2", "chain": "forward", "action": "accept"},  # New rule
                    ],
                ]
            )
            mock_rest_client.post = AsyncMock(
                return_value={".id": "*2"}  # New rule ID
            )
            mock_rest_client.delete = AsyncMock(return_value=None)
            mock_rest_client.close = AsyncMock(return_value=None)

            # Mock plan service
            fake_plan_service = AsyncMock()
            fake_plan_service.get_plan = AsyncMock(
                return_value={
                    "plan_id": "plan-test-001",
                    "created_by": "test-user",
                    "status": "pending",
                    "device_ids": ["dev-lab-01"],
                    "changes": {
                        "operation": "add_firewall_rule",
                        "chain": "forward",
                        "action": "accept",
                        "src_address": "192.168.1.0/24",
                        "approval_token_timestamp": datetime.now(UTC).isoformat(),
                        "approval_expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
                    },
                }
            )
            fake_plan_service._validate_approval_token = Mock(return_value=None)
            fake_plan_service.update_plan_status = AsyncMock(return_value=None)

            # Mock device service
            fake_device_service = AsyncMock()
            fake_device_service.get_device = AsyncMock(
                return_value=FakeDevice("dev-lab-01", "lab")
            )
            fake_device_service.get_rest_client = AsyncMock(
                return_value=mock_rest_client
            )

            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    return_value=fake_plan_service,
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    return_value=fake_device_service,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["apply_firewall_plan"]
                result = await fn(
                    plan_id="plan-test-001",
                    approval_token="approve-test-abc123",
                )

                # Check that it reports failure
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("failed", content_text.lower())

                # Check metadata shows rollback
                meta = result["_meta"]
                self.assertEqual(meta["successful_count"], 0)
                self.assertEqual(meta["failed_count"], 1)
                device_result = meta["device_results"][0]
                self.assertEqual(device_result["status"], "rolled_back")
                self.assertIn("rollback", device_result)

                # Verify plan status was updated to failed
                fake_plan_service.update_plan_status.assert_any_call(
                    "plan-test-001", "failed", "mcp-user"
                )

        asyncio.run(_run())

    def test_apply_firewall_plan_device_unreachable(self) -> None:
        """Test apply with unreachable device."""

        async def _run() -> None:
            from datetime import UTC, datetime, timedelta
            from unittest.mock import AsyncMock

            # Mock plan service
            fake_plan_service = AsyncMock()
            fake_plan_service.get_plan = AsyncMock(
                return_value={
                    "plan_id": "plan-test-001",
                    "created_by": "test-user",
                    "status": "pending",
                    "device_ids": ["dev-lab-01"],
                    "changes": {
                        "operation": "add_firewall_rule",
                        "chain": "forward",
                        "action": "accept",
                        "approval_token_timestamp": datetime.now(UTC).isoformat(),
                        "approval_expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
                    },
                }
            )
            fake_plan_service._validate_approval_token = Mock(return_value=None)
            fake_plan_service.update_plan_status = AsyncMock(return_value=None)

            # Mock device service with unreachable device
            fake_device_service = AsyncMock()
            fake_device_service.get_device = AsyncMock(
                side_effect=Exception("Device unreachable")
            )

            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    return_value=fake_plan_service,
                ),
                patch.object(
                    firewall_write_module,
                    "DeviceService",
                    return_value=fake_device_service,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["apply_firewall_plan"]
                result = await fn(
                    plan_id="plan-test-001",
                    approval_token="approve-test-abc123",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("failed", content_text.lower())

                # Check metadata
                meta = result["_meta"]
                self.assertEqual(meta["failed_count"], 1)
                device_result = meta["device_results"][0]
                self.assertEqual(device_result["status"], "failed")
                self.assertIn("error", device_result)

        asyncio.run(_run())

    def test_apply_firewall_plan_invalid_status(self) -> None:
        """Test apply with plan in invalid status."""

        async def _run() -> None:
            from datetime import UTC, datetime, timedelta
            from unittest.mock import AsyncMock

            # Mock plan service with completed plan
            fake_plan_service = AsyncMock()
            fake_plan_service.get_plan = AsyncMock(
                return_value={
                    "plan_id": "plan-test-001",
                    "created_by": "test-user",
                    "status": "completed",  # Already completed
                    "device_ids": ["dev-lab-01"],
                    "changes": {
                        "approval_token_timestamp": datetime.now(UTC).isoformat(),
                        "approval_expires_at": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
                    },
                }
            )
            fake_plan_service._validate_approval_token = Mock(return_value=None)

            with (
                patch.object(
                    firewall_write_module,
                    "get_session_factory",
                    return_value=FakeSessionFactory(),
                ),
                patch.object(
                    firewall_write_module,
                    "PlanService",
                    return_value=fake_plan_service,
                ),
            ):
                mcp = self._register_tools()
                fn = mcp.tools["apply_firewall_plan"]
                result = await fn(
                    plan_id="plan-test-001",
                    approval_token="approve-test-abc123",
                )

                # Check error
                self.assertTrue(result.get("isError", False))
                content_text = self._get_content_text(result)
                self.assertIn("cannot be applied", content_text.lower())

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
