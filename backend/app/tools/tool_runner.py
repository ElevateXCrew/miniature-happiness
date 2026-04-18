"""
Deterministic backend tool runner.

This module exposes all 19 tools from TOOL_CATALOG.md as callable async functions.
Each function validates inputs, delegates to the appropriate service, and returns
a structured dict result that the LLM orchestration layer can include in the chat.

The LLM NEVER mutates state directly — it only calls these functions.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.core.config import settings
from app.models.enums import (
    ActorType,
    AwaitingReviewFrom,
    BookingStatus,
    Channel,
    NotificationChannel,
    NotificationTargetType,
)
from app.repositories.client_repo import ClientRepository
from app.repositories.session_repo import SessionRepository
from app.services.availability_service import AvailabilityService
from app.services.booking_service import BookingService
from app.services.media_service import MediaService
from app.services.notification_service import NotificationService
from app.services.worker_service import WorkerService


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **data}


def _err(message: str) -> dict[str, Any]:
    return {"ok": False, "error": message}


_STRICT_ISO_MINUTE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?(Z|[+-]\d{2}:\d{2})?$"
)
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_iso_datetime(value: str) -> tuple[datetime | None, str | None]:
    raw = value.strip()

    # Date-only: ask the LLM/user for a time component
    if _DATE_ONLY.match(raw):
        return None, "Please specify a time as well. Use format like 2026-04-18T20:30."

    # Accept both 'T' and space separator between date and time
    normalized_raw = raw.replace(" ", "T", 1) if " " in raw and "T" not in raw else raw

    if not _STRICT_ISO_MINUTE.match(normalized_raw):
        return None, "Invalid datetime format. Use ISO format like 2026-04-18T20:30."

    normalized = normalized_raw[:-1] + "+00:00" if normalized_raw.endswith("Z") else normalized_raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None, "Invalid datetime format. Use ISO format like 2026-04-18T20:30."

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)

    return parsed, None


class ToolRunner:
    """
    Wraps all deterministic backend tools.
    Instantiated per-request with the current DB session.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # 1. Identity and Session
    # ------------------------------------------------------------------

    async def get_or_create_client_by_phone(self, phone_e164: str) -> dict[str, Any]:
        repo = ClientRepository(self.db)
        client, created = await repo.get_or_create(phone_e164)
        return _ok(
            {
                "client_id": str(client.id),
                "phone_e164": client.phone_e164,
                "display_name": client.display_name,
                "is_blocked": client.is_blocked,
                "created": created,
            }
        )

    async def get_or_create_active_session(
        self, client_id: str, worker_id: str, channel: str
    ) -> dict[str, Any]:
        repo = SessionRepository(self.db)
        try:
            session, created = await repo.get_or_create(
                client_id=uuid.UUID(client_id),
                worker_id=uuid.UUID(worker_id),
                channel=Channel(channel),
            )
        except ValueError as e:
            return _err(str(e))
        return _ok(
            {
                "session_id": str(session.id),
                "state": session.state.value,
                "active_booking_id": str(session.active_booking_id)
                if session.active_booking_id
                else None,
                "created": created,
            }
        )

    # ------------------------------------------------------------------
    # 2. Booking Data Collection
    # ------------------------------------------------------------------

    async def get_required_next_field(self, booking_id: str) -> dict[str, Any]:
        from app.repositories.booking_repo import BookingRepository

        repo = BookingRepository(self.db)
        booking = await repo.get_by_id(uuid.UUID(booking_id))
        if not booking:
            return _err(f"Booking {booking_id} not found.")
        svc = BookingService(self.db)
        field = svc.get_next_required_field(booking)
        return _ok({"next_required_field": field, "all_required_collected": field is None})

    async def update_booking_field(
        self, booking_id: str, field_name: str, field_value: Any
    ) -> dict[str, Any]:
        svc = BookingService(self.db)
        booking, errors = await svc.update_field(
            booking_id=uuid.UUID(booking_id),
            field_name=field_name,
            field_value=field_value,
            actor_type=ActorType.AGENT,
        )
        if errors:
            return _err("; ".join(errors))
        return _ok({"booking_id": booking_id, "field_updated": field_name})

    async def validate_booking_fields(self, booking_id: str) -> dict[str, Any]:
        from app.repositories.booking_repo import BookingRepository

        repo = BookingRepository(self.db)
        booking = await repo.get_by_id(uuid.UUID(booking_id))
        if not booking:
            return _err(f"Booking {booking_id} not found.")
        svc = BookingService(self.db)
        result = svc.validate_fields(booking)
        return _ok(
            {
                "complete": result.complete,
                "next_required_field": result.next_required_field,
                "errors": result.errors,
            }
        )

    # ------------------------------------------------------------------
    # 3. Availability and Slot Management
    # ------------------------------------------------------------------

    async def check_availability(
        self, worker_id: str, start_at: str, duration_minutes: int
    ) -> dict[str, Any]:
        svc = AvailabilityService(self.db)
        start_dt, parse_error = _parse_iso_datetime(start_at)
        if parse_error is not None or start_dt is None:
            metrics.incr("tool_input_validation_failed_total")
            return _err(parse_error or "Invalid datetime format.")
        result = await svc.check(
            worker_id=uuid.UUID(worker_id),
            proposed_start=start_dt,
            duration_minutes=duration_minutes,
        )
        return _ok(
            {
                "available": result.available,
                "conflict_reason": result.conflict_reason,
                "suggested_start": result.suggested_start.isoformat()
                if result.suggested_start
                else None,
            }
        )

    async def reserve_tentative_slot(self, booking_id: str) -> dict[str, Any]:
        from app.repositories.booking_repo import BookingRepository

        repo = BookingRepository(self.db)
        booking = await repo.get_by_id(uuid.UUID(booking_id))
        if not booking:
            return _err(f"Booking {booking_id} not found.")
        if not booking.scheduled_start_at or not booking.duration_minutes:
            return _err("Booking must have scheduled_start_at and duration_minutes set first.")
        svc = AvailabilityService(self.db)
        result = await svc.reserve_tentative(
            worker_id=booking.worker_id,
            booking_id=uuid.UUID(booking_id),
            proposed_start=booking.scheduled_start_at,
            duration_minutes=booking.duration_minutes,
        )
        return _ok({"available": result.available, "conflict_reason": result.conflict_reason})

    async def release_slot(self, booking_id: str, reason: str) -> dict[str, Any]:
        # Slot is implicitly released when booking moves to CANCELLED/REJECTED/COMPLETED.
        from app.repositories.audit_repo import AuditRepository

        audit = AuditRepository(self.db)
        await audit.log(
            entity_type="booking",
            entity_id=uuid.UUID(booking_id),
            event_type="slot_released",
            actor_type=ActorType.SYSTEM,
            metadata={"reason": reason},
        )
        return _ok({"booking_id": booking_id, "released": True, "reason": reason})

    # ------------------------------------------------------------------
    # 4. Lifecycle Actions
    # ------------------------------------------------------------------

    async def submit_booking_for_review(
        self, booking_id: str, reviewer: str = "admin"
    ) -> dict[str, Any]:
        svc = BookingService(self.db)
        try:
            reviewer_enum = AwaitingReviewFrom(reviewer)
        except ValueError:
            reviewer_enum = AwaitingReviewFrom.ADMIN
        booking, errors = await svc.submit_for_review(
            booking_id=uuid.UUID(booking_id),
            reviewer=reviewer_enum,
        )
        if errors:
            return _err("; ".join(errors))
        return _ok({"booking_id": booking_id, "status": booking.status.value if booking else None})

    async def set_booking_status(
        self,
        booking_id: str,
        status: str,
        actor_type: str,
        actor_ref: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        svc = BookingService(self.db)
        try:
            status_enum = BookingStatus(status)
            actor_enum = ActorType(actor_type)
        except ValueError as e:
            return _err(str(e))
        booking, errors = await svc.set_status(
            booking_id=uuid.UUID(booking_id),
            status=status_enum,
            actor_type=actor_enum,
            actor_ref=actor_ref,
            note=note,
        )
        if errors:
            return _err("; ".join(errors))
        return _ok({"booking_id": booking_id, "new_status": booking.status.value})

    async def complete_booking_early(
        self, booking_id: str, actor_ref: str | None = None
    ) -> dict[str, Any]:
        svc = BookingService(self.db)
        booking, errors = await svc.complete_early(
            booking_id=uuid.UUID(booking_id), actor_ref=actor_ref
        )
        if errors:
            return _err("; ".join(errors))
        return _ok({"booking_id": booking_id, "status": "COMPLETED"})

    # ------------------------------------------------------------------
    # 5. Channel and Messaging
    # ------------------------------------------------------------------

    async def send_client_message(
        self,
        client_id: str,
        channel: str,
        text: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # Actual Twilio send is implemented in Phase 2.
        # For Phase 1 this is a stub that logs intent.
        from app.repositories.audit_repo import AuditRepository

        audit = AuditRepository(self.db)
        await audit.log(
            entity_type="client",
            entity_id=uuid.UUID(client_id),
            event_type="outbound_message_queued",
            actor_type=ActorType.AGENT,
            metadata={"channel": channel, "text": text, "context": context or {}},
        )
        return _ok({"client_id": client_id, "channel": channel, "queued": True, "stub": True})

    async def route_media_request_to_whatsapp(self, client_id: str) -> dict[str, Any]:
        return await self.send_client_message(
            client_id=client_id,
            channel="sms",
            text="Can you send that over on WhatsApp using this same number? Thanks!",
            context={"reason": "media_required"},
        )

    # ------------------------------------------------------------------
    # 6. Media
    # ------------------------------------------------------------------

    async def attach_media_to_session_or_booking(
        self, client_id: str, session_id: str, media_payload: dict[str, Any]
    ) -> dict[str, Any]:
        svc = MediaService(self.db)
        media = await svc.attach(
            client_id=uuid.UUID(client_id),
            session_id=uuid.UUID(session_id),
            source_url=media_payload.get("source_url", ""),
            channel=Channel(media_payload.get("channel", "whatsapp")),
            media_type=media_payload.get("media_type"),
            twilio_media_sid=media_payload.get("twilio_media_sid"),
            booking_id=uuid.UUID(media_payload["booking_id"])
            if media_payload.get("booking_id")
            else None,
        )
        return _ok({"media_id": str(media.id), "is_receipt": media.is_receipt})

    async def mark_media_as_receipt(
        self, media_id: str, booking_id: str | None = None
    ) -> dict[str, Any]:
        svc = MediaService(self.db)
        media = await svc.mark_as_receipt(
            media_id=uuid.UUID(media_id),
            booking_id=uuid.UUID(booking_id) if booking_id else None,
        )
        if not media:
            return _err(f"Media {media_id} not found.")
        return _ok(
            {
                "media_id": media_id,
                "booking_id": str(media.booking_id) if media.booking_id else None,
                "is_receipt": media.is_receipt,
            }
        )

    # ------------------------------------------------------------------
    # 7. Notifications and Reminders
    # ------------------------------------------------------------------

    async def create_notification(
        self,
        target_type: str,
        target_ref: str,
        template_key: str,
        payload: dict[str, Any],
        send_at: str,
        booking_id: str | None = None,
        channel: str = "in_app",
    ) -> dict[str, Any]:
        svc = NotificationService(self.db)
        notif = await svc.create(
            target_type=NotificationTargetType(target_type),
            target_ref=target_ref,
            template_key=template_key,
            payload=payload,
            send_at=datetime.fromisoformat(send_at),
            booking_id=uuid.UUID(booking_id) if booking_id else None,
            channel=NotificationChannel(channel),
        )
        return _ok({"notification_id": str(notif.id), "status": notif.status.value})

    async def schedule_booking_reminders(
        self, booking_id: str, minutes_before: int = settings.reminder_minutes_before
    ) -> dict[str, Any]:
        svc = NotificationService(self.db)
        notifications = await svc.schedule_booking_reminders(
            booking_id=uuid.UUID(booking_id), minutes_before=minutes_before
        )
        return _ok(
            {
                "booking_id": booking_id,
                "reminders_created": len(notifications),
                "notification_ids": [str(n.id) for n in notifications],
            }
        )

    # ------------------------------------------------------------------
    # 8. Worker Commands
    # ------------------------------------------------------------------

    async def process_worker_command(self, worker_id: str, message_text: str) -> dict[str, Any]:
        svc = WorkerService(self.db)
        result = await svc.process_command(
            worker_id=uuid.UUID(worker_id), message_text=message_text
        )
        return _ok({"success": result.success, "message": result.message})

    async def set_worker_availability_override(
        self, worker_id: str, from_at: str, to_at: str, mode: str
    ) -> dict[str, Any]:
        svc = WorkerService(self.db)
        result = await svc.set_availability_override(
            worker_id=uuid.UUID(worker_id),
            from_at=datetime.fromisoformat(from_at),
            to_at=datetime.fromisoformat(to_at),
            mode=mode,
        )
        return _ok({"success": result.success, "message": result.message})
