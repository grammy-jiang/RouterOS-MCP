"""Unit tests for wireless service."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.wireless import WirelessService


class _FakeRestClient:
    """Fake REST client for testing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, dict | None]] = []
        self.store = {
            "/rest/interface/wireless": [
                {
                    ".id": "*1",
                    "name": "wlan1",
                    "ssid": "TestNetwork",
                    "frequency": "2437",
                    "band": "2ghz-b/g/n",
                    "channel-width": "20mhz",
                    "tx-power": "20",
                    "tx-power-mode": "default",
                    "mode": "ap-bridge",
                    "running": True,
                    "disabled": False,
                    "comment": "Main AP",
                    "mac-address": "aa:bb:cc:dd:ee:01",
                    "registered-clients": 2,
                    "authenticated-clients": 2,
                },
                {
                    ".id": "*2",
                    "name": "wlan2",
                    "ssid": "GuestNetwork",
                    "frequency": "5180",
                    "band": "5ghz-a/n/ac",
                    "channel-width": "40mhz",
                    "tx-power": "17",
                    "tx-power-mode": "default",
                    "mode": "ap-bridge",
                    "running": False,
                    "disabled": True,
                    "comment": "Guest AP",
                    "mac-address": "aa:bb:cc:dd:ee:02",
                    "registered-clients": 0,
                    "authenticated-clients": 0,
                },
            ],
            "/rest/interface/wireless/registration-table": [
                {
                    ".id": "*a",
                    "interface": "wlan1",
                    "mac-address": "11:22:33:44:55:66",
                    "signal-strength": "-65",
                    "signal-to-noise": "35",
                    "tx-rate": "54Mbps",
                    "rx-rate": "54Mbps",
                    "uptime": "1h23m45s",
                    "tx-bytes": 1024000,
                    "rx-bytes": 2048000,
                    "tx-packets": 5000,
                    "rx-packets": 6000,
                },
                {
                    ".id": "*b",
                    "interface": "wlan1",
                    "mac-address": "77:88:99:aa:bb:cc",
                    "signal-strength": "-72",
                    "signal-to-noise": "28",
                    "tx-rate": "144.4Mbps",
                    "rx-rate": "144.4Mbps",
                    "uptime": "45m12s",
                    "tx-bytes": 512000,
                    "rx-bytes": 768000,
                    "tx-packets": 2500,
                    "rx-packets": 3000,
                },
            ],
        }

    async def get(self, path: str, params: dict | None = None):
        self.calls.append(("get", path, params))
        return self.store.get(path, {})

    async def close(self):
        self.calls.append(("close", None, None))


class _FakeSSHClient:
    """Fake SSH client for testing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def execute(self, command: str) -> str:
        self.calls.append(("execute", command))

        if "/interface/wireless/print" in command:
            return """Flags: D - DYNAMIC; R - RUNNING
Columns: NAME, SSID, FREQUENCY, BAND
 #     NAME    SSID          FREQUENCY  BAND
 0  R  wlan1   TestNetwork   2437       2ghz-b/g/n
 1  D  wlan2   GuestNetwork  5180       5ghz-a/n/ac
"""
        elif "/interface/wireless/registration-table/print" in command:
            return """Flags: D - DYNAMIC
Columns: INTERFACE, MAC-ADDRESS, SIGNAL-STRENGTH
 #     INTERFACE  MAC-ADDRESS        SIGNAL-STRENGTH
 0     wlan1      11:22:33:44:55:66  -65
 1     wlan1      77:88:99:aa:bb:cc  -72
