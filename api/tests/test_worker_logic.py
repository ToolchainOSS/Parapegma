from __future__ import annotations

import json
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base
from app.worker.outbox_worker import _handle_scheduled_nudge

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
async def test_handle_scheduled_nudge_is_noop(db_session: AsyncSession) -> None:
    """_handle_scheduled_nudge is a legacy no-op stub."""
    event = SimpleNamespace(
        project_id="p_test",
        membership_id=1,
        payload_json=json.dumps({"topic": "Test Topic"}),
    )
    # Should return without error
    await _handle_scheduled_nudge(db_session, event)
