from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pywebpush import WebPushException, webpush
from sqlalchemy import Select, delete, or_, select, update

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
    NudgeSchedule,
    OutboxEvent,
    PushSubscription,
)
from app.services.notification_engine import (
    claim_due_deliveries,
    claim_due_rules,
    compute_local_date_for_rule,
    get_user_timezone,
    recompute_rule_due_time,
)
from app.services.outbox_service import (
    enqueue_outbox_event,
    next_run_at,
)
from app.services.profile_service import load_user_profile

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
FAILED_EVENT_POSTPONE_DAYS = 3650
LOCK_DURATION_SECONDS = 300
PUSH_TIMEOUT_SECONDS = 10
WORKER_POOL_SIZE = 5
MAX_QUEUE_SIZE = WORKER_POOL_SIZE * 2


def _make_worker_id() -> str:
    base = config.get_worker_id()
    # Note: socket.gethostname() is handled in config.get_worker_id()
    # But wait, config.get_worker_id() handles FLOW_WORKER_ID or socket.gethostname()
    # But here we want pid and uuid as well?
    # Actually, let's keep the pid and uuid part here, but use config for the base.
    import os

    return f"{base}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


async def _claim_due_events(worker_id: str, limit: int = 20) -> list[OutboxEvent]:
    async with async_session_factory() as db:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=LOCK_DURATION_SECONDS)
        id_query: Select[tuple[int]] = (
            select(OutboxEvent.id)
            .where(
                OutboxEvent.available_at <= now,
                or_(
                    OutboxEvent.locked_until.is_(None),
                    OutboxEvent.locked_until < now,
                ),
            )
            .order_by(OutboxEvent.available_at.asc(), OutboxEvent.id.asc())
            .limit(limit)
        )
        if db.bind and db.bind.dialect.name == "postgresql":
            id_query = id_query.with_for_update(skip_locked=True)

        result = await db.execute(id_query)
        ids = [event_id for (event_id,) in result.all()]
        if not ids:
            return []

        await db.execute(
            update(OutboxEvent)
            .where(
                OutboxEvent.id.in_(ids),
                or_(
                    OutboxEvent.locked_until.is_(None),
                    OutboxEvent.locked_until < now,
                ),
            )
            .values(locked_by=worker_id, claimed_at=now, locked_until=locked_until)
        )
        await db.commit()

        claimed_result = await db.execute(
            select(OutboxEvent).where(
                OutboxEvent.id.in_(ids),
                OutboxEvent.locked_by == worker_id,
            )
        )
        return list(claimed_result.scalars().all())


def _push_enabled() -> bool:
    return bool(config.get_vapid_private_key() and config.get_vapid_public_key())


async def _send_push_notifications(
    db,
    membership_id: int,
    title: str,
    body: str,
    url: str,
    data: dict | None = None,
) -> None:
    if not _push_enabled():
        return

    result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.membership_id == membership_id,
            PushSubscription.revoked_at.is_(None),
        )
    )
    subscriptions = result.scalars().all()
    if not subscriptions:
        return

    payload = json.dumps(
        {
            "title": title,
            "body": body,
            "url": url,
            "data": data or {},
        }
    )

    vapid_private_key = config.get_vapid_private_key()
    # vapid_utils.get_vapid_claims() was just {"sub": get_vapid_sub()}
    vapid_claims = {"sub": config.get_vapid_sub()}

    async def _send_single(sub: PushSubscription):
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
        except asyncio.TimeoutError:
            sub.last_failure_at = datetime.now(UTC)
            logger.warning("Push send timed out for subscription %s", sub.id)
        except WebPushException as exc:
            sub.last_failure_at = datetime.now(UTC)
            logger.warning("Push send failed for subscription %s: %s", sub.id, exc)

    await asyncio.gather(*[_send_single(sub) for sub in subscriptions])


