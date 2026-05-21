"""Unified notification worker: rule polling → instance creation → delivery sending.

Single worker process — no legacy outbox events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import string
import uuid
from datetime import UTC, datetime, timedelta

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pywebpush import WebPushException, webpush
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from app import config
from app.db import async_session_factory
from app.id_utils import generate_server_msg_id
from app.logging_conf import LLMLoggingCallbackHandler, configure_logging
from app.models import (
    Conversation,
    DailyInterventionLog,
    Message,
    Notification,
    NotificationDelivery,
    NotificationRule,
    NotificationRuleState,
    Participation,
    ProjectMembership,
    PushSubscription,
    ScheduledTask,
)
from app.services.notification_engine import (
    claim_due_deliveries,
    claim_due_rules,
    compute_local_date_for_rule,
    get_user_timezone,
    recompute_rule_due_time,
)
from app.services.condition_filters import contains_condition_c_framing
from app.services.event_service import persist_event
from app.services.intervention_config import get_static_intervention
from app.services.prompt_context import get_prompt_context_for_membership
from app.services.profile_service import load_user_profile
from app.services.randomization import get_daily_condition
from app.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
FAILED_EVENT_POSTPONE_DAYS = 3650
LOCK_DURATION_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 10
MAX_CONDITION_C_REGEN_ATTEMPTS = 3
CONDITION_C_REGEN_INSTRUCTION = (
    "Your previous output contained forbidden conditional planning, commitment, "
    "or reward framing. Regenerate the nudge with NO if/then structure, NO "
    "commitment contract, NO promise, and NO reward language. One or two "
    "sentences, mentioning the user's anchor as the trigger and a single "
    "one-minute physical action."
)
CONDITION_C_SAFE_FALLBACK = (
    "When your next routine begins, take one minute to move your body — a short "
    "set of squats or a brisk walk in place."
)
PROMPT_GENERATOR_DEFAULT = "prompt_generator_system"
PROMPT_GENERATOR_BY_CONDITION = {
    "C": "prompt_generator_condition_c",
    "D": "prompt_generator_condition_d",
}


def _condition_to_source_tag(condition: str | None) -> str:
    """Map an experimental condition letter to the Message.condition_source tag."""
    if not condition:
        return "SYSTEM"
    return f"COND_{condition.upper()}"


def _randomization_salt() -> str | None:
    """Return the configured randomization salt, or None if unconfigured.

    The worker is permissive about a missing salt (it falls back to the
    generic prompt) so that an unconfigured environment still produces
    useful nudges instead of failing every fire.
    """
    salt = os.environ.get("FLOW_RANDOMIZATION_SALT")
    if salt and len(salt) >= 32:
        return salt
    return None


async def _resolve_condition_for_membership(
    db, membership_id: int
) -> tuple[str | None, Participation | None, int | None]:
    """Resolve today's experimental condition for a membership.

    Returns (condition, participation, study_day_index). Any of these may be
    None when the membership is not enrolled in the study or the
    randomization salt is not configured.
    """
    result = await db.execute(
        select(Participation)
        .where(Participation.membership_id == membership_id)
        .order_by(Participation.id.desc())
        .limit(1)
    )
    participation = result.scalar_one_or_none()
    if participation is None:
        return None, None, None

    salt = _randomization_salt()
    if salt is None:
        return None, participation, None

    today = datetime.now(UTC).date()
    study_day_index = (today - participation.study_start_date.date()).days
    condition = get_daily_condition(
        participation_id=participation.id,
        study_start_date=participation.study_start_date,
        current_date=today,
        salt=salt,
    )
    return condition, participation, study_day_index


async def _ensure_daily_intervention_log(
    db,
    participation: Participation,
    study_day_index: int,
    condition: str,
) -> None:
    """Make sure today's DailyInterventionLog exists, mirroring the engine path."""
    today = datetime.now(UTC).date()
    result = await db.execute(
        select(DailyInterventionLog).where(
            DailyInterventionLog.participation_id == participation.id,
            DailyInterventionLog.intervention_date == today,
        )
    )
    if result.scalar_one_or_none() is not None:
        return
    db.add(
        DailyInterventionLog(
            participation_id=participation.id,
            intervention_date=today,
            study_day_index=study_day_index,
            assigned_condition=condition,
            extracted_state={},
        )
    )
    await db.flush()


