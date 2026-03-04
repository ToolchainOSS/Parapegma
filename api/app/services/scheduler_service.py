"""Scheduler service — logic for managing nudge schedules and outbox events."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    NotificationRule,
    NotificationRuleState,
    NudgeSchedule,
    ProjectMembership,
)
from app.services.notification_engine import compute_next_due_utc, get_user_timezone
from app.services.outbox_service import enqueue_outbox_event, next_run_at


async def list_active_schedules(
    db: AsyncSession, membership_id: int
) -> list[NudgeSchedule]:
    """List all active nudge schedules for a membership."""
    result = await db.execute(
        select(NudgeSchedule).where(
            NudgeSchedule.membership_id == membership_id, NudgeSchedule.is_active
        )
    )
    return list(result.scalars().all())


async def create_nudge_schedule(
    db: AsyncSession, membership_id: int, topic: str, cron_rule: str
) -> NudgeSchedule:
    """Create a new daily nudge schedule, a notification rule, and enqueue the first event."""
    # Check membership exists
    mem_result = await db.execute(
        select(ProjectMembership).where(ProjectMembership.id == membership_id)
    )
    membership = mem_result.scalar_one_or_none()
    if not membership:
        raise ValueError(f"Membership {membership_id} not found.")

    # Create legacy schedule (for backward compat)
    schedule = NudgeSchedule(
        membership_id=membership_id, topic=topic, cron_rule=cron_rule, is_active=True
    )
    db.add(schedule)
    await db.flush()

    # Create notification rule + state
    rule = NotificationRule(
        membership_id=membership_id,
        kind="daily_local_time",
        config_json=json.dumps({"topic": topic, "time": cron_rule}),
        tz_policy="floating_user_tz",
        is_active=True,
    )
    db.add(rule)
    await db.flush()

    # Compute next due time using user's timezone
    user_tz = await get_user_timezone(db, membership_id)
    next_due = compute_next_due_utc(rule, user_tz)

    state = NotificationRuleState(
        rule_id=rule.id,
        next_due_at_utc=next_due,
    )
    db.add(state)

    # Also enqueue legacy outbox event for backward compat
    run_at = next_run_at(cron_rule, datetime.now(UTC))
    dedupe_key = f"nudge:{schedule.id}:{run_at.date().isoformat()}"

    await enqueue_outbox_event(
        db,
        project_id=membership.project_id,
        membership_id=membership.id,
        event_type="scheduled_nudge",
        payload={
            "schedule_id": schedule.id,
            "topic": topic,
            "project_id": membership.project_id,
        },
        dedupe_key=dedupe_key,
        available_at=run_at,
    )

    return schedule


async def deactivate_schedule(db: AsyncSession, schedule_id: int) -> bool:
    """Deactivate a nudge schedule. Returns True if found and deactivated."""
    result = await db.execute(
        select(NudgeSchedule).where(NudgeSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if not schedule:
        return False

    schedule.is_active = False

    # Also deactivate matching notification rules
    rules_result = await db.execute(
        select(NotificationRule).where(
            NotificationRule.membership_id == schedule.membership_id,
            NotificationRule.kind == "daily_local_time",
            NotificationRule.is_active.is_(True),
        )
    )
    for rule in rules_result.scalars().all():
        config_data = json.loads(rule.config_json)
        if config_data.get("topic") == schedule.topic:
            rule.is_active = False

    return True
