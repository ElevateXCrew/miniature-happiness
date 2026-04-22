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

    media_result = await db.execute(
        select(BookingMedia).where(BookingMedia.twilio_media_sid == "ME_TEST_WA_001")
    )
    media = media_result.scalar_one_or_none()
    assert media is not None
    assert media.is_receipt is True


@pytest.mark.asyncio
async def test_whatsapp_media_ack_does_not_request_whatsapp_again(
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    out = await runtime._apply_media_ack_policy(
        session_id=session.id,
        channel=Channel.WHATSAPP,
        text="I have received your photo babe. Please send it on WhatsApp.",
    )

    assert "send it on whatsapp" not in out.lower()
    assert "received your photo" in out.lower() or "received your photo/screenshot" in out.lower()


@pytest.mark.asyncio
async def test_whatsapp_media_ack_does_not_claim_review_without_pending_context(
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    out = await runtime._apply_media_ack_policy(
        session_id=session.id,
        channel=Channel.WHATSAPP,
        text="Yes babe, got it! Just reviewing - I'll confirm soon 😊",
    )

    assert "just reviewing" not in out.lower()
    assert "i'll confirm soon" not in out.lower()
    assert "date and time" in out.lower()


@pytest.mark.asyncio
async def test_whatsapp_media_ack_keeps_review_reply_when_pending_context_exists(
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.WAITING_REVIEW,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    booking = Booking(
        client_id=person.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.OUTCALL,
        scheduled_start_at=datetime.now(UTC) + timedelta(days=1),
        duration_minutes=60,
        scheduled_end_at=datetime.now(UTC) + timedelta(days=1, hours=1),
        client_age=26,
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
    out = await runtime._apply_media_ack_policy(
        session_id=session.id,
        channel=Channel.WHATSAPP,
        text="Yes babe, got it! Just reviewing - I'll confirm soon 😊",
    )

    assert "just reviewing" in out.lower()


@pytest.mark.asyncio
async def test_whatsapp_media_ack_strips_review_wording_for_active_draft(
    db: AsyncSession,
) -> None:
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    booking = Booking(
        client_id=person.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.OUTCALL,
        scheduled_start_at=datetime.now(UTC) + timedelta(days=1),
        duration_minutes=60,
        scheduled_end_at=datetime.now(UTC) + timedelta(days=1, hours=1),
        client_age=26,
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
    out = await runtime._apply_media_ack_policy(
        session_id=session.id,
        channel=Channel.WHATSAPP,
        text="Yes babe, got it! Just reviewing - I'll confirm soon 😊",
    )

    assert "just reviewing" not in out.lower()
    assert "i'll confirm soon" not in out.lower()


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
async def test_update_booking_field_normalizes_aliases_and_values(
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

    booking_type_result = await runtime._execute_tool(
        "update_booking_field",
        {
            "booking_id": str(booking.id),
            "field_name": "booking_type",
            "field_value": "Incall",
        },
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="I want incall",
    )
    assert booking_type_result["ok"] is True

    size_result = await runtime._execute_tool(
        "update_booking_field",
        {
            "booking_id": str(booking.id),
            "field_name": "client_size",
            "field_value": "4 inches",
        },
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="size is 4",
    )
    # Guard should block out-of-order size save, but alias/value normalization should
    # avoid low-signal "Unknown field" tool failures.
    assert size_result["ok"] is False
    assert "unknown field" not in str(size_result.get("error", "")).lower()


@pytest.mark.asyncio
async def test_route_media_request_defaults_placeholder_client_id(
    db: AsyncSession,
) -> None:
    runtime = AgentRuntimeService(db)
    client_id = uuid.uuid4()
    result = await runtime._execute_tool(
        "route_media_request_to_whatsapp",
        {"client_id": "client"},
        client_id=client_id,
        worker_id=uuid.uuid4(),
        channel=Channel.SMS,
        inbound_text="can i send screenshot",
    )

    assert result["ok"] is True
    assert result.get("channel") == "sms"
    assert result.get("queued") is True


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
async def test_llm_yes_reply_submits_outcall_and_sets_default_advance(
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
        booking_type=BookingType.OUTCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
        outcall_address="Hotel 21, London",
        client_age=25,
        client_ethnicity="Asian",
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
        body="Just to confirm: outcall tomorrow 8pm for 1 hour. Reply yes to confirm.",
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
    assert refreshed_booking.advance_required_gbp is not None
    assert float(refreshed_booking.advance_required_gbp) == 50.0


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
async def test_pre_capture_bulk_outcall_message_captures_address_and_ethnicity(
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
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    await runtime._pre_capture_required_field_from_inbound(
        session_id=session.id,
        inbound_text=(
            "Outcall: central bermighem streat 5 house 20\n"
            "duration: 1hr\n"
            "age: 21\n"
            "ethnicity: asian\n"
            "size: 4"
        ),
    )

    refreshed_booking = await db.get(Booking, booking.id)
    assert refreshed_booking is not None
    assert refreshed_booking.booking_type == BookingType.OUTCALL
    assert (refreshed_booking.outcall_address or "").lower().startswith("central")
    assert refreshed_booking.duration_minutes == 60
    assert refreshed_booking.client_age == 21
    assert refreshed_booking.client_ethnicity is not None
    assert "asian" in refreshed_booking.client_ethnicity.lower()
    assert refreshed_booking.client_size_inches == 4
    assert (
        runtime.booking_service.get_next_required_field(refreshed_booking)
        == "alone_policy_confirmed"
    )


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
async def test_llm_reply_is_not_server_overridden_when_time_already_known(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    async def _fake_create(**_: object) -> object:
        msg = type("Msg", (), {"content": "Ok babe. What time do you prefer?", "tool_calls": None})
        choice = type("Choice", (), {"message": msg})
        return type("Resp", (), {"choices": [choice]})

    fake_client = type(
        "FakeClient",
        (),
        {
            "chat": type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": staticmethod(_fake_create)},
                    )()
                },
            )()
        },
    )()
    monkeypatch.setattr(runtime, "_get_openai_client", lambda: fake_client)

    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="Anything",
    )

    assert "what time" in reply.text.lower()
    assert "confirm your age" not in reply.text.lower()


@pytest.mark.asyncio
async def test_llm_greeting_does_not_force_booking_prompt_when_idle(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    async def _fake_create(**_: object) -> object:
        msg = type("Msg", (), {"content": "Hi babe 😘", "tool_calls": None})
        choice = type("Choice", (), {"message": msg})
        return type("Resp", (), {"choices": [choice]})

    fake_client = type(
        "FakeClient",
        (),
        {
            "chat": type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": staticmethod(_fake_create)},
                    )()
                },
            )()
        },
    )()
    monkeypatch.setattr(runtime, "_get_openai_client", lambda: fake_client)

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
async def test_collection_flow_does_not_force_consent_prompt(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
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

    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        scheduled_start_at=datetime.now(UTC) + timedelta(days=1),
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    runtime = AgentRuntimeService(db)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    async def _fake_create(**_: object) -> object:
        msg = type(
            "Msg",
            (),
            {
                "content": "Of course babe, would you prefer incall or outcall?",
                "tool_calls": None,
            },
        )
        choice = type("Choice", (), {"message": msg})
        return type("Resp", (), {"choices": [choice]})

    fake_client = type(
        "FakeClient",
        (),
        {
            "chat": type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": staticmethod(_fake_create)},
                    )()
                },
            )()
        },
    )()
    monkeypatch.setattr(runtime, "_get_openai_client", lambda: fake_client)

    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="I want to book",
    )

    assert "collect some information" not in reply.text.lower()
    assert "incall or outcall" in reply.text.lower()


