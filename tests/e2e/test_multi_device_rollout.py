"""End-to-end integration tests for Phase 4 multi-device rollout workflows.

These tests validate the multi-device rollout planning and execution framework:
- Multi-device plan creation with batching configuration
- Batch processing with simulated health checks
- Health check failure detection and automatic rollback scenarios
- Manual cancellation between batches
- Partial device failures within a batch
- Audit log validation for all lifecycle events
- Device status tracking throughout rollout

Design principles:
- Use in-memory SQLite for fast test execution
- Mock RouterOS REST clients with realistic responses and failure modes
- Test plan service and job coordination layers
- Validate job progress, device statuses, and audit logs
- Follow patterns from test_phase3_workflows.py
- Simulate batch execution since full job runner not yet implemented

Note: These tests focus on plan creation, approval, and coordination logic.
The actual job execution with batch processing is simulated since the job runner
framework is part of Phase 4 implementation.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.domain.models import PlanStatus
from routeros_mcp.domain.services.job import JobService
from routeros_mcp.domain.services.plan import PlanService
from routeros_mcp.infra.db.models import AuditEvent, Base, Device, Job, Plan

from .e2e_test_utils import TEST_ENCRYPTION_KEY, make_test_settings
from .phase3_test_utils import MockDeviceService, MockRouterOSRestClient, create_mock_device


# Helper function to simulate batch execution
async def simulate_batch_execution(
    session: AsyncSession,
    job: Job,
    plan: Plan,
    mock_rest_clients: dict,
    fail_on_device: str | None = None,
    fail_health_on_device: str | None = None,
    cancel_after_batch: int | None = None,
) -> dict:
    """Simulate batched job execution with configurable failure modes.
    
    Args:
        session: Database session
        job: Job model
        plan: Plan model  
        mock_rest_clients: Mock REST clients for devices
        fail_on_device: Device ID to simulate apply failure on
        fail_health_on_device: Device ID to simulate health check failure on
        cancel_after_batch: Cancel job after this batch number (1-indexed)
        
    Returns:
        Execution results dictionary
    """
    device_ids = plan.device_ids
    batch_size = plan.batch_size or 5
    batches = [device_ids[i:i + batch_size] for i in range(0, len(device_ids), batch_size)]
    
    results = {
        "status": "completed",
        "devices_processed": 0,
        "batches_completed": 0,
        "failed_devices": 0,
        "device_results": {},
    }
    
    # Update job status
    job.status = "executing"
    await session.commit()
    
    # Update plan status
    plan.status = PlanStatus.EXECUTING.value
    await session.commit()
    
    for batch_idx, batch_device_ids in enumerate(batches):
        # Check for cancellation before batch
        if cancel_after_batch is not None and batch_idx > 0 and batch_idx == cancel_after_batch:
            job.cancellation_requested = True
            await session.commit()
        
        if job.cancellation_requested:
            # Handle cancellation
            results["status"] = "cancelled"
            results["batches_completed"] = batch_idx
            job.status = "cancelled"
            job.result_summary = f"Cancelled after {results['devices_processed']}/{len(device_ids)} devices, {batch_idx}/{len(batches)} batches"
            plan.status = PlanStatus.CANCELLED.value
            await session.commit()
            return results
        
        # Process batch
        for device_id in batch_device_ids:
            # Simulate apply changes
            if device_id == fail_on_device:
                results["device_results"][device_id] = {"status": "failed", "error": "Connection timeout"}
                results["failed_devices"] += 1
                if plan.device_statuses is not None:
                    plan.device_statuses[device_id] = "failed"
            else:
                results["device_results"][device_id] = {"status": "applied"}
                if plan.device_statuses is not None:
                    plan.device_statuses[device_id] = "applied"
                
            results["devices_processed"] += 1
        
        # Mark device_statuses as modified for SQLAlchemy
        from sqlalchemy.orm import attributes
        attributes.flag_modified(plan, "device_statuses")
        
        results["batches_completed"] += 1
        
        # Health check after batch
        if fail_health_on_device and fail_health_on_device in batch_device_ids:
            # Health check failed - trigger rollback
            results["status"] = "rolled_back"
            job.status = "rolled_back"
            job.result_summary = f"Health check failed on {fail_health_on_device}, rolled back {results['devices_processed']} devices"
            plan.status = PlanStatus.ROLLED_BACK.value
            
            # Mark all applied devices as rolled_back
            if plan.device_statuses is not None:
                for dev_id in device_ids:
                    if plan.device_statuses.get(dev_id) == "applied":
                        plan.device_statuses[dev_id] = "rolled_back"
            
            attributes.flag_modified(plan, "device_statuses")
            await session.commit()
            return results
    
    # Completed successfully (or with partial failures)
    if results["failed_devices"] > 0:
        results["status"] = "completed_with_errors"
        job.status = "completed_with_errors"
        job.result_summary = f"Completed {results['devices_processed'] - results['failed_devices']}/{results['devices_processed']} devices successfully"
        plan.status = PlanStatus.COMPLETED.value
    else:
        job.status = "completed"
        job.result_summary = f"Completed {results['devices_processed']}/{len(device_ids)} devices in {results['batches_completed']} batches"
        plan.status = PlanStatus.COMPLETED.value
    
    await session.commit()
    return results


class TestMultiDeviceRollout(unittest.TestCase):
    """E2E tests for multi-device rollout workflow with batching."""

    def test_successful_rollout_3_batches(self) -> None:
        """Test successful multi-device rollout with 3 batches (5 devices, batch_size=2).
        
        Scenario:
        - 5 devices: dev-lab-01 through dev-lab-05
        - Batch size: 2 (creates 3 batches: [2, 2, 1])
        - All batches complete successfully
        - All devices end in 'applied' state
        - Plan state transitions: pending → approved → executing → completed
        
        Validates:
        - Multi-device plan creation with batch configuration
        - Batch calculation (3 batches for 5 devices with batch_size=2)
        - Plan approval workflow
        - Job creation linked to plan
        - Simulated batch execution with health checks
        - Device status tracking (pending → applied)
        - Audit log entries for lifecycle events
        """

        async def _run() -> None:
            # Setup: Use in-memory database session
            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session_maker() as session:
                # Create 5 test devices in database
                devices = []
                for i in range(1, 6):
                    device = Device(
                        id=f"dev-lab-0{i}",
                        name=f"router-lab-0{i}",
                        management_ip=f"192.168.1.{i}",
                        management_port=443,
                        environment="lab",
                        status="healthy",
                        tags={},
                        allow_advanced_writes=True,
                        allow_professional_workflows=True,
                        allow_firewall_writes=True,
                    )
                    devices.append(device)
                    session.add(device)
                await session.commit()

            # Setup mock device service and REST clients (all healthy)
            mock_devices = {
                f"dev-lab-0{i}": create_mock_device(f"dev-lab-0{i}")
                for i in range(1, 6)
            }
            mock_rest_clients = {
                f"dev-lab-0{i}": MockRouterOSRestClient(f"dev-lab-0{i}")
                for i in range(1, 6)
            }
            mock_device_service = MockDeviceService(mock_devices, mock_rest_clients)

            # Create settings and services
            settings = make_test_settings(encryption_key=TEST_ENCRYPTION_KEY)
            
            async with async_session_maker() as session:
                plan_service = PlanService(session, settings)
                job_service = JobService(session)

                # Step 1: Create multi-device plan
                device_ids = [f"dev-lab-0{i}" for i in range(1, 6)]
                plan_result = await plan_service.create_multi_device_plan(
                    tool_name="firewall.plan_multi_device_changes",
                    created_by="test-user",
                    device_ids=device_ids,
                    summary="Test firewall rule deployment across 5 devices",
                    changes={
                        "action": "add_firewall_rules",
                        "rules": [
                            {"chain": "input", "action": "accept", "protocol": "tcp", "dst_port": "22"}
                        ],
                    },
                    change_type="firewall",
                    risk_level="medium",
                    batch_size=2,
                    pause_seconds_between_batches=0,  # No pause for test speed
                    rollback_on_failure=True,
                )

                plan_id = plan_result["plan_id"]
                self.assertEqual(plan_result["device_count"], 5)
                self.assertEqual(plan_result["batch_count"], 3)  # [2, 2, 1]
                self.assertEqual(plan_result["status"], PlanStatus.PENDING.value)

                # Verify batches are correctly structured
                batches = plan_result["batches"]
                self.assertEqual(len(batches), 3)
                self.assertEqual(batches[0]["device_count"], 2)
                self.assertEqual(batches[1]["device_count"], 2)
                self.assertEqual(batches[2]["device_count"], 1)

                # Step 2: Approve the plan
                approval_token = plan_result["approval_token"]
                await plan_service.approve_plan(
                    plan_id=plan_id,
                    approval_token=approval_token,
                    approved_by="test-user",
                )

                # Verify plan status updated
                stmt = select(Plan).where(Plan.id == plan_id)
                result = await session.execute(stmt)
                plan = result.scalar_one()
                self.assertEqual(plan.status, PlanStatus.APPROVED.value)

                # Step 3: Create job for plan application
                job_result = await job_service.create_job(
                    job_type="APPLY_PLAN",
                    device_ids=device_ids,
                    plan_id=plan_id,
                    max_attempts=3,
                )
                job_id = job_result["job_id"]

                # Step 4: Simulate batch execution (all successful)
                stmt = select(Job).where(Job.id == job_id)
                result = await session.execute(stmt)
                job = result.scalar_one()
                
                await session.refresh(plan)
                
                execution_result = await simulate_batch_execution(
                    session=session,
                    job=job,
                    plan=plan,
                    mock_rest_clients=mock_rest_clients,
                    fail_on_device=None,
                    fail_health_on_device=None,
                    cancel_after_batch=None,
                )

                # Step 5: Validate execution results
                self.assertEqual(execution_result["status"], "completed")
                self.assertEqual(execution_result["devices_processed"], 5)
                self.assertEqual(execution_result["batches_completed"], 3)
                self.assertEqual(execution_result["failed_devices"], 0)

                # Verify all devices have 'applied' status
                device_results = execution_result.get("device_results", {})
                for device_id in device_ids:
                    self.assertIn(device_id, device_results)
                    self.assertEqual(device_results[device_id]["status"], "applied")

                # Step 6: Verify plan status updated to completed
                await session.refresh(plan)
                self.assertEqual(plan.status, PlanStatus.COMPLETED.value)
                
                # Verify device statuses tracked in plan
                device_statuses = plan.device_statuses or {}
                for device_id in device_ids:
                    self.assertEqual(device_statuses.get(device_id), "applied")

                # Step 7: Verify job status
                await session.refresh(job)
                self.assertEqual(job.status, "completed")
                self.assertIsNotNone(job.result_summary)
                self.assertIn("5/5 devices", job.result_summary)

                # Step 8: Verify audit log entries
                stmt = select(AuditEvent).where(AuditEvent.plan_id == plan_id).order_by(AuditEvent.timestamp)
                result = await session.execute(stmt)
                audit_events = list(result.scalars().all())

                # Should have multiple audit events
                self.assertGreater(len(audit_events), 0)
                
                # Verify key audit actions
                audit_actions = [event.action for event in audit_events]
                self.assertIn("PLAN_CREATED", audit_actions)
                self.assertIn("PLAN_APPROVED", audit_actions)

        asyncio.run(_run())

    def test_rollout_halts_on_health_failure(self) -> None:
        """Test rollout halts when batch 2 health check fails and triggers rollback.
        
        Scenario:
        - 6 devices: dev-lab-01 through dev-lab-06
        - Batch size: 2 (creates 3 batches)
        - Batch 1 (dev-lab-01, dev-lab-02): succeeds, health checks pass
        - Batch 2 (dev-lab-03, dev-lab-04): changes applied but health check FAILS on dev-lab-03
        - Rollback triggered for all applied devices (batch 1 + batch 2)
        - Batch 3 (dev-lab-05, dev-lab-06): NEVER started
        - Plan state transitions: pending → approved → executing → rolled_back
        
        Validates:
        - Health check failure detection after batch application
        - Automatic rollback trigger on health failure
        - Batch 3 is not executed when rollback triggered
        - Device status tracking during rollback (applied → rolled_back)
        - Job progress reflects rollback
        - Audit logs include plan lifecycle events
        """

        async def _run() -> None:
            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session_maker() as session:
                # Create 6 test devices in database
                for i in range(1, 7):
                    device = Device(
                        id=f"dev-lab-0{i}",
                        name=f"router-lab-0{i}",
                        management_ip=f"192.168.1.{i}",
                        management_port=443,
                        environment="lab",
                        status="healthy",
                        tags={},
                        allow_advanced_writes=True,
                        allow_professional_workflows=True,
                        allow_firewall_writes=True,
                    )
                    session.add(device)
                await session.commit()

            # Setup mock device service and REST clients
            mock_devices = {
                f"dev-lab-0{i}": create_mock_device(f"dev-lab-0{i}")
                for i in range(1, 7)
            }
            mock_rest_clients = {
                f"dev-lab-0{i}": MockRouterOSRestClient(f"dev-lab-0{i}")
                for i in range(1, 7)
            }
            
            mock_device_service = MockDeviceService(mock_devices, mock_rest_clients)

            settings = make_test_settings(encryption_key=TEST_ENCRYPTION_KEY)
            
            async with async_session_maker() as session:
                plan_service = PlanService(session, settings)
                job_service = JobService(session)

                # Step 1: Create multi-device plan with rollback enabled
                device_ids = [f"dev-lab-0{i}" for i in range(1, 7)]
                plan_result = await plan_service.create_multi_device_plan(
                    tool_name="firewall.plan_multi_device_changes",
                    created_by="test-user",
                    device_ids=device_ids,
                    summary="Test rollout with health failure in batch 2",
                    changes={
                        "action": "add_firewall_rules",
                        "rules": [{"chain": "input", "action": "drop", "protocol": "tcp"}],
                    },
                    change_type="firewall",
                    risk_level="high",
                    batch_size=2,
                    pause_seconds_between_batches=0,
                    rollback_on_failure=True,
                )

                plan_id = plan_result["plan_id"]
                self.assertEqual(plan_result["batch_count"], 3)

                # Step 2: Approve and create job
                await plan_service.approve_plan(
                    plan_id=plan_id,
                    approval_token=plan_result["approval_token"],
                    approved_by="test-user",
                )

                job_result = await job_service.create_job(
                    job_type="APPLY_PLAN",
                    device_ids=device_ids,
                    plan_id=plan_id,
                )
                job_id = job_result["job_id"]

                # Step 3: Get job and plan for simulation
                stmt = select(Job).where(Job.id == job_id)
                result = await session.execute(stmt)
                job = result.scalar_one()
                
                stmt = select(Plan).where(Plan.id == plan_id)
                result = await session.execute(stmt)
                plan = result.scalar_one()

                # Step 4: Simulate batch execution with health failure on dev-lab-03 (batch 2)
                execution_result = await simulate_batch_execution(
                    session=session,
                    job=job,
                    plan=plan,
                    mock_rest_clients=mock_rest_clients,
                    fail_on_device=None,
                    fail_health_on_device="dev-lab-03",  # Fail health check in batch 2
                    cancel_after_batch=None,
                )

                # Step 5: Validate rollback occurred
                self.assertEqual(execution_result["status"], "rolled_back")
                
                # Only batches 1 and 2 should have been processed (4 devices)
                self.assertEqual(execution_result["batches_completed"], 2)
                self.assertEqual(execution_result["devices_processed"], 4)

                # Step 6: Verify plan status is rolled_back
                await session.refresh(plan)
                self.assertEqual(plan.status, PlanStatus.ROLLED_BACK.value)

                # Verify devices in batch 1 and 2 show rolled_back status
                device_statuses = plan.device_statuses or {}
                self.assertEqual(device_statuses.get("dev-lab-01"), "rolled_back")
                self.assertEqual(device_statuses.get("dev-lab-02"), "rolled_back")
                self.assertEqual(device_statuses.get("dev-lab-03"), "rolled_back")
                self.assertEqual(device_statuses.get("dev-lab-04"), "rolled_back")
                
                # Devices in batch 3 should still be pending (never started)
                self.assertEqual(device_statuses.get("dev-lab-05"), "pending")
                self.assertEqual(device_statuses.get("dev-lab-06"), "pending")

                # Step 7: Verify job status shows rollback
                await session.refresh(job)
                self.assertEqual(job.status, "rolled_back")
                self.assertIn("health", job.result_summary.lower())

                # Step 8: Verify audit logs exist
                stmt = select(AuditEvent).where(AuditEvent.plan_id == plan_id).order_by(AuditEvent.timestamp)
                result = await session.execute(stmt)
                audit_events = list(result.scalars().all())
                
                self.assertGreater(len(audit_events), 0)

        asyncio.run(_run())

    def test_manual_cancellation(self) -> None:
        """Test manual job cancellation after batch 1 completes.
        
        Scenario:
        - 6 devices: dev-lab-01 through dev-lab-06
        - Batch size: 2 (creates 3 batches)
        - Batch 1 (dev-lab-01, dev-lab-02): completes successfully
        - Cancellation requested BEFORE batch 2 starts
        - Batch 2 (dev-lab-03, dev-lab-04): NOT started
        - Batch 3 (dev-lab-05, dev-lab-06): NOT started
        - Plan state: pending → approved → executing → cancelled
        
        Validates:
        - Cancellation detection between batches
        - Remaining batches are not executed
        - Devices in batch 1 remain in 'applied' state (no rollback on cancellation)
        - Devices in batches 2 and 3 remain 'pending'
        - Job status reflects cancellation with partial completion
        - Audit logs include plan lifecycle events
        """

        async def _run() -> None:
            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session_maker() as session:
                # Create 6 test devices
                for i in range(1, 7):
                    device = Device(
                        id=f"dev-lab-0{i}",
                        name=f"router-lab-0{i}",
                        management_ip=f"192.168.1.{i}",
                        management_port=443,
                        environment="lab",
                        status="healthy",
                        tags={},
                        allow_advanced_writes=True,
                        allow_professional_workflows=True,
                        allow_firewall_writes=True,
                    )
                    session.add(device)
                await session.commit()

            # Setup mocks
            mock_devices = {f"dev-lab-0{i}": create_mock_device(f"dev-lab-0{i}") for i in range(1, 7)}
            mock_rest_clients = {f"dev-lab-0{i}": MockRouterOSRestClient(f"dev-lab-0{i}") for i in range(1, 7)}
            mock_device_service = MockDeviceService(mock_devices, mock_rest_clients)

            settings = make_test_settings(encryption_key=TEST_ENCRYPTION_KEY)
            
            async with async_session_maker() as session:
                plan_service = PlanService(session, settings)
                job_service = JobService(session)

                # Step 1: Create plan
                device_ids = [f"dev-lab-0{i}" for i in range(1, 7)]
                plan_result = await plan_service.create_multi_device_plan(
                    tool_name="routing.plan_multi_device_changes",
                    created_by="test-user",
                    device_ids=device_ids,
                    summary="Test manual cancellation after batch 1",
                    changes={"action": "add_routes", "routes": [{"dst_address": "10.0.0.0/8"}]},
                    change_type="routing",
                    risk_level="medium",
                    batch_size=2,
                    pause_seconds_between_batches=0,
                    rollback_on_failure=False,
                )

                plan_id = plan_result["plan_id"]

                # Step 2: Approve and create job
                await plan_service.approve_plan(
                    plan_id=plan_id,
                    approval_token=plan_result["approval_token"],
                    approved_by="test-user",
                )

                job_result = await job_service.create_job(
                    job_type="APPLY_PLAN",
                    device_ids=device_ids,
                    plan_id=plan_id,
                )
                job_id = job_result["job_id"]

                # Step 3: Get job and plan for simulation
                stmt = select(Job).where(Job.id == job_id)
                result = await session.execute(stmt)
                job = result.scalar_one()
                
                stmt = select(Plan).where(Plan.id == plan_id)
                result = await session.execute(stmt)
                plan = result.scalar_one()

                # Step 4: Simulate batch execution with cancellation after batch 1
                execution_result = await simulate_batch_execution(
                    session=session,
                    job=job,
                    plan=plan,
                    mock_rest_clients=mock_rest_clients,
                    fail_on_device=None,
                    fail_health_on_device=None,
                    cancel_after_batch=1,  # Cancel after batch 1 completes
                )

                # Step 5: Verify cancellation results
                self.assertEqual(execution_result["status"], "cancelled")
                self.assertEqual(execution_result["devices_processed"], 2)  # Only batch 1
                self.assertEqual(execution_result["batches_completed"], 1)

                # Only batch 1 devices should be in results
                device_results = execution_result.get("device_results", {})
                self.assertIn("dev-lab-01", device_results)
                self.assertIn("dev-lab-02", device_results)
                # Batch 2 devices not processed
                self.assertNotIn("dev-lab-03", device_results)

                # Step 6: Verify job status
                await session.refresh(job)
                self.assertTrue(job.cancellation_requested)
                self.assertEqual(job.status, "cancelled")
                self.assertIn("cancel", job.result_summary.lower())

                # Step 7: Verify plan status
                await session.refresh(plan)
                self.assertEqual(plan.status, PlanStatus.CANCELLED.value)

                # Batch 1 devices should be 'applied' (completed before cancellation)
                device_statuses = plan.device_statuses or {}
                self.assertEqual(device_statuses.get("dev-lab-01"), "applied")
                self.assertEqual(device_statuses.get("dev-lab-02"), "applied")
                
                # Batch 2 and 3 devices should remain 'pending' (never started)
                self.assertEqual(device_statuses.get("dev-lab-03"), "pending")
                self.assertEqual(device_statuses.get("dev-lab-04"), "pending")
                self.assertEqual(device_statuses.get("dev-lab-05"), "pending")
                self.assertEqual(device_statuses.get("dev-lab-06"), "pending")

                # Step 8: Verify audit logs
                stmt = select(AuditEvent).where(AuditEvent.plan_id == plan_id).order_by(AuditEvent.timestamp)
                result = await session.execute(stmt)
                audit_events = list(result.scalars().all())
                
                self.assertGreater(len(audit_events), 0)

        asyncio.run(_run())

    def test_partial_device_failure(self) -> None:
        """Test rollout continues when one device in a batch fails.
        
        Scenario:
        - 4 devices: dev-lab-01 through dev-lab-04
        - Batch size: 2 (creates 2 batches)
        - Batch 1 (dev-lab-01, dev-lab-02):
          - dev-lab-01: SUCCESS
          - dev-lab-02: FAILURE (device error during apply)
        - Batch 2 (dev-lab-03, dev-lab-04): continues execution, both succeed
        - Plan completes but marked as 'completed_with_errors'
        
        Validates:
        - Partial failures within a batch don't halt entire rollout
        - Failed device is tracked with error status
        - Subsequent batches continue execution
        - Job completes with mixed results
        - Failed device count is accurate
        - Audit logs capture plan lifecycle events
        """

        async def _run() -> None:
            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session_maker() as session:
                # Create 4 test devices
                for i in range(1, 5):
                    device = Device(
                        id=f"dev-lab-0{i}",
                        name=f"router-lab-0{i}",
                        management_ip=f"192.168.1.{i}",
                        management_port=443,
                        environment="lab",
                        status="healthy",
                        tags={},
                        allow_advanced_writes=True,
                        allow_professional_workflows=True,
                        allow_dhcp_writes=True,
                    )
                    session.add(device)
                await session.commit()

            # Setup mocks
            mock_devices = {f"dev-lab-0{i}": create_mock_device(f"dev-lab-0{i}") for i in range(1, 5)}
            mock_rest_clients = {
                f"dev-lab-0{i}": MockRouterOSRestClient(f"dev-lab-0{i}")
                for i in range(1, 5)
            }
            
            mock_device_service = MockDeviceService(mock_devices, mock_rest_clients)

            settings = make_test_settings(encryption_key=TEST_ENCRYPTION_KEY)
            
            async with async_session_maker() as session:
                plan_service = PlanService(session, settings)
                job_service = JobService(session)

                # Step 1: Create plan
                device_ids = [f"dev-lab-0{i}" for i in range(1, 5)]
                plan_result = await plan_service.create_multi_device_plan(
                    tool_name="dhcp.plan_multi_device_changes",
                    created_by="test-user",
                    device_ids=device_ids,
                    summary="Test partial device failure in batch",
                    changes={"action": "add_dhcp_server", "servers": [{"name": "dhcp1"}]},
                    change_type="dhcp",
                    risk_level="low",
                    batch_size=2,
                    pause_seconds_between_batches=0,
                    rollback_on_failure=False,  # Continue on partial failure
                )

                plan_id = plan_result["plan_id"]

                # Step 2: Approve and create job
                await plan_service.approve_plan(
                    plan_id=plan_id,
                    approval_token=plan_result["approval_token"],
                    approved_by="test-user",
                )

                job_result = await job_service.create_job(
                    job_type="APPLY_PLAN",
                    device_ids=device_ids,
                    plan_id=plan_id,
                )
                job_id = job_result["job_id"]

                # Step 3: Get job and plan for simulation
                stmt = select(Job).where(Job.id == job_id)
                result = await session.execute(stmt)
                job = result.scalar_one()
                
                stmt = select(Plan).where(Plan.id == plan_id)
                result = await session.execute(stmt)
                plan = result.scalar_one()

                # Step 4: Simulate batch execution with dev-lab-02 failure
                execution_result = await simulate_batch_execution(
                    session=session,
                    job=job,
                    plan=plan,
                    mock_rest_clients=mock_rest_clients,
                    fail_on_device="dev-lab-02",  # Fail this device
                    fail_health_on_device=None,
                    cancel_after_batch=None,
                )

                # Step 5: Validate partial failure results
                self.assertEqual(execution_result["status"], "completed_with_errors")
                
                # All batches should be processed
                self.assertEqual(execution_result["batches_completed"], 2)
                
                # Should have 1 failed device
                self.assertEqual(execution_result["failed_devices"], 1)
                
                # Should have processed all 4 devices (attempted)
                self.assertEqual(execution_result["devices_processed"], 4)

                # Verify device-level results
                device_results = execution_result.get("device_results", {})
                self.assertEqual(device_results["dev-lab-01"]["status"], "applied")
                self.assertEqual(device_results["dev-lab-02"]["status"], "failed")
                self.assertEqual(device_results["dev-lab-03"]["status"], "applied")
                self.assertEqual(device_results["dev-lab-04"]["status"], "applied")

                # Step 6: Verify plan status
                await session.refresh(plan)
                self.assertEqual(plan.status, PlanStatus.COMPLETED.value)

                # Verify device statuses
                device_statuses = plan.device_statuses or {}
                self.assertEqual(device_statuses.get("dev-lab-01"), "applied")
                self.assertEqual(device_statuses.get("dev-lab-02"), "failed")
                self.assertEqual(device_statuses.get("dev-lab-03"), "applied")
                self.assertEqual(device_statuses.get("dev-lab-04"), "applied")

                # Step 7: Verify job records partial success
                await session.refresh(job)
                self.assertEqual(job.status, "completed_with_errors")
                self.assertIsNotNone(job.result_summary)
                self.assertIn("3/4 devices", job.result_summary)

                # Step 8: Verify audit logs exist
                stmt = select(AuditEvent).where(AuditEvent.plan_id == plan_id).order_by(AuditEvent.timestamp)
                result = await session.execute(stmt)
                audit_events = list(result.scalars().all())
                
                self.assertGreater(len(audit_events), 0)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
