import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking
from app.models.client import Client
from app.models.conversation_session import ConversationSession
from app.models.enums import (
    BookingStatus,
    BookingType,
    Channel,
    ConversationState,
    MessageDirection,
    SenderType,
)
from app.models.message import Message
from app.models.worker import Worker
from app.services.agent_runtime import AgentRuntimeService


@pytest.mark.asyncio
async def test_agent_process_incoming_is_idempotent(client: AsyncClient) -> None:
    payload = {
        "channel": "sms",
        "phone_e164": "+447700900001",
        "inbound_text": "hi babe",
        "message_sid": "SM_PHASE2_001",
    }

    first = await client.post("/agent/process-incoming", json=payload)
    assert first.status_code == 200
    first_body = first.json()
    assert first_body["duplicate"] is False
    assert first_body["session_id"] is not None
    assert first_body["client_id"] is not None
    assert first_body["response_text"]

    second = await client.post("/agent/process-incoming", json=payload)
    assert second.status_code == 200
    second_body = second.json()
    assert second_body["duplicate"] is True
    assert second_body["replayed"] is True
    assert second_body["response_text"] == first_body["response_text"]


@pytest.mark.asyncio
async def test_cross_channel_continuity_uses_single_client_identity(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    phone = "+447700900123"
    sms_payload = {
        "channel": "sms",
        "phone_e164": phone,
        "inbound_text": "I want to book",
        "message_sid": "SM_PHASE2_010",
    }
    whatsapp_payload = {
        "channel": "whatsapp",
        "phone_e164": phone,
        "inbound_text": "tomorrow 20:00",
        "message_sid": "SM_PHASE2_011",
    }

    sms_res = await client.post("/agent/process-incoming", json=sms_payload)
    wa_res = await client.post("/agent/process-incoming", json=whatsapp_payload)
    assert sms_res.status_code == 200
    assert wa_res.status_code == 200

    client_count_result = await db.execute(select(func.count()).select_from(Client))
    assert client_count_result.scalar_one() == 1

    session_count_result = await db.execute(select(func.count()).select_from(ConversationSession))
    assert session_count_result.scalar_one() == 1

    session_result = await db.execute(select(ConversationSession))
    session = session_result.scalar_one()
    assert session.last_channel == Channel.WHATSAPP


@pytest.mark.asyncio
async def test_twilio_sms_webhook_parses_form_and_handles_duplicates(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "twilio_validate_signature", False)

    payload = {
        "MessageSid": "SM_PHASE2_WEBHOOK_001",
        "From": "+447700900222",
        "Body": "hello",
        "NumMedia": "0",
    }
    first = await client.post("/webhooks/twilio/sms", data=payload)
    assert first.status_code == 200
    assert first.headers["content-type"].startswith("application/xml")
    assert "<Response" in first.text

    second = await client.post("/webhooks/twilio/sms", data=payload)
    assert second.status_code == 200
    assert "<Response" in second.text

    inbound_count = await db.scalar(
        select(func.count())
        .select_from(Message)
        .where(Message.twilio_message_sid == payload["MessageSid"])
    )
    assert inbound_count == 1


@pytest.mark.asyncio
async def test_twilio_sms_with_media_routes_to_whatsapp_prompt(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "twilio_validate_signature", False)

    payload = {
        "MessageSid": f"SM_PHASE2_MEDIA_{uuid.uuid4().hex}",
        "From": "+447700900333",
        "Body": "sending receipt",
        "NumMedia": "1",
        "MediaUrl0": "https://example.com/r.jpg",
        "MediaContentType0": "image/jpeg",
        "MediaSid0": "ME_TEST_001",
    }
    response = await client.post("/webhooks/twilio/sms", data=payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    assert "<Response" in response.text

    saved_message_result = await db.execute(
        select(Message).where(Message.twilio_message_sid == payload["MessageSid"])
    )
    saved_message = saved_message_result.scalar_one()
    assert saved_message.raw_payload is not None
    assert saved_message.raw_payload.get("MediaUrl0") == payload["MediaUrl0"]


@pytest.mark.asyncio
async def test_check_availability_tool_call_patches_missing_worker_id(
    db: AsyncSession,
) -> None:
    runtime = AgentRuntimeService(db)
    result = await runtime._execute_tool(
        "check_availability",
        {
            "start_at": "2099-01-01T20:00",
            "duration_minutes": 60,
        },
        client_id=uuid.uuid4(),
        worker_id=uuid.uuid4(),
        channel=Channel.WHATSAPP,
    )

    assert result["ok"] is True
    assert "available" in result


@pytest.mark.asyncio
async def test_check_availability_tool_call_overrides_invalid_worker_id(
    db: AsyncSession,
) -> None:
    runtime = AgentRuntimeService(db)
    result = await runtime._execute_tool(
        "check_availability",
        {
            "worker_id": "alysha",
            "start_at": "2099-01-01T20:00",
            "duration_minutes": 60,
        },
        client_id=uuid.uuid4(),
        worker_id=uuid.uuid4(),
        channel=Channel.WHATSAPP,
    )

    assert result["ok"] is True
    assert "available" in result


@pytest.mark.asyncio
async def test_check_availability_auto_creates_draft_booking_for_active_session(
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

    runtime = AgentRuntimeService(db)
    result = await runtime._execute_tool(
        "check_availability",
        {
            "start_at": "2099-01-01T20:00",
            "duration_minutes": 60,
        },
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
    )

    assert result["ok"] is True

    booking_result = await db.execute(
        select(Booking).where(
            Booking.session_id == session.id,
            Booking.status == BookingStatus.DRAFT,
        )
    )
    booking = booking_result.scalar_one_or_none()
    assert booking is not None
    assert booking.duration_minutes == 60

    refreshed_session = await db.get(ConversationSession, session.id)
    assert refreshed_session is not None
    assert refreshed_session.active_booking_id == booking.id


@pytest.mark.asyncio
async def test_llm_yes_reply_submits_active_draft_for_review(
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, client])
    await db.flush()

    session = ConversationSession(
        client_id=client.id,
        worker_id=worker.id,
        state=ConversationState.AWAITING_CLIENT_CONFIRMATION,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=datetime.now(UTC) + timedelta(days=1),
        duration_minutes=60,
        scheduled_end_at=datetime.now(UTC) + timedelta(days=1, hours=1),
        client_age=24,
        client_ethnicity="British",
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    outbound_prompt = Message(
        session_id=session.id,
        direction=MessageDirection.OUTBOUND,
        channel=Channel.WHATSAPP,
        sender_type=SenderType.AGENT,
        body="Just to confirm: tomorrow 8pm for 1 hour. Reply yes to confirm.",
    )
    db.add(outbound_prompt)
    await db.flush()

    runtime = AgentRuntimeService(db)
    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="yes",
    )

    assert "sent it for review" in reply.text.lower()

    refreshed_booking = await db.get(Booking, booking.id)
    assert refreshed_booking is not None
    assert refreshed_booking.status == BookingStatus.PENDING_REVIEW
