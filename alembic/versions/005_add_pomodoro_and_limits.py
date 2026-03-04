"""Add pomodoro_timers, pomodoro_records, app_limits, and limit_alerts tables

Revision ID: 005
Revises: 004
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pomodoro_timers",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="idle"),
        sa.Column("work_minutes", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("short_break_minutes", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("long_break_minutes", sa.Integer(), nullable=False, server_default="15"),
        sa.Column("long_break_every", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("phase_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phase_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pomodoro_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interruption_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "pomodoro_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("timer_id", sa.BigInteger(), nullable=False),
        sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("interruptions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("primary_app", sa.String(255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pomodoro_records_date", "pomodoro_records", ["date"])

    op.create_table(
        "app_limits",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("process_name", sa.String(255), nullable=False),
        sa.Column("daily_limit_seconds", sa.Integer(), nullable=False),
        sa.Column("warn_at_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("process_name"),
    )
    op.create_index("ix_app_limits_process_name", "app_limits", ["process_name"])

    op.create_table(
        "limit_alerts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("process_name", sa.String(255), nullable=False),
        sa.Column("alert_type", sa.String(20), nullable=False),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("usage_seconds", sa.Float(), nullable=False),
        sa.Column("limit_seconds", sa.Integer(), nullable=False),
        sa.Column("notified", sa.Boolean(), nullable=False, server_default="false"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_limit_alerts_process_name", "limit_alerts", ["process_name"])


def downgrade() -> None:
    op.drop_table("limit_alerts")
    op.drop_table("app_limits")
    op.drop_table("pomodoro_records")
    op.drop_table("pomodoro_timers")
