"""
Slot availability checker with mandatory 15-minute buffer between bookings.

The 15-minute buffer is enforced by expanding the proposed window by
BUFFER_MINUTES on each side before checking for conflicts.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.booking_repo import BookingRepository


@dataclass
class AvailabilityResult:
    available: bool
    conflict_reason: str | None = None
    # Nearest alternative slot if unavailable
    suggested_start: datetime | None = None


class AvailabilityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = BookingRepository(db)
        self.buffer = timedelta(minutes=settings.slot_buffer_minutes)

    async def check(
        self,
        worker_id: uuid.UUID,
        proposed_start: datetime,
        duration_minutes: int,
        exclude_booking_id: uuid.UUID | None = None,
    ) -> AvailabilityResult:
        """
        Returns AvailabilityResult.
        The proposed window is buffered: effective window is
        [proposed_start - buffer, proposed_end + buffer].
        """
        if proposed_start <= datetime.now(UTC):
            return AvailabilityResult(
                available=False,
                conflict_reason="Requested time is in the past.",
            )

        proposed_end = proposed_start + timedelta(minutes=duration_minutes)
        buffered_start = proposed_start - self.buffer
        buffered_end = proposed_end + self.buffer

        conflicts = await self.repo.get_conflicting_bookings(
            worker_id=worker_id,
            proposed_start=buffered_start,
            proposed_end=buffered_end,
            exclude_booking_id=exclude_booking_id,
        )

        if not conflicts:
            return AvailabilityResult(available=True)

        # Find next available slot after the latest conflicting booking end + buffer
        conflict_ends = [
            b.scheduled_end_at + self.buffer
            for b in conflicts
            if b.scheduled_end_at is not None
        ]
        if not conflict_ends:
            return AvailabilityResult(
                available=False,
                conflict_reason="Time slot conflicts with existing booking(s).",
            )
        latest_end = max(conflict_ends)
        return AvailabilityResult(
            available=False,
            conflict_reason=(
                f"Time slot conflicts with {len(conflicts)} existing booking(s). "
                f"A 15-minute buffer is required between all bookings."
            ),
            suggested_start=latest_end,
        )

    async def reserve_tentative(
        self,
        worker_id: uuid.UUID,
        booking_id: uuid.UUID,
        proposed_start: datetime,
        duration_minutes: int,
    ) -> AvailabilityResult:
        """Check availability; actual reservation is done by saving the booking."""
        return await self.check(
            worker_id=worker_id,
            proposed_start=proposed_start,
            duration_minutes=duration_minutes,
            exclude_booking_id=booking_id,
        )
