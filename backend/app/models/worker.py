from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Worker(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workers"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Europe/London")

    # Relationships
    bookings: Mapped[list["Booking"]] = relationship(  # noqa: F821
        "Booking", back_populates="worker"
    )
    conversation_sessions: Mapped[list["ConversationSession"]] = relationship(  # noqa: F821
        "ConversationSession", back_populates="worker"
    )
