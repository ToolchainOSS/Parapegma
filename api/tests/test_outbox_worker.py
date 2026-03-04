from __future__ import annotations
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Base,
    Conversation,
    Project,
    ProjectMembership,
)
from app.services.profile_service import save_user_profile
from app.schemas.patches import UserProfileData
from app.worker.outbox_worker import _claim_due_events, _process_event

_engine = create_async_engine("sqlite+aiosqlite://", echo=False)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with _session_factory() as session:
        yield session
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def seeded(db: AsyncSession) -> dict[str, int | str]:
    project = Project(id="p" + "a" * 31, display_name="Study")
    db.add(project)
    await db.flush()
    membership = ProjectMembership(
        project_id=project.id,
        user_id="u_seeded_00000000000000000000",
        status="active",
    )
    db.add(membership)
    await db.flush()
    db.add(Conversation(membership_id=membership.id))
    await save_user_profile(
        db,
        membership.id,
        UserProfileData(prompt_anchor="after coffee", preferred_time="08:00"),
    )
    await db.commit()
    return {"project_id": project.id, "membership_id": membership.id}


@pytest.mark.asyncio
async def test_claim_due_events_returns_empty(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """Legacy _claim_due_events always returns an empty list."""
    claimed = await _claim_due_events(worker_id="worker-1")
    assert claimed == []


@pytest.mark.asyncio
async def test_process_event_is_noop(
    db: AsyncSession, seeded: dict[str, int | str]
) -> None:
    """Legacy _process_event is a no-op stub."""
    from types import SimpleNamespace

    event = SimpleNamespace(id=1)
    await _process_event(event, worker_id="worker-1")


async def fake_generate(db, membership_id: int, topic: str) -> str:
    return f"Nudge: {topic}"
