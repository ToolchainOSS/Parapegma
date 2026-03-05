from __future__ import annotations

import json
import logging
from typing import Annotated

from langchain_core.tools import BaseTool, tool

from app.db import async_session_factory
from app.models import NotificationRule, NotificationRuleState
from app.services.notification_engine import compute_next_due_utc, get_user_timezone
from sqlalchemy import select

logger = logging.getLogger(__name__)


@tool
async def list_schedules(
    membership_id: Annotated[
        int, "The ID of the project membership to list schedules for"
    ],
) -> str:
    """List all active notification rules for a membership (internal/admin use)."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(NotificationRule).where(
                NotificationRule.membership_id == membership_id,
                NotificationRule.is_active.is_(True),
            )
        )
        rules = result.scalars().all()
        if not rules:
            return "No active schedules found."

        lines = []
        for r in rules:
            config = json.loads(r.config_json)
            topic = config.get("topic", "?")
            time_str = config.get("time", "?")
            lines.append(f"ID: {r.id}, Topic: {topic}, Time: {time_str}")
        return "\n".join(lines)


def make_scoped_list_schedules_tool(membership_id: int) -> BaseTool:
    """Create a list_schedules tool scoped to a specific membership.

    The returned tool accepts NO arguments — the membership_id is captured
    from the runtime context so the LLM cannot supply a foreign id.
    """

    @tool("list_schedules")
    async def _scoped_list_schedules() -> str:
        """List active notification schedules for this project only.

        Takes no arguments — the project scope is determined automatically.
        """
        return await list_schedules.ainvoke({"membership_id": membership_id})

    return _scoped_list_schedules


@tool
async def schedule_nudge(
    membership_id: Annotated[int, "The ID of the project membership"],
    topic: Annotated[str, "The topic or prompt for the daily nudge"],
    time: Annotated[str, "The time of day in HH:MM format (24h)"],
) -> str:
    """Schedule a new daily nudge via notification rule."""
    async with async_session_factory() as db:
        try:
            rule = NotificationRule(
                membership_id=membership_id,
                kind="daily_local_time",
                config_json=json.dumps({"topic": topic, "time": time}),
                tz_policy="floating_user_tz",
                is_active=True,
            )
            db.add(rule)
            await db.flush()

            user_tz = await get_user_timezone(db, membership_id)
            next_due = compute_next_due_utc(rule, user_tz)

            state = NotificationRuleState(
                rule_id=rule.id,
                next_due_at_utc=next_due,
            )
            db.add(state)
            await db.commit()
            return f"Scheduled nudge ID {rule.id} for {time} daily."
        except ValueError as e:
            return f"Error: {e}"


@tool
async def delete_schedule(
    schedule_id: Annotated[int, "The ID of the notification rule to deactivate"],
    membership_id: Annotated[
        int, "The ID of the project membership that owns the rule"
    ],
) -> str:
    """Deactivate a notification rule. Only rules belonging to the given membership can be deactivated."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(NotificationRule).where(
                NotificationRule.id == schedule_id,
                NotificationRule.membership_id == membership_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            logger.warning(
                "delete_schedule: rule_id=%s not found for membership_id=%s",
                schedule_id,
                membership_id,
            )
            return "Schedule not found."
        rule.is_active = False
        await db.commit()
        return f"Schedule {schedule_id} deactivated."
