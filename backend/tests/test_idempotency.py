"""
Tests for inbound message idempotency.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import InboundProvider
from app.repositories.idempotency_repo import IdempotencyRepository


@pytest.mark.asyncio
async def test_first_message_not_duplicate(db: AsyncSession) -> None:
    repo = IdempotencyRepository(db)
    already_processed = await repo.check_and_mark(
        provider=InboundProvider.TWILIO,
        external_id="SM_TEST_001",
    )
    assert already_processed is False


@pytest.mark.asyncio
async def test_duplicate_message_detected(db: AsyncSession) -> None:
    repo = IdempotencyRepository(db)
    sid = "SM_TEST_DUPLICATE_002"
    # First call
    await repo.check_and_mark(provider=InboundProvider.TWILIO, external_id=sid)
    # Second call with same SID
    already_processed = await repo.check_and_mark(provider=InboundProvider.TWILIO, external_id=sid)
    assert already_processed is True


@pytest.mark.asyncio
async def test_different_sids_are_independent(db: AsyncSession) -> None:
    repo = IdempotencyRepository(db)
    r1 = await repo.check_and_mark(provider=InboundProvider.TWILIO, external_id="SM_A_003")
    r2 = await repo.check_and_mark(provider=InboundProvider.TWILIO, external_id="SM_B_003")
    assert r1 is False
    assert r2 is False
