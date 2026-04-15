from datetime import datetime

from sqlalchemy import DateTime, Enum, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow
from app.models.enums import InboundProvider


class InboundIdempotency(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "inbound_idempotency"

    provider: Mapped[InboundProvider] = mapped_column(
        Enum(InboundProvider, name="inbound_provider"), nullable=False
    )
    external_id: Mapped[str] = mapped_column(Text, nullable=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    result_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_idempotency_provider_external"),
    )
