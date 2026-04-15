import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import AwaitingReviewFrom, BookingStatus, BookingType


class Booking(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "bookings"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False), ForeignKey("clients.id"), nullable=False
    )
    worker_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False), ForeignKey("workers.id"), nullable=False
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False),
        ForeignKey("conversation_sessions.id"),
        nullable=False,
    )
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"),
        nullable=False,
        default=BookingStatus.DRAFT,
    )
    booking_type: Mapped[BookingType | None] = mapped_column(
        Enum(BookingType, name="booking_type"), nullable=True
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
        Enum(AwaitingReviewFrom, name="awaiting_review_from"),
        nullable=False,
        default=AwaitingReviewFrom.NONE,
    )

    # Lifecycle timestamps
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    client: Mapped["Client"] = relationship(  # noqa: F821
        "Client", back_populates="bookings"
    )
    worker: Mapped["Worker"] = relationship(  # noqa: F821
        "Worker", back_populates="bookings"
    )
    session: Mapped["ConversationSession"] = relationship(  # noqa: F821
        "ConversationSession",
        foreign_keys=[session_id],
        overlaps="active_sessions",
    )
    active_sessions: Mapped[list["ConversationSession"]] = relationship(  # noqa: F821
        "ConversationSession",
        foreign_keys="ConversationSession.active_booking_id",
        back_populates="active_booking",
    )
    media: Mapped[list["BookingMedia"]] = relationship(  # noqa: F821
        "BookingMedia", back_populates="booking"
    )
    notifications: Mapped[list["Notification"]] = relationship(  # noqa: F821
        "Notification", back_populates="booking"
    )

    __table_args__ = (
        Index("ix_bookings_worker_start", "worker_id", "scheduled_start_at"),
        Index("ix_bookings_client_status", "client_id", "status"),
    )
