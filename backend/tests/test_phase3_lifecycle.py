import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.booking_media import BookingMedia
from app.models.client import Client
from app.models.conversation_session import ConversationSession
from app.models.enums import (
    ActorType,
    BookingStatus,
    BookingType,
    Channel,
    ConversationState,
    MessageDirection,
    SenderType,
)
from app.models.message import Message
from app.models.notification import Notification
from app.models.worker import Worker
from app.services.booking_service import BookingService
from app.services.media_service import MediaService


async def _setup_pending_booking(
    db: AsyncSession,
) -> tuple[Worker, Client, ConversationSession, Booking]:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add(worker)
    db.add(client)
    await db.flush()

    session = ConversationSession(
        client_id=client.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=24,
        client_ethnicity="British",
        client_name="Mia",
        client_size_inches=5,  # New required field
        alone_policy_confirmed=True,  # New required field
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    await db.flush()

    booking_service = BookingService(db)
    updated, errors = await booking_service.submit_for_review(booking.id)
    assert updated is not None
    assert errors == []
    return worker, client, session, booking


@pytest.mark.asyncio
async def test_admin_queue_detail_and_timeline(client: AsyncClient, db: AsyncSession) -> None:
    _, _, session, booking = await _setup_pending_booking(db)

    inbound = Message(
        session_id=session.id,
        direction=MessageDirection.INBOUND,
        channel=Channel.WHATSAPP,
        sender_type=SenderType.CLIENT,
        body="Can I book tomorrow 8pm?",
    )
    db.add(inbound)
    await db.flush()

    media = MediaService(db)
    await media.attach(
        client_id=booking.client_id,
        session_id=booking.session_id,
        source_url="https://example.com/receipt.jpg",
        channel=Channel.WHATSAPP,
        booking_id=booking.id,
        media_type="image/jpeg",
    )

    queue_res = await client.get("/admin/bookings", params={"status": "PENDING_REVIEW"})
    assert queue_res.status_code == 200
    queue_body = queue_res.json()
    assert len(queue_body) >= 1
    queue_item = next(item for item in queue_body if item["id"] == str(booking.id))
    assert queue_item["client_phone_e164"].startswith("+44")
    assert queue_item["awaiting_review_from"] == "admin"

    detail_res = await client.get(f"/admin/bookings/{booking.id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["id"] == str(booking.id)
    assert detail["created_at"]
    assert detail["updated_at"]

    timeline_res = await client.get(f"/admin/bookings/{booking.id}/timeline")
    assert timeline_res.status_code == 200
    timeline = timeline_res.json()["timeline"]
    kinds = {item["kind"] for item in timeline}
    assert "message" in kinds
    assert "audit" in kinds
    assert "notification" in kinds
    assert "media" in kinds


@pytest.mark.asyncio
async def test_admin_approve_sends_client_decision_and_notification(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    _, _, session, booking = await _setup_pending_booking(db)

    res = await client.post(f"/admin/bookings/{booking.id}/approve", json={"note": "looks good"})
    assert res.status_code == 200
    assert res.json()["status"] == "confirmed"

    # The decision message is dispatched as a BackgroundTask (own session) after
    # the HTTP response returns, so we trigger it directly here to test it.
    from app.models.enums import BookingStatus as BS
    from app.repositories.booking_repo import BookingRepository
    from app.services.booking_service import BookingService as BkSvc

    booking_fresh = await BookingRepository(db).get_by_id(booking.id)
    assert booking_fresh is not None
    await BkSvc(db).send_client_decision_message(booking_fresh, BS.CONFIRMED)
    await db.flush()

    message_result = await db.execute(
        select(Message)
        .where(Message.session_id == session.id, Message.direction == MessageDirection.OUTBOUND)
        .order_by(Message.created_at.desc())
    )
    outbound = message_result.scalars().first()
    assert outbound is not None
    assert outbound.raw_payload is not None
    assert outbound.raw_payload.get("decision_send") is True
    assert "confirmed" in (outbound.body or "").lower()

    notif_result = await db.execute(
        select(Notification).where(
            Notification.booking_id == booking.id,
            Notification.template_key == "booking_confirmed_admin",
        )
    )
    assert notif_result.scalars().first() is not None


@pytest.mark.asyncio
async def test_confirming_an_already_confirmed_booking_is_idempotent(
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, client])
    await db.flush()

    session = ConversationSession(
        client_id=client.id,
        worker_id=worker.id,
        state=ConversationState.IDLE,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.CONFIRMED,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=24,
        client_ethnicity="British",
        client_size_inches=5,
        alone_policy_confirmed=True,
    )
    db.add(booking)
    await db.flush()

    svc = BookingService(db)
    updated, errors = await svc.set_status(
        booking_id=booking.id,
        status=BookingStatus.CONFIRMED,
        actor_type=ActorType.ADMIN,
    )

    assert errors == []
    assert updated is not None
    assert updated.status == BookingStatus.CONFIRMED


@pytest.mark.asyncio
async def test_admin_decision_instruction_keeps_recent_client_context(db: AsyncSession) -> None:
    _, _, session, booking = await _setup_pending_booking(db)

    inbound = Message(
        session_id=session.id,
        direction=MessageDirection.INBOUND,
        channel=Channel.WHATSAPP,
        sender_type=SenderType.CLIENT,
        body="Perfect babe, can you confirm this exact time for me?",
    )
    db.add(inbound)
    await db.flush()

    svc = BookingService(db)
    instruction = await svc._build_agent_decision_instruction(booking, BookingStatus.CONFIRMED)

    assert "[ADMIN ACTION: booking confirmed]" in instruction
    assert "Recent client message" in instruction
    assert "Perfect babe, can you confirm this exact time for me?" in instruction
    assert "Do not mention admin actions" in instruction


@pytest.mark.asyncio
async def test_admin_can_clear_session_messages(client: AsyncClient, db: AsyncSession) -> None:
    _, _, session, _ = await _setup_pending_booking(db)

    db.add_all(
        [
            Message(
                session_id=session.id,
                direction=MessageDirection.INBOUND,
                channel=Channel.WHATSAPP,
                sender_type=SenderType.CLIENT,
                body="Hello",
            ),
            Message(
                session_id=session.id,
                direction=MessageDirection.OUTBOUND,
                channel=Channel.WHATSAPP,
                sender_type=SenderType.AGENT,
                body="Hey babe 😘",
            ),
        ]
    )
    await db.flush()

    before = await client.get(f"/admin/sessions/{session.id}/messages")
    assert before.status_code == 200
    assert len(before.json()) >= 2

    clear_res = await client.delete(f"/admin/sessions/{session.id}/messages")
    assert clear_res.status_code == 200
    assert clear_res.json()["session_id"] == str(session.id)
    assert clear_res.json()["deleted_count"] >= 2

    after = await client.get(f"/admin/sessions/{session.id}/messages")
    assert after.status_code == 200
    assert after.json() == []


@pytest.mark.asyncio
async def test_worker_booking_actions_enforce_ownership(
    client: AsyncClient, db: AsyncSession
) -> None:
    worker1 = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    worker2 = Worker(name="Other", timezone="Europe/London", is_active=True)
    c = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker1, worker2, c])
    await db.flush()

    session = ConversationSession(
        client_id=c.id,
        worker_id=worker1.id,
        state=ConversationState.WAITING_REVIEW,
        last_channel=Channel.SMS,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=c.id,
        worker_id=worker1.id,
        session_id=session.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=26,
        client_ethnicity="British",
    )
    db.add(booking)
    await db.flush()

    res = await client.post(
        f"/worker/bookings/{booking.id}/approve", params={"worker_id": str(worker2.id)}
    )
    assert res.status_code == 403
    assert "does not belong" in res.text


