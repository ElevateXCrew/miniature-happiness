"""
Media ingestion and receipt classification service.
"""

import mimetypes
import re
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.audit_event import AuditEvent
from app.models.booking_media import BookingMedia
from app.models.enums import ActorType, Channel
from app.repositories.booking_repo import BookingRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.session_repo import SessionRepository
from app.services.twilio_gateway import TwilioGateway


class MediaService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.booking_repo = BookingRepository(db)
        self.session_repo = SessionRepository(db)
        self.client_repo = ClientRepository(db)
        self.twilio = TwilioGateway()

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

        normalized_source_url = source_url.strip()
        normalized_media_type = media_type.strip().lower() if media_type else None
        storage_url = await self._persist_media_file(
            client_id=client_id,
            source_url=normalized_source_url,
            media_type=normalized_media_type,
            twilio_media_sid=twilio_media_sid,
        )
        inferred_receipt = self._looks_like_receipt(
            source_url=normalized_source_url,
            media_type=normalized_media_type,
            twilio_media_sid=twilio_media_sid,
        )

        media = BookingMedia(
            client_id=client_id,
            booking_id=booking_id,
            session_id=session_id,
            channel=channel,
            media_type=normalized_media_type,
            twilio_media_sid=twilio_media_sid,
            source_url=normalized_source_url,
            storage_url=storage_url,
            is_receipt=inferred_receipt,
        )
        self.db.add(media)
        await self.db.flush()

        self.db.add(
            AuditEvent(
                entity_type="booking_media",
                entity_id=media.id,
                event_type="media_attached",
                actor_type=ActorType.SYSTEM,
                metadata_={
                    "client_id": str(client_id),
                    "session_id": str(session_id),
                    "booking_id": str(booking_id) if booking_id else None,
                    "channel": channel.value,
                    "media_type": normalized_media_type,
                    "twilio_media_sid": twilio_media_sid,
                    "source_url": normalized_source_url,
                    "storage_url": storage_url,
                    "is_receipt": inferred_receipt,
                },
            )
        )
        await self.db.flush()
        return media

    async def _persist_media_file(
        self,
        *,
        client_id: uuid.UUID,
        source_url: str,
        media_type: str | None,
        twilio_media_sid: str | None,
    ) -> str | None:
        try:
            content, response_media_type = await self.twilio.fetch_media_binary(source_url)
        except Exception:
            return None

        if not content:
            return None

        client = await self.client_repo.get_by_id(client_id)
        client_folder = self._client_folder_name(client.phone_e164 if client else str(client_id))
        media_root = Path(__file__).resolve().parents[2] / settings.media_storage_root
        client_dir = media_root / client_folder
        client_dir.mkdir(parents=True, exist_ok=True)

        ext = self._resolve_media_extension(media_type or response_media_type, source_url)
        file_stem = twilio_media_sid or str(uuid.uuid4())
        file_name = f"{file_stem}{ext}"
        file_path = client_dir / file_name
        file_path.write_bytes(content)

        return str(file_path.relative_to(media_root).as_posix())

    def _client_folder_name(self, phone: str) -> str:
        sanitized = re.sub(r"[^0-9+]", "", phone.strip())
        sanitized = sanitized.lstrip("+")
        return sanitized or "unknown"

    def _resolve_media_extension(self, media_type: str | None, source_url: str) -> str:
        if media_type:
            guessed = mimetypes.guess_extension(media_type.split(";", 1)[0].strip())
            if guessed:
                return ".jpg" if guessed == ".jpe" else guessed

        path = Path(source_url.split("?", 1)[0])
        if path.suffix:
            return path.suffix.lower()
        return ".bin"

    async def mark_as_receipt(
        self, media_id: uuid.UUID, booking_id: uuid.UUID | None = None
    ) -> BookingMedia | None:
        result = await self.db.execute(select(BookingMedia).where(BookingMedia.id == media_id))
        media = result.scalar_one_or_none()
        if not media:
            return None
        media.is_receipt = True
        if booking_id:
            media.booking_id = booking_id
        self.db.add(media)
        await self.db.flush()

        self.db.add(
            AuditEvent(
                entity_type="booking_media",
                entity_id=media.id,
                event_type="media_marked_receipt",
                actor_type=ActorType.SYSTEM,
                metadata_={
                    "booking_id": str(media.booking_id) if media.booking_id else None,
                    "source_url": media.source_url,
                },
            )
        )
        await self.db.flush()
        return media

    async def has_receipt_for_booking(self, booking_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(BookingMedia.id).where(
                BookingMedia.booking_id == booking_id,
                BookingMedia.is_receipt.is_(True),
            )
        )
        return result.scalar_one_or_none() is not None

    def _looks_like_receipt(
        self,
        *,
        source_url: str,
        media_type: str | None,
        twilio_media_sid: str | None,
    ) -> bool:
        receipt_markers = ("receipt", "proof", "advance", "payment", "bank", "transfer")
        haystacks: list[str] = [source_url.lower()]
        if media_type:
            haystacks.append(media_type.lower())
        if twilio_media_sid:
            haystacks.append(twilio_media_sid.lower())

        for marker in receipt_markers:
            if any(marker in value for value in haystacks):
                return True
        return False
