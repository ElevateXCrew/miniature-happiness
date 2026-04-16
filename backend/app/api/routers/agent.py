import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.enums import Channel
from app.services.conversation_orchestrator import ConversationOrchestrator

router = APIRouter(prefix="/agent", tags=["agent"])


class ProcessIncomingBody(BaseModel):
    channel: Channel
    phone_e164: str
    inbound_text: str
    message_sid: str
    raw_payload: dict[str, Any] | None = None
    media_items: list[dict[str, Any]] = []


class SendMessageBody(BaseModel):
    client_id: uuid.UUID
    channel: Channel
    text: str
    metadata: dict[str, Any] | None = None


@router.post("/process-incoming")
async def process_incoming(body: ProcessIncomingBody, db: AsyncSession = Depends(get_db)) -> Any:
    orchestrator = ConversationOrchestrator(db)
    result = await orchestrator.process_incoming(
        channel=body.channel,
        phone_e164=body.phone_e164,
        inbound_text=body.inbound_text,
        message_sid=body.message_sid,
        raw_payload=body.raw_payload,
        media_items=body.media_items,
    )
    return {
        "duplicate": result.duplicate,
        "replayed": result.replayed,
        "response_text": result.response_text,
        "session_id": str(result.session_id) if result.session_id else None,
        "client_id": str(result.client_id) if result.client_id else None,
        "outbound_message_sid": result.outbound_message_sid,
    }


@router.post("/send-message")
async def send_message(body: SendMessageBody, db: AsyncSession = Depends(get_db)) -> Any:
    orchestrator = ConversationOrchestrator(db)
    result = await orchestrator.send_message(
        client_id=body.client_id,
        channel=body.channel,
        text=body.text,
        metadata=body.metadata,
    )
    if not result["ok"]:
        raise HTTPException(status_code=422, detail=result["error"])
    return result
