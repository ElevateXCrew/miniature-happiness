"""
Notification dispatch and reminder endpoints.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import require_role
from app.db.engine import get_db
from app.models.enums import UserRole
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


class DispatchBody(BaseModel):
    notification_id: uuid.UUID
    outcome: str  # "sent" or "failed" or "dead_letter"
    error: str | None = None


class ReminderRunBody(BaseModel):
    booking_id: uuid.UUID | None = None
    minutes_before: int = 20


@router.post("/dispatch")
async def dispatch_notification(
    body: DispatchBody,
    _: object = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = NotificationService(db)
    if body.outcome == "sent":
        await svc.mark_sent(body.notification_id)
    elif body.outcome == "dead_letter":
        await svc.mark_failed(body.notification_id, error=body.error, allow_retry=False)
    else:
        await svc.mark_failed(body.notification_id, error=body.error, allow_retry=True)
    return {"notification_id": str(body.notification_id), "outcome": body.outcome}


@router.post("/dispatch/run")
async def run_dispatch(
    _: object = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    svc = NotificationService(db)
    result = await svc.dispatch_due_notifications()
    return result


@router.post("/reminders/run")
async def run_reminders(
    body: ReminderRunBody = ReminderRunBody(),
    _: object = Depends(require_role(UserRole.ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    from app.repositories.notification_repo import NotificationRepository

    if body.booking_id:
        svc = NotificationService(db)
        notifications = await svc.schedule_booking_reminders(
            booking_id=body.booking_id, minutes_before=body.minutes_before
        )
        return {
            "mode": "single_booking",
            "scheduled": len(notifications),
            "notification_ids": [str(item.id) for item in notifications],
        }

    svc = NotificationService(db)
    scheduled = await svc.schedule_due_booking_reminders(minutes_before=body.minutes_before)

    # Dispatch all queued notifications due now (stub; actual send in Phase 2)
    repo = NotificationRepository(db)
    due = await repo.list_queued_due(datetime.now(UTC))
    dispatch = await svc.dispatch_due_notifications()
    return {
        "mode": "scheduler_window",
        "bookings_considered": scheduled["bookings_considered"],
        "scheduled": scheduled["notifications_created"],
        "due_notifications": len(due),
        "dispatch": dispatch,
    }
