"""
Tests for booking lifecycle state machine transitions.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.client import Client
from app.models.conversation_session import ConversationSession
from app.models.enums import BookingStatus, BookingType, Channel, ConversationState
from app.models.worker import Worker
from app.services.booking_service import BookingService


def utcnow() -> datetime:
    return datetime.now(UTC)


async def _setup(db: AsyncSession):
    worker = Worker(name="Alysha", timezone="Europe/London", is_active=True)
    client = Client(phone_e164=f"+447{uuid.uuid4().int % 1_000_000_000:09d}")
    db.add(worker)
    db.add(client)
    await db.flush()

    session = ConversationSession(
        client_id=client.id,
        worker_id=worker.id,
        state=ConversationState.COLLECTING,
        last_channel=Channel.SMS,
    )
    db.add(session)
    await db.flush()

    start = utcnow() + timedelta(days=1)
    booking = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=25,
        client_ethnicity="British",
        client_size_inches=5,
        alone_policy_confirmed=True,
    )
    db.add(booking)
    await db.flush()

    # Link booking to session
    session.active_booking_id = booking.id
    await db.flush()

    return worker, client, session, booking


@pytest.mark.asyncio
async def test_submit_for_review_happy_path(db: AsyncSession) -> None:
    worker, client, session, booking = await _setup(db)
    svc = BookingService(db)
    updated, errors = await svc.submit_for_review(booking_id=booking.id)
    assert errors == []
    assert updated.status == BookingStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_field_validation_rejects_under_18(db: AsyncSession) -> None:
    worker, client, session, booking = await _setup(db)
    svc = BookingService(db)
    _, errors = await svc.update_field(
        booking_id=booking.id, field_name="client_age", field_value=16
    )
    assert any("18" in e for e in errors)


@pytest.mark.asyncio
async def test_field_validation_rejects_blank_ethnicity(db: AsyncSession) -> None:
    worker, client, session, booking = await _setup(db)
    svc = BookingService(db)
    _, errors = await svc.update_field(
        booking_id=booking.id, field_name="client_ethnicity", field_value="   "
    )
    assert errors


@pytest.mark.asyncio
async def test_confirm_booking(db: AsyncSession) -> None:
    worker, client, session, booking = await _setup(db)
    svc = BookingService(db)

    # Submit first
    await svc.submit_for_review(booking_id=booking.id)

    from app.models.enums import ActorType

    updated, errors = await svc.set_status(
        booking_id=booking.id,
        status=BookingStatus.CONFIRMED,
        actor_type=ActorType.ADMIN,
    )
    assert errors == []
    assert updated.status == BookingStatus.CONFIRMED
    assert updated.confirmed_at is not None


@pytest.mark.asyncio
async def test_invalid_transition_rejected_to_confirmed(db: AsyncSession) -> None:
    worker, client, session, booking = await _setup(db)
    svc = BookingService(db)

    from app.models.enums import ActorType

    # Reject it
    await svc.submit_for_review(booking_id=booking.id)
    await svc.set_status(
        booking_id=booking.id,
        status=BookingStatus.REJECTED,
        actor_type=ActorType.ADMIN,
    )

    # Try to confirm rejected — should fail
    _, errors = await svc.set_status(
        booking_id=booking.id,
        status=BookingStatus.CONFIRMED,
        actor_type=ActorType.ADMIN,
    )
    assert errors  # transition not allowed


@pytest.mark.asyncio
async def test_double_booking_blocked(db: AsyncSession) -> None:
    """Two bookings for the same worker at the same time should result in the second failing."""
    worker, client, session, booking1 = await _setup(db)
    svc = BookingService(db)

    # Confirm first booking
    from app.models.enums import ActorType

    await svc.submit_for_review(booking_id=booking1.id)
    await svc.set_status(
        booking_id=booking1.id, status=BookingStatus.CONFIRMED, actor_type=ActorType.ADMIN
    )

    # Create second booking at the same time
    start = booking1.scheduled_start_at
    booking2 = Booking(
        client_id=client.id,
        worker_id=worker.id,
        session_id=session.id,
        status=BookingStatus.DRAFT,
        booking_type=BookingType.INCALL,
        scheduled_start_at=start,
        duration_minutes=60,
        scheduled_end_at=start + timedelta(minutes=60),
        client_age=22,
        client_ethnicity="Asian",
        client_size_inches=5,
        alone_policy_confirmed=True,
    )
    db.add(booking2)
    await db.flush()

    # Submit second booking should fail due to conflict
    _, errors = await svc.submit_for_review(booking_id=booking2.id)
    assert errors  # should be blocked