async def _llm_generate_nudge(
    prompt_name: str,
    prompt_ctx: dict[str, str],
    profile_json: str,
    topic: str,
    extra_instruction: str | None = None,
    daily_summary: str | None = None,
) -> str:
    """Invoke the LLM with the given prompt template. Raises on failure."""
    llm_key = config.get_openai_api_key()
    if not llm_key:
        raise RuntimeError("OpenAI API key not configured")

    system_text = load_prompt(prompt_name)
    system_text = string.Template(system_text).safe_substitute(prompt_ctx)
    if extra_instruction:
        system_text = f"{system_text}\n\nADDITIONAL INSTRUCTION:\n{extra_instruction}"

    human_parts = [f"Topic: {topic}", f"User profile: {profile_json}"]
    if daily_summary:
        human_parts.append(
            "Sterilized cross-day memory (clinical, no framing) — use for "
            f"continuity but do not imitate its phrasing:\n{daily_summary}"
        )
    human_parts.append("Generate the nudge.")
    messages = [
        SystemMessage(content=system_text),
        HumanMessage(content="\n".join(human_parts)),
    ]
    llm = ChatOpenAI(
        model=config.get_llm_model(),
        api_key=llm_key,
        callbacks=[LLMLoggingCallbackHandler()],
    )
    res = await asyncio.wait_for(llm.ainvoke(messages), timeout=15)
    return str(res.content).strip()


async def _generate_condition_nudge(
    db, membership_id: int, topic: str
) -> tuple[str, str | None]:
    """Generate a nudge respecting the active experimental condition.

    Returns ``(content, condition_source_tag)`` where ``condition_source_tag``
    is one of ``"COND_A"``, ``"COND_B"``, ``"COND_C"``, ``"COND_D"`` or
    ``"SYSTEM"`` for unenrolled / fallback cases.
    """
    condition, participation, study_day_index = await _resolve_condition_for_membership(
        db, membership_id
    )

    # Conditions A and B: bypass the LLM entirely with a static template.
    if (
        condition in {"A", "B"}
        and participation is not None
        and study_day_index is not None
    ):
        await _ensure_daily_intervention_log(
            db, participation, study_day_index, condition
        )
        try:
            content = get_static_intervention(
                condition, participation.id, study_day_index
            )
        except Exception as exc:
            logger.error("Static intervention lookup failed for %s: %s", condition, exc)
            content = f"{topic}"
        return content, _condition_to_source_tag(condition)

    # All LLM paths share the same prompt context + profile shape.
    profile = await load_user_profile(db, membership_id)
    prompt_ctx = await get_prompt_context_for_membership(db, membership_id)
    profile_data = profile.model_dump()
    profile_data.pop("preferred_time", None)
    profile_json = json.dumps(
        {k: v for k, v in profile_data.items() if v is not None}, default=str
    )

    prompt_name = (
        PROMPT_GENERATOR_BY_CONDITION.get(condition) if condition else None
    ) or PROMPT_GENERATOR_DEFAULT

    # For Conditions C and D, fetch the sterilized cross-day memory so the
    # nudge generator has multi-day context without seeing raw assistant
    # framing from prior days. This is the "semantic firewall" — both
    # conditions read the same clinical summary.
    daily_summary: str | None = None
    if condition in {"C", "D"} and participation is not None:
        try:
            from app.services.eod_summarizer import (
                ensure_summaries_up_to,
                load_latest_summary,
            )

            yesterday = datetime.now(UTC).date() - timedelta(days=1)
            await ensure_summaries_up_to(db, participation, yesterday)
            daily_summary = await load_latest_summary(db, participation.id)
        except Exception:
            logger.exception("Failed to ensure/load EOD summary for nudge generation")

    # Condition D and the default path: single LLM call, return as-is.
    if condition != "C":
        if (
            condition == "D"
            and participation is not None
            and study_day_index is not None
        ):
            await _ensure_daily_intervention_log(
                db, participation, study_day_index, condition
            )
        try:
            content = await _llm_generate_nudge(
                prompt_name,
                prompt_ctx,
                profile_json,
                topic,
                daily_summary=daily_summary,
            )
        except Exception as exc:
            logger.error("LLM nudge generation failed (%s): %s", prompt_name, exc)
            content = f"{topic} (Generation failed)"
        return content, _condition_to_source_tag(condition)

    # Condition C: generate, regex-filter, regenerate up to N times, then
    # fall back to a safe neutral string. This protects against the LLM
    # implicitly drifting toward Condition D's framing.
    if participation is not None and study_day_index is not None:
        await _ensure_daily_intervention_log(
            db, participation, study_day_index, condition
        )
    extra: str | None = None
    last_content: str | None = None
    for attempt in range(MAX_CONDITION_C_REGEN_ATTEMPTS):
        try:
            candidate = await _llm_generate_nudge(
                prompt_name,
                prompt_ctx,
                profile_json,
                topic,
                extra_instruction=extra,
                daily_summary=daily_summary,
            )
        except Exception as exc:
            logger.error("Condition C LLM call failed on attempt %d: %s", attempt, exc)
            break
        last_content = candidate
        if not contains_condition_c_framing(candidate):
            return candidate, _condition_to_source_tag(condition)
        logger.warning(
            "Condition C output contained framing on attempt %d; regenerating",
            attempt,
        )
        extra = CONDITION_C_REGEN_INSTRUCTION

    logger.error(
        "Condition C output still contained framing after %d attempts; using safe fallback",
        MAX_CONDITION_C_REGEN_ATTEMPTS,
    )
    _ = last_content  # kept for log context only
    return CONDITION_C_SAFE_FALLBACK, _condition_to_source_tag(condition)


