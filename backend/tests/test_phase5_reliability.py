import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.models.audit_event import AuditEvent
from app.models.client import Client
from app.models.conversation_session import ConversationSession
from app.models.enums import (
    Channel,
    InboundProvider,
    NotificationChannel,
    NotificationStatus,
    NotificationTargetType,
)
from app.models.notification import Notification
from app.models.worker import Worker
from app.repositories.idempotency_repo import IdempotencyRepository
from app.services.agent_runtime import AgentRuntimeService
from app.services.notification_service import NotificationService
from app.services.twilio_gateway import OutboundSendResult, TwilioGateway


@pytest.mark.asyncio
async def test_out_of_order_inbound_is_ignored(client: AsyncClient) -> None:
    first = await client.post(
        "/agent/process-incoming",
        json={
            "channel": "sms",
            "phone_e164": "+447700910001",
            "inbound_text": "hello",
            "message_sid": "SM_PHASE5_ORDER_1",
            "raw_payload": {"Timestamp": "2026-04-16T10:00:00Z"},
        },
    )
    assert first.status_code == 200
    assert first.json()["response_text"]

    second = await client.post(
        "/agent/process-incoming",
        json={
            "channel": "sms",
            "phone_e164": "+447700910001",
            "inbound_text": "older message",
            "message_sid": "SM_PHASE5_ORDER_2",
            "raw_payload": {"Timestamp": "2026-04-16T09:59:00Z"},
        },
    )
    assert second.status_code == 200
    body = second.json()
    assert body["duplicate"] is False
    assert body["response_text"] is None


@pytest.mark.asyncio
async def test_idempotency_check_and_mark_concurrent_same_sid(db: AsyncSession) -> None:
    repo = IdempotencyRepository(db)
    sid = f"SM_PHASE5_RACE_{uuid.uuid4().hex}"

    first = await repo.check_and_mark(provider=InboundProvider.TWILIO, external_id=sid)
    second = await repo.check_and_mark(provider=InboundProvider.TWILIO, external_id=sid)
    assert sorted([first, second]) == [False, True]


@pytest.mark.asyncio
async def test_notification_retry_and_dead_letter_flow(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "outbound_retry_max_attempts", 1)
    monkeypatch.setattr(settings, "outbound_retry_backoff_seconds", 1)

    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, client])
    await db.flush()

    session = ConversationSession(
        client_id=client.id,
        worker_id=worker.id,
        last_channel=Channel.SMS,
    )
    db.add(session)
    await db.flush()

    async def _always_fail(
        self: TwilioGateway, *, to_phone_e164: str, channel: str, text: str
    ) -> OutboundSendResult:
        return OutboundSendResult(ok=False, sid=None, error="simulated_failure")

    monkeypatch.setattr(TwilioGateway, "send_client_message", _always_fail)

    svc = NotificationService(db)
    notif = await svc.create(
        target_type=NotificationTargetType.CLIENT,
        target_ref=str(client.id),
        template_key="outbound_retry_message",
        payload={"text": "Test message"},
        send_at=datetime.now(UTC) - timedelta(minutes=1),
        channel=NotificationChannel.SMS,
    )

    first = await svc.dispatch_due_notifications()
    assert first["failed"] == 1

    stored = await db.get(Notification, notif.id)
    assert stored is not None
    assert stored.status == NotificationStatus.RETRY_PENDING
    assert stored.retry_count == 1

    stored.send_at = datetime.now(UTC) - timedelta(seconds=1)
    await db.flush()

    second = await svc.dispatch_due_notifications()
    assert second["dead_lettered"] == 1

    dead = await db.get(Notification, notif.id)
    assert dead is not None
    assert dead.status == NotificationStatus.DEAD_LETTER


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_reliability_counters(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200
    payload = response.json()
    assert "counters" in payload
    assert "pending_reviews" in payload
    assert "failed_tool_calls" in payload
    assert "reminder_failures" in payload


@pytest.mark.asyncio
async def test_tool_failure_telemetry_increments_counter_and_writes_audit(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = AgentRuntimeService(db)
    baseline = metrics.snapshot().get("tool_calls_failed_total", 0)

    async def _failing_tool(**kwargs: object) -> dict[str, object]:
        raise RuntimeError("simulated_tool_failure")

    monkeypatch.setattr(service.tool_runner, "failing_tool", _failing_tool, raising=False)

    client_id = uuid.uuid4()
    worker_id = uuid.uuid4()
    result = await service._execute_tool(
        "failing_tool",
        {"example": "value"},
        client_id,
        worker_id,
        Channel.SMS,
    )
    assert result["ok"] is False
    assert "simulated_tool_failure" in str(result.get("error"))

    updated = metrics.snapshot().get("tool_calls_failed_total", 0)
    assert updated == baseline + 1

    audit_result = await db.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "client",
            AuditEvent.entity_id == client_id,
            AuditEvent.event_type == "tool_execution_failed",
        )
    )
    audit = audit_result.scalars().first()
    assert audit is not None
    assert audit.metadata_["tool"] == "failing_tool"
    assert audit.metadata_["arguments"]["example"] == "value"
    assert "simulated_tool_failure" in str(audit.metadata_["error"])


@pytest.mark.asyncio
async def test_race_condition_confirmation_conflict_still_blocked(db: AsyncSession) -> None:
    from app.models.booking import Booking
    from app.models.enums import ActorType, BookingStatus, BookingType
    from app.services.booking_service import BookingService

    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    client1 = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    client2 = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, client1, client2])
    await db.flush()

    session1 = ConversationSession(
        client_id=client1.id, worker_id=worker.id, last_channel=Channel.SMS
    )
    session2 = ConversationSession(
        client_id=client2.id, worker_id=worker.id, last_channel=Channel.WHATSAPP
    )
    db.add_all([session1, session2])
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking1 = Booking(
        client_id=client1.id,
        worker_id=worker.id,
        session_id=session1.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=24,
        client_ethnicity="British",
    )
    booking2 = Booking(
        client_id=client2.id,
        worker_id=worker.id,
        session_id=session2.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=26,
        client_ethnicity="British",
    )
    db.add_all([booking1, booking2])
    await db.flush()

    svc = BookingService(db)
    first_after, first_errors = await svc.set_status(
        booking_id=booking1.id,
        status=BookingStatus.CONFIRMED,
        actor_type=ActorType.ADMIN,
    )
    second_after, second_errors = await svc.set_status(
        booking_id=booking2.id,
        status=BookingStatus.CONFIRMED,
        actor_type=ActorType.ADMIN,
    )
    assert first_after is not None
    assert second_after is not None

    confirmed_count = int(first_after.status == BookingStatus.CONFIRMED) + int(
        second_after.status == BookingStatus.CONFIRMED
    )
    assert confirmed_count <= 1
    assert first_errors or second_errors
