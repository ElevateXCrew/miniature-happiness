import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client


class ClientRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, client_id: uuid.UUID) -> Client | None:
        result = await self.db.execute(select(Client).where(Client.id == client_id))
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone_e164: str) -> Client | None:
        result = await self.db.execute(select(Client).where(Client.phone_e164 == phone_e164))
        return result.scalar_one_or_none()

    async def get_or_create(self, phone_e164: str) -> tuple[Client, bool]:
        """Returns (client, created). Uses SELECT then INSERT to avoid race on unique key."""
        existing = await self.get_by_phone(phone_e164)
        if existing:
            return existing, False
        client = Client(phone_e164=phone_e164)
        self.db.add(client)
        await self.db.flush()
        return client, True

    async def update(self, client: Client) -> Client:
        self.db.add(client)
        await self.db.flush()
        return client
