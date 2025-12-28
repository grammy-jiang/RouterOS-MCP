from __future__ import annotations

from types import SimpleNamespace

import pytest

from routeros_mcp.config import Settings
from tests.unit.mcp_tools_test_utils import DummyMCP, FakeSessionFactory


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_success_returns_formatted_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def has_capsman_managed_aps(self, _device_id: str) -> bool:
            return True

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return [{"id": "*1", "name": "wlan1"}]

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return [{"interface": "wlan1", "mac_address": "AA:BB:CC:DD:EE:FF"}]

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is False
    assert "hints" in result["_meta"]
    hints = result["_meta"]["hints"]
    assert len(hints) == 1
    assert hints[0]["code"] == "capsman_detected"
    assert "CAPsMAN" in hints[0]["message"]
    assert result["_meta"]["total_count"] == 1
    # Verify content field contains the hint message text
    assert "CAPsMAN note:" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_wireless_clients_tool_when_service_raises_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            raise RuntimeError("boom")

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is True
    assert "boom" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_when_mcp_error_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools
    from routeros_mcp.mcp.errors import MCPError

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            raise MCPError("denied", data={"reason": "auth"})

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is True
    assert result["_meta"]["reason"] == "auth"


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_when_generic_exception_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            raise RuntimeError("boom")

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is True
    assert "boom" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_wireless_clients_tool_when_mcp_error_returns_error_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools
    from routeros_mcp.mcp.errors import MCPError

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            raise MCPError("denied")

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is True
    assert result["content"][0]["text"] == "denied"


@pytest.mark.asyncio
async def test_wireless_clients_tool_success_returns_formatted_result(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def has_capsman_managed_aps(self, _device_id: str) -> bool:
            return True

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return [{"interface": "wlan1", "mac_address": "AA:BB:CC:DD:EE:FF"}]

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is False
    assert "hints" in result["_meta"]
    hints = result["_meta"]["hints"]
    assert len(hints) == 1
    assert hints[0]["code"] == "capsman_detected"
    assert "CAPsMAN" in hints[0]["message"]
    assert result["_meta"]["total_count"] == 1
    # Verify content field contains the hint message text
    assert "CAPsMAN note:" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_wireless_interfaces_tool_when_no_capsman_aps_omits_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def has_capsman_managed_aps(self, _device_id: str) -> bool:
            return False

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_interfaces"](device_id="dev-1")

    assert result["isError"] is False
    assert "hints" not in result["_meta"]


@pytest.mark.asyncio
async def test_wireless_clients_tool_when_no_capsman_aps_omits_hints(monkeypatch: pytest.MonkeyPatch) -> None:
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def get_device(self, _device_id: str) -> object:
            return SimpleNamespace(
                environment="lab",
                allow_advanced_writes=False,
                allow_professional_workflows=False,
                name="dev-1",
            )

    class StubWirelessService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        async def has_capsman_managed_aps(self, _device_id: str) -> bool:
            return False

        async def get_wireless_interfaces(self, _device_id: str) -> list[dict[str, object]]:
            return []

        async def get_wireless_clients(self, _device_id: str) -> list[dict[str, object]]:
            return []

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "WirelessService", StubWirelessService)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")

    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["get_wireless_clients"](device_id="dev-1")

    assert result["isError"] is False
    assert "hints" not in result["_meta"]



# Phase 3: Plan/Apply workflow tests


