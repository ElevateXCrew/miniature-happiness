"""
Notification dispatch and reminder endpoints.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


class DispatchBody(BaseModel):
    notification_id: uuid.UUID
    outcome: str  # "sent" or "failed"


class ReminderRunBody(BaseModel):
    booking_id: uuid.UUID | None = None
    minutes_before: int = 20


@router.post("/dispatch")
async def dispatch_notification(body: DispatchBody, db: AsyncSession = Depends(get_db)) -> Any:
    svc = NotificationService(db)
    if body.outcome == "sent":
        await svc.mark_sent(body.notification_id)
    else:
        await svc.mark_failed(body.notification_id)
    return {"notification_id": str(body.notification_id), "outcome": body.outcome}


@router.post("/reminders/run")
async def run_reminders(
    body: ReminderRunBody = ReminderRunBody(), db: AsyncSession = Depends(get_db)
) -> Any:
    from app.repositories.notification_repo import NotificationRepository

    if body.booking_id:
        svc = NotificationService(db)
        notifications = await svc.schedule_booking_reminders(
            booking_id=body.booking_id, minutes_before=body.minutes_before
        )
        return {"scheduled": len(notifications)}

    # Dispatch all queued notifications due now (stub; actual send in Phase 2)
    repo = NotificationRepository(db)
    due = await repo.list_queued_due(datetime.now(UTC))
    return {"due_notifications": len(due), "note": "Actual dispatch implemented in Phase 2."}
