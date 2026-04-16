from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics
from app.db.engine import get_db
from app.repositories.booking_repo import BookingRepository
from app.repositories.notification_repo import NotificationRepository

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("")
async def get_metrics(db: AsyncSession = Depends(get_db)) -> dict[str, dict[str, int] | int]:
    bookings = BookingRepository(db)
    notifications = NotificationRepository(db)
    due_notifications = await notifications.list_queued_due(datetime.now(UTC))
    counters = metrics.snapshot()
    reminder_failures = counters.get("notifications_failed_total", 0) + counters.get(
        "notifications_dead_letter_total", 0
    )
    return {
        "counters": counters,
        "pending_reviews": await bookings.count_pending_review(),
        "queued_due_notifications": len(due_notifications),
        "failed_tool_calls": counters.get("tool_calls_failed_total", 0),
        "reminder_failures": reminder_failures,
    }
