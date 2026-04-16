"""
Unit tests for the slot availability checker (15-minute buffer logic).
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.enums import BookingStatus, BookingType
from app.services.availability_service import AvailabilityService


def utcnow() -> datetime:
    return datetime.now(UTC)


async def _create_confirmed_booking(
    db: AsyncSession,
    worker_id: uuid.UUID,
    client_id: uuid.UUID,
    session_id: uuid.UUID,
    start: datetime,
    duration_minutes: int,
) -> Booking:
    booking = Booking(
        client_id=client_id,
        worker_id=worker_id,
        session_id=session_id,
        status=BookingStatus.CONFIRMED,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=duration_minutes,
        scheduled_end_at=start + timedelta(minutes=duration_minutes),
        client_age=25,
        client_ethnicity="Test",
    )
    db.add(booking)
    await db.flush()
    return booking


@pytest.mark.asyncio
async def test_slot_available_no_existing_bookings(db: AsyncSession) -> None:
    """A fresh worker should have all slots available."""
    worker_id = uuid.uuid4()
    svc = AvailabilityService(db)
    future = utcnow() + timedelta(hours=2)
    result = await svc.check(
        worker_id=worker_id,
        proposed_start=future,
        duration_minutes=60,
    )
    assert result.available is True


@pytest.mark.asyncio
async def test_slot_blocked_by_overlap(db: AsyncSession) -> None:
    """A slot that directly overlaps an existing booking should be blocked."""
    worker_id = uuid.uuid4()
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()

    # Need real rows for FK; we bypass FK checks in SQLite tests by inserting raw bookings
    # with mocked IDs — SQLite doesn't enforce FKs by default.
    start = utcnow() + timedelta(hours=3)
    await _create_confirmed_booking(db, worker_id, client_id, session_id, start, 60)

    svc = AvailabilityService(db)
    # Propose exact same slot
    result = await svc.check(
        worker_id=worker_id,
        proposed_start=start,
        duration_minutes=60,
    )
    assert result.available is False
    assert result.conflict_reason is not None


@pytest.mark.asyncio
async def test_slot_blocked_within_buffer(db: AsyncSession) -> None:
    """A slot starting within 15 minutes of an existing booking end should be blocked."""
    worker_id = uuid.uuid4()
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()

    start = utcnow() + timedelta(hours=4)
    existing_end = start + timedelta(minutes=60)  # existing ends at start+60

    await _create_confirmed_booking(db, worker_id, client_id, session_id, start, 60)

    svc = AvailabilityService(db)
    # New booking starts 10 minutes after existing ends — within 15-min buffer
    new_start = existing_end + timedelta(minutes=10)
    result = await svc.check(
        worker_id=worker_id,
        proposed_start=new_start,
        duration_minutes=60,
    )
    assert result.available is False


@pytest.mark.asyncio
async def test_slot_available_after_buffer(db: AsyncSession) -> None:
    """A slot starting exactly 15 minutes after an existing booking end should be allowed."""
    worker_id = uuid.uuid4()
    client_id = uuid.uuid4()
    session_id = uuid.uuid4()

    start = utcnow() + timedelta(hours=6)
    existing_end = start + timedelta(minutes=60)

    await _create_confirmed_booking(db, worker_id, client_id, session_id, start, 60)

    svc = AvailabilityService(db)
    # New booking starts exactly 15 minutes after existing ends — just outside buffer
    new_start = existing_end + timedelta(minutes=15)
    result = await svc.check(
        worker_id=worker_id,
        proposed_start=new_start,
        duration_minutes=60,
    )
    assert result.available is True


@pytest.mark.asyncio
async def test_past_slot_rejected(db: AsyncSession) -> None:
    """Slots in the past should be rejected."""
    worker_id = uuid.uuid4()
    svc = AvailabilityService(db)
    past = utcnow() - timedelta(hours=1)
    result = await svc.check(
        worker_id=worker_id,
        proposed_start=past,
        duration_minutes=60,
    )
    assert result.available is False
    assert "past" in (result.conflict_reason or "").lower()
