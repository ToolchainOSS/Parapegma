from __future__ import annotations

import json
from typing import Annotated

from langchain_core.tools import tool

from app.db import async_session_factory
from app.models import NotificationRule, NotificationRuleState
from app.services.notification_engine import compute_next_due_utc, get_user_timezone
from sqlalchemy import select


@tool
async def list_schedules(
    membership_id: Annotated[
        int, "The ID of the project membership to list schedules for"
    ],
) -> str:
    """List all active notification rules for a user."""
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
) -> str:
    """Deactivate a notification rule."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(NotificationRule).where(NotificationRule.id == schedule_id)
        )
        rule = result.scalar_one_or_none()
        if not rule:
            return "Schedule not found."
        rule.is_active = False
        await db.commit()
        return f"Schedule {schedule_id} deactivated."