async def _handle_read_receipt(db, event: OutboxEvent) -> None:
    payload = json.loads(event.payload_json)
    notification_id = payload.get("notification_id")
    payload.get("project_id", event.project_id)

    if notification_id:
        await _send_push_notifications(
            db,
            event.membership_id,
            title="",  # Silent push
            body="",
            url="",
            data={"action": "dismiss", "notification_id": notification_id},
        )


async def _generate_custom_prompt(db, membership_id: int, topic: str) -> str:
    llm_key = config.get_openai_api_key()
    if not llm_key:
        return f"{topic} (LLM not configured)"

    profile = await load_user_profile(db, membership_id)
    # Simple prompt
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful coach. Generate a short, encouraging daily nudge for the user about: {topic}. User profile: {profile_json}",
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


async def _handle_scheduled_nudge(db, event: OutboxEvent) -> None:
    payload = json.loads(event.payload_json)
    schedule_id = payload.get("schedule_id")
    topic = payload.get("topic", "Daily Nudge")
    project_id = payload.get("project_id", event.project_id)

    # Check schedule active
    if schedule_id:
        sched_result = await db.execute(
            select(NudgeSchedule).where(NudgeSchedule.id == schedule_id)
        )
        schedule = sched_result.scalar_one_or_none()
        if not schedule or not schedule.is_active:
            logger.info("Schedule %s inactive, stopping recurrence.", schedule_id)
            return

        # Enqueue next recurrence
        run_at = next_run_at(schedule.cron_rule, datetime.now(UTC))
        next_dedupe_key = f"nudge:{schedule.id}:{run_at.date().isoformat()}"

        await enqueue_outbox_event(
            db,
            project_id=project_id,
            membership_id=event.membership_id,
            event_type="scheduled_nudge",
            payload=payload,
            dedupe_key=next_dedupe_key,
            available_at=run_at,
        )

    # Generate Content
    content = await _generate_custom_prompt(db, event.membership_id, topic)

    # Get conversation
    conversation_result = await db.execute(
        select(Conversation).where(Conversation.membership_id == event.membership_id)
    )
    conversation = conversation_result.scalar_one_or_none()
    if not conversation:
        # Create if missing (edge case)
        conversation = Conversation(membership_id=event.membership_id)
        db.add(conversation)
        await db.flush()

    # Persist Message (Chat History)
    server_msg_id = generate_server_msg_id()
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        server_msg_id=server_msg_id,
        client_msg_id=event.dedupe_key,
    )
    db.add(message)
    await db.flush()

    # Persist Notification (Updates Tab)
    # Link to chat with notification_id param for read-sync
    notification = Notification(
        membership_id=event.membership_id,
        title=topic,
        body=content,
        payload_json=json.dumps(
            {
                "schedule_id": schedule_id,
                "server_msg_id": server_msg_id,
                "project_id": project_id,
            }
        ),
    )
    db.add(notification)
    await db.flush()

    # Send Push (Browser Notification)
    # Clicking goes to chat, passing nid to mark it read on open
    chat_url = f"/p/{project_id}/chat?nid={notification.id}"
    await _send_push_notifications(
        db,
        event.membership_id,
        title=topic,
        body=content,
        url=chat_url,
        data={
            "notification_id": notification.id,
            "project_id": project_id,
            "url": chat_url,
        },
    )

    await db.commit()