@pytest.mark.asyncio
async def test_worker_free_now_marks_active_booking_completed(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    c = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, c])
    await db.flush()

    session = ConversationSession(
        client_id=c.id,
        worker_id=worker.id,
        state=ConversationState.IDLE,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) - timedelta(minutes=10)
    booking = Booking(
        client_id=c.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.CONFIRMED,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=23,
        client_ethnicity="British",
    )
    db.add(booking)
    await db.flush()

    res = await client.post(
        "/worker/messages",
        json={"worker_id": str(worker.id), "message_text": "free now"},
    )
    assert res.status_code == 200
    assert res.json()["success"] is True

    refreshed = await db.get(Booking, booking.id)
    assert refreshed is not None
    assert refreshed.status == BookingStatus.COMPLETED
    assert refreshed.completed_at is not None


@pytest.mark.asyncio
async def test_worker_message_query_returns_next_booking_with_action(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    c = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, c])
    await db.flush()

    session = ConversationSession(
        client_id=c.id,
        worker_id=worker.id,
        state=ConversationState.IDLE,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(hours=3)
    booking = Booking(
        client_id=c.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.CONFIRMED,
        booking_type=BookingType.OUTCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=29,
        client_ethnicity="British",
    )
    db.add(booking)
    await db.flush()

    res = await client.post(
        "/worker/messages",
        json={"worker_id": str(worker.id), "message_text": "What is my next booking time?"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "assistant_reply" in body
    assert body["executed_actions"]
    assert body["executed_actions"][0]["name"] == "booking.lookup_next"
    assert body["executed_actions"][0]["booking_id"] == str(booking.id)


@pytest.mark.asyncio
async def test_worker_message_relay_dispatches_client_message(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    c = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, c])
    await db.flush()

    session = ConversationSession(
        client_id=c.id,
        worker_id=worker.id,
        state=ConversationState.IDLE,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(hours=2)
    booking = Booking(
        client_id=c.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.CONFIRMED,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=26,
        client_ethnicity="British",
    )
    db.add(booking)
    await db.flush()

    relay_text = "wait outside the building. I will call you."
    res = await client.post(
        "/worker/messages",
        json={
            "worker_id": str(worker.id),
            "message_text": f"Tell him to {relay_text}",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["executed_actions"]
    assert body["executed_actions"][0]["name"] == "client.message.send"
    assert body["executed_actions"][0]["ok"] is True

    msg_result = await db.execute(
        select(Message).where(
            Message.session_id == session.id,
            Message.direction == MessageDirection.OUTBOUND,
            Message.body == relay_text,
        )
    )
    assert msg_result.scalars().first() is not None


@pytest.mark.asyncio
async def test_outcall_cannot_submit_without_address_and_advance(db: AsyncSession) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, client])
    await db.flush()

    session = ConversationSession(
        client_id=client.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.OUTCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=24,
        client_ethnicity="British",
        client_size_inches=5,  # New required field
        alone_policy_confirmed=True,  # New required field
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    await db.flush()

    svc = BookingService(db)
    _, errors = await svc.submit_for_review(booking.id)
    assert errors
    # Address is required first for outcall, so submit_for_review blocks on that before
    # evaluating advance rules.
    assert any("address" in e.lower() for e in errors), f"Expected address error, got: {errors}"


@pytest.mark.asyncio
async def test_outcall_confirmation_requires_advance_and_receipt(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    c = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, c])
    await db.flush()

    session = ConversationSession(
        client_id=c.id,
        worker_id=worker.id,
        state=ConversationState.WAITING_REVIEW,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=c.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.OUTCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=28,
        client_ethnicity="British",
        outcall_address="12 River Rd",
        advance_required_gbp=20,
        advance_received=False,
    )
    db.add(booking)
    await db.flush()

    not_paid = await client.post(f"/admin/bookings/{booking.id}/approve")
    assert not_paid.status_code == 422
    assert "advance" in not_paid.text.lower()

    booking.advance_received = True
    await db.flush()

    no_receipt = await client.post(f"/admin/bookings/{booking.id}/approve")
    assert no_receipt.status_code == 422
    assert "receipt" in no_receipt.text.lower()

    media = MediaService(db)
    attached = await media.attach(
        client_id=c.id,
        session_id=session.id,
        source_url="https://example.com/receipt-proof.jpg",
        channel=Channel.WHATSAPP,
        booking_id=booking.id,
        media_type="image/jpeg",
    )
    assert attached.is_receipt is True

    ok = await client.post(f"/admin/bookings/{booking.id}/approve")
    assert ok.status_code == 200
    assert ok.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_media_ingestion_enrichment_and_detail_flags(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    c = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, c])
    await db.flush()

    session = ConversationSession(
        client_id=c.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=c.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.OUTCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=25,
        client_ethnicity="British",
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    await db.flush()

    ingest_res = await client.post(
        "/media/twilio/ingest",
        json={
            "client_id": str(c.id),
            "session_id": str(session.id),
            "source_url": "https://example.com/payments/receipt.png",
            "channel": "whatsapp",
            "media_type": "image/png",
            "twilio_media_sid": "ME_PHASE4_001",
        },
    )
    assert ingest_res.status_code == 200
    ingest_body = ingest_res.json()
    assert ingest_body["booking_id"] == str(booking.id)
    assert ingest_body["is_receipt"] is True

    detail = await client.get(f"/admin/bookings/{booking.id}")
    assert detail.status_code == 200
    assert detail.json()["media_count"] == 1
    assert detail.json()["has_receipt"] is True


@pytest.mark.asyncio
async def test_incall_address_sent_endpoint_requires_confirmed_incall(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    c = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, c])
    await db.flush()

    session = ConversationSession(
        client_id=c.id,
        worker_id=worker.id,
        state=ConversationState.IDLE,
        last_channel=Channel.SMS,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=c.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=29,
        client_ethnicity="British",
    )
    db.add(booking)
    await db.flush()

    not_confirmed = await client.post(f"/admin/bookings/{booking.id}/incall-address-sent")
    assert not_confirmed.status_code == 422

    booking.status = BookingStatus.CONFIRMED
    await db.flush()

    ok = await client.post(f"/admin/bookings/{booking.id}/incall-address-sent")
    assert ok.status_code == 200
    body = ok.json()
    assert body["booking_id"] == str(booking.id)
    assert body["incall_address_sent_at"] is not None


@pytest.mark.asyncio
async def test_reminder_scheduler_creates_t20_with_style_hints(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    c = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, c])
    await db.flush()

    session = ConversationSession(
        client_id=c.id,
        worker_id=worker.id,
        state=ConversationState.IDLE,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start = datetime.now(UTC) + timedelta(minutes=15)
    booking = Booking(
        client_id=c.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.CONFIRMED,
        booking_type=BookingType.OUTCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=30,
        client_ethnicity="British",
        outcall_address="22 Dock Lane",
        advance_required_gbp=25,
        advance_received=True,
    )
    db.add(booking)
    await db.flush()

    receipt = BookingMedia(
        client_id=c.id,
        booking_id=booking.id,
        session_id=session.id,
        channel=Channel.WHATSAPP,
        media_type="image/jpeg",
        source_url="https://example.com/receipt.jpg",
        is_receipt=True,
    )
    db.add(receipt)
    await db.flush()

    response = await client.post("/notifications/reminders/run", json={"minutes_before": 20})
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "scheduler_window"
    assert body["scheduled"] == 3

    result = await db.execute(select(Notification).where(Notification.booking_id == booking.id))
    created = list(result.scalars().all())
    assert len(created) >= 3

    templates = {item.template_key for item in created}
    assert "booking_reminder_admin" in templates
    assert "booking_reminder_worker_outcall" in templates
    assert "booking_reminder_client_outcall" in templates

    client_notif = next(
        item for item in created if item.template_key == "booking_reminder_client_outcall"
    )
    assert client_notif.payload["style_hint"] == "i_am_about_to_arrive"
