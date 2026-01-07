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
    session_factory = get_session_factory(settings)

    @mcp.tool()
    async def config_plan_dns_ntp_rollout(
        device_ids: list[str],
        dns_servers: list[str] | None = None,
        ntp_servers: list[str] | None = None,
        batch_size: int = 5,
        created_by: str = "system",
    ) -> dict[str, Any]:
        """Plan DNS/NTP configuration changes across multiple devices.

        Professional-tier tool that creates an immutable plan for DNS/NTP
        changes across multiple devices with validation and risk assessment.
        Uses Phase 4 multi-device batched execution pattern.

        Use when:
        - Rolling out DNS/NTP configuration to multiple devices (2-50)
        - Testing configuration changes before applying
        - Need approval workflow for production changes
        - Want detailed preview of changes per device with batching

        Args:
            device_ids: List of device identifiers to target (2-50 devices)
            dns_servers: List of DNS server IPs (optional, max 3)
            ntp_servers: List of NTP server addresses (optional, max 4)
            batch_size: Number of devices per batch (default: 5)
            created_by: User identifier (for audit trail)

        Returns:
            Plan details including plan_id, approval_token, and batch summary
        """
        try:
            async with session_factory.session() as session:
                # Validate device count for multi-device plan (2-50)
                if len(device_ids) < 2:
                    raise ValueError("Multi-device plans require at least 2 devices")
                if len(device_ids) > 50:
                    raise ValueError("Multi-device plans support maximum 50 devices")

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

                # Create plan using Phase 4 multi-device method
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

                plan = await plan_service.create_multi_device_plan(
                    tool_name="config/plan-dns-ntp-rollout",
                    created_by=created_by,
                    device_ids=device_ids,
                    summary=summary,
                    changes=changes,
                    change_type="dns_ntp",
                    risk_level=risk_level,
                    batch_size=batch_size,
                )

                # Extract batch information
                batches = plan.get("batches", [])
                devices_per_batch = [batch["device_count"] for batch in batches]

                # Build device list
                device_list = "\n".join(
                    f"  - {d['device_id']} ({d['environment']})" for d in devices_config
                )

                return format_tool_result(
                    content=f"""DNS/NTP rollout plan created successfully.

Plan ID: {plan['plan_id']}
Risk Level: {risk_level.upper()}
Devices: {len(device_ids)}
Batch Count: {plan['batch_count']}
Devices per Batch: {devices_per_batch}
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
                        "batch_count": plan["batch_count"],
                        "devices_per_batch": devices_per_batch,
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
    ) -> dict[str, Any]:
        """Apply approved DNS/NTP rollout plan with background job tracking.

        Professional-tier tool that creates a background job to execute an 
        approved DNS/NTP rollout plan across devices in batches with health 
        checks between batches.

        Use when:
        - Ready to execute an approved plan
        - Have obtained approval token from plan creation
        - Want safe, monitored rollout with automatic health checks
        - Need to track long-running multi-device operations

        Args:
            plan_id: Plan identifier from plan creation
            approval_token: Approval token from plan creation
            approved_by: User identifier approving the plan

        Returns:
            Job details with job_id for status tracking
        """
        try:
            async with session_factory.session() as session:
                # Create services
                plan_service = PlanService(session)
                job_service = JobService(session)

                # Get and approve plan
                plan = await plan_service.get_plan(plan_id)
                if plan["status"] != "approved":
                    await plan_service.approve_plan(plan_id, approval_token, approved_by)

                # Refresh plan to get approved status
                plan = await plan_service.get_plan(plan_id)

                # Create job for background execution
                job = await job_service.create_job(
                    job_type="APPLY_DNS_NTP_ROLLOUT",
                    device_ids=plan["device_ids"],
                    plan_id=plan_id,
                    max_attempts=3,
                )

                # Calculate estimated duration: ~1 minute per device in batches
                # With batch_size=5 and 30s pause between batches
                device_count = len(plan["device_ids"])
                batch_size = plan.get("batch_size", 5)
                batch_count = (device_count + batch_size - 1) // batch_size
                # Estimate: 60s per batch + 30s pause between batches
                estimated_minutes = max(1, int((batch_count * 90) / 60))

                return format_tool_result(
                    content=f"""DNS/NTP rollout job created successfully.

Plan ID: {plan_id}
Job ID: {job['job_id']}
Status: pending
Devices: {device_count}
Estimated Duration: ~{estimated_minutes} minutes

The job will execute in the background with staged rollout.
Use job/get-status or query the Job model to track progress.
View plan details with plan://{plan_id} resource.
""",
                    meta={
                        "job_id": job["job_id"],
                        "status": "pending",
                        "estimated_duration_minutes": estimated_minutes,
                        "plan_id": plan_id,
                        "device_count": device_count,
                        "batch_count": batch_count,
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

                if plan["status"] not in ["completed", "applied", "failed"]:
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
