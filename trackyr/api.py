"""FastAPI server exposing activity data for ClawdBot integration."""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone

import uvicorn
from fastapi import FastAPI, HTTPException

from trackyr.config import cfg
from trackyr.db.engine import get_session
from trackyr.db.models import ActivitySample
from trackyr.reports import generate_daily_report, generate_hours_report, generate_weekly_report

log = logging.getLogger(__name__)

app = FastAPI(title="Trackyr API", version="0.1.0")


@app.get("/api/v1/summary/today")
def summary_today():
    """Today's activity breakdown."""
    return generate_daily_report()


@app.get("/api/v1/summary/{target_date}")
def summary_date(target_date: date):
    """Activity breakdown for a specific date (YYYY-MM-DD)."""
    return generate_daily_report(target_date)


@app.get("/api/v1/weekly")
def weekly_summary():
    """Current week summary (last 7 days)."""
    return generate_weekly_report()


@app.get("/api/v1/summary/hours/{n}")
def summary_hours(n: int):
    """Activity breakdown for the last N hours."""
    if n < 1 or n > 72:
        raise HTTPException(status_code=400, detail="Hours must be between 1 and 72")
    return generate_hours_report(n)


@app.get("/api/v1/current")
def current_activity():
    """What app is active right now (most recent sample)."""
    session = get_session()
    try:
        sample = (
            session.query(ActivitySample)
            .order_by(ActivitySample.sampled_at.desc())
            .first()
        )
        if not sample:
            raise HTTPException(status_code=404, detail="No samples recorded yet")

        age = (datetime.now(timezone.utc) - sample.sampled_at).total_seconds()

        return {
            "process_name": sample.process_name,
            "window_title": sample.window_title,
            "sampled_at": sample.sampled_at.isoformat(),
            "is_idle": sample.is_idle,
            "idle_seconds": sample.idle_seconds,
            "age_seconds": round(age, 1),
            "stale": age > 30,
        }
    finally:
        session.close()


def start_api_server() -> threading.Thread:
    """Start uvicorn in a daemon thread. Returns the thread."""
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=cfg.api_port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name="api-server")
    thread.start()
    log.info("API server started on port %d", cfg.api_port)
    return thread