@pytest.mark.asyncio
async def test_collection_flow_does_not_force_bulk_prompt_after_yes(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
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

    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        scheduled_start_at=datetime.now(UTC) + timedelta(days=1),
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    _ = Message(
        session_id=session.id,
        direction=MessageDirection.OUTBOUND,
        channel=Channel.WHATSAPP,
        sender_type=SenderType.AGENT,
        body="I need to collect some information for the booking, if you don't mind?",
    )

    runtime = AgentRuntimeService(db)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    async def _fake_create(**_: object) -> object:
        msg = type(
            "Msg",
            (),
            {
                "content": "Perfect babe, just tell me if you'd like incall or outcall.",
                "tool_calls": None,
            },
        )
        choice = type("Choice", (), {"message": msg})
        return type("Resp", (), {"choices": [choice]})

    fake_client = type(
        "FakeClient",
        (),
        {
            "chat": type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": staticmethod(_fake_create)},
                    )()
                },
            )()
        },
    )()
    monkeypatch.setattr(runtime, "_get_openai_client", lambda: fake_client)

    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="yes",
    )

    assert "send these in one message" not in reply.text.lower()
    assert "incall or outcall" in reply.text.lower()


@pytest.mark.asyncio
async def test_collection_flow_handles_partial_details_without_bulk_intercept(
    db: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
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

    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        scheduled_start_at=datetime.now(UTC) + timedelta(days=1),
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    _ = Message(
        session_id=session.id,
        direction=MessageDirection.OUTBOUND,
        channel=Channel.WHATSAPP,
        sender_type=SenderType.AGENT,
        body=(
            "Perfect babe. Send these in one message: booking type (incall or outcall), "
            "duration, age, ethnicity, size, and confirm it'll be just you."
        ),
    )

    runtime = AgentRuntimeService(db)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")

    async def _fake_create(**_: object) -> object:
        msg = type(
            "Msg",
            (),
            {
                "content": "Thanks babe, would you prefer incall or outcall?",
                "tool_calls": None,
            },
        )
        choice = type("Choice", (), {"message": msg})
        return type("Resp", (), {"choices": [choice]})

    fake_client = type(
        "FakeClient",
        (),
        {
            "chat": type(
                "Chat",
                (),
                {
                    "completions": type(
                        "Completions",
                        (),
                        {"create": staticmethod(_fake_create)},
                    )()
                },
            )()
        },
    )()
    monkeypatch.setattr(runtime, "_get_openai_client", lambda: fake_client)

    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=client.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="I am 27 and Asian",
    )

    assert "send these in one message" not in reply.text.lower()
    assert "incall or outcall" in reply.text.lower()


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

