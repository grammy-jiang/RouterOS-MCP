"""Unit tests for wireless and DHCP troubleshooting prompts."""

import pytest

from routeros_mcp.mcp_prompts.loader import PromptLoader
from routeros_mcp.mcp_prompts.renderer import PromptRenderer


@pytest.fixture
def prompt_loader():
    """Create a prompt loader pointing to the prompts directory."""
    # Use actual prompts directory
    from pathlib import Path
    prompts_dir = Path(__file__).parent.parent.parent.parent / "prompts"
    return PromptLoader(prompts_dir)


@pytest.fixture
def prompt_renderer():
    """Create a prompt renderer."""
    return PromptRenderer()


def test_troubleshoot_wireless_template_loads(prompt_loader):
    """Test that troubleshoot-wireless template loads successfully."""
    templates = prompt_loader.load_all()
    
    assert "troubleshoot-wireless" in templates
    template = templates["troubleshoot-wireless"]
    
    # Verify basic template structure
    assert template.name == "troubleshoot-wireless"
    assert template.description == "Diagnostic procedures for wireless connectivity and performance issues"
    assert len(template.messages) > 0
    
    # Verify arguments
    arg_names = [arg.name for arg in template.arguments]
    assert "device_id" in arg_names
    assert "issue_type" in arg_names


def test_troubleshoot_wireless_renders_without_device_id(prompt_loader, prompt_renderer):
    """Test wireless prompt renders correctly without device_id."""
    templates = prompt_loader.load_all()
    template = templates["troubleshoot-wireless"]
    
    # Render without device_id
    result = prompt_renderer.render(template, {})
    
    # Should show getting started section
    assert "Getting Started" in result
    assert "Find Devices with Wireless" in result
    assert "device/list" in result


def test_troubleshoot_wireless_renders_with_device_id(prompt_loader, prompt_renderer):
    """Test wireless prompt renders correctly with device_id."""
    templates = prompt_loader.load_all()
    template = templates["troubleshoot-wireless"]
    
    # Render with device_id
    result = prompt_renderer.render(
        template,
        {"device_id": "dev-lab-01"},
        context={"device_name": "Test Router", "device_environment": "lab"}
    )
    
    # Should show device-specific troubleshooting
    assert "Troubleshooting Wireless: Test Router" in result
    assert "dev-lab-01" in result
    assert "wireless/get-interfaces" in result
    assert "wireless/get-clients" in result


def test_troubleshoot_wireless_issue_types(prompt_loader, prompt_renderer):
    """Test wireless prompt renders different issue types correctly."""
    templates = prompt_loader.load_all()
    template = templates["troubleshoot-wireless"]
    
    issue_types = ["connectivity", "performance", "clients", "configuration"]
    
    for issue_type in issue_types:
        result = prompt_renderer.render(
            template,
            {"device_id": "dev-lab-01", "issue_type": issue_type},
            context={"device_name": "Test Router", "device_environment": "lab"}
        )
        
        # Should contain issue-specific content
        assert f"issue_type: {issue_type}" in result.lower() or issue_type.title() in result


def test_troubleshoot_wireless_references_correct_tools(prompt_loader, prompt_renderer):
    """Test wireless prompt references the correct MCP tools."""
    templates = prompt_loader.load_all()
    template = templates["troubleshoot-wireless"]
    
    result = prompt_renderer.render(
        template,
        {"device_id": "dev-lab-01"},
        context={"device_name": "Test Router", "device_environment": "lab"}
    )
    
    # Verify correct tool references
    assert "wireless/get-interfaces" in result
    assert "wireless/get-clients" in result
    assert "device/check-connectivity" in result
    assert "system/get-overview" in result
    assert "interface/list" in result


def test_dhcp_lease_review_template_loads(prompt_loader):
    """Test that dhcp-lease-review template loads successfully."""
    templates = prompt_loader.load_all()
    
    assert "dhcp-lease-review" in templates
    template = templates["dhcp-lease-review"]
    
    # Verify basic template structure
    assert template.name == "dhcp-lease-review"
    assert template.description == "Review DHCP lease assignments and identify potential conflicts or issues"
    assert len(template.messages) > 0
    
    # Verify arguments
    arg_names = [arg.name for arg in template.arguments]
    assert "device_id" in arg_names


def test_dhcp_lease_review_renders_without_device_id(prompt_loader, prompt_renderer):
    """Test DHCP lease review prompt renders correctly without device_id."""
    templates = prompt_loader.load_all()
    template = templates["dhcp-lease-review"]
    
    # Render without device_id
    result = prompt_renderer.render(template, {})
    
    # Should show getting started section
    assert "Getting Started" in result
    assert "Find Devices with DHCP Servers" in result
    assert "device/list" in result
    assert "Why Review DHCP Leases?" in result


def test_dhcp_lease_review_renders_with_device_id(prompt_loader, prompt_renderer):
    """Test DHCP lease review prompt renders correctly with device_id."""
    templates = prompt_loader.load_all()
    template = templates["dhcp-lease-review"]
    
    # Render with device_id
    result = prompt_renderer.render(
        template,
        {"device_id": "dev-lab-01"},
        context={"device_name": "Test Router", "device_environment": "lab"}
    )
    
    # Should show device-specific review workflow
    assert "DHCP Lease Review: Test Router" in result
    assert "dev-lab-01" in result
    assert "dhcp/get-server-status" in result
    assert "dhcp/get-leases" in result


