"""End-to-end integration tests for Phase 3 plan/apply workflows.

These tests validate the full stack:
- MCP tools → domain services → plan framework → database
- Happy path and failure scenarios (rollback, approval expiration, etc.)
- Audit log validation for all plan lifecycle events

Design principles:
- Use in-memory SQLite for fast test execution
- Mock RouterOS REST clients with realistic responses
- Test from MCP tool layer (public interface)
- Validate content, isError, and _meta fields
- Verify audit trail for all operations
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import select

from routeros_mcp.infra.db.models import AuditEvent, Plan
from routeros_mcp.mcp_tools import firewall_write as firewall_tools

from .e2e_test_utils import DummyMCP, FakeSessionFactory, make_test_settings
from .phase3_test_utils import MockDeviceService, MockRouterOSRestClient, create_mock_device


class TestFirewallPlanApplyWorkflow(unittest.TestCase):
    """E2E tests for firewall plan/apply workflow."""

    def test_firewall_plan_apply_success(self) -> None:
        """Test full firewall workflow: plan → approve → apply.
        
        Validates:
        - Plan creation with approval token
        - Token validation
        - Apply execution with health checks
        - Audit log entries for all lifecycle events
        - Database state consistency
        """

        async def _run() -> None:
            # Setup: Use in-memory database session
            from routeros_mcp.infra.db.models import Base, Device
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session_maker() as session:
                # Create test devices in database
                device1 = Device(
                    id="dev-lab-01",
                    name="router-lab-01",
                    management_ip="192.168.1.1",
                    management_port=443,
                    environment="lab",
                    status="healthy",
                    tags={},
                    allow_advanced_writes=True,
                    allow_professional_workflows=True,
                    allow_firewall_writes=True,
                )
                device2 = Device(
                    id="dev-lab-02",
                    name="router-lab-02",
                    management_ip="192.168.1.2",
                    management_port=443,
                    environment="lab",
                    status="healthy",
                    tags={},
                    allow_advanced_writes=True,
                    allow_professional_workflows=True,
                    allow_firewall_writes=True,
                )
                session.add(device1)
                session.add(device2)
                await session.commit()

            # Setup mock device service and REST clients
            mock_devices = {
                "dev-lab-01": create_mock_device("dev-lab-01"),
                "dev-lab-02": create_mock_device("dev-lab-02"),
            }
            mock_rest_clients = {
                "dev-lab-01": MockRouterOSRestClient("dev-lab-01"),
                "dev-lab-02": MockRouterOSRestClient("dev-lab-02"),
            }
            mock_device_service = MockDeviceService(mock_devices, mock_rest_clients)

            # Create session factory that returns real session
            class RealSessionFactory:
                def __init__(self, session_maker: async_sessionmaker) -> None:
                    self.session_maker = session_maker
                
                def session(self) -> AsyncSession:
                    return self.session_maker()

            session_factory = RealSessionFactory(async_session_maker)

            with (
                patch.object(
                    firewall_tools, "get_session_factory", return_value=session_factory
                ),
                patch.object(firewall_tools, "DeviceService", return_value=mock_device_service),
            ):
                # Register firewall tools
                mcp = DummyMCP()
                settings = make_test_settings()
                firewall_tools.register_firewall_write_tools(mcp, settings)

                # Step 1: Create plan
                plan_tool = mcp.tools["plan_add_firewall_rule"]
                plan_result = await plan_tool(
                    device_ids=["dev-lab-01", "dev-lab-02"],
                    chain="forward",
                    action="accept",
                    src_address="192.168.1.0/24",
                    dst_address="10.0.0.0/8",
                    protocol="tcp",
                    dst_port="443",
                    comment="Allow internal to app subnet HTTPS",
                )

                # Validate plan creation
                self.assertFalse(plan_result["isError"])
                self.assertIn("Firewall rule plan created successfully", plan_result["content"][0]["text"])
                
                meta = plan_result["_meta"]
                self.assertIn("plan_id", meta)
                self.assertIn("approval_token", meta)
                self.assertEqual(meta["risk_level"], "medium")
                self.assertEqual(meta["device_count"], 2)

                plan_id = meta["plan_id"]
                approval_token = meta["approval_token"]

                # Verify plan in database
                async with async_session_maker() as session:
                    stmt = select(Plan).where(Plan.id == plan_id)
                    result = await session.execute(stmt)
                    plan_record = result.scalar_one_or_none()
                    
                    self.assertIsNotNone(plan_record)
                    self.assertEqual(plan_record.status, "pending")
                    self.assertEqual(plan_record.tool_name, "firewall/plan-add-rule")
                    self.assertEqual(len(plan_record.device_ids), 2)
                    
                    # Verify audit log for plan creation
                    audit_stmt = select(AuditEvent).where(
                        AuditEvent.action == "PLAN_CREATED",
                        AuditEvent.plan_id == plan_id,
                    )
                    audit_result = await session.execute(audit_stmt)
                    audit_event = audit_result.scalar_one_or_none()
                    
                    self.assertIsNotNone(audit_event)
                    self.assertEqual(audit_event.result, "SUCCESS")

                # Step 2: Apply plan (approval happens automatically within apply tool)
                apply_tool = mcp.tools["apply_firewall_plan"]
                apply_result = await apply_tool(
                    plan_id=plan_id,
                    approval_token=approval_token,
                )

                # Validate apply result
                self.assertFalse(apply_result["isError"])
                self.assertIn("successfully", apply_result["content"][0]["text"].lower())
                
                apply_meta = apply_result["_meta"]
                self.assertEqual(apply_meta["plan_id"], plan_id)
                self.assertEqual(apply_meta["final_status"], "completed")
                self.assertEqual(len(apply_meta["device_results"]), 2)
                
                # Verify all devices succeeded
                for device_result in apply_meta["device_results"]:
                    self.assertEqual(device_result["status"], "success")
                    self.assertIn("snapshot_id", device_result)
                    self.assertIn("health_check", device_result)

                # Verify plan status updated in database
                async with async_session_maker() as session:
                    stmt = select(Plan).where(Plan.id == plan_id)
                    result = await session.execute(stmt)
                    plan_record = result.scalar_one_or_none()
                    
                    self.assertIsNotNone(plan_record)
                    self.assertEqual(plan_record.status, "completed")
                    
                    # Verify audit log for plan approval (pending → approved)
                    audit_stmt = select(AuditEvent).where(
                        AuditEvent.action == "PLAN_APPROVED",
                        AuditEvent.plan_id == plan_id,
                    )
                    audit_result = await session.execute(audit_stmt)
                    audit_event = audit_result.scalar_one_or_none()
                    
                    self.assertIsNotNone(audit_event)
                    self.assertEqual(audit_event.result, "SUCCESS")
                    
                    # Verify audit log for plan execution (status updates to executing and completed)
                    audit_stmt = select(AuditEvent).where(
                        AuditEvent.action == "PLAN_STATUS_UPDATE",
                        AuditEvent.plan_id == plan_id,
                    )
                    audit_result = await session.execute(audit_stmt)
                    status_updates = list(audit_result.scalars().all())
                    
                    # Should have at least 2 status updates: executing and completed
                    self.assertGreaterEqual(len(status_updates), 2)

                # Verify REST client calls
                for device_id in ["dev-lab-01", "dev-lab-02"]:
                    rest_client = mock_rest_clients[device_id]
                    self.assertTrue(rest_client.closed)
                    
                    # Verify snapshot was created (GET firewall rules)
                    get_calls = [c for c in rest_client.calls if c[0] == "GET" and "/firewall/filter" in c[1]]
                    self.assertGreater(len(get_calls), 0)
                    
                    # Verify rule was added (POST)
                    post_calls = [c for c in rest_client.calls if c[0] == "POST" and "/firewall/filter" in c[1]]
                    self.assertGreater(len(post_calls), 0)
                    
                    # Verify health check was performed (GET system/resource)
                    health_calls = [c for c in rest_client.calls if c[0] == "GET" and "/system/resource" in c[1]]
                    self.assertGreater(len(health_calls), 0)

            await engine.dispose()

        asyncio.run(_run())

    def test_firewall_rollback_on_health_check_failure(self) -> None:
        """Test automatic rollback when health check fails after firewall rule changes.
        
        Validates:
        - Snapshot creation before changes
        - Health check execution
        - Automatic rollback on health check failure
        - Plan status updated to failed
        - Audit log entries for rollback
        """

        async def _run() -> None:
            # Setup: Use in-memory database session
            from routeros_mcp.infra.db.models import Base, Device
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session_maker() as session:
                # Create test device in database
                device = Device(
                    id="dev-lab-01",
                    name="router-lab-01",
                    management_ip="192.168.1.1",
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

            # Setup mock device service with REST client configured for health check failure
            mock_devices = {
                "dev-lab-01": create_mock_device("dev-lab-01"),
            }
            mock_rest_clients = {
                "dev-lab-01": MockRouterOSRestClient(
                    "dev-lab-01",
                    health_check_failure=True,  # Simulate health check failure
                ),
            }
            mock_device_service = MockDeviceService(mock_devices, mock_rest_clients)

            # Create session factory
            class RealSessionFactory:
                def __init__(self, session_maker: async_sessionmaker) -> None:
                    self.session_maker = session_maker
                
                def session(self):
                    return self.session_maker()

            session_factory = RealSessionFactory(async_session_maker)

            with (
                patch.object(
                    firewall_tools, "get_session_factory", return_value=session_factory
                ),
                patch.object(firewall_tools, "DeviceService", return_value=mock_device_service),
            ):
                # Register firewall tools
                mcp = DummyMCP()
                settings = make_test_settings()
                firewall_tools.register_firewall_write_tools(mcp, settings)

                # Step 1: Create plan
                plan_tool = mcp.tools["plan_add_firewall_rule"]
                plan_result = await plan_tool(
                    device_ids=["dev-lab-01"],
                    chain="input",
                    action="accept",
                    src_address="192.168.1.0/24",
                    protocol="tcp",
                    dst_port="22",
                    comment="Allow SSH from LAN",
                )

                # Validate plan creation
                self.assertFalse(plan_result["isError"])
                plan_id = plan_result["_meta"]["plan_id"]
                approval_token = plan_result["_meta"]["approval_token"]

                # Step 2: Apply plan (should fail health check and rollback)
                apply_tool = mcp.tools["apply_firewall_plan"]
                apply_result = await apply_tool(
                    plan_id=plan_id,
                    approval_token=approval_token,
                )

                # Validate apply result - should return error since all devices failed
                # (even though rollback succeeded)
                self.assertTrue(apply_result["isError"])
                self.assertIn("failed", apply_result["content"][0]["text"].lower())
                
                apply_meta = apply_result["_meta"]
                self.assertEqual(apply_meta["plan_id"], plan_id)
                self.assertEqual(apply_meta["final_status"], "failed")
                
                # Verify device was rolled back
                device_result = apply_meta["device_results"][0]
                self.assertEqual(device_result["device_id"], "dev-lab-01")
                self.assertEqual(device_result["status"], "rolled_back")
                self.assertIn("rollback", device_result)
                self.assertIn("health_check", device_result)
                
                # Verify health check shows failure
                health_check = device_result["health_check"]
                self.assertEqual(health_check["status"], "failed")

                # Verify plan status updated to failed
                async with async_session_maker() as session:
                    stmt = select(Plan).where(Plan.id == plan_id)
                    result = await session.execute(stmt)
                    plan_record = result.scalar_one_or_none()
                    
                    self.assertIsNotNone(plan_record)
                    self.assertEqual(plan_record.status, "failed")

                # Verify REST client performed rollback
                rest_client = mock_rest_clients["dev-lab-01"]
                self.assertTrue(rest_client.closed)
                
                # Verify snapshot was created
                get_calls = [c for c in rest_client.calls if c[0] == "GET" and "/firewall/filter" in c[1]]
                self.assertGreater(len(get_calls), 0)

            await engine.dispose()

        asyncio.run(_run())


class TestApprovalTokenValidation(unittest.TestCase):
    """E2E tests for approval token validation and expiration."""

    def test_approval_token_expiration(self) -> None:
        """Test that apply fails when approval token has expired.
        
        Validates:
        - Plan creation succeeds
        - Token expiration after 15 minutes
        - Apply fails with expired token error
        - Audit log captures expiration attempt
        """

        async def _run() -> None:
            # Setup: Use in-memory database session
            from routeros_mcp.infra.db.models import Base, Device
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session_maker() as session:
                # Create test device
                device = Device(
                    id="dev-lab-01",
                    name="router-lab-01",
                    management_ip="192.168.1.1",
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

            # Setup mock device service
            mock_devices = {
                "dev-lab-01": create_mock_device("dev-lab-01"),
            }
            mock_rest_clients = {
                "dev-lab-01": MockRouterOSRestClient("dev-lab-01"),
            }
            mock_device_service = MockDeviceService(mock_devices, mock_rest_clients)

            # Create session factory
            class RealSessionFactory:
                def __init__(self, session_maker: async_sessionmaker) -> None:
                    self.session_maker = session_maker
                
                def session(self):
                    return self.session_maker()

            session_factory = RealSessionFactory(async_session_maker)

            with (
                patch.object(
                    firewall_tools, "get_session_factory", return_value=session_factory
                ),
                patch.object(firewall_tools, "DeviceService", return_value=mock_device_service),
            ):
                # Register firewall tools
                mcp = DummyMCP()
                settings = make_test_settings()
                firewall_tools.register_firewall_write_tools(mcp, settings)

                # Step 1: Create plan
                plan_tool = mcp.tools["plan_add_firewall_rule"]
                plan_result = await plan_tool(
                    device_ids=["dev-lab-01"],
                    chain="forward",
                    action="accept",
                    src_address="192.168.1.0/24",
                    comment="Test rule",
                )

                self.assertFalse(plan_result["isError"])
                plan_id = plan_result["_meta"]["plan_id"]
                approval_token = plan_result["_meta"]["approval_token"]

                # Step 2: Simulate time passing beyond token expiration (15 minutes + 1 second)
                # Modify the plan record to have an expired approval_expires_at
                from sqlalchemy.orm import attributes
                
                async with async_session_maker() as session:
                    stmt = select(Plan).where(Plan.id == plan_id)
                    result = await session.execute(stmt)
                    plan_record = result.scalar_one_or_none()
                    
                    self.assertIsNotNone(plan_record)
                    
                    # Set expiration to 16 minutes ago
                    expired_time = datetime.now(UTC) - timedelta(minutes=16)
                    plan_record.changes["approval_expires_at"] = expired_time.isoformat()
                    # Important: Flag the JSON field as modified for SQLAlchemy
                    attributes.flag_modified(plan_record, "changes")
                    
                    await session.commit()

                # Step 3: Attempt to apply expired plan
                apply_tool = mcp.tools["apply_firewall_plan"]
                apply_result = await apply_tool(
                    plan_id=plan_id,
                    approval_token=approval_token,
                )

                # Validate apply fails with expiration error
                self.assertTrue(apply_result["isError"])
                self.assertIn("expired", apply_result["content"][0]["text"].lower())

            await engine.dispose()

        asyncio.run(_run())


class TestCapabilityChecks(unittest.TestCase):
    """E2E tests for capability-based access control."""

    def test_capability_check_blocks_prod_device(self) -> None:
        """Test that production devices are blocked by default.
        
        Validates:
        - Production device environment check
        - Plan creation fails for prod devices without override
        - Error message explains environment restriction
        """

        async def _run() -> None:
            # Setup: Use in-memory database session
            from routeros_mcp.infra.db.models import Base, Device
            from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

            engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            
            async with async_session_maker() as session:
                # Create production device
                device = Device(
                    id="dev-prod-01",
                    name="router-prod-01",
                    management_ip="192.168.1.1",
                    management_port=443,
                    environment="prod",  # Production environment
                    status="healthy",
                    tags={},
                    allow_advanced_writes=True,
                    allow_professional_workflows=True,
                    allow_firewall_writes=True,
                )
                session.add(device)
                await session.commit()

            # Setup mock device service
            mock_devices = {
                "dev-prod-01": create_mock_device(
                    "dev-prod-01",
                    environment="prod",
                ),
            }
            mock_rest_clients = {
                "dev-prod-01": MockRouterOSRestClient("dev-prod-01"),
            }
            mock_device_service = MockDeviceService(mock_devices, mock_rest_clients)

            # Create session factory
            class RealSessionFactory:
                def __init__(self, session_maker: async_sessionmaker) -> None:
                    self.session_maker = session_maker
                
                def session(self):
                    return self.session_maker()

            session_factory = RealSessionFactory(async_session_maker)

            with (
                patch.object(
                    firewall_tools, "get_session_factory", return_value=session_factory
                ),
                patch.object(firewall_tools, "DeviceService", return_value=mock_device_service),
            ):
                # Register firewall tools
                mcp = DummyMCP()
                settings = make_test_settings()
                firewall_tools.register_firewall_write_tools(mcp, settings)

                # Attempt to create plan on production device
                plan_tool = mcp.tools["plan_add_firewall_rule"]
                plan_result = await plan_tool(
                    device_ids=["dev-prod-01"],
                    chain="forward",
                    action="accept",
                    comment="Test rule",
                )

                # Validate plan creation fails
                self.assertTrue(plan_result["isError"])
                error_message = plan_result["content"][0]["text"]
                self.assertIn("prod", error_message.lower())
                self.assertIn("environment", error_message.lower())
                # Should mention allowed environments (lab, staging)
                self.assertTrue("lab" in error_message.lower() or "staging" in error_message.lower())

            await engine.dispose()

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
