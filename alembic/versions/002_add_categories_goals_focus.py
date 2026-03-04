"""Add app_categories, goals, focus_sessions tables and device_id column

Revision ID: 002
Revises: 001
Create Date: 2026-03-03
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_categories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("process_name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="other"),
        sa.Column("is_productive", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("process_name"),
    )
    op.create_index(
        "ix_app_categories_process_name", "app_categories", ["process_name"]
    )

    op.create_table(
        "goals",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("goal_type", sa.String(50), nullable=False),
        sa.Column("target_process", sa.String(255), nullable=True),
        sa.Column("target_category", sa.String(50), nullable=True),
        sa.Column("target_value", sa.Float(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "focus_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("primary_app", sa.String(255), nullable=False),
        sa.Column("app_switches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_keys", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column(
        "activity_samples",
        sa.Column(
            "device_id",
            sa.String(100),
            nullable=False,
            server_default="default",
        ),
    )


def downgrade() -> None:
    op.drop_column("activity_samples", "device_id")
    op.drop_table("focus_sessions")
    op.drop_table("goals")
    op.drop_table("app_categories")
