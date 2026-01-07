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

    def test_apply_rollout_updates_plan_status(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "approved"

            dns_service = FakeDNSNTPService(None, Settings())
            health_service = FakeHealthService(None, Settings())
            job_service = FakeJobService(None)

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "DeviceService", FakeDeviceService),
                patch.object(config_module, "DNSNTPService", lambda s, st: dns_service),
                patch.object(config_module, "HealthService", lambda s, st: health_service),
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

                self.assertEqual(("plan-123", "completed"), plan_service.status_updates[-1])
                self.assertEqual("success", result["_meta"]["status"])
                self.assertTrue(dns_service.dns_updates)
                self.assertTrue(dns_service.ntp_updates)
                self.assertTrue(health_service.calls)

        asyncio.run(_run())

    def test_apply_rollout_pending_approval_and_failure(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "pending"
            plan_service.plan["device_ids"] = ["dev-1"]
            plan_service.plan["changes"] = {
                "dns_servers": ["9.9.9.9"],
                "ntp_servers": ["ntp"],
                "device_ids": ["dev-1"],
            }

            class FailingJobService(FakeJobService):
                async def execute_job(self, *args, **kwargs):  # type: ignore[override]
                    return {
                        "device_results": {"dev-1": {"status": "failed", "error": "boom"}},
                        "status": "failed",
                        "total_devices": 1,
                        "batches_completed": 0,
                        "batches_total": 1,
                    }

            dns_service = FakeDNSNTPService(None, Settings())
            health_service = FakeHealthService(None, Settings())

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(config_module, "JobService", lambda s: FailingJobService(s)),
                patch.object(config_module, "DNSNTPService", lambda s, st: dns_service),
                patch.object(config_module, "HealthService", lambda s, st: health_service),
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

                self.assertEqual(("plan-123", "failed"), plan_service.status_updates[-1])
                self.assertEqual(
                    "failed",
                    result["_meta"]["results"]["device_results"]["dev-1"]["status"],
                )

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
            plan_service.plan["status"] = "applied"
            plan_service.plan["changes"]["devices"] = [
                {
                    "device_id": "dev-1",
                    "current_dns": {"dns_servers": ["8.8.8.8"]},
                    "current_ntp": {"ntp_servers": ["time.old"]},
                }
            ]

            dns_service = FakeDNSNTPService(None, Settings())

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(config_module, "DNSNTPService", lambda s, st: dns_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                rollback_tool = tools["config_rollback_plan"]

                result = await rollback_tool(plan_id="plan-xyz", approved_by="user")

                self.assertEqual(("plan-xyz", "cancelled"), plan_service.status_updates[-1])
                self.assertTrue(result["content"][0]["text"].startswith("Rollback completed"))
                self.assertEqual(("dev-1", ["8.8.8.8"]), dns_service.dns_updates[0])
                self.assertEqual(("dev-1", ["time.old"]), dns_service.ntp_updates[0])

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
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                rollback_tool = tools["config_rollback_plan"]

                with self.assertRaises(MappedError):
                    await rollback_tool(plan_id="plan-xyz", approved_by="user")

        asyncio.run(_run())

    def test_rollback_plan_handles_device_failure(self) -> None:
        async def _run() -> None:
            fake_mcp = FakeMCP()
            fake_session = FakeSession()
            session_factory = FakeSessionFactory(fake_session)

            plan_service = FakePlanService(None)
            plan_service.plan["status"] = "applied"
            plan_service.plan["changes"]["devices"] = [
                {
                    "device_id": "dev-1",
                    "current_dns": {"dns_servers": ["8.8.8.8"]},
                    "current_ntp": {"ntp_servers": ["time.old"]},
                }
            ]

            class FailingDNS(FakeDNSNTPService):
                async def update_dns_servers(self, *_args, **_kwargs):  # type: ignore[override]
                    raise RuntimeError("rollback fail")

            dns_service = FailingDNS(None, Settings())

            with (
                patch.object(
                    config_module,
                    "get_session_factory",
                    lambda *_args, **_kwargs: session_factory,
                ),
                patch.object(config_module, "PlanService", lambda s: plan_service),
                patch.object(config_module, "DNSNTPService", lambda s, st: dns_service),
                patch.object(
                    config_module,
                    "map_exception_to_error",
                    lambda e: MappedError(str(e)),
                ),
            ):
                settings, tools = self._register_tools(fake_mcp)
                rollback_tool = tools["config_rollback_plan"]

                result = await rollback_tool(plan_id="plan-err", approved_by="user")

                self.assertEqual(
                    "failed",
                    result["_meta"]["devices"]["dev-1"]["status"],
                )
                self.assertEqual(("plan-err", "cancelled"), plan_service.status_updates[-1])

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
