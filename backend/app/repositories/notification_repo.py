import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import NotificationStatus
from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, notification_id: uuid.UUID) -> Notification | None:
        result = await self.db.execute(
            select(Notification).where(Notification.id == notification_id)
        )
        return result.scalar_one_or_none()

    async def list_queued_due(self, now: datetime) -> list[Notification]:
        result = await self.db.execute(
            select(Notification).where(
                Notification.status == NotificationStatus.QUEUED,
                Notification.send_at <= now,
            )
        )
        return list(result.scalars().all())

    async def list_for_booking(self, booking_id: uuid.UUID) -> list[Notification]:
        result = await self.db.execute(
            select(Notification).where(Notification.booking_id == booking_id)
        )
        return list(result.scalars().all())

    async def save(self, notification: Notification) -> Notification:
        self.db.add(notification)
        await self.db.flush()
        return notification
