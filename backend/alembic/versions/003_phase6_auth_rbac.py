"""Phase 6 auth and RBAC foundation

Revision ID: 003
Revises: 002
Create Date: 2026-04-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_role = postgresql.ENUM("admin", "worker", name="user_role", create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)

    section_key = postgresql.ENUM(
        "dashboard",
        "live_chat",
        "bookings",
        "timeline",
        "media",
        "notifications",
        "schedule",
        "settings",
        name="section_key",
        create_type=False,
    )
    section_key.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "role",
            user_role,
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_refresh_jti", sa.Text(), nullable=True),
        sa.Column("worker_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("worker_id", name="uq_users_worker_id"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"]),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "worker_section_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "section_key",
            section_key,
            nullable=False,
        ),
        sa.Column("can_view", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.UniqueConstraint("worker_user_id", "section_key", name="uq_worker_user_section"),
        sa.ForeignKeyConstraint(["worker_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
    )


def downgrade() -> None:
    op.drop_table("worker_section_permissions")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS section_key")
    op.execute("DROP TYPE IF EXISTS user_role")
