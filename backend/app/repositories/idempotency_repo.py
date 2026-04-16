from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
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
        record = InboundIdempotency(
            provider=provider,
            external_id=external_id,
            processed_at=datetime.now(UTC),
            result_ref=result_ref,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(record)
                await self.db.flush()
            return False
        except IntegrityError:
            return True

    async def set_result_ref(
        self,
        provider: InboundProvider,
        external_id: str,
        result_ref: str,
    ) -> None:
        result = await self.db.execute(
            select(InboundIdempotency).where(
                InboundIdempotency.provider == provider,
                InboundIdempotency.external_id == external_id,
            )
        )
        existing = result.scalar_one_or_none()
        if not existing:
            return
        existing.result_ref = result_ref
        existing.processed_at = datetime.now(UTC)
        self.db.add(existing)
        await self.db.flush()

    async def get_record(
        self,
        provider: InboundProvider,
        external_id: str,
    ) -> InboundIdempotency | None:
        result = await self.db.execute(
            select(InboundIdempotency).where(
                InboundIdempotency.provider == provider,
                InboundIdempotency.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()
