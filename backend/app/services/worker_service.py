"""
Worker command service: parses and executes worker intents.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.worker_repo import WorkerRepository
from app.services.booking_service import BookingService


@dataclass
class WorkerCommandResult:
    success: bool
    message: str


class WorkerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.worker_repo = WorkerRepository(db)
        self.booking_service = BookingService(db)

    async def process_command(self, worker_id: uuid.UUID, message_text: str) -> WorkerCommandResult:
        text = message_text.strip().lower()

        if "free now" in text or "done early" in text or "finished" in text:
            return await self._handle_free_now(worker_id)

        return WorkerCommandResult(success=False, message="Command not recognized.")

    async def _handle_free_now(self, worker_id: uuid.UUID) -> WorkerCommandResult:
        from sqlalchemy import select

        from app.models.booking import Booking
        from app.models.enums import BookingStatus

        # Find the currently active CONFIRMED booking for this worker
        now = datetime.utcnow()
        result = await self.db.execute(
            select(Booking).where(
                Booking.worker_id == worker_id,
                Booking.status == BookingStatus.CONFIRMED,
                Booking.scheduled_start_at <= now,
            )
        )
        active = result.scalars().first()
        if not active:
            return WorkerCommandResult(success=False, message="No active booking to complete.")

        _, errors = await self.booking_service.complete_early(
            booking_id=active.id,
            actor_ref=str(worker_id),
        )
        if errors:
            return WorkerCommandResult(success=False, message="; ".join(errors))
        return WorkerCommandResult(
            success=True,
            message=f"Booking {active.id} marked as completed early. Slot released.",
        )

    async def set_availability_override(
        self,
        worker_id: uuid.UUID,
        from_at: datetime,
        to_at: datetime,
        mode: str,  # "block" or "unblock"
    ) -> WorkerCommandResult:
        # Availability overrides are modelled as audit events for now.
        # A dedicated availability_overrides table can be added in Phase 4.
        from app.models.enums import ActorType
        from app.repositories.audit_repo import AuditRepository

        audit = AuditRepository(self.db)
        await audit.log(
            entity_type="worker",
            entity_id=worker_id,
            event_type=f"availability_override:{mode}",
            actor_type=ActorType.WORKER,
            actor_ref=str(worker_id),
            metadata={"from_at": from_at.isoformat(), "to_at": to_at.isoformat(), "mode": mode},
        )
        return WorkerCommandResult(
            success=True,
            message=f"Availability {mode}ed from {from_at} to {to_at}.",
        )
