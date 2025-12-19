"""Unit tests for CAPsMAN wireless service functionality."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.wireless import WirelessService


class _FakeRestClient:
    """Fake REST client for testing CAPsMAN."""

    def __init__(self, has_capsman: bool = True) -> None:
        self.calls: list[tuple[str, str | None, dict | None]] = []
        self.has_capsman = has_capsman
        
        if has_capsman:
            self.store = {
                "/rest/caps-man/remote-cap": [
                    {
                        ".id": "*1",
                        "name": "cap-ap-1",
                        "address": "192.168.1.10",
                        "identity": "CAP-Office-AP",
                        "version": "7.16",
                        "state": "authorized",
                        "base-mac": "aa:bb:cc:dd:ee:01",
                        "radio-mac": "aa:bb:cc:dd:ee:02",
                        "board": "cAP",
                        "rx-signal": "-55",
                        "uptime": "1d2h15m",
                    },
                    {
                        ".id": "*2",
                        "name": "cap-ap-2",
                        "address": "192.168.1.11",
                        "identity": "CAP-Lobby-AP",
                        "version": "7.15.3",
                        "state": "provisioning",
                        "base-mac": "bb:cc:dd:ee:ff:01",
                        "radio-mac": "bb:cc:dd:ee:ff:02",
                        "board": "cAP ac",
                        "rx-signal": "-62",
                        "uptime": "3h45m",
                    },
                ],
                "/rest/caps-man/registration-table": [
                    {
                        ".id": "*a",
                        "interface": "cap-ap-1",
                        "mac-address": "11:22:33:44:55:66",
                        "ssid": "CorpWiFi",
                        "ap": "CAP-Office-AP",
                        "radio-name": "radio1",
                        "rx-signal": "-68",
                        "tx-signal": "-65",
                        "uptime": "45m",
                        "packets": "1234",
                        "bytes": "567890",
                    },
                    {
                        ".id": "*b",
                        "interface": "cap-ap-1",
                        "mac-address": "77:88:99:aa:bb:cc",
                        "ssid": "CorpWiFi",
                        "ap": "CAP-Office-AP",
                        "radio-name": "radio1",
                        "rx-signal": "-72",
                        "tx-signal": "-70",
                        "uptime": "1h20m",
                        "packets": "2345",
                        "bytes": "678901",
                    },
                    {
                        ".id": "*c",
                        "interface": "cap-ap-2",
                        "mac-address": "aa:bb:cc:dd:ee:ff",
                        "ssid": "GuestWiFi",
                        "ap": "CAP-Lobby-AP",
                        "radio-name": "radio2",
                        "rx-signal": "-75",
                        "tx-signal": "-73",
                        "uptime": "15m",
                        "packets": "456",
                        "bytes": "123456",
                    },
                ],
            }
        else:
            self.store = {}

    async def get(self, path: str, params: dict | None = None):
        self.calls.append(("get", path, params))
        
        if not self.has_capsman and "caps-man" in path:
            raise Exception("no such command")
            
        return self.store.get(path, [])

    async def close(self):
        self.calls.append(("close", None, None))


class _FakeSSHClient:
    """Fake SSH client for testing CAPsMAN."""

    def __init__(self, has_capsman: bool = True) -> None:
        self.calls: list[tuple[str, str]] = []
        self.has_capsman = has_capsman

    async def execute(self, command: str) -> str:
        self.calls.append(("execute", command))

        if not self.has_capsman and "caps-man" in command:
            raise Exception("no such command")

        if "/caps-man/remote-cap/print" in command:
            return """Flags: D - DYNAMIC; A - AUTHORIZED
Columns: NAME, ADDRESS, IDENTITY, STATE
 #     NAME        ADDRESS        IDENTITY          STATE
 0  A  cap-ap-1    192.168.1.10   CAP-Office-AP     authorized
 1     cap-ap-2    192.168.1.11   CAP-Lobby-AP      provisioning
"""
        elif "/caps-man/registration-table/print" in command or "/caps-man/interface/print" in command:
            return """Flags: D - DYNAMIC
Columns: INTERFACE, MAC-ADDRESS, SSID
 #     INTERFACE  MAC-ADDRESS        SSID
 0     cap-ap-1   11:22:33:44:55:66  CorpWiFi
 1     cap-ap-1   77:88:99:aa:bb:cc  CorpWiFi
 2     cap-ap-2   aa:bb:cc:dd:ee:ff  GuestWiFi
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
async def test_get_capsman_remote_caps_via_rest():
    """Test getting CAPsMAN remote CAPs via REST API."""
    rest_client = _FakeRestClient(has_capsman=True)
    ssh_client = _FakeSSHClient(has_capsman=True)
    device_service = _FakeDeviceService(rest_client, ssh_client)

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get CAPsMAN remote CAPs
    caps = await service.get_capsman_remote_caps("dev-1")

    # Verify results
    assert len(caps) == 2

    # Check first CAP
    assert caps[0]["id"] == "*1"
    assert caps[0]["name"] == "cap-ap-1"
    assert caps[0]["address"] == "192.168.1.10"
    assert caps[0]["identity"] == "CAP-Office-AP"
    assert caps[0]["version"] == "7.16"
    assert caps[0]["state"] == "authorized"
    assert caps[0]["base_mac"] == "aa:bb:cc:dd:ee:01"
    assert caps[0]["board"] == "cAP"
    assert caps[0]["transport"] == "rest"

    # Check second CAP
    assert caps[1]["id"] == "*2"
    assert caps[1]["name"] == "cap-ap-2"
    assert caps[1]["state"] == "provisioning"

    # Verify REST API was called
    assert ("get", "/rest/caps-man/remote-cap", None) in rest_client.calls


