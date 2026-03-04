from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ActivitySample(Base):
    __tablename__ = "activity_samples"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sampled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    window_title: Mapped[str | None] = mapped_column(Text)
    process_name: Mapped[str | None] = mapped_column(String(255), index=True)
    process_pid: Mapped[int | None] = mapped_column(Integer)
    is_idle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    idle_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mouse_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    key_presses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mouse_distance_px: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    device_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default", server_default="default")


class AppSession(Base):
    __tablename__ = "app_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    process_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    window_title: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_keys: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DailySummary(Base):
    __tablename__ = "daily_summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    process_name: Mapped[str] = mapped_column(String(255), nullable=False)
    total_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_keys: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TrackerEvent(Base):
    __tablename__ = "tracker_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[dict | None] = mapped_column(JSONB)


class AppCategory(Base):
    __tablename__ = "app_categories"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    process_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="other")
    is_productive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_process: Mapped[str | None] = mapped_column(String(255))
    target_category: Mapped[str | None] = mapped_column(String(50))
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class FocusSession(Base):
    __tablename__ = "focus_sessions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    primary_app: Mapped[str] = mapped_column(String(255), nullable=False)
    app_switches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_keys: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class DailyNote(Base):
    __tablename__ = "daily_notes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Baseline(Base):
    __tablename__ = "baselines"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    period_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    avg_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stddev_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    min_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[dict | None] = mapped_column(JSONB)
