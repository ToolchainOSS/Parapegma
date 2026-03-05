"""Unified notification worker: rule polling → instance creation → delivery sending.

Single worker process — no legacy outbox events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import config
from app.db import async_session_factory
from app.id_utils import generate_server_msg_id
from app.logging_conf import LLMLoggingCallbackHandler, configure_logging
from app.models import (
    Conversation,
    Message,
    Notification,
    NotificationDelivery,
    NotificationRule,
    NotificationRuleState,
    ProjectMembership,
    PushSubscription,
)
from app.services.notification_engine import (
    claim_due_deliveries,
    claim_due_rules,
    compute_local_date_for_rule,
    get_user_timezone,
    recompute_rule_due_time,
)
from app.services.profile_service import load_user_profile

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
FAILED_EVENT_POSTPONE_DAYS = 3650
LOCK_DURATION_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 10


def _make_worker_id() -> str:
    base = config.get_worker_id()
    return f"{base}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


def _push_enabled() -> bool:
    return bool(config.get_vapid_private_key() and config.get_vapid_public_key())


async def _send_push_notifications(
    db,
    user_id: str,
    title: str,
    body: str,
    url: str,
    data: dict | None = None,
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

    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "url": url,
            "data": data or {},
        }
    )

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


async def _generate_custom_prompt(db, membership_id: int, topic: str) -> str:
    llm_key = config.get_openai_api_key()
    if not llm_key:
        return f"{topic} (LLM not configured)"

    profile = await load_user_profile(db, membership_id)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful coach. Generate a short, encouraging daily nudge "
                "for the user about: {topic}. User profile: {profile_json}",
            ),
            ("human", "Generate the nudge."),
        ]
    )

    try:
        llm = ChatOpenAI(
            model=config.get_llm_model(),
            api_key=llm_key,
            callbacks=[LLMLoggingCallbackHandler()],
        )
        chain = prompt | llm
        res = await asyncio.wait_for(
            chain.ainvoke({"topic": topic, "profile_json": profile.model_dump_json()}),
            timeout=15,
        )
        return str(res.content)
    except Exception as exc:
        logger.error("LLM generation failed: %s", exc)
        return f"{topic} (Generation failed)"


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------


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

            # Generate content
            content = await _generate_custom_prompt(db, rule.membership_id, topic)

            # Persist Message (idempotent via client_msg_id = dedupe_key)
            server_msg_id = generate_server_msg_id()
            message = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=content,
                server_msg_id=server_msg_id,
                client_msg_id=dedupe_key,
            )
            db.add(message)
            await db.flush()

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
                )
            elif delivery.channel == "push_dismiss":
                success, total = await _send_push_notifications(
                    db,
                    user_id,
                    title="",
                    body="",
                    url="",
                    data=payload.get("data"),
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
            await _process_due_deliveries(worker_id)
        except Exception as exc:
            logger.error("Delivery processing error: %s", exc)

        await asyncio.sleep(poll_seconds)


def main() -> None:
    configure_logging()
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
