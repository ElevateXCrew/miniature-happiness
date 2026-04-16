"""
Notification service: queues and dispatches notifications, schedules reminders.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import (
    ActorType,
    BookingType,
    Channel,
    MessageDirection,
    NotificationChannel,
    NotificationStatus,
    NotificationTargetType,
    SenderType,
)
from app.models.message import Message
from app.models.notification import Notification
from app.repositories.booking_repo import BookingRepository
from app.repositories.client_repo import ClientRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.notification_repo import NotificationRepository
from app.repositories.session_repo import SessionRepository
from app.repositories.worker_repo import WorkerRepository
from app.services.twilio_gateway import TwilioGateway


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = NotificationRepository(db)
        self.booking_repo = BookingRepository(db)
        self.clients = ClientRepository(db)
        self.sessions = SessionRepository(db)
        self.workers = WorkerRepository(db)
        self.messages = MessageRepository(db)
        self.gateway = TwilioGateway()

    async def create(
        self,
        target_type: NotificationTargetType,
        target_ref: str,
        template_key: str,
        payload: dict,
        send_at: datetime,
        booking_id: uuid.UUID | None = None,
        channel: NotificationChannel = NotificationChannel.IN_APP,
    ) -> Notification:
        notification = Notification(
            booking_id=booking_id,
            target_type=target_type,
            target_ref=target_ref,
            channel=channel,
            template_key=template_key,
            payload=payload,
            status=NotificationStatus.QUEUED,
            send_at=send_at,
        )
        return await self.repo.save(notification)

    async def schedule_booking_reminders(
        self,
        booking_id: uuid.UUID,
        minutes_before: int = settings.reminder_minutes_before,
    ) -> list[Notification]:
        booking = await self.booking_repo.get_by_id(booking_id)
        if not booking or not booking.scheduled_start_at:
            return []

        send_at = booking.scheduled_start_at - timedelta(minutes=minutes_before)
        now = datetime.now(UTC)
        if send_at <= now:
            # Too late to schedule; fire immediately
            send_at = now

        is_outcall = booking.booking_type == BookingType.OUTCALL
        existing = await self.repo.list_for_booking(booking_id)
        if any(
            n.template_key
            in {
                "booking_reminder_admin",
                "booking_reminder_worker_outcall",
                "booking_reminder_worker_incall",
                "booking_reminder_client_outcall",
                "booking_reminder_client_incall",
            }
            for n in existing
        ):
            return []

        created: list[Notification] = []

        # Admin reminder
        admin_notif = await self.create(
            target_type=NotificationTargetType.ADMIN,
            target_ref="admin",
            template_key="booking_reminder_admin",
            payload={
                "booking_id": str(booking_id),
                "booking_type": booking.booking_type.value if booking.booking_type else None,
                "style_hint": "ops_t_minus_20",
            },
            send_at=send_at,
            booking_id=booking_id,
            channel=NotificationChannel.IN_APP,
        )
        created.append(admin_notif)

        # Worker reminder
        worker_template = (
            "booking_reminder_worker_outcall" if is_outcall else "booking_reminder_worker_incall"
        )
        worker_notif = await self.create(
            target_type=NotificationTargetType.WORKER,
            target_ref=str(booking.worker_id),
            template_key=worker_template,
            payload={
                "booking_id": str(booking_id),
                "booking_type": booking.booking_type.value if booking.booking_type else None,
                "style_hint": "i_am_about_to_arrive" if is_outcall else "are_you_coming",
            },
            send_at=send_at,
            booking_id=booking_id,
            channel=NotificationChannel.WHATSAPP,
        )
        created.append(worker_notif)

        # Client reminder
        client_template = (
            "booking_reminder_client_outcall" if is_outcall else "booking_reminder_client_incall"
        )
        client_channel = (
            NotificationChannel.WHATSAPP
            if booking.session
            and hasattr(booking.session, "last_channel")
            and str(booking.session.last_channel) == "whatsapp"
            else NotificationChannel.SMS
        )
        client_notif = await self.create(
            target_type=NotificationTargetType.CLIENT,
            target_ref=str(booking.client_id),
            template_key=client_template,
            payload={
                "booking_id": str(booking_id),
                "booking_type": booking.booking_type.value if booking.booking_type else None,
                "style_hint": "i_am_about_to_arrive" if is_outcall else "are_you_coming",
            },
            send_at=send_at,
            booking_id=booking_id,
            channel=client_channel,
        )
        created.append(client_notif)

        return created

    async def mark_sent(self, notification_id: uuid.UUID) -> None:
        notif = await self.repo.get_by_id(notification_id)
        if notif:
            notif.status = NotificationStatus.SENT
            notif.sent_at = datetime.now(UTC)
            await self.repo.save(notif)

    async def mark_failed(self, notification_id: uuid.UUID) -> None:
        notif = await self.repo.get_by_id(notification_id)
        if notif:
            notif.status = NotificationStatus.FAILED
            await self.repo.save(notif)

    async def create_review_notifications(self, booking: Any) -> list[Notification]:
        now = datetime.now(UTC)
        notifications: list[Notification] = []

        notifications.append(
            await self.create(
                target_type=NotificationTargetType.ADMIN,
                target_ref="admin",
                template_key="booking_pending_review_admin",
                payload={
                    "booking_id": str(booking.id),
                    "status": booking.status.value,
                    "awaiting_review_from": booking.awaiting_review_from.value,
                },
                send_at=now,
                booking_id=booking.id,
                channel=NotificationChannel.IN_APP,
            )
        )
        notifications.append(
            await self.create(
                target_type=NotificationTargetType.WORKER,
                target_ref=str(booking.worker_id),
                template_key="booking_pending_review_worker",
                payload={"booking_id": str(booking.id), "status": booking.status.value},
                send_at=now,
                booking_id=booking.id,
                channel=NotificationChannel.WHATSAPP,
            )
        )
        return notifications

    async def create_booking_decision_notifications(
        self,
        booking: Any,
        actor_type: ActorType,
        note: str | None = None,
    ) -> list[Notification]:
        status = booking.status.value.lower()
        if status not in {"confirmed", "rejected", "cancelled", "completed"}:
            return []

        now = datetime.now(UTC)
        return [
            await self.create(
                target_type=NotificationTargetType.ADMIN,
                target_ref="admin",
                template_key=f"booking_{status}_admin",
                payload={
                    "booking_id": str(booking.id),
                    "status": booking.status.value,
                    "actor_type": actor_type.value,
                    "note": note or "",
                },
                send_at=now,
                booking_id=booking.id,
                channel=NotificationChannel.IN_APP,
            )
        ]

    async def schedule_due_booking_reminders(
        self,
        *,
        now: datetime | None = None,
        minutes_before: int = settings.reminder_minutes_before,
    ) -> dict[str, int]:
        reference_now = now or datetime.now(UTC)
        cutoff = reference_now + timedelta(minutes=minutes_before)
        candidates = await self.booking_repo.list_confirmed_starting_before(cutoff)

        created_total = 0
        for booking in candidates:
            created = await self.schedule_booking_reminders(
                booking_id=booking.id,
                minutes_before=minutes_before,
            )
            created_total += len(created)

        return {
            "bookings_considered": len(candidates),
            "notifications_created": created_total,
        }

    async def send_client_message(
        self,
        client_id: uuid.UUID,
        channel: str,
        text: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        client = await self.clients.get_by_id(client_id)
        if client is None:
            return {"ok": False, "error": "Client not found."}

        worker = await self.workers.get_active_worker()
        if worker is None:
            worker, _ = await self.workers.get_or_create_default(
                name="Alysha", timezone="Europe/London"
            )

        mapped_channel = Channel.WHATSAPP if channel == "whatsapp" else Channel.SMS
        session, _ = await self.sessions.get_or_create(client.id, worker.id, mapped_channel)
        send_result = await self.gateway.send_client_message(
            to_phone_e164=client.phone_e164,
            channel=mapped_channel.value,
            text=text,
        )

        outbound = Message(
            session_id=session.id,
            direction=MessageDirection.OUTBOUND,
            channel=mapped_channel,
            sender_type=SenderType.AGENT,
            body=text,
            twilio_message_sid=send_result.sid,
            raw_payload={
                "decision_send": True,
                "context": context,
                "dispatch": {
                    "ok": send_result.ok,
                    "sid": send_result.sid,
                    "stub": send_result.stub,
                    "error": send_result.error,
                },
            },
        )
        await self.messages.save(outbound)
        return {"ok": send_result.ok, "error": send_result.error, "message_id": str(outbound.id)}
