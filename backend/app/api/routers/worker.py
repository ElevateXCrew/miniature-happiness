"""
Worker API endpoints (mobile-ready).
"""

import uuid
from datetime import UTC
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import get_current_user, require_role, require_section
from app.db.engine import get_db
from app.models.enums import ActorType, BookingStatus, SectionKey, UserRole
from app.models.user import User
from app.repositories.booking_repo import BookingRepository
from app.services.booking_service import BookingService
from app.services.worker_service import WorkerService

router = APIRouter(
    prefix="/worker",
    tags=["worker"],
    dependencies=[Depends(require_role(UserRole.WORKER, UserRole.ADMIN))],
)


async def _require_worker_booking(
    db: AsyncSession,
    booking_id: uuid.UUID,
    worker_id: uuid.UUID,
) -> None:
    repo = BookingRepository(db)
    booking = await repo.get_by_id(booking_id)
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    if booking.worker_id != worker_id:
        raise HTTPException(status_code=403, detail="Booking does not belong to worker")


class WorkerMessageBody(BaseModel):
    worker_id: uuid.UUID
    message_text: str


class AvailabilityBlock(BaseModel):
    worker_id: uuid.UUID
    from_at: str
    to_at: str


def _resolve_worker_id(current_user: User, requested_worker_id: uuid.UUID) -> uuid.UUID:
    if current_user.role == UserRole.WORKER:
        if current_user.worker_id is None:
            raise HTTPException(
                status_code=403,
                detail="Worker user is not linked to a worker record",
            )
        if requested_worker_id != current_user.worker_id:
            raise HTTPException(status_code=403, detail="Cannot act on another worker")
    return requested_worker_id


@router.get("/bookings/upcoming")
async def upcoming_bookings(
    worker_id: uuid.UUID,
    _: User = Depends(require_section(SectionKey.BOOKINGS)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from datetime import datetime

    worker_id = _resolve_worker_id(current_user, worker_id)
    repo = BookingRepository(db)
    bookings = await repo.list_upcoming_confirmed(worker_id=worker_id, from_dt=datetime.now(UTC))
    return [
        {
            "id": str(b.id),
            "status": b.status.value,
            "scheduled_start_at": b.scheduled_start_at.isoformat()
            if b.scheduled_start_at
            else None,
            "duration_minutes": b.duration_minutes,
            "booking_type": b.booking_type.value if b.booking_type else None,
            "client_name": b.client_name,
        }
        for b in bookings
    ]


@router.post("/bookings/{booking_id}/approve")
async def worker_approve_booking(
    booking_id: uuid.UUID,
    worker_id: uuid.UUID,
    _: User = Depends(require_section(SectionKey.BOOKINGS)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    worker_id = _resolve_worker_id(current_user, worker_id)
    await _require_worker_booking(db, booking_id, worker_id)
    svc = BookingService(db)
    booking, errors = await svc.set_status(
        booking_id=booking_id,
        status=BookingStatus.CONFIRMED,
        actor_type=ActorType.WORKER,
        actor_ref=str(worker_id),
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": booking.status.value}


@router.post("/bookings/{booking_id}/reject")
async def worker_reject_booking(
    booking_id: uuid.UUID,
    worker_id: uuid.UUID,
    _: User = Depends(require_section(SectionKey.BOOKINGS)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    worker_id = _resolve_worker_id(current_user, worker_id)
    await _require_worker_booking(db, booking_id, worker_id)
    svc = BookingService(db)
    booking, errors = await svc.set_status(
        booking_id=booking_id,
        status=BookingStatus.REJECTED,
        actor_type=ActorType.WORKER,
        actor_ref=str(worker_id),
    )
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": booking.status.value}


@router.post("/bookings/{booking_id}/complete-early")
async def complete_early(
    booking_id: uuid.UUID,
    worker_id: uuid.UUID,
    _: User = Depends(require_section(SectionKey.BOOKINGS)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    worker_id = _resolve_worker_id(current_user, worker_id)
    await _require_worker_booking(db, booking_id, worker_id)
    svc = BookingService(db)
    booking, errors = await svc.complete_early(booking_id=booking_id, actor_ref=str(worker_id))
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": "COMPLETED"}


@router.post("/availability/free-now")
async def free_now(
    body: WorkerMessageBody,
    _: User = Depends(require_section(SectionKey.SCHEDULE)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    body.worker_id = _resolve_worker_id(current_user, body.worker_id)
    svc = WorkerService(db)
    result = await svc.process_command(worker_id=body.worker_id, message_text="free now")
    return {"success": result.success, "message": result.message}


@router.post("/availability/block")
async def block_availability(
    body: AvailabilityBlock,
    _: User = Depends(require_section(SectionKey.SCHEDULE)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from datetime import datetime

    body.worker_id = _resolve_worker_id(current_user, body.worker_id)
    svc = WorkerService(db)
    result = await svc.set_availability_override(
        worker_id=body.worker_id,
        from_at=datetime.fromisoformat(body.from_at),
        to_at=datetime.fromisoformat(body.to_at),
        mode="block",
    )
    return {"success": result.success, "message": result.message}


@router.post("/messages")
async def worker_message(
    body: WorkerMessageBody,
    _: User = Depends(require_section(SectionKey.LIVE_CHAT)),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    body.worker_id = _resolve_worker_id(current_user, body.worker_id)
    svc = WorkerService(db)
    result = await svc.process_worker_message(
        worker_user_id=current_user.id,
        worker_id=body.worker_id,
        message_text=body.message_text,
    )
    return {
        "success": result.success,
        "assistant_reply": result.assistant_reply,
        "message": result.assistant_reply,
        "executed_actions": result.executed_actions,
    }
