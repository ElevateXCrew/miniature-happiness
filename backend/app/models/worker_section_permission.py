import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import SectionKey


class WorkerSectionPermission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "worker_section_permissions"
    __table_args__ = (
        UniqueConstraint("worker_user_id", "section_key", name="uq_worker_user_section"),
    )

    worker_user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    section_key: Mapped[SectionKey] = mapped_column(
        Enum(
            SectionKey,
            name="section_key",
            values_callable=lambda enum_cls: [item.value for item in enum_cls],
        ),
        nullable=False,
    )
    can_view: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True, native_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
    )