"""
        return ""

    async def close(self):
        self.calls.append(("close", ""))


class _FakeDeviceService:
    """Fake device service for testing."""

    def __init__(self, rest_client: _FakeRestClient, ssh_client: _FakeSSHClient) -> None:
        self.rest_client = rest_client
        self.ssh_client = ssh_client
        self.device = SimpleNamespace(
            id="dev-1",
            name="router-1",
            environment="lab",
            allow_advanced_writes=True,
            allow_professional_workflows=False,
        )

    async def get_device(self, device_id: str):
        return self.device

    async def get_rest_client(self, device_id: str):
        return self.rest_client

    async def get_ssh_client(self, device_id: str):
        return self.ssh_client


@pytest.mark.asyncio
async def test_get_wireless_interfaces_via_rest():
    """Test getting wireless interfaces via REST API."""
    rest_client = _FakeRestClient()
    ssh_client = _FakeSSHClient()
    device_service = _FakeDeviceService(rest_client, ssh_client)

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get wireless interfaces
    interfaces = await service.get_wireless_interfaces("dev-1")

    # Verify results
    assert len(interfaces) == 2

    # Check first interface
    assert interfaces[0]["id"] == "*1"
    assert interfaces[0]["name"] == "wlan1"
    assert interfaces[0]["ssid"] == "TestNetwork"
    assert interfaces[0]["frequency"] == "2437"
    assert interfaces[0]["band"] == "2ghz-b/g/n"
    assert interfaces[0]["channel_width"] == "20mhz"
    assert interfaces[0]["tx_power"] == "20"
    assert interfaces[0]["mode"] == "ap-bridge"
    assert interfaces[0]["running"] is True
    assert interfaces[0]["disabled"] is False
    assert interfaces[0]["registered_clients"] == 2
    assert interfaces[0]["transport"] == "rest"

    # Check second interface
    assert interfaces[1]["id"] == "*2"
    assert interfaces[1]["name"] == "wlan2"
    assert interfaces[1]["ssid"] == "GuestNetwork"
    assert interfaces[1]["running"] is False
    assert interfaces[1]["disabled"] is True

    # Verify REST API was called
    assert ("get", "/rest/interface/wireless", None) in rest_client.calls


@pytest.mark.asyncio
async def test_get_wireless_interfaces_via_ssh_fallback():
    """Test getting wireless interfaces via SSH when REST fails."""
    rest_client = _FakeRestClient()
    ssh_client = _FakeSSHClient()
    device_service = _FakeDeviceService(rest_client, ssh_client)

    # Make REST fail
    rest_client.store["/rest/interface/wireless"] = None
    original_get = rest_client.get

    async def failing_get(path: str, params: dict | None = None):
        if path == "/rest/interface/wireless":
            raise Exception("REST API failed")
        return await original_get(path, params)

    rest_client.get = failing_get

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get wireless interfaces - should fallback to SSH
    interfaces = await service.get_wireless_interfaces("dev-1")

    # Verify results from SSH
    assert len(interfaces) == 2
    assert interfaces[0]["name"] == "wlan1"
    assert interfaces[0]["ssid"] == "TestNetwork"
    assert interfaces[0]["running"] is True
    assert interfaces[0]["transport"] == "ssh"
    assert interfaces[0]["fallback_used"] is True

    # Verify SSH was called
    assert ("execute", "/interface/wireless/print") in ssh_client.calls


@pytest.mark.asyncio
async def test_get_wireless_clients_via_rest():
    """Test getting wireless clients via REST API."""
    rest_client = _FakeRestClient()
    ssh_client = _FakeSSHClient()
    device_service = _FakeDeviceService(rest_client, ssh_client)

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get wireless clients
    clients = await service.get_wireless_clients("dev-1")

    # Verify results
    assert len(clients) == 2

    # Check first client
    assert clients[0]["id"] == "*a"
    assert clients[0]["interface"] == "wlan1"
    assert clients[0]["mac_address"] == "11:22:33:44:55:66"
    assert clients[0]["signal_strength"] == -65
    assert clients[0]["signal_to_noise"] == 35
    assert clients[0]["tx_rate"] == "54Mbps"
    assert clients[0]["rx_rate"] == "54Mbps"
    assert clients[0]["uptime"] == "1h23m45s"
    assert clients[0]["bytes_sent"] == 1024000
    assert clients[0]["bytes_received"] == 2048000
    assert clients[0]["packets_sent"] == 5000
    assert clients[0]["packets_received"] == 6000
    assert clients[0]["transport"] == "rest"

    # Check second client
    assert clients[1]["id"] == "*b"
    assert clients[1]["mac_address"] == "77:88:99:aa:bb:cc"
    assert clients[1]["signal_strength"] == -72
    assert clients[1]["signal_to_noise"] == 28
    assert clients[1]["tx_rate"] == "144.4Mbps"

    # Verify REST API was called
    assert ("get", "/rest/interface/wireless/registration-table", None) in rest_client.calls


@pytest.mark.asyncio
async def test_get_wireless_clients_via_ssh_fallback():
    """Test getting wireless clients via SSH when REST fails."""
    rest_client = _FakeRestClient()
    ssh_client = _FakeSSHClient()
    device_service = _FakeDeviceService(rest_client, ssh_client)

    # Make REST fail
    original_get = rest_client.get

    async def failing_get(path: str, params: dict | None = None):
        if path == "/rest/interface/wireless/registration-table":
            raise Exception("REST API failed")
        return await original_get(path, params)

    rest_client.get = failing_get

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get wireless clients - should fallback to SSH
    clients = await service.get_wireless_clients("dev-1")

    # Verify results from SSH
    assert len(clients) == 2
    assert clients[0]["interface"] == "wlan1"
    assert clients[0]["mac_address"] == "11:22:33:44:55:66"
    assert clients[0]["signal_strength"] == -65
    assert clients[0]["transport"] == "ssh"
    assert clients[0]["fallback_used"] is True

    # Verify SSH was called
    assert ("execute", "/interface/wireless/registration-table/print") in ssh_client.calls


def test_parse_signal_strength():
    """Test signal strength parsing."""
    assert WirelessService._parse_signal_strength("-65") == -65
    assert WirelessService._parse_signal_strength("-65dBm") == -65
    assert WirelessService._parse_signal_strength(-72) == -72
    assert WirelessService._parse_signal_strength("") == 0
    assert WirelessService._parse_signal_strength(None) == 0


def test_parse_snr():
    """Test signal-to-noise ratio parsing."""
    assert WirelessService._parse_snr("35") == 35
    assert WirelessService._parse_snr("35dB") == 35
    assert WirelessService._parse_snr(28) == 28
    assert WirelessService._parse_snr("") == 0
    assert WirelessService._parse_snr(None) == 0


def test_parse_rate():
    """Test rate parsing."""
    assert WirelessService._parse_rate("54Mbps") == "54Mbps"
    assert WirelessService._parse_rate("144.4Mbps") == "144.4Mbps"
    assert WirelessService._parse_rate("") == ""
    assert WirelessService._parse_rate(None) == ""


def test_parse_wireless_print_output():
    """Test parsing wireless interface print output."""
    output = """Flags: D - DYNAMIC; R - RUNNING
