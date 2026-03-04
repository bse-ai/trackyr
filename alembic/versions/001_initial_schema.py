"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "activity_samples",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "sampled_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("window_title", sa.Text(), nullable=True),
        sa.Column("process_name", sa.String(255), nullable=True),
        sa.Column("process_pid", sa.Integer(), nullable=True),
        sa.Column("is_idle", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("idle_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("mouse_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("key_presses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mouse_distance_px", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_activity_samples_sampled_at", "activity_samples", ["sampled_at"])
    op.create_index("ix_activity_samples_process_name", "activity_samples", ["process_name"])

    op.create_table(
        "app_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("process_name", sa.String(255), nullable=False),
        sa.Column("window_title", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("total_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_keys", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_app_sessions_process_name", "app_sessions", ["process_name"])

    op.create_table(
        "daily_summaries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("process_name", sa.String(255), nullable=False),
        sa.Column("total_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_keys", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("session_count", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_daily_summaries_date", "daily_summaries", ["date"])

    op.create_table(
        "tracker_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tracker_events_event_type", "tracker_events", ["event_type"])


def downgrade() -> None:
    op.drop_table("tracker_events")
    op.drop_table("daily_summaries")
    op.drop_table("app_sessions")
    op.drop_table("activity_samples")
