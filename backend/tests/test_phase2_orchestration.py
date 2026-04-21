import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.booking import Booking
from app.models.booking_media import BookingMedia
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
async def test_twilio_whatsapp_with_media_sends_ack_and_marks_receipt(
    client: AsyncClient,
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services.media_service import MediaService

    monkeypatch.setattr(settings, "twilio_validate_signature", False)
    monkeypatch.setattr(settings, "openai_api_key", "")

    async def _fake_fetch(self: MediaService, **_: object) -> str | None:
        return None

    monkeypatch.setattr(MediaService, "_persist_media_file", _fake_fetch)

    payload = {
        "MessageSid": f"SM_PHASE2_WA_MEDIA_{uuid.uuid4().hex}",
        "From": "whatsapp:+447700900334",
        "Body": "",
        "NumMedia": "1",
        "MediaUrl0": "https://example.com/screenshot.jpg",
        "MediaContentType0": "image/jpeg",
        "MediaSid0": "ME_TEST_WA_001",
    }
    response = await client.post("/webhooks/twilio/whatsapp", data=payload)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")

    outbound_result = await db.execute(
        select(Message)
        .where(Message.direction == MessageDirection.OUTBOUND)
        .order_by(Message.created_at.desc())
    )
    outbound = outbound_result.scalars().first()
    assert outbound is not None
    assert "received" in (outbound.body or "").lower()
    assert "photo" in (outbound.body or "").lower() or "screenshot" in (outbound.body or "").lower()

    media_result = await db.execute(select(BookingMedia).where(BookingMedia.twilio_media_sid == "ME_TEST_WA_001"))
    media = media_result.scalar_one_or_none()
    assert media is not None
    assert media.is_receipt is True


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
        inbound_text="I want to book for tomorrow",
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
        inbound_text="Can I book a slot?",
    )

    assert result["ok"] is True
    assert "available" in result


@pytest.mark.asyncio
async def test_age_extraction_requires_explicit_age_statement(db: AsyncSession) -> None:
    runtime = AgentRuntimeService(db)

    assert runtime._extract_age("I am available at 19:00 tonight") is None
    assert runtime._extract_age("I am 24 years old") == 24


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
        inbound_text="I want to book tomorrow at 8pm",
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
    # Default availability check duration should not skip explicit duration collection.
    assert booking.duration_minutes is None

    refreshed_booking = await db.get(Booking, booking.id)
    assert refreshed_booking is not None
    assert runtime.booking_service.get_next_required_field(refreshed_booking) == "booking_type"

    refreshed_session = await db.get(ConversationSession, session.id)
    assert refreshed_session is not None
    assert refreshed_session.active_booking_id == booking.id


@pytest.mark.asyncio
async def test_check_availability_rejected_without_booking_intent_when_no_active_draft(
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
        inbound_text="Hi",
    )

    assert result["ok"] is False
    assert "booking intent" in str(result.get("error", "")).lower()


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
        client_size_inches=5,
        alone_policy_confirmed=True,
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

    assert "finalizing" in reply.text.lower()

    refreshed_booking = await db.get(Booking, booking.id)
    assert refreshed_booking is not None
    assert refreshed_booking.status == BookingStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_sync_draft_from_inbound_sets_booking_type(
    db: AsyncSession,
) -> None:
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

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    await runtime._sync_draft_from_inbound(session_id=session.id, inbound_text="Incall")

    refreshed_booking = await db.get(Booking, booking.id)
    assert refreshed_booking is not None
    assert refreshed_booking.booking_type == BookingType.INCALL


@pytest.mark.asyncio
async def test_pre_capture_required_field_from_inbound_updates_age(
    db: AsyncSession,
) -> None:
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

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    await runtime._pre_capture_required_field_from_inbound(
        session_id=session.id,
        inbound_text="I am 24 babe",
    )

    refreshed_booking = await db.get(Booking, booking.id)
    assert refreshed_booking is not None
    assert refreshed_booking.client_age == 24
    assert runtime.booking_service.get_next_required_field(refreshed_booking) == "client_ethnicity"


@pytest.mark.asyncio
async def test_pre_capture_alone_policy_accepts_ok_reply(
    db: AsyncSession,
) -> None:
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

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
        client_age=24,
        client_ethnicity="British",
        client_size_inches=4,
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    await runtime._pre_capture_required_field_from_inbound(
        session_id=session.id,
        inbound_text="ok that's fine",
    )

    refreshed_booking = await db.get(Booking, booking.id)
    assert refreshed_booking is not None
    assert refreshed_booking.alone_policy_confirmed is True


@pytest.mark.asyncio
async def test_update_booking_field_rejects_out_of_order_hallucinated_save(
    db: AsyncSession,
) -> None:
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

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    result = await runtime._execute_tool(
        "update_booking_field",
        {
            "booking_id": str(booking.id),
            "field_name": "client_size_inches",
            "field_value": 4,
        },
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="ok than book my session",
    )

    assert result["ok"] is False
    assert "collect" in str(result.get("error", "")).lower()


@pytest.mark.asyncio
async def test_override_redundant_time_question_when_time_already_known(
    db: AsyncSession,
) -> None:
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

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    overridden = await runtime._override_redundant_prompt_for_booking(
        session_id=session.id,
        llm_content="Ok babe. What time do you prefer?",
    )

    assert "what time" not in overridden.lower()
    assert overridden == "Confirm your age for me please (18+)."


@pytest.mark.asyncio
async def test_llm_greeting_does_not_force_booking_prompt_when_idle(
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
    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="Hi",
    )

    assert "date and time" not in reply.text.lower()
    assert "hi babe" in reply.text.lower()


@pytest.mark.asyncio
async def test_llm_yes_when_awaiting_confirmation_submits_without_recent_prompt_match(
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

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
        client_age=21,
        client_ethnicity="Asian",
        client_size_inches=5,
        alone_policy_confirmed=True,
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="Yes",
    )

    assert "finalizing" in reply.text.lower()
    refreshed_booking = await db.get(Booking, booking.id)
    assert refreshed_booking is not None
    assert refreshed_booking.status == BookingStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_admin_media_list_returns_entries_with_client_phone(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.IDLE,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    media_one = BookingMedia(
        client_id=person.id,
        session_id=session.id,
        booking_id=None,
        channel=Channel.WHATSAPP,
        media_type="image/jpeg",
        source_url="https://example.com/one.jpg",
        storage_url="447700000001/one.jpg",
        is_receipt=False,
    )
    media_two = BookingMedia(
        client_id=person.id,
        session_id=session.id,
        booking_id=None,
        channel=Channel.WHATSAPP,
        media_type="image/png",
        source_url="https://example.com/two.png",
        storage_url="447700000001/two.png",
        is_receipt=True,
    )
    db.add_all([media_one, media_two])
    await db.commit()

    response = await client.get("/admin/media")
    assert response.status_code == 200
    rows = response.json()

    matching = [r for r in rows if r["client_id"] == str(person.id)]
    assert len(matching) == 2
    assert all(r["client_phone_e164"] == person.phone_e164 for r in matching)


@pytest.mark.asyncio
async def test_pending_review_status_guard_avoids_reasking_fields(
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, client])
    await db.flush()

    session = ConversationSession(
        client_id=client.id,
        worker_id=worker.id,
        state=ConversationState.WAITING_REVIEW,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
        client_age=21,
        client_ethnicity="Asian",
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="Yes babe",
    )

    assert "with admin now" in reply.text.lower()
    assert "confirm your age" not in reply.text.lower()
