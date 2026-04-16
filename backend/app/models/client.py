from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.booking_media import BookingMedia
    from app.models.conversation_session import ConversationSession


class Client(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "clients"

    phone_e164: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="client"
    )
    conversation_sessions: Mapped[list["ConversationSession"]] = relationship(
        "ConversationSession", back_populates="client"
    )
    booking_media: Mapped[list["BookingMedia"]] = relationship(
        "BookingMedia", back_populates="client"
    )