async def _generate_custom_prompt(db, membership_id: int, topic: str) -> str:
    """Backwards-compatible wrapper used by older call sites and tests.

    Prefer :func:`_generate_condition_nudge` when you need the condition tag
    alongside the content.
    """
    content, _tag = await _generate_condition_nudge(db, membership_id, topic)
    return content


def _make_worker_id() -> str:
    base = config.get_worker_id()
    return f"{base}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _push_enabled() -> bool:
    return bool(config.get_vapid_private_key() and config.get_vapid_public_key())


def _to_feedback_poll_actions(actions: list[dict] | None) -> list[dict[str, str]]:
    valid_actions: list[dict[str, str]] = []
    for action in actions or []:
        if not isinstance(action, dict):
            continue
        action_id = str(action.get("action") or "").strip()
        action_title = str(action.get("title") or "").strip()
        if action_id and action_title:
            valid_actions.append({"id": action_id, "title": action_title})
    return valid_actions


async def _send_push_notifications(
    db,
    user_id: str,
    title: str,
    body: str,
    url: str,
    data: dict | None = None,
    actions: list[dict] | None = None,
) -> tuple[int, int]:
    """Send Web Push to all active subscriptions for a user.

    Returns (success_count, total_count).
    """
    if not _push_enabled():
        return 0, 0

    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id,
            PushSubscription.revoked_at.is_(None),
        )
    )
    subscriptions = result.scalars().all()
    if not subscriptions:
        return 0, 0

    payload_dict: dict[str, object] = {
        "title": title,
        "body": body,
        "url": url,
        "data": data or {},
    }
    if actions:
        valid_actions: list[dict[str, str]] = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            action_id = action.get("action")
            action_title = action.get("title")
            if isinstance(action_id, str) and isinstance(action_title, str):
                valid_actions.append({"action": action_id, "title": action_title})
        if valid_actions:
            payload_dict["actions"] = valid_actions
    payload = json.dumps(payload_dict)

    vapid_private_key = config.get_vapid_private_key()
    vapid_claims = {"sub": config.get_vapid_sub()}

    success_count = 0

    async def _send_single(sub: PushSubscription) -> bool:
        try:
            await asyncio.wait_for(
                asyncio.to_thread(
                    webpush,
                    subscription_info={
                        "endpoint": sub.endpoint,
                        "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
                    },
                    data=payload,
                    vapid_private_key=vapid_private_key,
                    vapid_claims=vapid_claims,
                ),
                timeout=PUSH_TIMEOUT_SECONDS,
            )
            sub.last_success_at = datetime.now(UTC)
            sub.consecutive_gone_410_count = 0
            return True
        except asyncio.TimeoutError:
            sub.last_failure_at = datetime.now(UTC)
            sub.consecutive_gone_410_count = 0
            logger.warning("Push send timed out for subscription %s", sub.id)
            return False
        except WebPushException as exc:
            sub.last_failure_at = datetime.now(UTC)
            resp = getattr(exc, "response", None)
            try:
                status_code = resp.status_code if resp is not None else None
            except AttributeError:
                status_code = None
            if status_code == 404:
                # 404: revoke immediately
                sub.revoked_at = datetime.now(UTC)
                sub.consecutive_gone_410_count = 0
                logger.info("Revoking subscription %s: permanent error 404", sub.id)
            elif status_code == 410:
                # 410 Gone: increment counter, revoke only at threshold
                sub.consecutive_gone_410_count += 1
                threshold = config.get_push_gone_410_threshold()
                if sub.consecutive_gone_410_count >= threshold:
                    sub.revoked_at = datetime.now(UTC)
                    logger.info(
                        "Revoking subscription %s: %d consecutive 410s (threshold=%d)",
                        sub.id,
                        sub.consecutive_gone_410_count,
                        threshold,
                    )
                else:
                    logger.info(
                        "Subscription %s: 410 count %d/%d, not revoking yet",
                        sub.id,
                        sub.consecutive_gone_410_count,
                        threshold,
                    )
            else:
                sub.consecutive_gone_410_count = 0
                logger.warning("Push send failed for subscription %s: %s", sub.id, exc)
            return False

    results = await asyncio.gather(*[_send_single(sub) for sub in subscriptions])
    success_count = sum(1 for r in results if r)
    return success_count, len(subscriptions)