@pytest.mark.asyncio
async def test_plan_create_wireless_ssid_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful wireless SSID creation plan."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools
    from routeros_mcp.domain.models import PlanStatus

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01", environment: str = "lab") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = environment
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_wireless_writes = True
            self.status = "healthy"

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            self.devices = {
                "dev-lab-01": FakeDevice("dev-lab-01", "lab"),
                "dev-lab-02": FakeDevice("dev-lab-02", "lab"),
            }

        async def get_device(self, device_id: str) -> object:
            if device_id not in self.devices:
                raise ValueError(f"Device not found: {device_id}")
            return self.devices[device_id]

    class StubPlanService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
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
                "plan_id": "plan-wireless-001",
                "approval_token": "approve-wireless-abc123",
                "approval_expires_at": "2025-12-20T16:00:00Z",
                "risk_level": risk_level,
                "device_count": len(device_ids),
                "devices": device_ids,
                "summary": summary,
                "status": PlanStatus.PENDING.value,
                "pre_check_results": {"status": "passed"},
            }

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "PlanService", StubPlanService)
    monkeypatch.setattr(wireless_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["plan_create_wireless_ssid"](
        device_ids=["dev-lab-01", "dev-lab-02"],
        ssid="TestNetwork",
        security_profile="default",
        band="2ghz-n",
        channel=6,
    )

    assert result["isError"] is False
    assert "plan created successfully" in result["content"][0]["text"]
    assert result["_meta"]["plan_id"] == "plan-wireless-001"
    assert result["_meta"]["approval_token"] == "approve-wireless-abc123"
    assert result["_meta"]["device_count"] == 2
    assert result["_meta"]["tool_name"] == "wireless/plan-create-ssid"
    assert result["_meta"]["risk_level"] in ["medium", "high"]


@pytest.mark.asyncio
async def test_plan_create_wireless_ssid_invalid_ssid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test plan with invalid SSID (too long)."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01", environment: str = "lab") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = environment
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_wireless_writes = True

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> object:
            return FakeDevice(device_id, "lab")

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["plan_create_wireless_ssid"](
        device_ids=["dev-lab-01"],
        ssid="A" * 33,  # Too long (max 32 chars)
        security_profile="default",
    )

    assert result["isError"] is True
    assert "SSID too long" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plan_create_wireless_ssid_invalid_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test plan with DFS channel (blocked for safety)."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01", environment: str = "lab") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = environment
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_wireless_writes = True

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> object:
            return FakeDevice(device_id, "lab")

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["plan_create_wireless_ssid"](
        device_ids=["dev-lab-01"],
        ssid="TestNetwork",
        band="5ghz-ac",
        channel=52,  # DFS channel
    )

    assert result["isError"] is True
    assert "DFS channel" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plan_create_wireless_ssid_prod_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test plan is blocked for production environment devices."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-prod-01", environment: str = "prod") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = environment
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_wireless_writes = True

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> object:
            return FakeDevice(device_id, "prod")

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["plan_create_wireless_ssid"](
        device_ids=["dev-prod-01"],
        ssid="TestNetwork",
    )

    assert result["isError"] is True
    assert "prod environment" in result["content"][0]["text"]
    assert "only allowed in" in result["content"][0]["text"]


@pytest.mark.asyncio
async def test_plan_wireless_rf_settings_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test successful RF settings plan."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools
    from routeros_mcp.domain.models import PlanStatus

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01", environment: str = "lab") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = environment
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_wireless_writes = True

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> object:
            return FakeDevice(device_id, "lab")

    class StubPlanService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
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
                "plan_id": "plan-wireless-rf-001",
                "approval_token": "approve-rf-abc123",
                "approval_expires_at": "2025-12-20T16:00:00Z",
                "risk_level": risk_level,
                "device_count": len(device_ids),
                "devices": device_ids,
                "summary": summary,
                "status": PlanStatus.PENDING.value,
            }

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "PlanService", StubPlanService)
    monkeypatch.setattr(wireless_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["plan_wireless_rf_settings"](
        device_ids=["dev-lab-01"],
        interface="wlan1",
        channel=36,  # Valid non-DFS 5GHz channel
        tx_power=20,
        band="5ghz-ac",
    )

    assert result["isError"] is False
    assert "plan created successfully" in result["content"][0]["text"]
    assert result["_meta"]["plan_id"] == "plan-wireless-rf-001"


@pytest.mark.asyncio
async def test_plan_wireless_rf_settings_invalid_tx_power(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test RF plan with invalid TX power (too high)."""
    import routeros_mcp.mcp_tools.wireless as wireless_tools

    class FakeDevice:
        def __init__(self, device_id: str = "dev-lab-01", environment: str = "lab") -> None:
            self.id = device_id
            self.name = f"router-{device_id}"
            self.environment = environment
            self.allow_professional_workflows = True
            self.allow_advanced_writes = True
            self.allow_wireless_writes = True

    class StubDeviceService:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get_device(self, device_id: str) -> object:
            return FakeDevice(device_id, "lab")

    monkeypatch.setattr(wireless_tools, "get_session_factory", lambda _settings: FakeSessionFactory())
    monkeypatch.setattr(wireless_tools, "DeviceService", StubDeviceService)
    monkeypatch.setattr(wireless_tools, "check_tool_authorization", lambda **_kwargs: None)

    mcp = DummyMCP()
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:", environment="lab")
    wireless_tools.register_wireless_tools(mcp, settings)

    result = await mcp.tools["plan_wireless_rf_settings"](
        device_ids=["dev-lab-01"],
        interface="wlan1",
        tx_power=40,  # Too high (max 30 dBm)
    )

    assert result["isError"] is True
    assert "out of range" in result["content"][0]["text"]


# Phase 3: Plan/Apply workflow tests

