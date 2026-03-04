"""Tests for the unified notification API and webpush endpoints."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.id_utils import generate_project_id
from app.models import (
    Base,
    FlowUserProfile,
    Notification,
    NotificationDelivery,
    Project,
    ProjectInvite,
    ProjectMembership,
    PushSubscription,
)
from h4ckath0n.auth.models import Base as H4ckath0nBase
from h4ckath0n.realtime import AuthContext

_test_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with _test_session_factory() as session:
        yield session


def _make_fake_user(
    user_id: str = "u_testuser_000000000000000000", role: str = "user"
) -> MagicMock:
    user = MagicMock()
    user.id = user_id
    user.role = role
    user.email = "test@example.com"
    return user


def _override_require_user(
    user_id: str = "u_testuser_000000000000000000", role: str = "user"
) -> Any:
    fake = _make_fake_user(user_id, role=role)

    async def _dep() -> Any:
        return fake

    return _dep


def _override_auth_context(
    user_id: str = "u_testuser_000000000000000000", device_id: str = "d_test"
) -> Any:
    async def _dep() -> AuthContext:
        return AuthContext(user_id=user_id, device_id=device_id)

    return _dep


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    from app.main import app
    from app.db import get_db
    from app.routes import _require_auth_context
    from h4ckath0n.auth.dependencies import _get_current_user

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(H4ckath0nBase.metadata.create_all)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[_get_current_user] = _override_require_user()
    app.dependency_overrides[_require_auth_context] = _override_auth_context()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(H4ckath0nBase.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded_project(client: AsyncClient) -> dict[str, Any]:
    project_id = generate_project_id()
    invite_code = "test-invite"
    code_hash = hashlib.sha256(invite_code.encode()).hexdigest()

    async with _test_session_factory() as db:
        project = Project(id=project_id, display_name="Test Project")
        db.add(project)
        invite = ProjectInvite(
            project_id=project_id,
            invite_code_hash=code_hash,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        db.add(invite)
        db.add(
            FlowUserProfile(
                user_id="u_testuser_000000000000000000",
                email_raw="test@example.com",
                timezone="America/New_York",
            )
        )
        await db.commit()

    await client.post(
        f"/p/{project_id}/activate/claim", json={"invite_code": invite_code}
    )

    return {"project_id": project_id, "client": client}


# ---------------------------------------------------------------------------
# Unified notification endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unified_notifications_lifecycle(seeded_project: dict[str, Any]) -> None:
    """GET /notifications returns items with project_id and project_name in one response."""
    client = seeded_project["client"]
    project_id = seeded_project["project_id"]

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()

        notif1 = Notification(
            membership_id=membership.id,
            title="Nudge 1",
            body="First nudge body.",
            payload_json="{}",
        )
        notif2 = Notification(
            membership_id=membership.id,
            title="Nudge 2",
            body="Second nudge body.",
            payload_json="{}",
        )
        db.add(notif1)
        db.add(notif2)
        await db.commit()
        notif1_id = notif1.id
        notif2_id = notif2.id

    # List unified notifications
    resp = await client.get("/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["notifications"]) == 2
    for n in data["notifications"]:
        assert n["project_id"] == project_id
        assert n["project_display_name"] == "Test Project"
        assert "membership_id" in n
        assert "payload_json" in n

    # Unread count
    resp = await client.get("/notifications/unread-count")
    assert resp.status_code == 200
    assert resp.json()["count"] == 2

    # Mark one read
    resp = await client.post(f"/notifications/{notif1_id}/read")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify unread count decreased
    resp = await client.get("/notifications/unread-count")
    assert resp.json()["count"] == 1

    # Verify the read status in unified list
    resp = await client.get("/notifications")
    notifications_data = {n["id"]: n for n in resp.json()["notifications"]}
    assert notifications_data[notif1_id]["read_at"] is not None
    assert notifications_data[notif2_id]["read_at"] is None


@pytest.mark.asyncio
async def test_unread_count_with_project_filter(
    seeded_project: dict[str, Any],
) -> None:
    """Unread count is correct with and without project_id filter."""
    client = seeded_project["client"]
    project_id = seeded_project["project_id"]

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()

        for i in range(3):
            db.add(
                Notification(
                    membership_id=membership.id,
                    title=f"Notif {i}",
                    body=f"Body {i}",
                    payload_json="{}",
                )
            )
        await db.commit()

    # Unread count without filter
    resp = await client.get("/notifications/unread-count")
    assert resp.json()["count"] == 3

    # Unread count with project filter
    resp = await client.get(
        "/notifications/unread-count", params={"project_id": project_id}
    )
    assert resp.json()["count"] == 3

    # Unread count with non-existent project filter
    resp = await client.get(
        "/notifications/unread-count", params={"project_id": "p_nonexistent_0000000"}
    )
    assert resp.json()["count"] == 0


@pytest.mark.asyncio
async def test_mark_read_enqueues_exactly_one_push_dismiss(
    seeded_project: dict[str, Any],
) -> None:
    """POST /notifications/{id}/read creates exactly ONE push_dismiss delivery."""
    client = seeded_project["client"]
    project_id = seeded_project["project_id"]

    async with _test_session_factory() as db:
        membership_result = await db.execute(
            select(ProjectMembership).where(ProjectMembership.project_id == project_id)
        )
        membership = membership_result.scalar_one()

        # Create multiple push subscriptions for this user
        for i in range(3):
            sub = PushSubscription(
                user_id="u_testuser_000000000000000000",
                endpoint=f"https://push.example.com/sub/{i}",
                p256dh=f"testkey{i}",
                auth=f"testauth{i}",
                user_agent="pytest",
            )
            db.add(sub)

        notif = Notification(
            membership_id=membership.id,
            title="Test",
            body="Body",
            payload_json="{}",
        )
        db.add(notif)
        await db.commit()
        notif_id = notif.id

    # Mark read
    resp = await client.post(f"/notifications/{notif_id}/read")
    assert resp.status_code == 200

    # Check exactly ONE delivery was created (not 3)
    async with _test_session_factory() as db:
        result = await db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.instance_id == notif_id,
                NotificationDelivery.channel == "push_dismiss",
            )
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1
        payload = json.loads(deliveries[0].payload_json)
        assert payload["data"]["action"] == "dismiss"
        assert payload["data"]["notification_id"] == notif_id
        assert deliveries[0].user_id == "u_testuser_000000000000000000"


@pytest.mark.asyncio
async def test_unified_notification_read_not_found(
    seeded_project: dict[str, Any],
) -> None:
    """Reading a non-existent notification returns 404."""
    client = seeded_project["client"]
    resp = await client.post("/notifications/999999/read")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Web Push endpoints (user-scoped)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webpush_vapid_key(client: AsyncClient) -> None:
    """GET /notifications/webpush/vapid-public-key returns 503 when not configured."""
    resp = await client.get("/notifications/webpush/vapid-public-key")
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_webpush_subscribe_and_list(
    seeded_project: dict[str, Any],
) -> None:
    """POST /notifications/webpush/subscriptions creates ONE user-scoped subscription."""
    client = seeded_project["client"]

    resp = await client.post(
        "/notifications/webpush/subscriptions",
        json={
            "endpoint": "https://push.example.com/sub/test",
            "keys": {"p256dh": "testkey123", "auth": "testauth123"},
            "user_agent": "pytest-browser",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["subscription_id"] > 0

    # List subscriptions
    resp = await client.get("/notifications/webpush/subscriptions")
    assert resp.status_code == 200
    subs = resp.json()["subscriptions"]
    assert len(subs) == 1
    assert subs[0]["endpoint"] == "https://push.example.com/sub/test"
    # User-scoped: no membership_id in response
    assert "membership_id" not in subs[0]


@pytest.mark.asyncio
async def test_webpush_subscribe_upserts(
    seeded_project: dict[str, Any],
) -> None:
    """Re-subscribing with same endpoint upserts keys."""
    client = seeded_project["client"]

    body: dict[str, Any] = {
        "endpoint": "https://push.example.com/sub/upsert",
        "keys": {"p256dh": "key1", "auth": "auth1"},
    }
    resp1 = await client.post("/notifications/webpush/subscriptions", json=body)
    sub_id_1 = resp1.json()["subscription_id"]

    body["keys"] = {"p256dh": "key2", "auth": "auth2"}
    resp2 = await client.post("/notifications/webpush/subscriptions", json=body)
    sub_id_2 = resp2.json()["subscription_id"]

    assert sub_id_1 == sub_id_2  # same subscription updated

    # Only one subscription in DB
    resp = await client.get("/notifications/webpush/subscriptions")
    assert len(resp.json()["subscriptions"]) == 1


@pytest.mark.asyncio
async def test_webpush_unsubscribe(
    seeded_project: dict[str, Any],
) -> None:
    """DELETE /notifications/webpush/subscriptions/{id} revokes subscription."""
    client = seeded_project["client"]

    resp = await client.post(
        "/notifications/webpush/subscriptions",
        json={
            "endpoint": "https://push.example.com/sub/delete-test",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
    )
    sub_id = resp.json()["subscription_id"]

    resp = await client.request(
        "DELETE", f"/notifications/webpush/subscriptions/{sub_id}"
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # List should be empty
    resp = await client.get("/notifications/webpush/subscriptions")
    assert len(resp.json()["subscriptions"]) == 0


# ---------------------------------------------------------------------------
# Scheduler tools (via NotificationRule)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduler_tools(seeded_project: dict[str, Any]) -> None:
    """Scheduler tools work with NotificationRule directly."""
    import app.tools.scheduler_tools as scheduler_tools_module
    from app.tools.scheduler_tools import (
        schedule_nudge,
        list_schedules,
        delete_schedule,
    )

    old_factory = scheduler_tools_module.async_session_factory
    scheduler_tools_module.async_session_factory = _test_session_factory

    try:
        project_id = seeded_project["project_id"]
        async with _test_session_factory() as db:
            membership_result = await db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.project_id == project_id
                )
            )
            membership = membership_result.scalar_one()
            membership_id = membership.id

        # Schedule
        res = await schedule_nudge.ainvoke(
            {"membership_id": membership_id, "topic": "Test Nudge", "time": "09:00"}
        )
        assert "Scheduled nudge ID" in res

        # List
        res = await list_schedules.ainvoke({"membership_id": membership_id})
        assert "Test Nudge" in res
        assert "09:00" in res

        # Parse ID from list
        import re

        match = re.search(r"ID: (\d+)", res)
        rule_id = int(match.group(1))

        # Delete
        res = await delete_schedule.ainvoke({"schedule_id": rule_id})
        assert "deactivated" in res

        # List again
        res = await list_schedules.ainvoke({"membership_id": membership_id})
        assert "No active schedules found" in res

    finally:
        scheduler_tools_module.async_session_factory = old_factory
