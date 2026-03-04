"""APScheduler cron jobs for daily and weekly email reports."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

from trackyr.config import cfg
from trackyr.db.writer import log_tracker_event
from trackyr.email_send import send_email
from trackyr.reports import generate_daily_report, generate_weekly_report, render_html

log = logging.getLogger(__name__)


def _send_report(report_type: str, generate_fn, make_subject) -> None:
    """Generate, render, and email a report. Logs result to tracker_events."""
    event_type = f"{report_type}_email"
    try:
        report = generate_fn()
        html = render_html(report, report_type)
        subject = make_subject(report)
        success = send_email(subject=subject, html_body=html)
        log_tracker_event(event_type, {"success": success})
    except Exception:
        log.exception("Failed to send %s report", report_type)
        log_tracker_event(event_type, {"success": False, "error": "exception"})


def _send_daily_report() -> None:
    today = datetime.now(timezone.utc).date()
    _send_report(
        "daily",
        lambda: generate_daily_report(today),
        lambda r: f"Trackyr Daily Report — {r['date']}",
    )


def _send_weekly_report() -> None:
    today = datetime.now(timezone.utc).date()
    _send_report(
        "weekly",
        lambda: generate_weekly_report(today),
        lambda r: f"Trackyr Weekly Report — {r['week_start']} to {r['week_ending']}",
    )


def start_scheduler() -> BackgroundScheduler:
    """Create and start the APScheduler with daily/weekly cron jobs."""
    scheduler = BackgroundScheduler(daemon=True)

    scheduler.add_job(
        _send_daily_report,
        "cron",
        hour=cfg.daily_report_hour,
        minute=0,
        id="daily_report",
        name="Daily activity report email",
    )

    weekly_day = cfg.weekly_report_day.lower()
    scheduler.add_job(
        _send_weekly_report,
        "cron",
        day_of_week=weekly_day,
        hour=cfg.weekly_report_hour,
        minute=0,
        id="weekly_report",
        name="Weekly activity report email",
    )

    scheduler.start()
    log.info(
        "Scheduler started — daily at %d:00, weekly on %s at %d:00",
        cfg.daily_report_hour,
        weekly_day,
        cfg.weekly_report_hour,
    )
    return scheduler
