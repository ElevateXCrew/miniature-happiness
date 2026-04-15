import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_twilio_sid(self, sid: str) -> Message | None:
        result = await self.db.execute(select(Message).where(Message.twilio_message_sid == sid))
        return result.scalar_one_or_none()

    async def list_for_session(self, session_id: uuid.UUID) -> list[Message]:
        result = await self.db.execute(
            select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
        )
        return list(result.scalars().all())

    async def save(self, message: Message) -> Message:
        self.db.add(message)
        await self.db.flush()
        return message