async def _evaluate_due_rules(worker_id: str) -> int:
    """Claim and evaluate due notification rules. Returns count processed."""
    processed = 0
    async with async_session_factory() as db:
        pairs = await claim_due_rules(db, worker_id)
        await db.commit()

    for rule, state in pairs:
        try:
            await _process_rule(rule.id, worker_id)
            processed += 1
        except Exception as exc:
            logger.error("Failed processing rule %s: %s", rule.id, exc)
    return processed


async def _process_rule(rule_id: int, worker_id: str) -> None:
    """Evaluate a single notification rule: create instance + delivery, advance state."""
    async with async_session_factory() as db:
        rule_result = await db.execute(
            select(NotificationRule).where(NotificationRule.id == rule_id)
        )
        rule = rule_result.scalar_one_or_none()
        state_result = await db.execute(
            select(NotificationRuleState).where(
                NotificationRuleState.rule_id == rule_id,
                NotificationRuleState.locked_by == worker_id,
            )
        )
        state = state_result.scalar_one_or_none()
        if not rule or not state:
            return

        if not rule.is_active:
            state.locked_by = None
            state.claimed_at = None
            state.locked_until = None
            state.next_due_at_utc = None
            await db.commit()
            return

        try:
            config_data = json.loads(rule.config_json)
            topic = config_data.get("topic", "Daily Nudge")
            user_tz = await get_user_timezone(db, rule.membership_id)

            # Compute local date for idempotency
            fire_utc = state.next_due_at_utc or datetime.now(UTC)
            local_date = compute_local_date_for_rule(rule, user_tz, fire_utc)
            dedupe_key = f"rule:{rule.id}:{local_date.isoformat()}"

            # Idempotency check — advance if already fired
            existing = await db.execute(
                select(Notification).where(Notification.dedupe_key == dedupe_key)
            )
            if existing.scalar_one_or_none():
                await recompute_rule_due_time(db, rule, state)
                await db.commit()
                return

            # Get or create conversation
            conversation_result = await db.execute(
                select(Conversation).where(
                    Conversation.membership_id == rule.membership_id
                )
            )
            conversation = conversation_result.scalar_one_or_none()
            if not conversation:
                conversation = Conversation(membership_id=rule.membership_id)
                db.add(conversation)
                await db.flush()

            # Determine project_id
            mem_result = await db.execute(
                select(ProjectMembership).where(
                    ProjectMembership.id == rule.membership_id
                )
            )
            membership = mem_result.scalar_one()
            project_id = membership.project_id

            # Generate content (condition-aware)
            content, condition_source = await _generate_condition_nudge(
                db, rule.membership_id, topic
            )

            # Resolve participation for traceability (tagging messages).
            participation_result = await db.execute(
                select(Participation)
                .where(Participation.membership_id == rule.membership_id)
                .order_by(Participation.id.desc())
                .limit(1)
            )
            participation = participation_result.scalar_one_or_none()

            # Persist Message (idempotent via client_msg_id = dedupe_key)
            server_msg_id = generate_server_msg_id()
            message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=content,
                server_msg_id=server_msg_id,
                client_msg_id=dedupe_key,
                condition_source=condition_source or "SYSTEM",
                participation_id=participation.id if participation else None,
            )
            db.add(message)
            await db.flush()
            await persist_event(
                db,
                conversation.id,
                "message.final",
                {
                    "message_id": message.id,
                    "server_msg_id": message.server_msg_id,
                    "role": "assistant",
                    "content": message.content,
                    "created_at": message.created_at.isoformat()
                    if message.created_at
                    else datetime.now(UTC).isoformat(),
                },
            )

            # Persist notification instance
            notification = Notification(
                membership_id=rule.membership_id,
                title=topic,
                body=content,
                payload_json=json.dumps(
                    {
                        "rule_id": rule.id,
                        "server_msg_id": server_msg_id,
                        "project_id": project_id,
                    }
                ),
                rule_id=rule.id,
                local_date=local_date,
                dedupe_key=dedupe_key,
            )
            db.add(notification)
            await db.flush()

            # Create push delivery with proper payload conventions
            chat_url = f"/p/{project_id}/chat?nid={notification.id}"
            delivery = NotificationDelivery(
                instance_id=notification.id,
                membership_id=rule.membership_id,
                user_id=membership.user_id,
                channel="push_notify",
                payload_json=json.dumps(
                    {
                        "title": topic,
                        "body": content,
                        "url": chat_url,
                        "data": {
                            "notification_id": notification.id,
                            "project_id": project_id,
                            "membership_id": rule.membership_id,
                            "rule_id": rule.id,
                            "action": "notify",
                        },
                    }
                ),
                run_at_utc=datetime.now(UTC),
            )
            db.add(delivery)

            if config.is_feedback_loop_enabled():
                actions = config.build_feedback_actions()
                task = ScheduledTask(
                    membership_id=rule.membership_id,
                    rule_id=rule.id,
                    parent_instance_id=notification.id,
                    task_type="feedback_request",
                    payload_json=json.dumps(
                        {
                            "text": config.get_feedback_prompt_text(),
                            "actions": actions,
                        }
                    ),
                    run_at_utc=datetime.now(UTC)
                    + timedelta(minutes=config.get_feedback_delay_minutes()),
                )
                db.add(task)

            # Advance rule state to next occurrence
            await recompute_rule_due_time(db, rule, state)
            await db.commit()

            logger.info(
                "Rule %s fired: notification %s, message %s",
                rule.id,
                notification.id,
                message.id,
            )

        except IntegrityError:
            # Dedupe collision — another worker already fired this rule.
            # After rollback, the original db session's ORM objects are invalidated,
            # so we must open a fresh session (db2) to advance the rule state.
            await db.rollback()
            async with async_session_factory() as db2:
                rule_r = await db2.execute(
                    select(NotificationRule).where(NotificationRule.id == rule_id)
                )
                rule2 = rule_r.scalar_one_or_none()
                state_r = await db2.execute(
                    select(NotificationRuleState).where(
                        NotificationRuleState.rule_id == rule_id
                    )
                )
                state2 = state_r.scalar_one_or_none()
                if rule2 and state2:
                    await recompute_rule_due_time(db2, rule2, state2)
                    await db2.commit()
            logger.info("Rule %s: dedupe collision, advancing state", rule_id)

        except Exception as exc:
            await db.rollback()
            state_result = await db.execute(
                select(NotificationRuleState).where(
                    NotificationRuleState.rule_id == rule_id
                )
            )
            state = state_result.scalar_one_or_none()
            if state:
                state.attempts += 1
                state.last_error = str(exc)
                state.locked_by = None
                state.claimed_at = None
                state.locked_until = None
                if state.attempts >= MAX_ATTEMPTS:
                    state.next_due_at_utc = datetime.now(UTC) + timedelta(
                        days=FAILED_EVENT_POSTPONE_DAYS
                    )
                else:
                    state.next_due_at_utc = datetime.now(UTC) + timedelta(
                        minutes=2 ** min(state.attempts, 8)
                    )
                await db.commit()
            raise