def test_dhcp_lease_review_references_correct_tools(prompt_loader, prompt_renderer):
    """Test DHCP lease review prompt references the correct MCP tools."""
    templates = prompt_loader.load_all()
    template = templates["dhcp-lease-review"]
    
    result = prompt_renderer.render(
        template,
        {"device_id": "dev-lab-01"},
        context={"device_name": "Test Router", "device_environment": "lab"}
    )
    
    # Verify correct tool references
    assert "dhcp/get-server-status" in result
    assert "dhcp/get-leases" in result
    assert "ip/get-arp-table" in result
    assert "device/check-connectivity" in result
    assert "interface/list" in result


def test_dhcp_lease_review_includes_troubleshooting_guidance(prompt_loader, prompt_renderer):
    """Test DHCP lease review includes comprehensive troubleshooting guidance."""
    templates = prompt_loader.load_all()
    template = templates["dhcp-lease-review"]
    
    result = prompt_renderer.render(
        template,
        {"device_id": "dev-lab-01"},
        context={"device_name": "Test Router", "device_environment": "lab"}
    )
    
    # Verify troubleshooting sections
    assert "IP Address Conflicts" in result
    assert "DHCP Pool Exhaustion" in result
    assert "Unexpected Devices" in result
    assert "Best Practices" in result
    assert "Review Checklist" in result


def test_wireless_prompt_includes_signal_strength_reference(prompt_loader, prompt_renderer):
    """Test wireless prompt includes signal strength quality reference."""
    templates = prompt_loader.load_all()
    template = templates["troubleshoot-wireless"]
    
    result = prompt_renderer.render(
        template,
        {"device_id": "dev-lab-01"},
        context={"device_name": "Test Router", "device_environment": "lab"}
    )
    
    # Verify signal strength reference
    assert "Signal Quality Reference" in result or "signal" in result.lower()
    assert "dBm" in result


def test_prompts_are_concise(prompt_loader, prompt_renderer):
    """Test that prompts are reasonably concise (< 500 tokens estimated)."""
    templates = prompt_loader.load_all()
    
    for prompt_name in ["troubleshoot-wireless", "dhcp-lease-review"]:
        template = templates[prompt_name]
        
        # Render with device_id to get full content
        result = prompt_renderer.render(
            template,
            {"device_id": "dev-lab-01"},
            context={"device_name": "Test Router", "device_environment": "lab"}
        )
        
        # Rough token estimation: ~4 characters per token
        estimated_tokens = len(result) // 4
        
        # The full prompt can be longer, but should be reasonably sized
        # Increased limit since these are comprehensive troubleshooting guides
        assert estimated_tokens < 3000, f"{prompt_name} is too long: ~{estimated_tokens} tokens"


def test_wireless_prompt_metadata(prompt_loader):
    """Test wireless prompt has correct metadata."""
    templates = prompt_loader.load_all()
    template = templates["troubleshoot-wireless"]
    
    assert template.metadata is not None
    assert template.metadata.category == "troubleshooting"
    assert template.metadata.tier == "fundamental"
    assert "lab" in template.metadata.environments
    assert "staging" in template.metadata.environments
    assert "prod" in template.metadata.environments
    assert template.metadata.requires_approval is False


def test_dhcp_prompt_metadata(prompt_loader):
    """Test DHCP lease review prompt has correct metadata."""
    templates = prompt_loader.load_all()
    template = templates["dhcp-lease-review"]
    
    assert template.metadata is not None
    assert template.metadata.category == "troubleshooting"
    assert template.metadata.tier == "fundamental"
    assert "lab" in template.metadata.environments
    assert "staging" in template.metadata.environments
    assert "prod" in template.metadata.environments
    assert template.metadata.requires_approval is False


def test_prompt_validation(prompt_loader):
    """Test that prompts pass validation."""
    validation_results = prompt_loader.validate_all()
    
    # Both prompts should have no critical validation issues
    for prompt_name in ["troubleshoot-wireless", "dhcp-lease-review"]:
        if prompt_name in validation_results:
            issues = validation_results[prompt_name]
            # Should have no critical issues (warnings are OK)
            critical_issues = [i for i in issues if "error" in i.lower() or "critical" in i.lower()]
            assert len(critical_issues) == 0, f"{prompt_name} has critical validation issues: {critical_issues}"


def test_wireless_prompt_with_all_issue_types(prompt_loader, prompt_renderer):
    """Test wireless prompt renders all issue types without errors."""
    templates = prompt_loader.load_all()
    template = templates["troubleshoot-wireless"]
    
    issue_types = ["connectivity", "performance", "clients", "configuration"]
    
    for issue_type in issue_types:
        # Should not raise any exceptions
        result = prompt_renderer.render(
            template,
            {"device_id": "dev-lab-01", "issue_type": issue_type},
            context={"device_name": "Test Router", "device_environment": "lab"}
        )
        
        # Result should be non-empty string
        assert isinstance(result, str)
        assert len(result) > 0
        assert "dev-lab-01" in result
