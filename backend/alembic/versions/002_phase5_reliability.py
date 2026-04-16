"""Phase 5 reliability hardening

Revision ID: 002
Revises: 001
Create Date: 2026-04-16

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE notification_status ADD VALUE IF NOT EXISTS 'retry_pending'")
    op.execute("ALTER TYPE notification_status ADD VALUE IF NOT EXISTS 'dead_letter'")

    op.add_column("notifications", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column(
        "notifications", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "notifications",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("notifications", "retry_count", server_default=None)


def downgrade() -> None:
    op.drop_column("notifications", "next_retry_at")
    op.drop_column("notifications", "retry_count")
    op.drop_column("notifications", "last_error")
