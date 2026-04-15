import uuid
from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import BookingStatus


class BookingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, booking_id: uuid.UUID) -> Booking | None:
        result = await self.db.execute(select(Booking).where(Booking.id == booking_id))
        return result.scalar_one_or_none()

    async def get_active_draft_for_session(self, session_id: uuid.UUID) -> Booking | None:
        result = await self.db.execute(
            select(Booking).where(
                Booking.session_id == session_id,
                Booking.status == BookingStatus.DRAFT,
            )
        )
        return result.scalar_one_or_none()

    async def get_conflicting_bookings(
        self,
        worker_id: uuid.UUID,
        proposed_start: datetime,
        proposed_end: datetime,
        exclude_booking_id: uuid.UUID | None = None,
    ) -> list[Booking]:
        """
        Returns bookings that overlap with [proposed_start, proposed_end].
        Excludes DRAFT, REJECTED, CANCELLED status.
        """
        active_statuses = [
            BookingStatus.PENDING_REVIEW,
            BookingStatus.CONFIRMED,
        ]
        query = select(Booking).where(
            Booking.worker_id == worker_id,
            Booking.status.in_(active_statuses),
            Booking.scheduled_start_at.is_not(None),
            Booking.scheduled_end_at.is_not(None),
            # Overlap: existing_start < proposed_end AND existing_end > proposed_start
            and_(
                Booking.scheduled_start_at < proposed_end,
                Booking.scheduled_end_at > proposed_start,
            ),
        )
        if exclude_booking_id:
            query = query.where(Booking.id != exclude_booking_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def list_upcoming_confirmed(
        self, worker_id: uuid.UUID, from_dt: datetime
    ) -> list[Booking]:
        result = await self.db.execute(
            select(Booking).where(
                Booking.worker_id == worker_id,
                Booking.status == BookingStatus.CONFIRMED,
                Booking.scheduled_start_at >= from_dt,
            )
        )
        return list(result.scalars().all())

    async def list_pending_review(self) -> list[Booking]:
        result = await self.db.execute(
            select(Booking).where(Booking.status == BookingStatus.PENDING_REVIEW)
        )
        return list(result.scalars().all())

    async def save(self, booking: Booking) -> Booking:
        self.db.add(booking)
        await self.db.flush()
        return booking
