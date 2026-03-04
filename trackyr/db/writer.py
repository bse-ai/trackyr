"""Batched database writer with bounded buffer and retry."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError

from trackyr.config import cfg
from trackyr.db.engine import get_session
from trackyr.db.models import ActivitySample, AppSession, DailySummary, TrackerEvent

if TYPE_CHECKING:
    from trackyr.collectors.input import InputSnapshot
    from trackyr.collectors.window import WindowInfo

log = logging.getLogger(__name__)


class BatchWriter:
    """Buffers activity samples and writes to PG with retry.

    Uses a bounded deque so if the DB is down we keep the most recent
    samples (up to buffer_max_size) and drop the oldest.
    """

    def __init__(self) -> None:
        self._buffer: deque[ActivitySample] = deque(maxlen=cfg.buffer_max_size)
        self._db_healthy = True
        # Track current app session for incremental updates
        self._current_session_id: int | None = None
        self._current_process: str | None = None

    @property
    def db_healthy(self) -> bool:
        return self._db_healthy

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    def add_sample(
        self,
        window: WindowInfo,
        idle_seconds: float,
        is_idle: bool,
        input_snap: InputSnapshot,
    ) -> None:
        """Create a sample and add to buffer."""
        now = datetime.now(timezone.utc)
        sample = ActivitySample(
            sampled_at=now,
            window_title=window.title[:2000] if window.title else None,
            process_name=window.process_name,
            process_pid=window.pid,
            is_idle=is_idle,
            idle_seconds=idle_seconds,
            mouse_clicks=input_snap.mouse_clicks,
            key_presses=input_snap.key_presses,
            mouse_distance_px=input_snap.mouse_distance_px,
        )
        self._buffer.append(sample)
        self._flush(window, input_snap, now)

    def log_event(self, event_type: str, details: dict | None = None) -> None:
        """Write a tracker event directly (best-effort)."""
        try:
            session = get_session()
            try:
                event = TrackerEvent(
                    event_type=event_type,
                    occurred_at=datetime.now(timezone.utc),
                    details=details,
                )
                session.add(event)
                session.commit()
            finally:
                session.close()
        except SQLAlchemyError:
            log.warning("Failed to log event %s", event_type, exc_info=True)

    def _flush(
        self,
        window: WindowInfo,
        input_snap: InputSnapshot,
        now: datetime,
    ) -> None:
        """Try to write all buffered samples to DB."""
        if not self._buffer:
            return

        try:
            session = get_session()
            try:
                # Flush buffered samples
                samples = list(self._buffer)
                session.add_all(samples)

                # Update app session
                self._update_app_session(session, window, input_snap, now)

                # Update daily summary
                self._update_daily_summary(
                    session, window.process_name, input_snap, now
                )

                session.commit()
                self._buffer.clear()
                if not self._db_healthy:
                    log.info("Database connection restored")
                self._db_healthy = True
            finally:
                session.close()
        except SQLAlchemyError:
            self._db_healthy = False
            log.warning(
                "DB write failed, %d samples buffered", len(self._buffer), exc_info=True
            )

    def _update_app_session(
        self,
        session,
        window: WindowInfo,
        input_snap: InputSnapshot,
        now: datetime,
    ) -> None:
        """Track contiguous time on one app."""
        process = window.process_name or "unknown"

        if process == self._current_process and self._current_session_id is not None:
            # Extend current session
            app_session = session.get(AppSession, self._current_session_id)
            if app_session:
                app_session.ended_at = now
                app_session.duration_seconds = (
                    now - app_session.started_at
                ).total_seconds()
                app_session.sample_count += 1
                app_session.total_clicks += input_snap.mouse_clicks
                app_session.total_keys += input_snap.key_presses
                app_session.window_title = (
                    window.title[:2000] if window.title else None
                )
                return

        # New app — start a new session
        new_session = AppSession(
            process_name=process,
            window_title=window.title[:2000] if window.title else None,
            started_at=now,
            ended_at=now,
            duration_seconds=0.0,
            sample_count=1,
            total_clicks=input_snap.mouse_clicks,
            total_keys=input_snap.key_presses,
        )
        session.add(new_session)
        session.flush()  # Get the ID
        self._current_session_id = new_session.id
        self._current_process = process

    def _update_daily_summary(
        self,
        session,
        process_name: str | None,
        input_snap: InputSnapshot,
        now: datetime,
    ) -> None:
        """Upsert the daily summary row for this process."""
        process = process_name or "unknown"
        today = now.date()

        summary = session.query(DailySummary).filter(
            and_(
                DailySummary.date == today,
                DailySummary.process_name == process,
            )
        ).first()

        if summary:
            summary.total_seconds += cfg.sample_interval
            summary.total_clicks += input_snap.mouse_clicks
            summary.total_keys += input_snap.key_presses
        else:
            summary = DailySummary(
                date=today,
                process_name=process,
                total_seconds=cfg.sample_interval,
                total_clicks=input_snap.mouse_clicks,
                total_keys=input_snap.key_presses,
                session_count=1,
            )
            session.add(summary)
