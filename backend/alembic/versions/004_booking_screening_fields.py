"""Add size screening and alone policy fields to bookings

Revision ID: 004
Revises: 003
Create Date: 2026-04-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("client_size_inches", sa.Integer(), nullable=True))
    op.add_column("bookings", sa.Column("alone_policy_confirmed", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "alone_policy_confirmed")
    op.drop_column("bookings", "client_size_inches")