async def _process_event(event: OutboxEvent, worker_id: str) -> None:
    async with async_session_factory() as db:
        row_result = await db.execute(
            select(OutboxEvent).where(
                OutboxEvent.id == event.id,
                OutboxEvent.locked_by == worker_id,
            )
        )
        row = row_result.scalar_one_or_none()
        if row is None:
            return
        try:
            if row.type == "scheduled_prompt":
                # Legacy event type — noop, delete, and log.
                logger.info(
                    "Ignoring legacy scheduled_prompt event %s, deleting.", row.id
                )
            elif row.type == "scheduled_nudge":
                await _handle_scheduled_nudge(db, row)
            elif row.type == "notification_read_receipt":
                await _handle_read_receipt(db, row)
            else:
                raise ValueError(f"Unsupported event type: {row.type}")
            await db.execute(
                delete(OutboxEvent).where(
                    OutboxEvent.id == row.id,
                    OutboxEvent.locked_by == worker_id,
                )
            )
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            # Reset failed transaction state before reloading the persisted row.
            await db.rollback()
            row_result = await db.execute(
                select(OutboxEvent).where(OutboxEvent.id == event.id)
            )
            row = row_result.scalar_one_or_none()
            if row is None:
                return
            row.attempts += 1
            row.last_error = str(exc)
            row.locked_by = None
            row.claimed_at = None
            row.locked_until = None
            if row.attempts >= MAX_ATTEMPTS:
                row.available_at = datetime.now(UTC) + timedelta(
                    days=FAILED_EVENT_POSTPONE_DAYS
                )
            else:
                row.available_at = datetime.now(UTC) + timedelta(
                    minutes=2 ** min(row.attempts, 8)
                )
            await db.commit()


async def _consumer_task(queue: asyncio.Queue, worker_id: str) -> None:
    """Continuously processes events from the queue."""
    while True:
        event = await queue.get()
        try:
            await _process_event(event, worker_id)
        except Exception as exc:
            logger.error("Failed processing event %s: %s", event.id, exc)
        finally:
            queue.task_done()


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

            # Check if instance already exists (idempotency)
            existing = await db.execute(
                select(Notification).where(Notification.dedupe_key == dedupe_key)
            )
            if existing.scalar_one_or_none():
                # Already processed — just advance
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

            # Determine project_id for this membership
            from app.models import ProjectMembership

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

            # Create push delivery
            chat_url = f"/p/{project_id}/chat?nid={notification.id}"
            delivery = NotificationDelivery(
                instance_id=notification.id,
                membership_id=rule.membership_id,
                channel="push_notify",
                payload_json=json.dumps(
                    {
                        "title": topic,
                        "body": content,
                        "url": chat_url,
                        "data": {
                            "notification_id": notification.id,
                            "project_id": project_id,
                            "url": chat_url,
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

        except Exception as exc:
            await db.rollback()
            # Reload state and record failure
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
    """Send a single delivery (push notification)."""
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
            if delivery.channel == "push_notify":
                await _send_push_notifications(
                    db,
                    delivery.membership_id,
                    title=payload.get("title", ""),
                    body=payload.get("body", ""),
                    url=payload.get("url", ""),
                    data=payload.get("data"),
                )
            elif delivery.channel == "push_dismiss":
                await _send_push_notifications(
                    db,
                    delivery.membership_id,
                    title="",
                    body="",
                    url="",
                    data=payload.get("data"),
                )

            delivery.status = "sent"
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
                await db.commit()
            raise


async def run_worker_loop(poll_seconds: int = 5) -> None:
    worker_id = _make_worker_id()
    queue: asyncio.Queue[OutboxEvent] = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)

    consumers = [
        asyncio.create_task(_consumer_task(queue, worker_id))
        for _ in range(WORKER_POOL_SIZE)
    ]

    try:
        while True:
            # 1. Legacy outbox event processing
            if queue.qsize() < WORKER_POOL_SIZE:
                fetch_limit = MAX_QUEUE_SIZE - queue.qsize()
                if fetch_limit > 0:
                    events = await _claim_due_events(
                        worker_id=worker_id, limit=fetch_limit
                    )
                    for event in events:
                        await queue.put(event)

            # 2. Rule-based notification engine
            try:
                await _evaluate_due_rules(worker_id)
            except Exception as exc:
                logger.error("Rule evaluation error: %s", exc)

            # 3. Delivery processing
            try:
                await _process_due_deliveries(worker_id)
            except Exception as exc:
                logger.error("Delivery processing error: %s", exc)

            await asyncio.sleep(poll_seconds)
    finally:
        for c in consumers:
            c.cancel()
        await asyncio.gather(*consumers, return_exceptions=True)


def main() -> None:
    configure_logging()
    asyncio.run(run_worker_loop())


if __name__ == "__main__":
    main()
