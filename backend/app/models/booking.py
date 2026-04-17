import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AwaitingReviewFrom, BookingStatus, BookingType

if TYPE_CHECKING:
    from app.models.booking_media import BookingMedia
    from app.models.client import Client
    from app.models.conversation_session import ConversationSession
    from app.models.notification import Notification
    from app.models.worker import Worker


class Booking(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bookings"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True), ForeignKey("clients.id"), nullable=False
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True), ForeignKey("workers.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True),
        ForeignKey("conversation_sessions.id"),
        nullable=False,
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(
            BookingStatus,
            name="booking_status",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=BookingStatus.DRAFT,
    )
    booking_type: Mapped[BookingType | None] = mapped_column(
        Enum(
            BookingType,
            name="booking_type",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=True,
    )

    # Schedule
    scheduled_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Client info
    client_age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_ethnicity: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Location
    outcall_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    incall_address_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Financials
    price_total_gbp: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    advance_required_gbp: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    advance_received: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Review
    awaiting_review_from: Mapped[AwaitingReviewFrom] = mapped_column(
        Enum(
            AwaitingReviewFrom,
            name="awaiting_review_from",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
        default=AwaitingReviewFrom.NONE,
    )

    # Lifecycle timestamps
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    client: Mapped["Client"] = relationship(
        "Client", back_populates="bookings"
    )
    worker: Mapped["Worker"] = relationship(
        "Worker", back_populates="bookings"
    )
    session: Mapped["ConversationSession"] = relationship(
        "ConversationSession",
        foreign_keys=[session_id],
        overlaps="active_sessions",
    )
    active_sessions: Mapped[list["ConversationSession"]] = relationship(
        "ConversationSession",
        foreign_keys="ConversationSession.active_booking_id",
        back_populates="active_booking",
    )
    media: Mapped[list["BookingMedia"]] = relationship(
        "BookingMedia", back_populates="booking"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="booking"
    )

    __table_args__ = (
        Index("ix_bookings_worker_start", "worker_id", "scheduled_start_at"),
        Index("ix_bookings_client_status", "client_id", "status"),
    )
