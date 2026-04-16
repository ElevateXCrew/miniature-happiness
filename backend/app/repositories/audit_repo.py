import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_event import AuditEvent
from app.models.enums import ActorType


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def log(
        self,
        entity_type: str,
        entity_id: uuid.UUID,
        event_type: str,
        actor_type: ActorType,
        actor_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            event_type=event_type,
            actor_type=actor_type,
            actor_ref=actor_ref,
            metadata_=metadata or {},
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def list_for_entity(self, entity_type: str, entity_id: uuid.UUID) -> list[AuditEvent]:
        result = await self.db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.entity_type == entity_type,
                AuditEvent.entity_id == entity_id,
            )
            .order_by(AuditEvent.created_at)
        )
        return list(result.scalars().all())
