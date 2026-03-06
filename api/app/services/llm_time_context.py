"""Centralized localized-time context for all product LLM prompts.

Provides a dict with timezone, current_date, current_time, and current_datetime
that can be merged into prompt template arguments.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_default_timezone
from app.services.notification_engine import get_user_timezone


def _resolve_tz(tz_name: str | None) -> str:
    """Return valid IANA timezone: user tz → app default."""
    if tz_name:
        try:
            ZoneInfo(tz_name)
            return tz_name
        except (ZoneInfoNotFoundError, KeyError):
            pass
    return get_default_timezone()


def get_llm_time_context(
    tz_name: str | None,
    now_utc: datetime | None = None,
) -> dict[str, str]:
    """Build localized time context dict from an already-known timezone name.

    Use this in the worker path where membership lookup is already done.
    """
    effective_tz = _resolve_tz(tz_name)
    if now_utc is None:
        now_utc = datetime.now(UTC)
    local_now = now_utc.astimezone(ZoneInfo(effective_tz))
    return {
        "timezone": effective_tz,
        "current_date": local_now.strftime("%Y-%m-%d"),
        "current_time": local_now.strftime("%H:%M"),
        "current_datetime": local_now.strftime("%Y-%m-%d %H:%M"),
    }


async def get_llm_time_context_for_membership(
    db: AsyncSession,
    membership_id: int,
    now_utc: datetime | None = None,
) -> dict[str, str]:
    """Build localized time context by resolving timezone from membership → profile."""
    user_tz = await get_user_timezone(db, membership_id)
    return get_llm_time_context(user_tz, now_utc)
