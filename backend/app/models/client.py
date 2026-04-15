from sqlalchemy import Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Client(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "clients"

    phone_e164: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    bookings: Mapped[list["Booking"]] = relationship(  # noqa: F821
        "Booking", back_populates="client"
    )
    conversation_sessions: Mapped[list["ConversationSession"]] = relationship(  # noqa: F821
        "ConversationSession", back_populates="client"
    )
    booking_media: Mapped[list["BookingMedia"]] = relationship(  # noqa: F821
        "BookingMedia", back_populates="client"
    )
