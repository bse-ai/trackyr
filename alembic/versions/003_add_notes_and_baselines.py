"""Add daily_notes and baselines tables

Revision ID: 003
Revises: 002
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "daily_notes",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("note_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="user"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daily_notes_date", "daily_notes", ["date"])

    op.create_table(
        "baselines",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("metric_name", sa.String(100), nullable=False),
        sa.Column("period_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("avg_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("stddev_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("min_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column("max_value", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_baselines_metric_name", "baselines", ["metric_name"])


def downgrade() -> None:
    op.drop_table("baselines")
    op.drop_table("daily_notes")
