import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Channel, ConversationState


class ConversationSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conversation_sessions"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False), ForeignKey("clients.id"), nullable=False
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False), ForeignKey("workers.id"), nullable=False
    )
    state: Mapped[ConversationState] = mapped_column(
        Enum(ConversationState, name="conversation_state"),
        nullable=False,
        default=ConversationState.IDLE,
    )
    active_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False), ForeignKey("bookings.id"), nullable=True
    )
    last_channel: Mapped[Channel | None] = mapped_column(
        Enum(Channel, name="channel"), nullable=True
    )
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    client: Mapped["Client"] = relationship(  # noqa: F821
        "Client", back_populates="conversation_sessions"
    )
    worker: Mapped["Worker"] = relationship(  # noqa: F821
        "Worker", back_populates="conversation_sessions"
    )
    active_booking: Mapped["Booking | None"] = relationship(  # noqa: F821
        "Booking",
        foreign_keys=[active_booking_id],
        back_populates="active_sessions",
    )
    messages: Mapped[list["Message"]] = relationship(  # noqa: F821
        "Message", back_populates="session"
    )
    booking_media: Mapped[list["BookingMedia"]] = relationship(  # noqa: F821
        "BookingMedia", back_populates="session"
    )

    __table_args__ = (UniqueConstraint("client_id", "worker_id", name="uq_session_client_worker"),)
