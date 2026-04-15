"""
Media ingestion and receipt classification service.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking_media import BookingMedia
from app.models.enums import Channel
from app.repositories.booking_repo import BookingRepository
from app.repositories.session_repo import SessionRepository


class MediaService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.booking_repo = BookingRepository(db)
        self.session_repo = SessionRepository(db)

    async def attach(
        self,
        client_id: uuid.UUID,
        session_id: uuid.UUID,
        source_url: str,
        channel: Channel,
        media_type: str | None = None,
        twilio_media_sid: str | None = None,
        booking_id: uuid.UUID | None = None,
    ) -> BookingMedia:
        """
        Stores media metadata and links to booking if determinable.
        If booking_id not given, tries to resolve from active session.
        """
        if not booking_id:
            session = await self.session_repo.get_by_id(session_id)
            if session and session.active_booking_id:
                booking_id = session.active_booking_id

        media = BookingMedia(
            client_id=client_id,
            booking_id=booking_id,
            session_id=session_id,
            channel=channel,
            media_type=media_type,
            twilio_media_sid=twilio_media_sid,
            source_url=source_url,
        )
        self.db.add(media)
        await self.db.flush()
        return media

    async def mark_as_receipt(
        self, media_id: uuid.UUID, booking_id: uuid.UUID | None = None
    ) -> BookingMedia | None:
        from sqlalchemy import select

        result = await self.db.execute(select(BookingMedia).where(BookingMedia.id == media_id))
        media = result.scalar_one_or_none()
        if not media:
            return None
        media.is_receipt = True
        if booking_id:
            media.booking_id = booking_id
        self.db.add(media)
        await self.db.flush()
        return media
