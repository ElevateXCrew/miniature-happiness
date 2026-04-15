import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Channel


class BookingMedia(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "booking_media"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False), ForeignKey("clients.id"), nullable=False
    )
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False), ForeignKey("bookings.id"), nullable=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False),
        ForeignKey("conversation_sessions.id"),
        nullable=False,
    )
    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="media_channel"), nullable=False)
    media_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    twilio_media_sid: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    storage_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_receipt: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    client: Mapped["Client"] = relationship(  # noqa: F821
        "Client", back_populates="booking_media"
    )
    booking: Mapped["Booking | None"] = relationship(  # noqa: F821
        "Booking", back_populates="media"
    )
    session: Mapped["ConversationSession"] = relationship(  # noqa: F821
        "ConversationSession", back_populates="booking_media"
    )
