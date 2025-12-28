"""Admin CLI for device onboarding and plan management.

This module provides human-facing admin tooling for operators to:
- Onboard new RouterOS devices with encrypted credentials
- Manage device environment tags and capability flags
- Review and approve/reject configuration change plans
- Test device connectivity (REST + SSH)

Complements the MCP tools which are AI-facing.
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

from routeros_mcp.config import Settings, load_settings_from_file
from routeros_mcp.domain.models import CredentialCreate, DeviceCreate
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.session import get_session_factory

console = Console()


def load_settings(config_path: str | None) -> Settings:
    """Load settings from config file or environment.

    Args:
        config_path: Optional path to config file

    Returns:
        Settings instance
    """
    if config_path:
        return load_settings_from_file(Path(config_path))
    return Settings()


@click.group()
@click.option(
    "--config",
    "-c",
    type=click.Path(exists=True, path_type=str),
    help="Path to configuration file (YAML or TOML)",
)
@click.pass_context
def admin(ctx: click.Context, config: str | None) -> None:
    """RouterOS MCP Admin CLI - Device onboarding and plan management."""
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@admin.group()
def device() -> None:
    """Manage RouterOS devices."""
    pass


@admin.group()
def plan() -> None:
    """Manage configuration change plans."""
    pass


@device.command("add")
@click.option("--id", "device_id", required=True, help="Unique device ID")
@click.option("--name", required=True, help="Human-friendly device name")
@click.option("--ip", "management_ip", required=True, help="Management IP address")
@click.option("--port", "management_port", default=443, type=int, help="Management port (default: 443)")
@click.option("--username", required=True, help="REST API username")
@click.option("--password", help="REST API password (will prompt if not provided)")
@click.option("--environment", type=click.Choice(["lab", "staging", "prod"]), help="Environment tag")
@click.option("--tags", help="JSON object with device tags (e.g., '{\"site\": \"home\"}')")
@click.option("--allow-advanced-writes", is_flag=True, help="Allow advanced write operations")
@click.option("--allow-professional-workflows", is_flag=True, help="Allow professional workflows")
@click.option("--allow-firewall-writes", is_flag=True, help="Allow firewall write operations")
@click.option("--allow-routing-writes", is_flag=True, help="Allow routing write operations")
@click.option("--allow-wireless-writes", is_flag=True, help="Allow wireless write operations")
@click.option("--allow-dhcp-writes", is_flag=True, help="Allow DHCP write operations")
@click.option("--allow-bridge-writes", is_flag=True, help="Allow bridge write operations")
@click.option("--non-interactive", is_flag=True, help="Non-interactive mode (no prompts)")
@click.pass_context
def device_add(
    ctx: click.Context,
    device_id: str,
    name: str,
    management_ip: str,
    management_port: int,
    username: str,
    password: str | None,
    environment: str | None,
    tags: str | None,
    allow_advanced_writes: bool,
    allow_professional_workflows: bool,
    allow_firewall_writes: bool,
    allow_routing_writes: bool,
    allow_wireless_writes: bool,
    allow_dhcp_writes: bool,
    allow_bridge_writes: bool,
    non_interactive: bool,
) -> None:
    """Add a new RouterOS device with encrypted credentials."""
    try:
        settings = load_settings(ctx.obj["config"])

        # Use environment from config if not specified
        if not environment:
            environment = settings.environment
            console.print(f"[yellow]Using environment from config: {environment}[/yellow]")

        # Prompt for password if not provided and in interactive mode
        if not password:
            if non_interactive:
                console.print("[red]Error: --password required in non-interactive mode[/red]")
                sys.exit(1)
            password = Prompt.ask("Password", password=True)

        # Parse tags
        parsed_tags = {}
        if tags:
            try:
                parsed_tags = json.loads(tags)
            except json.JSONDecodeError as e:
                console.print(f"[red]Error: Invalid JSON for --tags: {e}[/red]")
                sys.exit(1)

        # Show summary and confirm in interactive mode
        if not non_interactive:
            console.print("\n[bold]Device Configuration Summary:[/bold]")
            console.print(f"  ID: {device_id}")
            console.print(f"  Name: {name}")
            console.print(f"  IP: {management_ip}:{management_port}")
            console.print(f"  Username: {username}")
            console.print(f"  Environment: {environment}")
            console.print(f"  Tags: {parsed_tags}")
            console.print(f"  Allow Advanced Writes: {allow_advanced_writes}")
            console.print(f"  Allow Professional Workflows: {allow_professional_workflows}")
            console.print(f"  Allow Firewall Writes: {allow_firewall_writes}")
            console.print(f"  Allow Routing Writes: {allow_routing_writes}")
            console.print(f"  Allow Wireless Writes: {allow_wireless_writes}")
            console.print(f"  Allow DHCP Writes: {allow_dhcp_writes}")
            console.print(f"  Allow Bridge Writes: {allow_bridge_writes}")

            if not Confirm.ask("\nProceed with device registration?", default=True):
                console.print("[yellow]Operation cancelled[/yellow]")
                return

        # Register device
        async def _register_device() -> None:
            session_factory = get_session_factory(settings)
            await session_factory.init()

            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

                # Create device
                device_data = DeviceCreate(
                    id=device_id,
                    name=name,
                    management_ip=management_ip,
                    management_port=management_port,
                    environment=environment,
                    tags=parsed_tags,
                    allow_advanced_writes=allow_advanced_writes,
                    allow_professional_workflows=allow_professional_workflows,
                    allow_firewall_writes=allow_firewall_writes,
                    allow_routing_writes=allow_routing_writes,
                    allow_wireless_writes=allow_wireless_writes,
                    allow_dhcp_writes=allow_dhcp_writes,
                    allow_bridge_writes=allow_bridge_writes,
                )

                device = await device_service.register_device(device_data)
                console.print(f"\n[green]✓[/green] Device registered: {device.id}")

                # Add credentials
                credential_data = CredentialCreate(
                    device_id=device_id,
                    credential_type="rest",
                    username=username,
                    password=password,
                )

                await device_service.add_credential(credential_data)
                console.print("[green]✓[/green] Credentials stored (encrypted)")

                console.print(f"\n[bold green]Success![/bold green] Device '{device_id}' is ready to use.")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Registering device...", total=None)
            asyncio.run(_register_device())
            progress.update(task, completed=True)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@device.command("list")
@click.option("--environment", type=click.Choice(["lab", "staging", "prod"]), help="Filter by environment")
@click.option("--status", help="Filter by status")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def device_list(ctx: click.Context, environment: str | None, status: str | None, output_format: str) -> None:
    """List all registered devices."""
    try:
        settings = load_settings(ctx.obj["config"])

        async def _list_devices() -> list[dict[str, Any]]:
            session_factory = get_session_factory(settings)
            await session_factory.init()

            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                devices = await device_service.list_devices(
                    environment=environment,
                    status=status,
                )

                return [
                    {
                        "id": d.id,
                        "name": d.name,
                        "ip": d.management_ip,
                        "port": d.management_port,
                        "environment": d.environment,
                        "status": d.status,
                        "professional_workflows": d.allow_professional_workflows,
                    }
                    for d in devices
                ]

        devices = asyncio.run(_list_devices())

        if output_format == "json":
            console.print(json.dumps(devices, indent=2))
        else:
            table = Table(title="Registered Devices")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="white")
            table.add_column("IP:Port", style="yellow")
            table.add_column("Environment", style="magenta")
            table.add_column("Status", style="green")
            table.add_column("Prof. WF", style="blue")

            for device in devices:
                table.add_row(
                    device["id"],
                    device["name"],
                    f"{device['ip']}:{device['port']}",
                    device["environment"],
                    device["status"],
                    "✓" if device["professional_workflows"] else "✗",
                )

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@device.command("update")
@click.argument("device_id")
@click.option("--name", help="Update device name")
@click.option("--environment", type=click.Choice(["lab", "staging", "prod"]), help="Update environment")
@click.option("--tags", help="Update tags (JSON object)")
@click.option("--allow-professional-workflows", type=bool, help="Enable/disable professional workflows")
@click.option("--allow-firewall-writes", type=bool, help="Enable/disable firewall writes")
@click.option("--allow-routing-writes", type=bool, help="Enable/disable routing writes")
@click.option("--allow-wireless-writes", type=bool, help="Enable/disable wireless writes")
@click.option("--allow-dhcp-writes", type=bool, help="Enable/disable DHCP writes")
@click.option("--allow-bridge-writes", type=bool, help="Enable/disable bridge writes")
@click.pass_context
def device_update(
    ctx: click.Context,
    device_id: str,
    name: str | None,
    environment: str | None,
    tags: str | None,
    allow_professional_workflows: bool | None,
    allow_firewall_writes: bool | None,
    allow_routing_writes: bool | None,
    allow_wireless_writes: bool | None,
    allow_dhcp_writes: bool | None,
    allow_bridge_writes: bool | None,
) -> None:
    """Update device configuration."""
    try:
        settings = load_settings(ctx.obj["config"])

        # Parse tags if provided
        parsed_tags = None
        if tags:
            try:
                parsed_tags = json.loads(tags)
            except json.JSONDecodeError as e:
                console.print(f"[red]Error: Invalid JSON for --tags: {e}[/red]")
                sys.exit(1)

        # Build update dict
        updates: dict[str, Any] = {}
        if name is not None:
            updates["name"] = name
        if environment is not None:
            updates["environment"] = environment
        if parsed_tags is not None:
            updates["tags"] = parsed_tags
        if allow_professional_workflows is not None:
            updates["allow_professional_workflows"] = allow_professional_workflows
        if allow_firewall_writes is not None:
            updates["allow_firewall_writes"] = allow_firewall_writes
        if allow_routing_writes is not None:
            updates["allow_routing_writes"] = allow_routing_writes
        if allow_wireless_writes is not None:
            updates["allow_wireless_writes"] = allow_wireless_writes
        if allow_dhcp_writes is not None:
            updates["allow_dhcp_writes"] = allow_dhcp_writes
        if allow_bridge_writes is not None:
            updates["allow_bridge_writes"] = allow_bridge_writes

        if not updates:
            console.print("[yellow]No updates specified[/yellow]")
            return

        async def _update_device() -> None:
            session_factory = get_session_factory(settings)
            await session_factory.init()

            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)

                from routeros_mcp.domain.models import DeviceUpdate
                device_update_data = DeviceUpdate(**updates)

                await device_service.update_device(device_id, device_update_data)
                console.print(f"[green]✓[/green] Device '{device_id}' updated successfully")

        asyncio.run(_update_device())

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@device.command("test")
@click.argument("device_id")
@click.pass_context
def device_test(ctx: click.Context, device_id: str) -> None:
    """Test connectivity to a device (REST + SSH)."""
    try:
        settings = load_settings(ctx.obj["config"])

        async def _test_connectivity() -> tuple[bool, dict[str, Any]]:
            session_factory = get_session_factory(settings)
            await session_factory.init()

            async with session_factory.session() as session:
                device_service = DeviceService(session, settings)
                return await device_service.check_connectivity(device_id)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Testing connectivity to {device_id}...", total=None)
            is_reachable, metadata = asyncio.run(_test_connectivity())
            progress.update(task, completed=True)

        if is_reachable:
            console.print(f"\n[green]✓[/green] Device '{device_id}' is reachable")
            console.print("\nDevice Information:")
            for key, value in metadata.items():
                console.print(f"  {key}: {value}")
        else:
            console.print(f"\n[red]✗[/red] Device '{device_id}' is not reachable")
            console.print(f"\nError: {metadata.get('error', 'Unknown error')}")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@plan.command("list")
@click.option("--status", help="Filter by status (pending, approved, executing, completed, failed, cancelled)")
@click.option("--created-by", help="Filter by creator")
@click.option("--limit", default=50, type=int, help="Maximum number of results (default: 50)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table", help="Output format")
@click.pass_context
def plan_list(
    ctx: click.Context,
    status: str | None,
    created_by: str | None,
    limit: int,
    output_format: str,
) -> None:
    """List configuration change plans."""
    try:
        settings = load_settings(ctx.obj["config"])

        async def _list_plans() -> list[dict[str, Any]]:
            session_factory = get_session_factory(settings)
            await session_factory.init()

            async with session_factory.session() as session:
                plan_service = PlanService(session, settings)
                return await plan_service.list_plans(
                    created_by=created_by,
                    status=status,
                    limit=limit,
                )

        plans = asyncio.run(_list_plans())

        if output_format == "json":
            console.print(json.dumps(plans, indent=2))
        else:
            table = Table(title="Configuration Change Plans")
            table.add_column("Plan ID", style="cyan")
            table.add_column("Tool", style="white")
            table.add_column("Status", style="yellow")
            table.add_column("Devices", style="magenta")
            table.add_column("Created By", style="green")
            table.add_column("Created At", style="blue")

            for plan_item in plans:
                table.add_row(
                    plan_item["plan_id"],
                    plan_item["tool_name"],
                    plan_item["status"],
                    str(plan_item["device_count"]),
                    plan_item["created_by"],
                    plan_item["created_at"][:19],  # Trim to datetime only
                )

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@plan.command("show")
@click.argument("plan_id")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.pass_context
def plan_show(ctx: click.Context, plan_id: str, output_format: str) -> None:
    """Show detailed plan information."""
    try:
        settings = load_settings(ctx.obj["config"])

        async def _get_plan() -> dict[str, Any]:
            session_factory = get_session_factory(settings)
            await session_factory.init()

            async with session_factory.session() as session:
                plan_service = PlanService(session, settings)
                return await plan_service.get_plan(plan_id)

        plan_data = asyncio.run(_get_plan())

        if output_format == "json":
            console.print(json.dumps(plan_data, indent=2, default=str))
        else:
            console.print(f"\n[bold]Plan Details: {plan_id}[/bold]\n")
            console.print(f"Status: {plan_data['status']}")
            console.print(f"Tool: {plan_data['tool_name']}")
            console.print(f"Created By: {plan_data['created_by']}")
            console.print(f"Created At: {plan_data['created_at']}")
            console.print(f"Risk Level: {plan_data['risk_level']}")
            console.print(f"Device Count: {len(plan_data['device_ids'])}")
            console.print(f"Devices: {', '.join(plan_data['device_ids'])}")
            console.print(f"\nSummary: {plan_data['summary']}")
            console.print("\nChanges:")
            console.print(json.dumps(plan_data['changes'], indent=2))

            if plan_data.get("pre_check_results"):
                console.print("\nPre-check Results:")
                console.print(json.dumps(plan_data["pre_check_results"], indent=2))

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@plan.command("approve")
@click.argument("plan_id")
@click.option("--non-interactive", is_flag=True, help="Non-interactive mode (no prompts)")
@click.pass_context
def plan_approve(ctx: click.Context, plan_id: str, non_interactive: bool) -> None:
    """Approve a plan (admin-only operation)."""
    try:
        settings = load_settings(ctx.obj["config"])

        # In interactive mode, show plan details and confirm
        if not non_interactive:
            async def _get_plan() -> dict[str, Any]:
                session_factory = get_session_factory(settings)
                await session_factory.init()

                async with session_factory.session() as session:
                    plan_service = PlanService(session, settings)
                    return await plan_service.get_plan(plan_id)

            plan_data = asyncio.run(_get_plan())

            console.print(f"\n[bold]Plan to Approve: {plan_id}[/bold]")
            console.print(f"Tool: {plan_data['tool_name']}")
            console.print(f"Status: {plan_data['status']}")
            console.print(f"Risk Level: {plan_data['risk_level']}")
            console.print(f"Devices: {', '.join(plan_data['device_ids'])}")
            console.print(f"Summary: {plan_data['summary']}\n")

            if not Confirm.ask("Are you sure you want to approve this plan?", default=False):
                console.print("[yellow]Operation cancelled[/yellow]")
                return

        async def _approve_plan() -> dict[str, Any]:
            session_factory = get_session_factory(settings)
            await session_factory.init()

            async with session_factory.session() as session:
                plan_service = PlanService(session, settings)
                # Use a default admin user sub for CLI operations
                return await plan_service.approve_plan(plan_id, "admin-cli-user", {})

        result = asyncio.run(_approve_plan())

        console.print(f"\n[green]✓[/green] Plan '{plan_id}' approved successfully")
        console.print(f"\nApproval Token: {result['approval_token']}")
        console.print(f"Expires At: {result['approval_expires_at']}")
        console.print("\n[yellow]Use this token to execute the plan via MCP tools[/yellow]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@plan.command("reject")
@click.argument("plan_id")
@click.option("--reason", required=True, help="Reason for rejection")
@click.pass_context
def plan_reject(ctx: click.Context, plan_id: str, reason: str) -> None:
    """Reject a plan with reason."""
    try:
        settings = load_settings(ctx.obj["config"])

        async def _reject_plan() -> None:
            session_factory = get_session_factory(settings)
            await session_factory.init()

            async with session_factory.session() as session:
                plan_service = PlanService(session, settings)
                # Update plan status to cancelled with metadata
                from routeros_mcp.domain.models import PlanStatus
                await plan_service.update_plan_status(
                    plan_id,
                    PlanStatus.CANCELLED,
                    "admin-cli-user",
                    {"rejection_reason": reason},
                )

        asyncio.run(_reject_plan())
        console.print(f"[green]✓[/green] Plan '{plan_id}' rejected")
        console.print(f"Reason: {reason}")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    admin()
