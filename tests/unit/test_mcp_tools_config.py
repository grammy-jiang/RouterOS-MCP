"""Tests for professional-tier config MCP tools (plan/apply)."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from routeros_mcp.config import Settings
from routeros_mcp.mcp_tools import config as config_module


class MappedError(RuntimeError):
    pass


class FakeSession:
    pass


class FakeSessionContext:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def __aenter__(self) -> FakeSession:  # noqa: D401
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        return None


class FakeSessionFactory:
    def __init__(self, session: FakeSession) -> None:
        self._session = session
        self.calls = 0

    def session(self) -> FakeSessionContext:  # noqa: D401
        self.calls += 1
        return FakeSessionContext(self._session)


class FakeDevice:
    def __init__(self, device_id: str, environment: str, allow_professional: bool = True) -> None:
        self.id = device_id
        self.environment = environment
        self.name = f"name-{device_id}"
        self.allow_professional_workflows = allow_professional


class FakeDeviceService:
    def __init__(self, session, settings):  # noqa: D401, ANN001
        self.session = session
        self.settings = settings
        self.requests: list[str] = []

    async def get_device(self, device_id: str) -> FakeDevice:
        self.requests.append(device_id)
        # Default to prod environment to exercise risk logic; may be overridden in tests.
        env = getattr(self, "environment", "prod")
        allow = getattr(self, "allow_professional", True)
        return FakeDevice(device_id, env, allow)


class FakeDNSNTPService:
    def __init__(self, session, settings):  # noqa: D401, ANN001
        self.session = session
        self.settings = settings
        self.dns_updates: list[tuple[str, list[str]]] = []
        self.ntp_updates: list[tuple[str, list[str]]] = []

    async def get_dns_status(self, device_id: str):  # noqa: ANN001
        return {"device_id": device_id, "dns": []}

    async def get_ntp_status(self, device_id: str):  # noqa: ANN001
        return {"device_id": device_id, "ntp": []}

    async def update_dns_servers(self, device_id: str, servers: list[str], dry_run: bool = False):
        self.dns_updates.append((device_id, servers))

    async def update_ntp_servers(self, device_id: str, servers: list[str], dry_run: bool = False):
        self.ntp_updates.append((device_id, servers))


class FakePlanService:
    def __init__(self, session):  # noqa: D401, ANN001
        self.session = session
        self.created: list[dict] = []
        self.multi_device_created: list[dict] = []
        self.status_updates: list[tuple[str, str]] = []
        self.rollback_calls: list[dict] = []
        self.plan = {
            "plan_id": "plan-123",
            "approval_token": "token-abc",
            "approval_expires_at": "2030-01-01T00:00:00Z",
            "status": "pending",
            "device_ids": ["d1", "d2"],
            "changes": {
                "dns_servers": ["1.1.1.1"],
                "ntp_servers": ["ntp"],
                "device_ids": ["d1", "d2"],
            },
        }

    async def create_plan(self, **kwargs):
        self.created.append(kwargs)
        return self.plan

    async def create_multi_device_plan(self, **kwargs):
        self.multi_device_created.append(kwargs)
        device_ids = kwargs.get("device_ids", ["d1", "d2"])
        batch_size = kwargs.get("batch_size", 5)

        # Calculate batches
        batches = []
        for i in range(0, len(device_ids), batch_size):
            batch_devices = device_ids[i:i + batch_size]
            batches.append({
                "batch_number": len(batches) + 1,
                "device_ids": batch_devices,
                "device_count": len(batch_devices),
            })

        return {
            **self.plan,
            "batch_size": batch_size,
            "batch_count": len(batches),
            "batches": batches,
            "device_ids": device_ids,
        }

    async def get_plan(self, plan_id: str):  # noqa: ANN001
        self.plan["plan_id"] = plan_id
        return self.plan

    async def approve_plan(self, plan_id: str, approval_token: str, approved_by: str):
        self.plan["status"] = "approved"
        self.plan["approval_token"] = approval_token
        self.plan["approved_by"] = approved_by

    async def update_plan_status(self, plan_id: str, status: str):
        self.status_updates.append((plan_id, status))
        self.plan["status"] = status

    async def rollback_plan(self, plan_id: str, reason: str, triggered_by: str = "system", **kwargs):
        """Simulate rollback_plan method from PlanService."""
        self.rollback_calls.append({
            "plan_id": plan_id,
            "reason": reason,
            "triggered_by": triggered_by,
        })
        
        # Check if plan can be rolled back
        if self.plan["status"] not in ["executing", "completed", "applied", "failed"]:
            raise ValueError(f"Plan {plan_id} cannot be rolled back (status: {self.plan['status']})")
        
        # Extract device info from plan
        devices_config = self.plan["changes"].get("devices", [])
        device_count = len(devices_config) if devices_config else len(self.plan.get("device_ids", []))
        
        # Simulate rollback results
        devices_results = {}
        for device_config in devices_config:
            device_id = device_config["device_id"]
            # Check if we should simulate failure
            if hasattr(self, "fail_rollback") and self.fail_rollback:
                devices_results[device_id] = {
                    "status": "rollback_failed",
                    "errors": ["rollback fail"],
                }
            else:
                devices_results[device_id] = {
                    "status": "rolled_back",
                }
        
        success_count = sum(1 for r in devices_results.values() if r["status"] == "rolled_back")
        failed_count = len(devices_results) - success_count
        
        # Update plan status
        self.plan["status"] = "rolled_back"
        
        return {
            "plan_id": plan_id,
            "rollback_enabled": True,
            "reason": reason,
            "devices": devices_results,
            "summary": {
                "total": device_count,
                "success": success_count,
                "failed": failed_count,
            },
        }


class FakeJobService:
    def __init__(self, session):  # noqa: D401, ANN001
        self.session = session
        self.jobs_created: list[dict] = []
        self.executions: list[dict] = []

    async def create_job(self, **kwargs):
        self.jobs_created.append(kwargs)
        return {"job_id": "job-1", "device_ids": kwargs.get("device_ids", [])}

    async def execute_job(
        self,
        job_id: str,
        executor,
        executor_context: dict,
        batch_size: int,
        batch_pause_seconds: int,
    ) -> dict:
        self.executions.append(
            {
                "job_id": job_id,
                "context": executor_context,
                "batch_size": batch_size,
                "batch_pause_seconds": batch_pause_seconds,
            }
        )
        device_ids = executor_context.get("changes", {}).get("device_ids", [])
        # Execute single batch synchronously for test predictability
        result = await executor(job_id, device_ids, executor_context)
        return {
            "device_results": result.get("devices", {}),
            "status": "success",
            "total_devices": len(device_ids),
            "batches_completed": 1,
            "batches_total": 1,
        }


class FakeHealthService:
    def __init__(self, session, settings):  # noqa: D401, ANN001
        self.session = session
        self.settings = settings
        self.calls: list[str] = []

    async def check_device_health(self, device_id: str):
        self.calls.append(device_id)
        return {"status": "healthy"}


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, object] = {}

    def tool(self, *args, **kwargs):  # noqa: D401
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


class TestMCPToolsConfig(unittest.TestCase):
    def _register_tools(self, mcp: FakeMCP) -> tuple[Settings, dict[str, object]]:
        settings = Settings()
        config_module.register_config_tools(mcp, settings)
        return settings, mcp.tools

    def _common_patches(self):
        fake_session = FakeSession()
        session_factory = FakeSessionFactory(fake_session)
        return (
            session_factory,
            patch.object(
                config_module,
                "get_session_factory",
                lambda *_args, **_kwargs: session_factory,
            ),
            patch.object(config_module, "DeviceService", FakeDeviceService),
            patch.object(config_module, "DNSNTPService", FakeDNSNTPService),
            patch.object(config_module, "PlanService", FakePlanService),
            patch.object(config_module, "JobService", FakeJobService),
            patch.object(config_module, "HealthService", FakeHealthService),
            patch.object(config_module, "map_exception_to_error", lambda e: MappedError(str(e))),
        )

    def test_plan_validates_inputs(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            session_factory, *patchers = self._common_patches()
            with (
                patchers[0],
                patchers[1],
                patchers[2],
                patchers[3],
                patchers[4],
                patchers[5],
                patchers[6],
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                with self.assertRaises(MappedError):
                    await plan_tool(device_ids=["d1", "d2"], dns_servers=None, ntp_servers=None)

                with self.assertRaises(MappedError):
                    await plan_tool(
                        device_ids=["d1", "d2"], dns_servers=["1", "2", "3", "4"], ntp_servers=None
                    )

                with self.assertRaises(MappedError):
                    await plan_tool(
                        device_ids=["d1", "d2"],
                        dns_servers=None,
                        ntp_servers=["1", "2", "3", "4", "5"],
                    )

        asyncio.run(_run())

    def test_plan_rejects_devices_without_professional_flag(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            session_factory, *patchers = self._common_patches()

            async def disallowed_device(self, device_id: str):  # type: ignore[override]
                return FakeDevice(device_id, "lab", allow_professional=False)

            with (
                patchers[0],
                patchers[1],
                patchers[2],
                patchers[3],
                patchers[4],
                patchers[5],
                patchers[6],
                patch.object(FakeDeviceService, "get_device", disallowed_device),
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                with self.assertRaises(MappedError):
                    await plan_tool(device_ids=["d1", "d2"], dns_servers=["1.1.1.1"], ntp_servers=None)

        asyncio.run(_run())

    def test_plan_success_high_risk_for_prod(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            session_factory, *patchers = self._common_patches()

            class ProdDeviceService(FakeDeviceService):
                async def get_device(self, device_id: str) -> FakeDevice:  # type: ignore[override]
                    return FakeDevice(device_id, "prod", allow_professional=True)

            with (
                patchers[0],
                patch.object(config_module, "DeviceService", ProdDeviceService),
                patchers[2],
                patchers[3],
                patchers[4],
                patchers[5],
                patchers[6],
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                result = await plan_tool(
                    device_ids=["prod-1", "prod-2"],
                    dns_servers=["1.1.1.1"],
                    ntp_servers=["pool.ntp.org"],
                )

                self.assertEqual("high", result["_meta"]["risk_level"])
                self.assertEqual(2, result["_meta"]["device_count"])
                self.assertIn("plan_id", result["_meta"])

        asyncio.run(_run())

    def test_plan_high_risk_many_devices(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            session_factory, *patchers = self._common_patches()

            class LabDeviceService(FakeDeviceService):
                async def get_device(self, device_id: str) -> FakeDevice:  # type: ignore[override]
                    return FakeDevice(device_id, "lab", allow_professional=True)

            with (
                patchers[0],
                patch.object(config_module, "DeviceService", LabDeviceService),
                patchers[2],
                patchers[3],
                patchers[4],
                patchers[5],
                patchers[6],
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                device_ids = [f"dev-{i}" for i in range(11)]
                result = await plan_tool(
                    device_ids=device_ids,
                    dns_servers=["1.1.1.1"],
                    ntp_servers=None,
                )

                self.assertEqual("high", result["_meta"]["risk_level"])
                self.assertEqual(11, result["_meta"]["device_count"])

        asyncio.run(_run())

    def test_plan_fetch_config_warning(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()

            class WarnDNS(FakeDNSNTPService):
                async def get_dns_status(self, *_args, **_kwargs):  # type: ignore[override]
                    raise RuntimeError("fetch fail")

            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "DeviceService", FakeDeviceService),
                patch.object(config_module, "DNSNTPService", WarnDNS),
                patch.object(config_module, "PlanService", FakePlanService),
                patch.object(config_module, "JobService", FakeJobService),
                patch.object(config_module, "HealthService", FakeHealthService),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                result = await plan_tool(
                    device_ids=["d1", "d2"],
                    dns_servers=["1.1.1.1"],
                    ntp_servers=None,
                )
                self.assertIsNone(result["_meta"]["devices"][0]["current_dns"])

        asyncio.run(_run())

    def test_apply_rollout_creates_job_and_returns_pending(self) -> None:
        """Test that apply rollout creates job without executing."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "approved"
            plan_service.plan["device_ids"] = ["d1", "d2"]
            plan_service.plan["batch_size"] = 5

            job_service = FakeJobService(None)

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "JobService", lambda s: job_service),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                apply_tool = tools["config_apply_dns_ntp_rollout"]

                result = await apply_tool(
                    plan_id="plan-123",
                    approval_token="tok",
                    approved_by="user",
                )

                # Verify job created but not executed
                self.assertEqual(1, len(job_service.jobs_created))
                self.assertEqual(0, len(job_service.executions))

                # Verify response has pending status
                self.assertEqual("pending", result["_meta"]["status"])
                self.assertIn("job_id", result["_meta"])

        asyncio.run(_run())

    def test_apply_rollout_with_pending_approval(self) -> None:
        """Test that apply rollout approves pending plan and creates job."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "pending"
            plan_service.plan["device_ids"] = ["dev-1"]
            plan_service.plan["batch_size"] = 5

            job_service = FakeJobService(None)

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(config_module, "JobService", lambda s: job_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                apply_tool = tools["config_apply_dns_ntp_rollout"]

                result = await apply_tool(
                    plan_id="plan-123",
                    approval_token="tok",
                    approved_by="user",
                )

                # Verify plan was approved (approve_plan modifies plan status)
                self.assertEqual("approved", plan_service.plan["status"])

                # Verify job created and status is pending
                self.assertEqual(1, len(job_service.jobs_created))
                self.assertEqual("pending", result["_meta"]["status"])

        asyncio.run(_run())

    def test_apply_rollout_maps_exception(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            class ExplodingPlanService(FakePlanService):
                async def get_plan(self, *_args, **_kwargs):  # type: ignore[override]
                    raise RuntimeError("no plan")

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s: ExplodingPlanService(s)),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                apply_tool = tools["config_apply_dns_ntp_rollout"]

                with self.assertRaises(MappedError):
                    await apply_tool(
                        plan_id="plan-err",
                        approval_token="tok",
                        approved_by="user",
                    )

        asyncio.run(_run())

    def test_rollback_plan_success(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "executing"
            plan_service.plan["changes"]["devices"] = [
                {
                    "device_id": "dev-1",
                    "current_dns": {"dns_servers": ["8.8.8.8"]},
                    "current_ntp": {"ntp_servers": ["time.old"]},
                }
            ]

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s, st=None: plan_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                rollback_tool = tools["config_rollback_plan"]

                result = await rollback_tool(
                    plan_id="plan-xyz",
                    reason="Manual rollback due to issues",
                    triggered_by="user"
                )

                # Verify rollback_plan was called with correct parameters
                self.assertEqual(1, len(plan_service.rollback_calls))
                self.assertEqual("plan-xyz", plan_service.rollback_calls[0]["plan_id"])
                self.assertEqual("Manual rollback due to issues", plan_service.rollback_calls[0]["reason"])
                self.assertEqual("user", plan_service.rollback_calls[0]["triggered_by"])

                # Verify response format
                self.assertTrue(result["content"][0]["text"].startswith("Manual rollback initiated"))
                self.assertIn("reason", result["content"][0]["text"].lower())
                self.assertEqual("plan-xyz", result["_meta"]["plan_id"])
                self.assertEqual("rolling_back", result["_meta"]["status"])
                self.assertEqual(1, result["_meta"]["devices_affected"])
                self.assertEqual("Manual rollback due to issues", result["_meta"]["reason"])

        asyncio.run(_run())

    def test_rollback_plan_invalid_status_raises(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "pending"

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s, st=None: plan_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                rollback_tool = tools["config_rollback_plan"]

                with self.assertRaises(MappedError):
                    await rollback_tool(
                        plan_id="plan-xyz",
                        reason="Manual rollback",
                        triggered_by="user"
                    )

        asyncio.run(_run())

    def test_rollback_plan_handles_device_failure(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "executing"
            plan_service.plan["changes"]["devices"] = [
                {
                    "device_id": "dev-1",
                    "current_dns": {"dns_servers": ["8.8.8.8"]},
                    "current_ntp": {"ntp_servers": ["time.old"]},
                }
            ]
            plan_service.fail_rollback = True  # Simulate rollback failure

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s, st=None: plan_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                rollback_tool = tools["config_rollback_plan"]

                result = await rollback_tool(
                    plan_id="plan-err",
                    reason="Manual rollback",
                    triggered_by="user"
                )

                # Verify device failure is reported
                self.assertEqual(
                    "rollback_failed",
                    result["_meta"]["devices"]["dev-1"]["status"],
                )
                self.assertEqual(0, result["_meta"]["summary"]["success"])
                self.assertEqual(1, result["_meta"]["summary"]["failed"])

        asyncio.run(_run())

    def test_rollback_plan_reason_in_audit_trail(self) -> None:
        """Test that reason parameter is properly passed to PlanService for audit trail."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "executing"
            plan_service.plan["changes"]["devices"] = [
                {
                    "device_id": "dev-1",
                    "current_dns": {"dns_servers": ["8.8.8.8"]},
                }
            ]

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s, st=None: plan_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                rollback_tool = tools["config_rollback_plan"]

                custom_reason = "Discovered DNS resolution issues after rollout"
                result = await rollback_tool(
                    plan_id="plan-123",
                    reason=custom_reason,
                    triggered_by="admin-user"
                )

                # Verify reason was passed to rollback_plan
                self.assertEqual(1, len(plan_service.rollback_calls))
                self.assertEqual(custom_reason, plan_service.rollback_calls[0]["reason"])
                self.assertEqual("admin-user", plan_service.rollback_calls[0]["triggered_by"])
                
                # Verify reason is included in response
                self.assertIn(custom_reason, result["content"][0]["text"])
                self.assertEqual(custom_reason, result["_meta"]["reason"])

        asyncio.run(_run())

    def test_plan_dns_ntp_rollout_validates_device_count_minimum(self) -> None:
        """Test that plan creation fails with less than 2 devices."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            _, *patchers = self._common_patches()

            with (
                patchers[0],
                patchers[1],
                patchers[2],
                patchers[3],
                patchers[4],
                patchers[5],
                patchers[6],
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                # Should fail with only 1 device
                with self.assertRaises(MappedError) as ctx:
                    await plan_tool(
                        device_ids=["d1"],
                        dns_servers=["1.1.1.1"],
                        ntp_servers=None,
                    )
                self.assertIn("at least 2 devices", str(ctx.exception).lower())

        asyncio.run(_run())

    def test_plan_dns_ntp_rollout_validates_device_count_maximum(self) -> None:
        """Test that plan creation fails with more than 50 devices."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            _, *patchers = self._common_patches()

            with (
                patchers[0],
                patchers[1],
                patchers[2],
                patchers[3],
                patchers[4],
                patchers[5],
                patchers[6],
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                # Should fail with 51 devices
                device_ids = [f"dev-{i}" for i in range(51)]
                with self.assertRaises(MappedError) as ctx:
                    await plan_tool(
                        device_ids=device_ids,
                        dns_servers=["1.1.1.1"],
                        ntp_servers=None,
                    )
                self.assertIn("maximum 50 devices", str(ctx.exception).lower())

        asyncio.run(_run())

    def test_plan_dns_ntp_rollout_uses_multi_device_plan(self) -> None:
        """Test that plan creation uses create_multi_device_plan with batch_size."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "DeviceService", FakeDeviceService),
                patch.object(config_module, "DNSNTPService", FakeDNSNTPService),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(config_module, "JobService", FakeJobService),
                patch.object(config_module, "HealthService", FakeHealthService),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                await plan_tool(
                    device_ids=["dev-1", "dev-2", "dev-3"],
                    dns_servers=["1.1.1.1"],
                    ntp_servers=["pool.ntp.org"],
                    batch_size=2,
                )

                # Verify create_multi_device_plan was called
                self.assertEqual(1, len(plan_service.multi_device_created))
                plan_call = plan_service.multi_device_created[0]
                self.assertEqual("config/plan-dns-ntp-rollout", plan_call["tool_name"])
                self.assertEqual(["dev-1", "dev-2", "dev-3"], plan_call["device_ids"])
                self.assertEqual("dns_ntp", plan_call["change_type"])
                self.assertEqual(2, plan_call["batch_size"])

        asyncio.run(_run())

    def test_plan_dns_ntp_rollout_returns_batch_information(self) -> None:
        """Test that plan result includes batch_count and devices_per_batch."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "DeviceService", FakeDeviceService),
                patch.object(config_module, "DNSNTPService", FakeDNSNTPService),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(config_module, "JobService", FakeJobService),
                patch.object(config_module, "HealthService", FakeHealthService),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                # Test with 7 devices, batch_size=3 -> [3, 3, 1]
                device_ids = [f"dev-{i}" for i in range(7)]
                result = await plan_tool(
                    device_ids=device_ids,
                    dns_servers=["1.1.1.1"],
                    ntp_servers=None,
                    batch_size=3,
                )

                # Verify batch information in metadata
                self.assertIn("batch_count", result["_meta"])
                self.assertIn("devices_per_batch", result["_meta"])
                self.assertEqual(3, result["_meta"]["batch_count"])
                self.assertEqual([3, 3, 1], result["_meta"]["devices_per_batch"])

                # Verify it's in the content too
                self.assertIn("Batch Count: 3", result["content"][0]["text"])
                self.assertIn("[3, 3, 1]", result["content"][0]["text"])

        asyncio.run(_run())

    def test_plan_dns_ntp_rollout_default_batch_size(self) -> None:
        """Test that plan creation uses default batch_size of 5."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "DeviceService", FakeDeviceService),
                patch.object(config_module, "DNSNTPService", FakeDNSNTPService),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(config_module, "JobService", FakeJobService),
                patch.object(config_module, "HealthService", FakeHealthService),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                plan_tool = tools["config_plan_dns_ntp_rollout"]

                # Don't specify batch_size - should default to 5
                device_ids = [f"dev-{i}" for i in range(12)]
                result = await plan_tool(
                    device_ids=device_ids,
                    dns_servers=["1.1.1.1"],
                    ntp_servers=None,
                )

                # Verify default batch_size=5 was used -> [5, 5, 2]
                self.assertEqual(3, result["_meta"]["batch_count"])
                self.assertEqual([5, 5, 2], result["_meta"]["devices_per_batch"])

        asyncio.run(_run())

    def test_apply_dns_ntp_rollout(self) -> None:
        """Test that apply_dns_ntp_rollout creates job and returns immediately."""
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "approved"
            plan_service.plan["device_ids"] = ["dev-1", "dev-2", "dev-3"]
            plan_service.plan["batch_size"] = 5

            job_service = FakeJobService(None)

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(config_module, "JobService", lambda s: job_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                apply_tool = tools["config_apply_dns_ntp_rollout"]

                result = await apply_tool(
                    plan_id="plan-123",
                    approval_token="tok",
                    approved_by="user",
                )

                # Verify job was created
                self.assertEqual(1, len(job_service.jobs_created))
                job_created = job_service.jobs_created[0]
                self.assertEqual("APPLY_DNS_NTP_ROLLOUT", job_created["job_type"])
                self.assertEqual("plan-123", job_created["plan_id"])
                self.assertEqual(["dev-1", "dev-2", "dev-3"], job_created["device_ids"])

                # Verify response format
                self.assertIn("job_id", result["_meta"])
                self.assertEqual("job-1", result["_meta"]["job_id"])
                self.assertEqual("pending", result["_meta"]["status"])
                self.assertIn("estimated_duration_minutes", result["_meta"])
                self.assertGreater(result["_meta"]["estimated_duration_minutes"], 0)

                # Verify job was NOT executed (no executions)
                self.assertEqual(0, len(job_service.executions))

                # Verify content mentions background execution
                self.assertIn("background", result["content"][0]["text"].lower())

        asyncio.run(_run())
