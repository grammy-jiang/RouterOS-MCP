from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from routeros_mcp.config import Settings
from routeros_mcp.infra.db.models import AuditEvent, Base
from routeros_mcp.mcp_resources import audit as audit_resources

from tests.unit.mcp_tools_test_utils import DummyMCP


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    class Factory:
        @asynccontextmanager
        async def session(self):
            async with maker() as session:
                yield session
                await session.commit()

    factory = Factory()
    yield factory
    await engine.dispose()


@pytest.fixture
def settings() -> Settings:
    return Settings(environment="lab")


@pytest.fixture
async def seed_audit_events(session_factory):
    async with session_factory.session() as session:
        now = datetime.now(UTC)
        session.add(
            AuditEvent(
                id=str(uuid.uuid4()),
                timestamp=now,
                user_sub="user-123",
                user_email="user1@example.com",
                user_role="admin",
                device_id="dev-7",
                environment="lab",
                action="READ_SENSITIVE",
                tool_name="system/get-overview",
                tool_tier="fundamental",
                plan_id=None,
                job_id=None,
                result="SUCCESS",
                meta={
                    "summary": "overview fetched",
                    "ip_address": "127.0.0.1",
                    "user_agent": "pytest",
                    "source": "seed",
                },
                error_message=None,
            )
        )
        session.add(
            AuditEvent(
                id=str(uuid.uuid4()),
                timestamp=now,
                user_sub="user-999",
                user_email="user999@example.com",
                user_role="admin",
                device_id="dev-8",
                environment="lab",
                action="WRITE",
                tool_name="config/apply-plan",
                tool_tier="advanced",
                plan_id="plan-1",
                job_id="job-1",
                result="FAILURE",
                meta={
                    "summary": "apply plan failed",
                    "failure_reason": "timeout",
                    "ip_address": "127.0.0.1",
                    "user_agent": "pytest",
                    "source": "seed",
                },
                error_message="timeout",
            )
        )


@pytest.fixture
async def mcp_resources(session_factory, settings, seed_audit_events):
    mcp = DummyMCP()
    audit_resources.register_audit_resources(mcp, session_factory, settings)
    return mcp


@pytest.mark.asyncio
async def test_audit_recent_events(mcp_resources):
    result = await mcp_resources.resources["audit://events/recent/{limit}"]()
    payload = json.loads(result)
    assert payload["count"] == 2
    assert payload["events"][0]["id"]
    assert payload["events"][0]["result"]


@pytest.mark.asyncio
async def test_audit_by_user_and_device_and_tool(mcp_resources):
    by_user = await mcp_resources.resources["audit://events/by-user/{user_sub}"](
        user_sub="user-123", limit=2
    )
    payload_user = json.loads(by_user)
    assert payload_user["user_sub"] == "user-123"
    assert payload_user["count"] == 1

    by_device = await mcp_resources.resources["audit://events/by-device/{device_id}"](
        device_id="dev-7"
    )
    payload_device = json.loads(by_device)
    assert payload_device["device_id"] == "dev-7"
    assert payload_device["events"][0]["tool_name"] == "system/get-overview"

    by_tool = await mcp_resources.resources["audit://events/by-tool/{tool_name}"](
        tool_name="config/apply-plan"
    )
    payload_tool = json.loads(by_tool)
    assert payload_tool["tool_name"] == "config/apply-plan"
    assert payload_tool["count"] == 1
