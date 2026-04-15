"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Enums ---
    conversation_state = postgresql.ENUM(
        "IDLE",
        "COLLECTING",
        "AWAITING_CLIENT_CONFIRMATION",
        "WAITING_REVIEW",
        "PAUSED",
        "HANDOFF",
        "ERROR_REVIEW",
        name="conversation_state",
    )
    conversation_state.create(op.get_bind(), checkfirst=True)

    booking_status = postgresql.ENUM(
        "DRAFT",
        "PENDING_REVIEW",
        "CONFIRMED",
        "REJECTED",
        "CANCELLED",
        "COMPLETED",
        name="booking_status",
    )
    booking_status.create(op.get_bind(), checkfirst=True)

    booking_type = postgresql.ENUM("incall", "outcall", name="booking_type")
    booking_type.create(op.get_bind(), checkfirst=True)

    channel_enum = postgresql.ENUM("sms", "whatsapp", "worker_app", "admin_panel", name="channel")
    channel_enum.create(op.get_bind(), checkfirst=True)

    message_direction = postgresql.ENUM("inbound", "outbound", name="message_direction")
    message_direction.create(op.get_bind(), checkfirst=True)

    sender_type = postgresql.ENUM(
        "client", "agent", "worker", "admin", "system", name="sender_type"
    )
    sender_type.create(op.get_bind(), checkfirst=True)

    notification_target_type = postgresql.ENUM(
        "admin", "worker", "client", name="notification_target_type"
    )
    notification_target_type.create(op.get_bind(), checkfirst=True)

    notification_channel = postgresql.ENUM(
        "in_app", "sms", "whatsapp", "push", "system", name="notification_channel"
    )
    notification_channel.create(op.get_bind(), checkfirst=True)

    notification_status = postgresql.ENUM("queued", "sent", "failed", name="notification_status")
    notification_status.create(op.get_bind(), checkfirst=True)

    actor_type = postgresql.ENUM("agent", "admin", "worker", "system", name="actor_type")
    actor_type.create(op.get_bind(), checkfirst=True)

    awaiting_review_from = postgresql.ENUM("admin", "worker", "none", name="awaiting_review_from")
    awaiting_review_from.create(op.get_bind(), checkfirst=True)

    inbound_provider = postgresql.ENUM("twilio", name="inbound_provider")
    inbound_provider.create(op.get_bind(), checkfirst=True)

    media_channel = postgresql.ENUM("sms", "whatsapp", name="media_channel")
    media_channel.create(op.get_bind(), checkfirst=True)

    message_channel = postgresql.ENUM(
        "sms", "whatsapp", "worker_app", "admin_panel", name="message_channel"
    )
    message_channel.create(op.get_bind(), checkfirst=True)

    # --- workers ---
    op.create_table(
        "workers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("timezone", sa.Text, nullable=False, server_default="Europe/London"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- clients ---
    op.create_table(
        "clients",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phone_e164", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=True),
        sa.Column("is_blocked", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone_e164", name="uq_clients_phone_e164"),
    )
    op.create_index("ix_clients_phone_e164", "clients", ["phone_e164"], unique=True)

    # --- bookings (before conversation_sessions due to FK) ---
    op.create_table(
        "bookings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT",
                "PENDING_REVIEW",
                "CONFIRMED",
                "REJECTED",
                "CANCELLED",
                "COMPLETED",
                name="booking_status",
            ),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column(
            "booking_type",
            sa.Enum("incall", "outcall", name="booking_type"),
            nullable=True,
        ),
        sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_minutes", sa.Integer, nullable=True),
        sa.Column("scheduled_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("client_age", sa.Integer, nullable=True),
        sa.Column("client_ethnicity", sa.Text, nullable=True),
        sa.Column("client_name", sa.Text, nullable=True),
        sa.Column("outcall_address", sa.Text, nullable=True),
        sa.Column("incall_address_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("price_total_gbp", sa.Numeric(10, 2), nullable=True),
        sa.Column("advance_required_gbp", sa.Numeric(10, 2), nullable=True),
        sa.Column("advance_received", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "awaiting_review_from",
            sa.Enum("admin", "worker", "none", name="awaiting_review_from"),
            nullable=False,
            server_default="none",
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        # session_id FK added after conversation_sessions table is created
    )
    op.create_index("ix_bookings_worker_start", "bookings", ["worker_id", "scheduled_start_at"])
    op.create_index("ix_bookings_client_status", "bookings", ["client_id", "status"])

    # --- conversation_sessions ---
    op.create_table(
        "conversation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "IDLE",
                "COLLECTING",
                "AWAITING_CLIENT_CONFIRMATION",
                "WAITING_REVIEW",
                "PAUSED",
                "HANDOFF",
                "ERROR_REVIEW",
                name="conversation_state",
            ),
            nullable=False,
            server_default="IDLE",
        ),
        sa.Column("active_booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "last_channel",
            sa.Enum("sms", "whatsapp", "worker_app", "admin_panel", name="channel"),
            nullable=True,
        ),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
        sa.ForeignKeyConstraint(["active_booking_id"], ["bookings.id"]),
        sa.UniqueConstraint("client_id", "worker_id", name="uq_session_client_worker"),
    )

    # Add session_id FK on bookings now that conversation_sessions exists
    op.create_foreign_key(
        "fk_bookings_session_id",
        "bookings",
        "conversation_sessions",
        ["session_id"],
        ["id"],
    )

    # --- messages ---
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "direction",
            sa.Enum("inbound", "outbound", name="message_direction"),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.Enum("sms", "whatsapp", "worker_app", "admin_panel", name="message_channel"),
            nullable=False,
        ),
        sa.Column(
            "sender_type",
            sa.Enum("client", "agent", "worker", "admin", "system", name="sender_type"),
            nullable=False,
        ),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("twilio_message_sid", sa.Text, nullable=True),
        sa.Column("raw_payload", postgresql.JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"]),
        sa.UniqueConstraint("twilio_message_sid", name="uq_messages_twilio_sid"),
    )

    # --- booking_media ---
    op.create_table(
        "booking_media",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("sms", "whatsapp", name="media_channel"),
            nullable=False,
        ),
        sa.Column("media_type", sa.Text, nullable=True),
        sa.Column("twilio_media_sid", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("storage_url", sa.Text, nullable=True),
        sa.Column("is_receipt", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"]),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["conversation_sessions.id"]),
    )

    # --- notifications ---
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "target_type",
            sa.Enum("admin", "worker", "client", name="notification_target_type"),
            nullable=False,
        ),
        sa.Column("target_ref", sa.Text, nullable=False),
        sa.Column(
            "channel",
            sa.Enum("in_app", "sms", "whatsapp", "push", "system", name="notification_channel"),
            nullable=False,
        ),
        sa.Column("template_key", sa.Text, nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "status",
            sa.Enum("queued", "sent", "failed", name="notification_status"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"]),
    )

    # --- audit_events ---
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_type", sa.Text, nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column(
            "actor_type",
            sa.Enum("agent", "admin", "worker", "system", name="actor_type"),
            nullable=False,
        ),
        sa.Column("actor_ref", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # --- inbound_idempotency ---
    op.create_table(
        "inbound_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "provider",
            sa.Enum("twilio", name="inbound_provider"),
            nullable=False,
        ),
        sa.Column("external_id", sa.Text, nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("result_ref", sa.Text, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "external_id", name="uq_idempotency_provider_external"),
    )


def downgrade() -> None:
    op.drop_table("inbound_idempotency")
    op.drop_table("audit_events")
    op.drop_table("notifications")
    op.drop_table("booking_media")
    op.drop_table("messages")
    op.drop_constraint("fk_bookings_session_id", "bookings", type_="foreignkey")
    op.drop_table("conversation_sessions")
    op.drop_table("bookings")
    op.drop_table("clients")
    op.drop_table("workers")

    for enum_name in [
        "conversation_state",
        "booking_status",
        "booking_type",
        "channel",
        "message_direction",
        "sender_type",
        "notification_target_type",
        "notification_channel",
        "notification_status",
        "actor_type",
        "awaiting_review_from",
        "inbound_provider",
        "media_channel",
        "message_channel",
    ]:
        sa.Enum(name=enum_name).drop(op.get_bind(), checkfirst=True)
