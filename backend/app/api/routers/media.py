"""
Media ingestion and admin media endpoints.
"""

import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_role
from app.core.config import settings
from app.db.engine import get_db
from app.models.enums import UserRole
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
    return {
        "media_id": str(media.id),
        "booking_id": str(media.booking_id) if media.booking_id else None,
        "channel": media.channel.value,
        "media_type": media.media_type,
        "twilio_media_sid": media.twilio_media_sid,
        "is_receipt": media.is_receipt,
        "source_url": media.source_url,
    }


@router.get("/admin/bookings/{booking_id}/media")
async def get_booking_media(
    booking_id: uuid.UUID,
    _: object = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from sqlalchemy import select

    from app.models.booking_media import BookingMedia

    result = await db.execute(select(BookingMedia).where(BookingMedia.booking_id == booking_id))
    media_list = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "channel": m.channel.value,
            "media_type": m.media_type,
            "source_url": f"/admin/media/{m.id}/content" if m.storage_url else m.source_url,
            "storage_url": m.storage_url,
            "is_receipt": m.is_receipt,
            "created_at": m.created_at.isoformat(),
        }
        for m in media_list
    ]


@router.get("/admin/media/{media_id}/content")
async def get_media_content(
    media_id: uuid.UUID,
    _: object = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from sqlalchemy import select

    from app.models.booking_media import BookingMedia

    result = await db.execute(select(BookingMedia).where(BookingMedia.id == media_id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")
    if not media.storage_url:
        raise HTTPException(status_code=404, detail="Stored media file not found")

    media_root = Path(__file__).resolve().parents[3] / settings.media_storage_root
    file_path = media_root / media.storage_url
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Stored media file not found")

    return FileResponse(path=file_path, media_type=media.media_type or None)


@router.post("/admin/media/{media_id}/mark-receipt")
async def mark_receipt(
    media_id: uuid.UUID,
    body: MarkReceiptBody = MarkReceiptBody(),
    _: object = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = MediaService(db)
    media = await svc.mark_as_receipt(media_id=media_id, booking_id=body.booking_id)
    if not media:
        raise HTTPException(status_code=404, detail="Media not found")
    return {"media_id": str(media_id), "is_receipt": media.is_receipt}