# ---------------------------------------------------------------------------
# Delivery processing
# ---------------------------------------------------------------------------


async def _process_due_deliveries(worker_id: str) -> int:
    """Claim and send due notification deliveries. Returns count processed."""
    processed = 0
    async with async_session_factory() as db:
        deliveries = await claim_due_deliveries(db, worker_id)
        await db.commit()

    for delivery in deliveries:
        try:
            await _send_delivery(delivery.id, worker_id)
            processed += 1
        except Exception as exc:
            logger.error("Failed sending delivery %s: %s", delivery.id, exc)
    return processed


async def _send_delivery(delivery_id: int, worker_id: str) -> None:
    """Send a single delivery (push notification) to all user subscriptions."""
    async with async_session_factory() as db:
        d_result = await db.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.id == delivery_id,
                NotificationDelivery.locked_by == worker_id,
            )
        )
        delivery = d_result.scalar_one_or_none()
        if not delivery:
            return

        try:
            payload = json.loads(delivery.payload_json)
            user_id = delivery.user_id

            if delivery.channel == "push_notify":
                success, total = await _send_push_notifications(
                    db,
                    user_id,
                    title=payload.get("title", ""),
                    body=payload.get("body", ""),
                    url=payload.get("url", ""),
                    data=payload.get("data"),
                    actions=payload.get("actions"),
                )
            elif delivery.channel == "push_dismiss":
                success, total = await _send_push_notifications(
                    db,
                    user_id,
                    title="",
                    body="",
                    url="",
                    data=payload.get("data"),
                    actions=payload.get("actions"),
                )
            else:
                success, total = 0, 0

            # Mark sent if at least one push succeeded, or if there are no subscriptions
            if success > 0 or total == 0:
                delivery.status = "sent"
            else:
                # All sends failed — retry with backoff
                delivery.attempts += 1
                if delivery.attempts >= MAX_ATTEMPTS:
                    delivery.status = "failed"
                else:
                    backoff_minutes = 2 ** min(delivery.attempts, 8)
                    delivery.run_at_utc = datetime.now(UTC) + timedelta(
                        minutes=backoff_minutes
                    )
                delivery.locked_by = None
                delivery.claimed_at = None
                delivery.locked_until = None

            await db.commit()

        except Exception as exc:
            await db.rollback()
            d_result = await db.execute(
                select(NotificationDelivery).where(
                    NotificationDelivery.id == delivery_id
                )
            )
            delivery = d_result.scalar_one_or_none()
            if delivery:
                delivery.attempts += 1
                delivery.last_error = str(exc)
                delivery.locked_by = None
                delivery.claimed_at = None
                delivery.locked_until = None
                if delivery.attempts >= MAX_ATTEMPTS:
                    delivery.status = "failed"
                else:
                    backoff_minutes = 2 ** min(delivery.attempts, 8)
                    delivery.run_at_utc = datetime.now(UTC) + timedelta(
                        minutes=backoff_minutes
                    )
                await db.commit()
            raise


