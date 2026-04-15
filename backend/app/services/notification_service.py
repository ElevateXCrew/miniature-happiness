"""
Notification service: queues and dispatches notifications, schedules reminders.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.enums import (
    BookingType,
    NotificationChannel,
    NotificationStatus,
    NotificationTargetType,
)
from app.models.notification import Notification
from app.repositories.booking_repo import BookingRepository
from app.repositories.notification_repo import NotificationRepository


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = NotificationRepository(db)
        self.booking_repo = BookingRepository(db)

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
        created: list[Notification] = []

        # Admin reminder
        admin_notif = await self.create(
            target_type=NotificationTargetType.ADMIN,
            target_ref="admin",
            template_key="booking_reminder_admin",
            payload={"booking_id": str(booking_id)},
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
            payload={"booking_id": str(booking_id)},
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
            payload={"booking_id": str(booking_id)},
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
