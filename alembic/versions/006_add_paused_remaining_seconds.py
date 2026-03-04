"""Add paused_remaining_seconds to pomodoro_timers

Revision ID: 006
Revises: 005
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pomodoro_timers",
        sa.Column("paused_remaining_seconds", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("pomodoro_timers", "paused_remaining_seconds")
