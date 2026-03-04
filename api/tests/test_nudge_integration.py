from __future__ import annotations

import json
from types import SimpleNamespace
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.id_utils import generate_project_id
from app.models import (
    Base,
    FlowUserProfile,
    Notification,
    NotificationRule,
    NotificationRuleState,
    Project,
    ProjectMembership,
)
from app.worker.outbox_worker import _handle_read_receipt
from app.tools.scheduler_tools import schedule_nudge

# Helper to create DB
_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _test_session_factory() as session:
        yield session
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_schedule_nudge_creates_rule(db_session: AsyncSession) -> None:
    """schedule_nudge tool creates a NotificationRule and NotificationRuleState."""
    project_id = generate_project_id()
    db_session.add(Project(id=project_id, display_name="Test Project"))
    membership = ProjectMembership(
        project_id=project_id, user_id="u_test", status="active"
    )
    db_session.add(membership)
    db_session.add(FlowUserProfile(user_id="u_test", email_raw="test@example.com"))
    await db_session.commit()

    import app.tools.scheduler_tools as scheduler_tools_module

    old_factory = scheduler_tools_module.async_session_factory
    scheduler_tools_module.async_session_factory = _test_session_factory

    try:
        await schedule_nudge.ainvoke(
            {
                "membership_id": membership.id,
                "topic": "Morning Reflection",
                "time": "08:00",
            }
        )
    finally:
        scheduler_tools_module.async_session_factory = old_factory

    # Verify NotificationRule created
    rule = (await db_session.execute(select(NotificationRule))).scalar_one()
    config = json.loads(rule.config_json)
    assert config["topic"] == "Morning Reflection"
    assert config["time"] == "08:00"
    assert rule.is_active is True

    # Verify NotificationRuleState created
    state = (await db_session.execute(select(NotificationRuleState))).scalar_one()
    assert state.rule_id == rule.id
    assert state.next_due_at_utc is not None


@pytest.mark.asyncio
async def test_read_receipt_handler(db_session: AsyncSession) -> None:
    """_handle_read_receipt sends a dismiss push notification."""
    project_id = generate_project_id()
    db_session.add(Project(id=project_id, display_name="Test Project"))
    membership = ProjectMembership(
        project_id=project_id, user_id="u_test", status="active"
    )
    db_session.add(membership)
    db_session.add(FlowUserProfile(user_id="u_test", email_raw="test@example.com"))
    await db_session.commit()

    notification = Notification(
        membership_id=membership.id,
        title="Test",
        body="Test body",
        payload_json="{}",
    )
    db_session.add(notification)
    await db_session.flush()

    read_event = SimpleNamespace(
        project_id=project_id,
        membership_id=membership.id,
        payload_json=json.dumps(
            {"notification_id": notification.id, "project_id": project_id}
        ),
    )

    with patch(
        "app.worker.outbox_worker._send_push_notifications", new_callable=AsyncMock
    ) as mock_push_receipt:
        await _handle_read_receipt(db_session, read_event)

        mock_push_receipt.assert_called_once()
        _, kwargs = mock_push_receipt.call_args
        assert kwargs["data"]["action"] == "dismiss"
        assert kwargs["data"]["notification_id"] == notification.id
