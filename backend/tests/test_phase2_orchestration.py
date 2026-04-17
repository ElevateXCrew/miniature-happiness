import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.client import Client
from app.models.conversation_session import ConversationSession
from app.models.enums import Channel
from app.models.message import Message


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
