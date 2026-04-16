"""
Worker command service: parses and executes worker intents.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.worker_repo import WorkerRepository
from app.services.booking_service import BookingService
from app.services.event_stream import admin_event_stream


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
        worker = await self.worker_repo.get_by_id(worker_id)
        if worker is None or not worker.is_active:
            return WorkerCommandResult(success=False, message="Worker not found or inactive.")

        text = message_text.strip().lower()

        if "free now" in text or "done early" in text or "finished" in text:
            return await self._handle_free_now(worker_id)

        if text.startswith("block"):
            return await self._handle_block_command(worker_id, text)

        return WorkerCommandResult(success=False, message="Command not recognized.")

    async def _handle_free_now(self, worker_id: uuid.UUID) -> WorkerCommandResult:
        from sqlalchemy import select

        from app.models.booking import Booking
        from app.models.enums import BookingStatus

        # Find the currently active CONFIRMED booking for this worker
        now = datetime.now(UTC)
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
        admin_event_stream.publish(
            "worker.command.free_now",
            {
                "worker_id": str(worker_id),
                "booking_id": str(active.id),
                "result": "completed_early",
            },
        )
        return WorkerCommandResult(
            success=True,
            message=f"Booking {active.id} marked as completed early. Slot released.",
        )

    async def _handle_block_command(self, worker_id: uuid.UUID, text: str) -> WorkerCommandResult:
        match = re.search(
            r"block\s+(\d{4}-\d{2}-\d{2}t\d{2}:\d{2})\s+(\d{4}-\d{2}-\d{2}t\d{2}:\d{2})", text
        )
        if not match:
            return WorkerCommandResult(
                success=False,
                message="Use: block YYYY-MM-DDTHH:MM YYYY-MM-DDTHH:MM",
            )
        start = datetime.fromisoformat(match.group(1)).replace(tzinfo=UTC)
        end = datetime.fromisoformat(match.group(2)).replace(tzinfo=UTC)
        if end <= start:
            return WorkerCommandResult(success=False, message="Block end must be after start.")
        return await self.set_availability_override(
            worker_id=worker_id, from_at=start, to_at=end, mode="block"
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
        admin_event_stream.publish(
            "worker.availability_override",
            {
                "worker_id": str(worker_id),
                "mode": mode,
                "from_at": from_at.isoformat(),
                "to_at": to_at.isoformat(),
            },
        )
        return WorkerCommandResult(
            success=True,
            message=f"Availability {mode}ed from {from_at} to {to_at}.",
        )
