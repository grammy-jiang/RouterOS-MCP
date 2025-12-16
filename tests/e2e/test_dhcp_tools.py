"""E2E tests for DHCP tools and resources.

Tests DHCP server status and lease retrieval tools with mock RouterOS responses.
"""

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.dhcp import DHCPService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp_tools.dhcp import register_dhcp_tools
from tests.e2e.e2e_test_utils import create_test_mcp_server, MockRouterOSDevice


@pytest.fixture
async def test_device(initialize_session_manager):
    """Create a test device in the database."""
    settings = Settings()
    session_factory = get_session_factory(settings)

    async with session_factory.session() as session:
        device_service = DeviceService(session, settings)
        device = await device_service.create_device(
            device_id="test-dhcp-device",
            name="Test DHCP Device",
            management_ip="192.168.1.1",
            username="admin",
            password="test123",
            environment="lab",
        )
        await session.commit()
        yield device


@pytest.mark.asyncio
async def test_dhcp_server_status_tool(test_device, initialize_session_manager):
    """Test DHCP server status retrieval via MCP tool."""
    settings = Settings()
    session_factory = get_session_factory(settings)
    
    # Create mock RouterOS device with DHCP server
    mock_device = MockRouterOSDevice()
    mock_device.add_dhcp_server(
        name="dhcp1",
        interface="bridge",
        lease_time="10m",
        address_pool="pool1",
        disabled=False,
    )
    
    async with session_factory.session() as session:
        dhcp_service = DHCPService(session, settings)
        
        # Mock the REST client to return our test data
        original_get_rest_client = dhcp_service.device_service.get_rest_client
        
        async def mock_get_rest_client(device_id):
            client = await original_get_rest_client(device_id)
            # Override client.get to return mock data
            original_get = client.get
            
            async def mock_get(path):
                if path == "/rest/ip/dhcp-server":
                    return mock_device.dhcp_servers
                return await original_get(path)
            
            client.get = mock_get
            return client
        
        dhcp_service.device_service.get_rest_client = mock_get_rest_client
        
        # Get DHCP server status
        result = await dhcp_service.get_dhcp_server_status("test-dhcp-device")
        
        assert result["total_count"] == 1
        assert len(result["servers"]) == 1
        server = result["servers"][0]
        assert server["name"] == "dhcp1"
        assert server["interface"] == "bridge"
        assert server["lease_time"] == "10m"
        assert server["address_pool"] == "pool1"


@pytest.mark.asyncio
async def test_dhcp_leases_tool(test_device, initialize_session_manager):
    """Test DHCP lease retrieval via MCP tool."""
    settings = Settings()
    session_factory = get_session_factory(settings)
    
    # Create mock RouterOS device with DHCP leases
    mock_device = MockRouterOSDevice()
    mock_device.add_dhcp_lease(
        address="192.168.1.10",
        mac_address="00:11:22:33:44:55",
        client_id="1:00:11:22:33:44:55",
        host_name="client1",
        server="dhcp1",
        status="bound",
    )
    mock_device.add_dhcp_lease(
        address="192.168.1.11",
        mac_address="AA:BB:CC:DD:EE:FF",
        client_id="",
        host_name="client2",
        server="dhcp1",
        status="bound",
    )
    
    async with session_factory.session() as session:
        dhcp_service = DHCPService(session, settings)
        
        # Mock the REST client to return our test data
        original_get_rest_client = dhcp_service.device_service.get_rest_client
        
        async def mock_get_rest_client(device_id):
            client = await original_get_rest_client(device_id)
            original_get = client.get
            
            async def mock_get(path):
                if path == "/rest/ip/dhcp-server/lease":
                    return mock_device.dhcp_leases
                return await original_get(path)
            
            client.get = mock_get
            return client
        
        dhcp_service.device_service.get_rest_client = mock_get_rest_client
        
        # Get DHCP leases
        result = await dhcp_service.get_dhcp_leases("test-dhcp-device")
        
        assert result["total_count"] == 2
        assert len(result["leases"]) == 2
        
        lease1 = result["leases"][0]
        assert lease1["address"] == "192.168.1.10"
        assert lease1["mac_address"] == "00:11:22:33:44:55"
        assert lease1["host_name"] == "client1"
        
        lease2 = result["leases"][1]
        assert lease2["address"] == "192.168.1.11"
        assert lease2["mac_address"] == "AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_dhcp_leases_filters_non_bound(test_device, initialize_session_manager):
    """Test that DHCP leases tool filters out non-bound leases."""
    settings = Settings()
    session_factory = get_session_factory(settings)
    
    # Create mock RouterOS device with mixed lease statuses
    mock_device = MockRouterOSDevice()
    mock_device.dhcp_leases = [
        {
            "address": "192.168.1.10",
            "mac-address": "00:11:22:33:44:55",
            "server": "dhcp1",
            "status": "bound",
            "disabled": False,
        },
        {
            "address": "192.168.1.11",
            "mac-address": "AA:BB:CC:DD:EE:FF",
            "server": "dhcp1",
            "status": "waiting",  # Should be filtered
            "disabled": False,
        },
        {
            "address": "192.168.1.12",
            "mac-address": "11:22:33:44:55:66",
            "server": "dhcp1",
            "status": "bound",
            "disabled": True,  # Should be filtered (disabled)
        },
    ]
    
    async with session_factory.session() as session:
        dhcp_service = DHCPService(session, settings)
        
        original_get_rest_client = dhcp_service.device_service.get_rest_client
        
        async def mock_get_rest_client(device_id):
            client = await original_get_rest_client(device_id)
            original_get = client.get
            
            async def mock_get(path):
                if path == "/rest/ip/dhcp-server/lease":
                    return mock_device.dhcp_leases
                return await original_get(path)
            
            client.get = mock_get
            return client
        
        dhcp_service.device_service.get_rest_client = mock_get_rest_client
        
        # Get DHCP leases - should only return the bound, non-disabled lease
        result = await dhcp_service.get_dhcp_leases("test-dhcp-device")
        
        assert result["total_count"] == 1
        assert len(result["leases"]) == 1
        assert result["leases"][0]["address"] == "192.168.1.10"
