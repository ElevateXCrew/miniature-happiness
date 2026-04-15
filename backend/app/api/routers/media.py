"""
Media ingestion and admin media endpoints.
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.services.media_service import MediaService

router = APIRouter(tags=["media"])


class TwilioMediaPayload(BaseModel):
    client_id: uuid.UUID
    session_id: uuid.UUID
    source_url: str
    channel: str = "whatsapp"
    media_type: str | None = None
    twilio_media_sid: str | None = None
    booking_id: uuid.UUID | None = None


class MarkReceiptBody(BaseModel):
    booking_id: uuid.UUID | None = None


@router.post("/media/twilio/ingest")
async def ingest_media(payload: TwilioMediaPayload, db: AsyncSession = Depends(get_db)) -> Any:
    from app.models.enums import Channel

    svc = MediaService(db)
    media = await svc.attach(
        client_id=payload.client_id,
        session_id=payload.session_id,
        source_url=payload.source_url,
        channel=Channel(payload.channel),
        media_type=payload.media_type,
        twilio_media_sid=payload.twilio_media_sid,
        booking_id=payload.booking_id,
    )
    return {"media_id": str(media.id), "is_receipt": media.is_receipt}


@router.get("/admin/bookings/{booking_id}/media")
async def get_booking_media(booking_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    from sqlalchemy import select

    from app.models.booking_media import BookingMedia

    result = await db.execute(select(BookingMedia).where(BookingMedia.booking_id == booking_id))
    media_list = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "channel": m.channel.value,
            "media_type": m.media_type,
            "source_url": m.source_url,
            "storage_url": m.storage_url,
            "is_receipt": m.is_receipt,
            "created_at": m.created_at.isoformat(),
        }
        for m in media_list
    ]


@router.post("/admin/media/{media_id}/mark-receipt")
async def mark_receipt(
    media_id: uuid.UUID,
    body: MarkReceiptBody = MarkReceiptBody(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = MediaService(db)
    media = await svc.mark_as_receipt(media_id=media_id, booking_id=body.booking_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return {"media_id": str(media_id), "is_receipt": media.is_receipt}
