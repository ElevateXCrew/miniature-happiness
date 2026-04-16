from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.conversation_session import ConversationSession


class Worker(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "workers"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    timezone: Mapped[str] = mapped_column(Text, nullable=False, default="Europe/London")

    # Relationships
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="worker"
    )
    conversation_sessions: Mapped[list["ConversationSession"]] = relationship(
        "ConversationSession", back_populates="worker"
    )
