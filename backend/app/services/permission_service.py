from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ActorType, SectionKey, UserRole
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.repositories.user_repo import UserRepository
from app.repositories.worker_permission_repo import WorkerPermissionRepository
from app.services.event_stream import admin_event_stream

ALL_SECTIONS = [
    SectionKey.DASHBOARD,
    SectionKey.LIVE_CHAT,
    SectionKey.BOOKINGS,
    SectionKey.TIMELINE,
    SectionKey.MEDIA,
    SectionKey.NOTIFICATIONS,
    SectionKey.SCHEDULE,
    SectionKey.SETTINGS,
]


class PermissionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.permission_repo = WorkerPermissionRepository(db)
        self.audit_repo = AuditRepository(db)

    async def get_effective_sections(self, user: User) -> dict[str, bool]:
        if user.role == UserRole.ADMIN:
            return {section.value: True for section in ALL_SECTIONS}

        permissions = await self.permission_repo.list_for_user(user.id)
        permission_map = {p.section_key: p.can_view for p in permissions}

        # Unset section rows default to allowed; admin toggles create explicit records.
        return {section.value: permission_map.get(section, True) for section in ALL_SECTIONS}

    async def can_access_section(self, user: User, section_key: SectionKey) -> bool:
        if user.role == UserRole.ADMIN:
            return True
        effective = await self.get_effective_sections(user)
        return bool(effective.get(section_key.value, False))

    async def list_worker_users(self) -> list[User]:
        return await self.user_repo.list_workers()

    async def set_worker_permissions(
        self,
        *,
        worker_user_id: uuid.UUID,
        section_updates: dict[SectionKey, bool],
        updated_by_user: User,
    ) -> dict[str, bool]:
        worker_user = await self.user_repo.get_by_id(worker_user_id)
        if not worker_user or worker_user.role != UserRole.WORKER:
            raise ValueError("Worker user not found")

        for section_key, can_view in section_updates.items():
            await self.permission_repo.upsert_permission(
                worker_user_id=worker_user_id,
                section_key=section_key,
                can_view=can_view,
                updated_by_user_id=updated_by_user.id,
            )

        effective = await self.get_effective_sections(worker_user)

        await self.audit_repo.log(
            entity_type="user",
            entity_id=worker_user.id,
            event_type="worker_section_permissions.updated",
            actor_type=ActorType.ADMIN,
            actor_ref=str(updated_by_user.id),
            metadata={
                "sections": effective,
            },
        )

        admin_event_stream.publish(
            "worker.permissions.updated",
            {
                "worker_user_id": str(worker_user.id),
                "sections": effective,
            },
        )

        return effective
