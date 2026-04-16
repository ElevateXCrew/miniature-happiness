from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.enums import Channel
from app.services.conversation_orchestrator import ConversationOrchestrator
from app.services.twilio_gateway import TwilioGateway

router = APIRouter(prefix="/webhooks/twilio", tags=["twilio"])


def _parse_media(form_data: dict[str, Any]) -> list[dict[str, Any]]:
    raw_count = str(form_data.get("NumMedia", "0") or "0")
    try:
        count = int(raw_count)
    except ValueError:
        count = 0

    media: list[dict[str, Any]] = []
    for idx in range(count):
        source_url = str(form_data.get(f"MediaUrl{idx}", "") or "").strip()
        media_type = str(form_data.get(f"MediaContentType{idx}", "") or "").strip() or None
        media_sid = str(form_data.get(f"MediaSid{idx}", "") or "").strip() or None
        if source_url:
            media.append(
                {
                    "source_url": source_url,
                    "media_type": media_type,
                    "twilio_media_sid": media_sid,
                }
            )
    return media


async def _handle_twilio_channel(
    *,
    request: Request,
    db: AsyncSession,
    channel: Channel,
) -> Response:
    gateway = TwilioGateway()
    form = await request.form()
    form_data = {key: str(value) for key, value in form.multi_items()}

    valid_signature = await gateway.validate_signature(request, form_data)
    if not valid_signature:
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    message_sid = form_data.get("MessageSid", "").strip()
    from_phone = form_data.get("From", "").strip()
    inbound_text = form_data.get("Body", "").strip()

    if not message_sid or not from_phone:
        raise HTTPException(status_code=422, detail="Missing required Twilio fields")

    orchestrator = ConversationOrchestrator(db)
    result = await orchestrator.process_incoming(
        channel=channel,
        phone_e164=from_phone,
        inbound_text=inbound_text,
        message_sid=message_sid,
        raw_payload=form_data,
        media_items=_parse_media(form_data),
    )

    twiml = gateway.to_twiml(result.response_text)
    return Response(content=twiml, media_type="application/xml")


@router.post("/sms")
async def inbound_sms(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    return await _handle_twilio_channel(request=request, db=db, channel=Channel.SMS)


@router.post("/whatsapp")
async def inbound_whatsapp(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    return await _handle_twilio_channel(request=request, db=db, channel=Channel.WHATSAPP)