# ---------------------------------------------------------------------------
# Context-aware age guard regression tests (Phase 4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_age_reply_after_age_prompt_is_captured(
    db: AsyncSession,
) -> None:
    """
    After Alysha asks for age, a plain numeric reply like "25" must be saved
    without triggering a re-ask loop.
    """
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=person.id,
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

    # Simulate Alysha's last outbound message being an age question.
    age_prompt = Message(
        session_id=session.id,
        direction=MessageDirection.OUTBOUND,
        channel=Channel.WHATSAPP,
        sender_type=SenderType.AGENT,
        body="Confirm your age for me please (18+).",
    )
    db.add(age_prompt)
    await db.flush()

    runtime = AgentRuntimeService(db)
    # Client replies with plain "25" - should be accepted.
    await runtime._pre_capture_required_field_from_inbound(
        session_id=session.id,
        inbound_text="25",
    )

    refreshed = await db.get(Booking, booking.id)
    assert refreshed is not None
    assert refreshed.client_age == 25, (
        "Plain '25' after age prompt must be captured as client_age"
    )
    # Next field must be client_ethnicity -- not client_age again (no re-ask loop).
    assert runtime.booking_service.get_next_required_field(refreshed) == "client_ethnicity"


@pytest.mark.asyncio
async def test_plain_age_without_age_prompt_context_is_blocked(
    db: AsyncSession,
) -> None:
    """
    A plain "25" reply must NOT be captured as age when Alysha's last message
    was not an age question.
    """
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=person.id,
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

    # Last outbound message is NOT an age question.
    non_age_prompt = Message(
        session_id=session.id,
        direction=MessageDirection.OUTBOUND,
        channel=Channel.WHATSAPP,
        sender_type=SenderType.AGENT,
        body="Would you prefer incall or outcall babe?",
    )
    db.add(non_age_prompt)
    await db.flush()

    runtime = AgentRuntimeService(db)
    await runtime._pre_capture_required_field_from_inbound(
        session_id=session.id,
        inbound_text="25",
    )

    refreshed = await db.get(Booking, booking.id)
    assert refreshed is not None
    assert refreshed.client_age is None, (
        "Plain '25' without age context must NOT be saved as client_age"
    )


