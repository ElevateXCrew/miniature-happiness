import uuid

from sqlalchemy import JSON, Enum, ForeignKey, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import Channel, MessageDirection, SenderType


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=False),
        ForeignKey("conversation_sessions.id"),
        nullable=False,
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, name="message_direction"), nullable=False
    )
    channel: Mapped[Channel] = mapped_column(Enum(Channel, name="message_channel"), nullable=False)
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(SenderType, name="sender_type"), nullable=False
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    twilio_message_sid: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Relationships
    session: Mapped["ConversationSession"] = relationship(  # noqa: F821
        "ConversationSession", back_populates="messages"
    )
