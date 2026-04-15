"""
Admin Panel API endpoints.
"""

import uuid
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.models.enums import ActorType, BookingStatus
from app.repositories.booking_repo import BookingRepository
from app.repositories.notification_repo import NotificationRepository
from app.services.booking_service import BookingService

router = APIRouter(prefix="/admin", tags=["admin"])


class BookingActionNote(BaseModel):
    note: str | None = None


# ------------------------------------------------------------------
# Bookings
# ------------------------------------------------------------------


@router.get("/bookings")
async def list_bookings(db: AsyncSession = Depends(get_db)) -> Any:
    repo = BookingRepository(db)
    bookings = await repo.list_pending_review()
    return [
        {
            "id": str(b.id),
            "status": b.status.value,
            "client_id": str(b.client_id),
            "worker_id": str(b.worker_id),
            "scheduled_start_at": b.scheduled_start_at.isoformat()
            if b.scheduled_start_at
            else None,
            "booking_type": b.booking_type.value if b.booking_type else None,
        }
        for b in bookings
    ]


@router.get("/bookings/{booking_id}")
async def get_booking(booking_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> Any:
    repo = BookingRepository(db)
    booking = await repo.get_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    return {
        "id": str(booking.id),
        "status": booking.status.value,
        "client_id": str(booking.client_id),
        "worker_id": str(booking.worker_id),
        "session_id": str(booking.session_id),
        "booking_type": booking.booking_type.value if booking.booking_type else None,
        "scheduled_start_at": booking.scheduled_start_at.isoformat()
        if booking.scheduled_start_at
        else None,
        "scheduled_end_at": booking.scheduled_end_at.isoformat()
        if booking.scheduled_end_at
        else None,
        "duration_minutes": booking.duration_minutes,
        "client_age": booking.client_age,
        "client_ethnicity": booking.client_ethnicity,
        "client_name": booking.client_name,
        "outcall_address": booking.outcall_address,
        "price_total_gbp": str(booking.price_total_gbp) if booking.price_total_gbp else None,
        "advance_required_gbp": str(booking.advance_required_gbp)
        if booking.advance_required_gbp
        else None,
        "advance_received": booking.advance_received,
        "awaiting_review_from": booking.awaiting_review_from.value,
        "confirmed_at": booking.confirmed_at.isoformat() if booking.confirmed_at else None,
        "cancelled_at": booking.cancelled_at.isoformat() if booking.cancelled_at else None,
        "completed_at": booking.completed_at.isoformat() if booking.completed_at else None,
    }


@router.post("/bookings/{booking_id}/approve")
async def approve_booking(
    booking_id: uuid.UUID,
    body: BookingActionNote = BookingActionNote(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    booking, errors = await svc.set_status(
        booking_id=booking_id,
        status=BookingStatus.CONFIRMED,
        actor_type=ActorType.ADMIN,
        note=body.note,
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": booking.status.value}


@router.post("/bookings/{booking_id}/reject")
async def reject_booking(
    booking_id: uuid.UUID,
    body: BookingActionNote = BookingActionNote(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    booking, errors = await svc.set_status(
        booking_id=booking_id,
        status=BookingStatus.REJECTED,
        actor_type=ActorType.ADMIN,
        note=body.note,
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": booking.status.value}


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: uuid.UUID,
    body: BookingActionNote = BookingActionNote(),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    booking, errors = await svc.set_status(
        booking_id=booking_id,
        status=BookingStatus.CANCELLED,
        actor_type=ActorType.ADMIN,
        note=body.note,
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": booking.status.value}


@router.patch("/bookings/{booking_id}")
async def edit_booking(
    booking_id: uuid.UUID,
    updates: dict,
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = BookingService(db)
    errors_all: list[str] = []
    for field, value in updates.items():
        _, errors = await svc.update_field(
            booking_id=booking_id,
            field_name=field,
            field_value=value,
            actor_type=ActorType.ADMIN,
        )
        errors_all.extend(errors)
    if errors_all:
        raise HTTPException(status_code=422, detail=errors_all)
    return {"booking_id": str(booking_id), "updated_fields": list(updates.keys())}


# ------------------------------------------------------------------
# Sessions
# ------------------------------------------------------------------


@router.get("/sessions/active")
async def list_active_sessions(db: AsyncSession = Depends(get_db)) -> Any:
    from sqlalchemy import select

    from app.models.conversation_session import ConversationSession
    from app.models.enums import ConversationState

    result = await db.execute(
        select(ConversationSession).where(
            ConversationSession.state.notin_([ConversationState.IDLE, ConversationState.PAUSED])
        )
    )
    sessions = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "client_id": str(s.client_id),
            "worker_id": str(s.worker_id),
            "state": s.state.value,
            "last_channel": s.last_channel.value if s.last_channel else None,
            "active_booking_id": str(s.active_booking_id) if s.active_booking_id else None,
        }
        for s in sessions
    ]


# ------------------------------------------------------------------
# Notifications
# ------------------------------------------------------------------


@router.get("/notifications")
async def list_notifications(db: AsyncSession = Depends(get_db)) -> Any:
    from datetime import datetime

    repo = NotificationRepository(db)
    notifications = await repo.list_queued_due(datetime.now(UTC))
    return [
        {
            "id": str(n.id),
            "target_type": n.target_type.value,
            "target_ref": n.target_ref,
            "template_key": n.template_key,
            "status": n.status.value,
            "send_at": n.send_at.isoformat(),
        }
        for n in notifications
    ]


# ------------------------------------------------------------------
# Agent control
# ------------------------------------------------------------------


@router.post("/agent/pause")
async def pause_agent(db: AsyncSession = Depends(get_db)) -> Any:
    from sqlalchemy import update

    from app.models.conversation_session import ConversationSession
    from app.models.enums import ConversationState

    await db.execute(
        update(ConversationSession)
        .where(ConversationSession.state.notin_([ConversationState.IDLE, ConversationState.PAUSED]))
        .values(state=ConversationState.PAUSED)
    )
    return {"paused": True}


@router.post("/agent/resume")
async def resume_agent(db: AsyncSession = Depends(get_db)) -> Any:
    from sqlalchemy import update

    from app.models.conversation_session import ConversationSession
    from app.models.enums import ConversationState

    await db.execute(
        update(ConversationSession)
        .where(ConversationSession.state == ConversationState.PAUSED)
        .values(state=ConversationState.IDLE)
    )
    return {"resumed": True}