@pytest.mark.asyncio
async def test_out_of_order_age_save_remains_blocked(
    db: AsyncSession,
) -> None:
    """
    Directly calling update_booking_field for client_age when the next required
    field is NOT client_age must still be blocked by the hallucination guard.
    """
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start_at = datetime.now(UTC) + timedelta(days=1)
    # booking_type is not yet set -> next required field is booking_type, not age
    booking = Booking(
        client_id=person.id,
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
    result = await runtime._execute_tool(
        "update_booking_field",
        {
            "booking_id": str(booking.id),
            "field_name": "client_age",
            "field_value": 25,
        },
        client_id=person.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="I am 25 years old",
    )

    assert result["ok"] is False
    assert "collect" in str(result.get("error", "")).lower()


@pytest.mark.asyncio
async def test_review_submission_reaches_admin_queue_non_regression(
    db: AsyncSession,
) -> None:
    """
    Non-regression: after all fields are collected and client confirms, the
    booking must transition to PENDING_REVIEW (admin queue).
    """
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.AWAITING_CLIENT_CONFIRMATION,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=person.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
        client_age=25,
        client_ethnicity="Asian",
        client_size_inches=5,
        alone_policy_confirmed=True,
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.flush()

    confirm_prompt = Message(
        session_id=session.id,
        direction=MessageDirection.OUTBOUND,
        channel=Channel.WHATSAPP,
        sender_type=SenderType.AGENT,
        body="Just to confirm - incall tomorrow for 60 mins. Reply yes to confirm.",
    )
    db.add(confirm_prompt)
    await db.flush()

    runtime = AgentRuntimeService(db)
    reply = await runtime._generate_llm_reply(
        session_id=session.id,
        client_id=person.id,
        worker_id=worker.id,
        channel=Channel.WHATSAPP,
        inbound_text="yes",
    )

    assert "finalizing" in reply.text.lower()
    refreshed = await db.get(Booking, booking.id)
    assert refreshed is not None
    assert refreshed.status == BookingStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_admin_approve_transitions_booking_to_confirmed_non_regression(
    client: AsyncClient,
    db: AsyncSession,
) -> None:
    """
    Non-regression: admin approve endpoint must transition a PENDING_REVIEW
    booking to CONFIRMED and return the updated status.
    """
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    person = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add_all([worker, person])
    await db.flush()

    session = ConversationSession(
        client_id=person.id,
        worker_id=worker.id,
        state=ConversationState.WAITING_REVIEW,
        last_channel=Channel.WHATSAPP,
    )
    db.add(session)
    await db.flush()

    start_at = datetime.now(UTC) + timedelta(days=1)
    booking = Booking(
        client_id=person.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.PENDING_REVIEW,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start_at,
        duration_minutes=60,
        scheduled_end_at=start_at + timedelta(minutes=60),
        client_age=25,
        client_ethnicity="Asian",
        client_size_inches=5,
        alone_policy_confirmed=True,
    )
    db.add(booking)
    await db.flush()

    session.active_booking_id = booking.id
    db.add(session)
    await db.commit()

    response = await client.post(f"/admin/bookings/{booking.id}/approve", json={})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "confirmed"
