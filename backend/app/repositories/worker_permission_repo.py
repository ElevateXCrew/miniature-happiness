import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SectionKey
from app.models.worker_section_permission import WorkerSectionPermission


class WorkerPermissionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_user(self, worker_user_id: uuid.UUID) -> list[WorkerSectionPermission]:
        result = await self.db.execute(
            select(WorkerSectionPermission)
            .where(WorkerSectionPermission.worker_user_id == worker_user_id)
            .order_by(WorkerSectionPermission.section_key)
        )
        return list(result.scalars().all())

    async def get_for_user_and_section(
        self,
        worker_user_id: uuid.UUID,
        section_key: SectionKey,
    ) -> WorkerSectionPermission | None:
        result = await self.db.execute(
            select(WorkerSectionPermission).where(
                WorkerSectionPermission.worker_user_id == worker_user_id,
                WorkerSectionPermission.section_key == section_key,
            )
        )
        return result.scalar_one_or_none()

    async def upsert_permission(
        self,
        worker_user_id: uuid.UUID,
        section_key: SectionKey,
        can_view: bool,
        updated_by_user_id: uuid.UUID | None,
    ) -> WorkerSectionPermission:
        existing = await self.get_for_user_and_section(worker_user_id, section_key)
        if existing:
            existing.can_view = can_view
            existing.updated_by_user_id = updated_by_user_id
            await self.db.flush()
            return existing

        permission = WorkerSectionPermission(
            worker_user_id=worker_user_id,
            section_key=section_key,
            can_view=can_view,
            updated_by_user_id=updated_by_user_id,
        )
        self.db.add(permission)
        await self.db.flush()
        return permission
