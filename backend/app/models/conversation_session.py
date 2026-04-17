import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Channel, ConversationState

if TYPE_CHECKING:
    from app.models.booking import Booking
    from app.models.booking_media import BookingMedia
    from app.models.client import Client
    from app.models.message import Message
    from app.models.worker import Worker


class ConversationSession(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conversation_sessions"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True), ForeignKey("workers.id"), nullable=False
    )
    state: Mapped[ConversationState] = mapped_column(
        Enum(
            ConversationState,
            name="conversation_state",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=ConversationState.IDLE,
    )
    active_booking_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True), ForeignKey("bookings.id"), nullable=True
    )
    last_channel: Mapped[Channel | None] = mapped_column(
        Enum(
            Channel,
            name="channel",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=True,
    )
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    client: Mapped["Client"] = relationship(
        "Client", back_populates="conversation_sessions"
    )
    worker: Mapped["Worker"] = relationship(
        "Worker", back_populates="conversation_sessions"
    )
    active_booking: Mapped["Booking | None"] = relationship(
        "Booking",
        foreign_keys=[active_booking_id],
        back_populates="active_sessions",
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="session"
    )
    booking_media: Mapped[list["BookingMedia"]] = relationship(
        "BookingMedia", back_populates="session"
    )

    __table_args__ = (UniqueConstraint("client_id", "worker_id", name="uq_session_client_worker"),)
