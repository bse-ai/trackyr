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
