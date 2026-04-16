import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.client import Client
from app.models.conversation_session import ConversationSession
from app.models.enums import BookingStatus, Channel, ConversationState, MessageDirection, SenderType
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
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=24,
        client_ethnicity="British",
        client_name="Mia",
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
    assert res.json()["status"] == "CONFIRMED"

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