# ---------------------------------------------------------------------------
# Scheduled task processing
# ---------------------------------------------------------------------------


async def _process_scheduled_tasks(worker_id: str) -> int:
    """Claim and process due delayed tasks."""
    processed = 0
    now = datetime.now(UTC)
    locked_until = now + timedelta(seconds=LOCK_DURATION_SECONDS)

    async with async_session_factory() as db:
        id_query = (
            select(ScheduledTask.id)
            .where(
                ScheduledTask.run_at_utc <= now,
                ScheduledTask.status == "pending",
                or_(
                    ScheduledTask.locked_until.is_(None),
                    ScheduledTask.locked_until < now,
                ),
            )
            .order_by(ScheduledTask.run_at_utc.asc())
            .limit(20)
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            id_query = id_query.with_for_update(skip_locked=True)

        task_ids = [tid for (tid,) in (await db.execute(id_query)).all()]
        if not task_ids:
            return 0

        await db.execute(
            update(ScheduledTask)
            .where(ScheduledTask.id.in_(task_ids))
            .values(locked_by=worker_id, locked_until=locked_until)
        )

        tasks = (
            (
                await db.execute(
                    select(ScheduledTask).where(ScheduledTask.id.in_(task_ids))
                )
            )
            .scalars()
            .all()
        )

        for task in tasks:
            try:
                if task.rule_id is not None:
                    rule_result = await db.execute(
                        select(NotificationRule).where(
                            NotificationRule.id == task.rule_id
                        )
                    )
                    parent_rule = rule_result.scalar_one_or_none()
                    if parent_rule is None or not parent_rule.is_active:
                        logger.info(
                            "Cancelling scheduled task %s: parent rule is inactive",
                            task.id,
                        )
                        task.status = "cancelled"
                        task.locked_by = None
                        task.locked_until = None
                        continue

                if task.task_type == "feedback_request":
                    payload = json.loads(task.payload_json)
                    membership_result = await db.execute(
                        select(ProjectMembership).where(
                            ProjectMembership.id == task.membership_id
                        )
                    )
                    membership = membership_result.scalar_one()

                    conv_result = await db.execute(
                        select(Conversation).where(
                            Conversation.membership_id == task.membership_id
                        )
                    )
                    conversation = conv_result.scalar_one_or_none()
                    if conversation is None:
                        conversation = Conversation(membership_id=task.membership_id)
                        db.add(conversation)
                        await db.flush()

                    content = payload.get("text", "Feedback Request")
                    server_msg_id = generate_server_msg_id()

                    notification = Notification(
                        membership_id=task.membership_id,
                        title="Feedback Request",
                        body=content,
                        payload_json=json.dumps(
                            {
                                "server_msg_id": server_msg_id,
                                "project_id": membership.project_id,
                                "parent_notification_id": task.parent_instance_id,
                            }
                        ),
                        local_date=now.date(),
                        dedupe_key=f"feedback:{task.id}",
                    )
                    db.add(notification)
                    await db.flush()

                    message_metadata = {
                        "type": "feedback_poll",
                        "notification_id": notification.id,
                        "status": "pending",
                        "actions": _to_feedback_poll_actions(payload.get("actions")),
                    }
                    message = Message(
                        conversation_id=conversation.id,
                        role="assistant",
                        content=content,
                        server_msg_id=server_msg_id,
                        client_msg_id=f"feedback:{task.id}",
                        metadata_=message_metadata,
                    )
                    db.add(message)
                    await db.flush()
                    await persist_event(
                        db,
                        conversation.id,
                        "message.final",
                        {
                            "message_id": message.id,
                            "server_msg_id": message.server_msg_id,
                            "role": "assistant",
                            "content": message.content,
                            "metadata": message_metadata,
                            "created_at": message.created_at.isoformat()
                            if message.created_at
                            else datetime.now(UTC).isoformat(),
                        },
                    )

                    chat_url = f"/p/{membership.project_id}/chat?nid={notification.id}"
                    delivery = NotificationDelivery(
                        instance_id=notification.id,
                        membership_id=task.membership_id,
                        user_id=membership.user_id,
                        channel="push_notify",
                        payload_json=json.dumps(
                            {
                                "title": "Feedback Request",
                                "body": content,
                                "url": chat_url,
                                "actions": payload.get("actions", []),
                                "data": {
                                    "notification_id": notification.id,
                                    "project_id": membership.project_id,
                                    "action": "feedback",
                                },
                            }
                        ),
                        run_at_utc=now,
                    )
                    db.add(delivery)

                task.status = "completed"
                processed += 1
            except Exception as exc:
                logger.error("Task execution failed for %s: %s", task.id, exc)
                task.status = "failed"
                task.locked_by = None
                task.locked_until = None

        await db.commit()
    return processed


# ---------------------------------------------------------------------------
# Main worker loop
# ---------------------------------------------------------------------------


async def run_worker_loop(poll_seconds: int = 5) -> None:
    """Single unified worker loop: poll rules → process deliveries → sleep."""
    worker_id = _make_worker_id()
    logger.info("Notification worker started: %s", worker_id)

    while True:
        # 1. Rule-based notification engine
        try:
            await _evaluate_due_rules(worker_id)
        except Exception as exc:
            logger.error("Rule evaluation error: %s", exc)

        # 2. Delivery processing
        try:
            await _process_scheduled_tasks(worker_id)
        except Exception as exc:
            logger.error("Scheduled task processing error: %s", exc)

        # 3. Delivery processing
        try:
            await _process_due_deliveries(worker_id)
        except Exception as exc:
            logger.error("Delivery processing error: %s", exc)

        await asyncio.sleep(poll_seconds)


def main() -> None:
    configure_logging()
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