Columns: NAME, SSID, FREQUENCY, BAND
 #     NAME    SSID          FREQUENCY  BAND
 0  R  wlan1   TestNetwork   2437       2ghz-b/g/n
 1  D  wlan2   GuestNetwork  5180       5ghz-a/n/ac
"""
    interfaces = WirelessService._parse_wireless_print_output(output)

    assert len(interfaces) == 2
    assert interfaces[0]["name"] == "wlan1"
    assert interfaces[0]["ssid"] == "TestNetwork"
    assert interfaces[0]["frequency"] == "2437"
    assert interfaces[0]["running"] is True
    assert interfaces[0]["disabled"] is False

    assert interfaces[1]["name"] == "wlan2"
    assert interfaces[1]["ssid"] == "GuestNetwork"
    assert interfaces[1]["running"] is False
    assert interfaces[1]["disabled"] is False


def test_parse_wireless_clients_output():
    """Test parsing wireless clients output."""
    output = """Flags: D - DYNAMIC
Columns: INTERFACE, MAC-ADDRESS, SIGNAL-STRENGTH
 #     INTERFACE  MAC-ADDRESS        SIGNAL-STRENGTH
 0     wlan1      11:22:33:44:55:66  -65
 1     wlan1      77:88:99:aa:bb:cc  -72
"""
    clients = WirelessService._parse_wireless_clients_output(output)

    assert len(clients) == 2
    assert clients[0]["interface"] == "wlan1"
    assert clients[0]["mac_address"] == "11:22:33:44:55:66"
    assert clients[0]["signal_strength"] == -65

    assert clients[1]["interface"] == "wlan1"
    assert clients[1]["mac_address"] == "77:88:99:aa:bb:cc"
    assert clients[1]["signal_strength"] == -72
