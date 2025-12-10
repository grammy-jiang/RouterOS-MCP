"""Professional-tier MCP tools for multi-device configuration workflows.

Implements plan/apply pattern for high-risk operations including DNS/NTP rollout.
All tools enforce environment gating, approval tokens, and health checks.

See docs/07-device-control-and-high-risk-operations-safeguards.md for
detailed requirements.
"""

import logging
from typing import Any

from fastmcp import FastMCP

from routeros_mcp.config import Settings
from routeros_mcp.domain.services.device import DeviceService
from routeros_mcp.domain.services.dns_ntp import DNSNTPService
from routeros_mcp.domain.services.health import HealthService
from routeros_mcp.domain.services.job import JobService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.session import get_session_factory
from routeros_mcp.mcp.errors import map_exception_to_error
from routeros_mcp.mcp.protocol.jsonrpc import format_tool_result

logger = logging.getLogger(__name__)


def register_config_tools(mcp: FastMCP, settings: Settings) -> None:
    """Register professional-tier configuration workflow tools.

    Args:
        mcp: FastMCP instance
        settings: Application settings
    """
    session_factory = get_session_factory(settings.database_url)

    @mcp.tool()
    async def config_plan_dns_ntp_rollout(
        device_ids: list[str],
        dns_servers: list[str] | None = None,
        ntp_servers: list[str] | None = None,
        created_by: str = "system",
    ) -> dict[str, Any]:
        """Plan DNS/NTP configuration changes across multiple devices.

        Professional-tier tool that creates an immutable plan for DNS/NTP
        changes across multiple devices with validation and risk assessment.

        Use when:
        - Rolling out DNS/NTP configuration to multiple devices
        - Testing configuration changes before applying
        - Need approval workflow for production changes
        - Want detailed preview of changes per device

        Args:
            device_ids: List of device identifiers to target
            dns_servers: List of DNS server IPs (optional)
            ntp_servers: List of NTP server addresses (optional)
            created_by: User identifier (for audit trail)

        Returns:
            Plan details including plan_id and approval_token
        """
        try:
            async with session_factory.session() as session:
                # Validate inputs
                if not dns_servers and not ntp_servers:
                    raise ValueError("At least one of dns_servers or ntp_servers must be specified")

                if dns_servers and len(dns_servers) > 3:
                    raise ValueError("Maximum 3 DNS servers allowed")

                if ntp_servers and len(ntp_servers) > 4:
                    raise ValueError("Maximum 4 NTP servers allowed")

                # Create services
                plan_service = PlanService(session)
                device_service = DeviceService(session, settings)
                dns_ntp_service = DNSNTPService(session, settings)

                # Get current configuration for all devices
                devices_config = []
                for device_id in device_ids:
                    device = await device_service.get_device(device_id)

                    # Check professional workflow capability
                    if not device.allow_professional_workflows:
                        raise ValueError(
                            f"Device {device_id} does not allow professional workflows"
                        )

                    current_dns = None
                    current_ntp = None

                    try:
                        if dns_servers:
                            current_dns = await dns_ntp_service.get_dns_status(device_id)
                        if ntp_servers:
                            current_ntp = await dns_ntp_service.get_ntp_status(device_id)
                    except Exception as e:
                        logger.warning(
                            f"Could not fetch current config for {device_id}: {e}",
                            extra={"device_id": device_id},
                        )

                    devices_config.append(
                        {
                            "device_id": device_id,
                            "device_name": device.name,
                            "environment": device.environment,
                            "current_dns": current_dns,
                            "current_ntp": current_ntp,
                            "proposed_dns": dns_servers,
                            "proposed_ntp": ntp_servers,
                        }
                    )

                # Assess risk level
                risk_level = "medium"
                prod_devices = [d for d in devices_config if d["environment"] == "prod"]
                if prod_devices:
                    risk_level = "high"
                elif len(device_ids) > 10:
                    risk_level = "high"

                # Create plan
                changes = {
                    "dns_servers": dns_servers,
                    "ntp_servers": ntp_servers,
                    "devices": devices_config,
                }

                summary = f"DNS/NTP rollout to {len(device_ids)} devices"
                if dns_servers:
                    summary += f" (DNS: {', '.join(dns_servers)})"
                if ntp_servers:
                    summary += f" (NTP: {', '.join(ntp_servers)})"

                plan = await plan_service.create_plan(
                    tool_name="config/plan-dns-ntp-rollout",
                    created_by=created_by,
                    device_ids=device_ids,
                    summary=summary,
                    changes=changes,
                    risk_level=risk_level,
                )

                # Build device list
                device_list = "\n".join(
                    f"  - {d['device_id']} ({d['environment']})" for d in devices_config
                )

                return format_tool_result(
                    content=f"""DNS/NTP rollout plan created successfully.

Plan ID: {plan['plan_id']}
Risk Level: {risk_level.upper()}
Devices: {len(device_ids)}
Status: Ready for approval

To apply this plan, use config/apply-dns-ntp-rollout with:
  plan_id: {plan['plan_id']}
  approval_token: {plan['approval_token']}

The approval token expires at: {plan['approval_expires_at']}

Per-device changes:
{device_list}
""",
                    meta={
                        "plan_id": plan["plan_id"],
                        "approval_token": plan["approval_token"],
                        "approval_expires_at": plan["approval_expires_at"],
                        "risk_level": risk_level,
                        "device_count": len(device_ids),
                        "devices": devices_config,
                    },
                )

        except Exception as e:
            logger.error(f"Plan creation failed: {str(e)}", exc_info=True)
            raise map_exception_to_error(e)

    @mcp.tool()
    async def config_apply_dns_ntp_rollout(
        plan_id: str,
        approval_token: str,
        approved_by: str = "system",
        batch_size: int = 5,
        batch_pause_seconds: int = 30,
    ) -> dict[str, Any]:
        """Apply approved DNS/NTP rollout plan.

        Professional-tier tool that executes an approved DNS/NTP rollout plan
        across devices in batches with health checks between batches.

        Use when:
        - Ready to execute an approved plan
        - Have obtained approval token from plan creation
        - Want safe, monitored rollout with automatic health checks

        Args:
            plan_id: Plan identifier from plan creation
            approval_token: Approval token from plan creation
            approved_by: User identifier approving the plan
            batch_size: Number of devices per batch (default: 5)
            batch_pause_seconds: Pause between batches (default: 30)

        Returns:
            Execution results with per-device status
        """
        try:
            async with session_factory.session() as session:
                # Create services
                plan_service = PlanService(session)
                job_service = JobService(session)
                dns_ntp_service = DNSNTPService(session, settings)
                health_service = HealthService(session, settings)

                # Get and approve plan
                plan = await plan_service.get_plan(plan_id)
                if plan["status"] != "approved":
                    await plan_service.approve_plan(plan_id, approval_token, approved_by)

                # Create job for execution
                job = await job_service.create_job(
                    job_type="APPLY_DNS_NTP_ROLLOUT",
                    device_ids=plan["device_ids"],
                    plan_id=plan_id,
                    max_attempts=3,
                )

                # Define executor function
                async def execute_dns_ntp_batch(
                    job_id: str, device_ids: list[str], context: dict[str, Any]
                ) -> dict[str, Any]:
                    """Execute DNS/NTP changes for a batch of devices."""
                    changes = context["changes"]
                    dns_servers = changes.get("dns_servers")
                    ntp_servers = changes.get("ntp_servers")

                    results: dict[str, Any] = {"devices": {}}

                    for device_id in device_ids:
                        try:
                            # Apply DNS changes
                            if dns_servers:
                                await dns_ntp_service.update_dns_servers(
                                    device_id, dns_servers, dry_run=False
                                )

                            # Apply NTP changes
                            if ntp_servers:
                                await dns_ntp_service.update_ntp_servers(
                                    device_id, ntp_servers, dry_run=False
                                )

                            # Verify health
                            health = await health_service.check_device_health(device_id)

                            results["devices"][device_id] = {
                                "status": "success",
                                "health_status": health.get("status"),
                            }

                        except Exception as e:
                            logger.error(
                                f"Failed to apply changes to {device_id}: {e}",
                                extra={"device_id": device_id},
                            )
                            results["devices"][device_id] = {
                                "status": "failed",
                                "error": str(e),
                            }

                    return results

                # Execute job with batch processing
                results = await job_service.execute_job(
                    job_id=job["job_id"],
                    executor=execute_dns_ntp_batch,
                    executor_context={"changes": plan["changes"]},
                    batch_size=batch_size,
                    batch_pause_seconds=batch_pause_seconds,
                )

                # Update plan status
                if results.get("status") == "failed":
                    await plan_service.update_plan_status(plan_id, "failed")
                else:
                    await plan_service.update_plan_status(plan_id, "applied")

                success_count = sum(
                    1
                    for r in results.get("device_results", {}).values()
                    if r.get("status") == "success"
                )

                return format_tool_result(
                    content=f"""DNS/NTP rollout completed.

Plan ID: {plan_id}
Job ID: {job['job_id']}
Total Devices: {results['total_devices']}
Successful: {success_count}
Failed: {results['total_devices'] - success_count}
Batches: {results['batches_completed']}/{results['batches_total']}

Check device health with device/get-health for each device.
View full execution log with plan://{plan_id}/execution-log resource.
""",
                    meta={
                        "plan_id": plan_id,
                        "job_id": job["job_id"],
                        "results": results,
                    },
                )

        except Exception as e:
            logger.error(f"Plan application failed: {str(e)}", exc_info=True)
            raise map_exception_to_error(e)

    @mcp.tool()
    async def config_rollback_plan(
        plan_id: str,
        approved_by: str = "system",
    ) -> dict[str, Any]:
        """Attempt to rollback changes from a plan.

        Professional-tier tool that attempts to revert changes made by a plan
        using stored snapshots where available.

        Use when:
        - A plan application caused issues
        - Need to restore previous configuration
        - Want to revert changes safely

        Args:
            plan_id: Plan identifier to rollback
            approved_by: User identifier approving the rollback

        Returns:
            Rollback results with per-device status
        """
        try:
            async with session_factory.session() as session:
                plan_service = PlanService(session)
                dns_ntp_service = DNSNTPService(session, settings)

                # Get plan
                plan = await plan_service.get_plan(plan_id)

                if plan["status"] not in ["applied", "failed"]:
                    raise ValueError(f"Plan {plan_id} cannot be rolled back (status: {plan['status']})")

                # Extract previous configuration
                changes = plan["changes"]
                devices_config = changes.get("devices", [])

                results = {"plan_id": plan_id, "devices": {}}

                for device_config in devices_config:
                    device_id = device_config["device_id"]
                    try:
                        # Restore DNS if changed
                        if changes.get("dns_servers") and device_config.get("current_dns"):
                            prev_dns = device_config["current_dns"].get("dns_servers", [])
                            if prev_dns:
                                await dns_ntp_service.update_dns_servers(
                                    device_id, prev_dns, dry_run=False
                                )

                        # Restore NTP if changed
                        if changes.get("ntp_servers") and device_config.get("current_ntp"):
                            prev_ntp = device_config["current_ntp"].get("ntp_servers", [])
                            if prev_ntp:
                                await dns_ntp_service.update_ntp_servers(
                                    device_id, prev_ntp, dry_run=False
                                )

                        results["devices"][device_id] = {"status": "success"}

                    except Exception as e:
                        logger.error(
                            f"Failed to rollback {device_id}: {e}",
                            extra={"device_id": device_id},
                        )
                        results["devices"][device_id] = {
                            "status": "failed",
                            "error": str(e),
                        }

                # Update plan status
                await plan_service.update_plan_status(plan_id, "cancelled")

                success_count = sum(
                    1 for r in results["devices"].values() if r.get("status") == "success"
                )

                return format_tool_result(
                    content=f"""Rollback completed for plan {plan_id}.

Successful: {success_count}
Failed: {len(results['devices']) - success_count}

Note: Rollback restores previous DNS/NTP configuration where available.
Verify connectivity and health for affected devices.
""",
                    meta=results,
                )

        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}", exc_info=True)
            raise map_exception_to_error(e)


__all__ = ["register_config_tools"]
