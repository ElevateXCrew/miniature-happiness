import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation_session import ConversationSession
from app.models.enums import Channel, ConversationState


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, session_id: uuid.UUID) -> ConversationSession | None:
        result = await self.db.execute(
            select(ConversationSession).where(ConversationSession.id == session_id)
        )
        return result.scalar_one_or_none()

    async def get_active_for_client_worker(
        self, client_id: uuid.UUID, worker_id: uuid.UUID
    ) -> ConversationSession | None:
        result = await self.db.execute(
            select(ConversationSession).where(
                ConversationSession.client_id == client_id,
                ConversationSession.worker_id == worker_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        client_id: uuid.UUID,
        worker_id: uuid.UUID,
        channel: Channel,
    ) -> tuple[ConversationSession, bool]:
        existing = await self.get_active_for_client_worker(client_id, worker_id)
        if existing:
            # Update last channel
            existing.last_channel = channel
            existing.last_inbound_at = datetime.now(UTC)
            self.db.add(existing)
            await self.db.flush()
            return existing, False

        session = ConversationSession(
            client_id=client_id,
            worker_id=worker_id,
            state=ConversationState.IDLE,
            last_channel=channel,
            last_inbound_at=datetime.now(UTC),
        )
        self.db.add(session)
        await self.db.flush()
        return session, True

    async def update_state(
        self, session: ConversationSession, new_state: ConversationState
    ) -> ConversationSession:
        session.state = new_state
        self.db.add(session)
        await self.db.flush()
        return session

    async def update(self, session: ConversationSession) -> ConversationSession:
        self.db.add(session)
        await self.db.flush()
        return session