@pytest.mark.asyncio
async def test_get_capsman_remote_caps_via_ssh_fallback():
    """Test getting CAPsMAN remote CAPs via SSH when REST fails."""
    rest_client = _FakeRestClient(has_capsman=True)
    ssh_client = _FakeSSHClient(has_capsman=True)
    device_service = _FakeDeviceService(rest_client, ssh_client)

    # Make REST fail
    original_get = rest_client.get

    async def failing_get(path: str, params: dict | None = None):
        if "caps-man/remote-cap" in path:
            raise Exception("REST API failed")
        return await original_get(path, params)

    rest_client.get = failing_get

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get CAPsMAN remote CAPs - should fallback to SSH
    caps = await service.get_capsman_remote_caps("dev-1")

    # Verify results from SSH
    assert len(caps) == 2
    assert caps[0]["name"] == "cap-ap-1"
    assert caps[0]["address"] == "192.168.1.10"
    assert caps[0]["state"] == "authorized"
    assert caps[0]["transport"] == "ssh"
    assert caps[0]["fallback_used"] is True

    # Verify SSH was called
    assert ("execute", "/caps-man/remote-cap/print without-paging") in ssh_client.calls


@pytest.mark.asyncio
async def test_get_capsman_remote_caps_when_not_present():
    """Test getting CAPsMAN remote CAPs when CAPsMAN is not present."""
    rest_client = _FakeRestClient(has_capsman=False)
    ssh_client = _FakeSSHClient(has_capsman=False)
    device_service = _FakeDeviceService(rest_client, ssh_client)

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get CAPsMAN remote CAPs - should return empty list, not error
    caps = await service.get_capsman_remote_caps("dev-1")

    # Verify empty list returned
    assert len(caps) == 0
    assert caps == []


@pytest.mark.asyncio
async def test_get_capsman_registrations_via_rest():
    """Test getting CAPsMAN registrations via REST API."""
    rest_client = _FakeRestClient(has_capsman=True)
    ssh_client = _FakeSSHClient(has_capsman=True)
    device_service = _FakeDeviceService(rest_client, ssh_client)

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get CAPsMAN registrations
    registrations = await service.get_capsman_registrations("dev-1")

    # Verify results
    assert len(registrations) == 3

    # Check first registration
    assert registrations[0]["id"] == "*a"
    assert registrations[0]["interface"] == "cap-ap-1"
    assert registrations[0]["mac_address"] == "11:22:33:44:55:66"
    assert registrations[0]["ssid"] == "CorpWiFi"
    assert registrations[0]["ap"] == "CAP-Office-AP"
    assert registrations[0]["rx_signal"] == "-68"
    assert registrations[0]["uptime"] == "45m"
    assert registrations[0]["transport"] == "rest"

    # Check third registration (different AP)
    assert registrations[2]["interface"] == "cap-ap-2"
    assert registrations[2]["ssid"] == "GuestWiFi"
    assert registrations[2]["ap"] == "CAP-Lobby-AP"

    # Verify REST API was called
    assert ("get", "/rest/caps-man/registration-table", None) in rest_client.calls


@pytest.mark.asyncio
async def test_get_capsman_registrations_via_ssh_fallback():
    """Test getting CAPsMAN registrations via SSH when REST fails."""
    rest_client = _FakeRestClient(has_capsman=True)
    ssh_client = _FakeSSHClient(has_capsman=True)
    device_service = _FakeDeviceService(rest_client, ssh_client)

    # Make REST fail
    original_get = rest_client.get

    async def failing_get(path: str, params: dict | None = None):
        if "caps-man/registration-table" in path or "caps-man/interface" in path:
            raise Exception("REST API failed")
        return await original_get(path, params)

    rest_client.get = failing_get

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get CAPsMAN registrations - should fallback to SSH
    registrations = await service.get_capsman_registrations("dev-1")

    # Verify results from SSH
    assert len(registrations) == 3
    assert registrations[0]["interface"] == "cap-ap-1"
    assert registrations[0]["mac_address"] == "11:22:33:44:55:66"
    assert registrations[0]["ssid"] == "CorpWiFi"
    assert registrations[0]["transport"] == "ssh"
    assert registrations[0]["fallback_used"] is True

    # Verify SSH was called
    assert ("execute", "/caps-man/registration-table/print without-paging") in ssh_client.calls


@pytest.mark.asyncio
async def test_get_capsman_registrations_when_not_present():
    """Test getting CAPsMAN registrations when CAPsMAN is not present."""
    rest_client = _FakeRestClient(has_capsman=False)
    ssh_client = _FakeSSHClient(has_capsman=False)
    device_service = _FakeDeviceService(rest_client, ssh_client)

    service = WirelessService(AsyncMock(), Settings())
    service.device_service = device_service

    # Get CAPsMAN registrations - should return empty list, not error
    registrations = await service.get_capsman_registrations("dev-1")

    # Verify empty list returned
    assert len(registrations) == 0
    assert registrations == []
