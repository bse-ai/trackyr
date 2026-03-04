"""Shared utility functions."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def fmt_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym'."""
    h, remainder = divmod(int(seconds), 3600)
    m = remainder // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def day_bounds(target_date: date) -> tuple[datetime, datetime]:
    """Return (start, end) datetimes for a given date in UTC."""
    day_start = datetime(
        target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc
    )
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


def today() -> date:
    """Return today's date in UTC."""
    return datetime.now(timezone.utc).date()
