from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InboundProvider
from app.models.inbound_idempotency import InboundIdempotency


class IdempotencyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check_and_mark(
        self,
        provider: InboundProvider,
        external_id: str,
        result_ref: str | None = None,
    ) -> bool:
        """
        Returns True if this (provider, external_id) was already processed.
        If not, inserts it and returns False.
        """
        result = await self.db.execute(
            select(InboundIdempotency).where(
                InboundIdempotency.provider == provider,
                InboundIdempotency.external_id == external_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return True  # already processed

        record = InboundIdempotency(
            provider=provider,
            external_id=external_id,
            processed_at=datetime.now(UTC),
            result_ref=result_ref,
        )
        self.db.add(record)
        await self.db.flush()
        return False
