import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.worker import Worker


class WorkerRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_worker(self) -> Worker | None:
        result = await self.db.execute(select(Worker).where(Worker.is_active == True))  # noqa: E712
        return result.scalar_one_or_none()

    async def get_by_id(self, worker_id: uuid.UUID) -> Worker | None:
        result = await self.db.execute(select(Worker).where(Worker.id == worker_id))
        return result.scalar_one_or_none()

    async def get_or_create_default(self, name: str, timezone: str) -> tuple[Worker, bool]:
        existing = await self.get_active_worker()
        if existing:
            return existing, False
        worker = Worker(name=name, timezone=timezone, is_active=True)
        self.db.add(worker)
        await self.db.flush()
        return worker, True
