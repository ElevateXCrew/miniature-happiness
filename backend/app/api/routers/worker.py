"""
Worker API endpoints (mobile-ready).
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
from app.services.booking_service import BookingService
from app.services.worker_service import WorkerService

router = APIRouter(prefix="/worker", tags=["worker"])


class WorkerMessageBody(BaseModel):
    worker_id: uuid.UUID
    message_text: str


class AvailabilityBlock(BaseModel):
    worker_id: uuid.UUID
    from_at: str
    to_at: str


@router.get("/bookings/upcoming")
async def upcoming_bookings(
    worker_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    from datetime import datetime

    repo = BookingRepository(db)
    bookings = await repo.list_upcoming_confirmed(
        worker_id=worker_id, from_dt=datetime.now(UTC)
    )
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
    booking_id: uuid.UUID, worker_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
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
    booking_id: uuid.UUID, worker_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
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
    booking_id: uuid.UUID, worker_id: uuid.UUID, db: AsyncSession = Depends(get_db)
) -> Any:
    svc = BookingService(db)
    booking, errors = await svc.complete_early(booking_id=booking_id, actor_ref=str(worker_id))
    if errors:
        raise HTTPException(status_code=422, detail=errors)
    return {"booking_id": str(booking_id), "status": "COMPLETED"}


@router.post("/availability/free-now")
async def free_now(body: WorkerMessageBody, db: AsyncSession = Depends(get_db)) -> Any:
    svc = WorkerService(db)
    result = await svc.process_command(worker_id=body.worker_id, message_text="free now")
    return {"success": result.success, "message": result.message}


@router.post("/availability/block")
async def block_availability(body: AvailabilityBlock, db: AsyncSession = Depends(get_db)) -> Any:
    from datetime import datetime

    svc = WorkerService(db)
    result = await svc.set_availability_override(
        worker_id=body.worker_id,
        from_at=datetime.fromisoformat(body.from_at),
        to_at=datetime.fromisoformat(body.to_at),
        mode="block",
    )
    return {"success": result.success, "message": result.message}


@router.post("/messages")
async def worker_message(body: WorkerMessageBody, db: AsyncSession = Depends(get_db)) -> Any:
    svc = WorkerService(db)
    result = await svc.process_command(worker_id=body.worker_id, message_text=body.message_text)
    return {"success": result.success, "message": result.message}
