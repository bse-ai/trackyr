"""Generate daily and weekly activity reports from tracked data."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from typing import Any

from sqlalchemy import Integer, func
from sqlalchemy.sql.expression import cast

from trackyr.config import cfg
from trackyr.db.engine import get_session
from trackyr.db.models import ActivitySample, DailySummary
from trackyr.utils import day_bounds as _day_bounds, fmt_duration as _fmt_duration, today as _today

log = logging.getLogger(__name__)


def _render_app_rows_html(apps: list[dict], limit: int = 20) -> str:
    """Build HTML table rows for an app list."""
    parts = []
    for app in apps[:limit]:
        parts.append(
            f"<tr>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee'>{escape(app['process_name'])}</td>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee;text-align:right'>{app['total_seconds_fmt']}</td>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee;text-align:right'>{app['total_clicks']}</td>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee;text-align:right'>{app['total_keys']}</td>"
            f"</tr>"
        )
    return "".join(parts)


def generate_daily_report(target_date: date | None = None) -> dict[str, Any]:
    """Build a structured report dict for one day."""
    if target_date is None:
        target_date = _today()

    session = get_session()
    try:
        # Top apps from daily_summaries
        summaries = (
            session.query(DailySummary)
            .filter(DailySummary.date == target_date)
            .order_by(DailySummary.total_seconds.desc())
            .all()
        )

        top_apps = [
            {
                "process_name": s.process_name,
                "total_seconds": s.total_seconds,
                "total_seconds_fmt": _fmt_duration(s.total_seconds),
                "total_clicks": s.total_clicks,
                "total_keys": s.total_keys,
                "session_count": s.session_count,
            }
            for s in summaries
        ]

        # Aggregate totals from already-fetched summaries
        total_active = sum(s.total_seconds for s in summaries)
        total_clicks = sum(s.total_clicks for s in summaries)
        total_keys = sum(s.total_keys for s in summaries)
        session_count = sum(s.session_count for s in summaries)

        # Idle + total sample counts in a single query
        day_start, day_end = _day_bounds(target_date)

        sample_counts = (
            session.query(
                func.count(ActivitySample.id).label("total"),
                func.sum(cast(ActivitySample.is_idle, Integer)).label("idle"),
            )
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .one()
        )
        total_samples = sample_counts.total or 0
        idle_samples = sample_counts.idle or 0
        total_idle_seconds = idle_samples * cfg.sample_interval

        return {
            "date": target_date.isoformat(),
            "top_apps": top_apps,
            "total_active_seconds": total_active,
            "total_active_fmt": _fmt_duration(total_active),
            "total_idle_seconds": float(total_idle_seconds),
            "total_idle_fmt": _fmt_duration(total_idle_seconds),
            "total_clicks": total_clicks,
            "total_keys": total_keys,
            "session_count": session_count,
            "total_samples": total_samples,
        }
    finally:
        session.close()


def generate_hours_report(hours: int = 1) -> dict[str, Any]:
    """Build a structured report for the last N hours from activity_samples."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)
    interval = cfg.sample_interval

    session = get_session()
    try:
        # Per-app breakdown with idle counts in one query
        app_rows = (
            session.query(
                ActivitySample.process_name,
                func.count(ActivitySample.id).label("samples"),
                func.sum(ActivitySample.mouse_clicks).label("clicks"),
                func.sum(ActivitySample.key_presses).label("keys"),
                func.sum(cast(ActivitySample.is_idle, Integer)).label("idle"),
            )
            .filter(ActivitySample.sampled_at >= cutoff)
            .group_by(ActivitySample.process_name)
            .order_by(func.count(ActivitySample.id).desc())
            .all()
        )

        # Single pass over results
        top_apps = []
        total_samples = 0
        total_idle = 0
        total_clicks = 0
        total_keys = 0
        for r in app_rows:
            top_apps.append({
                "process_name": r.process_name or "unknown",
                "total_seconds": float(r.samples * interval),
                "total_seconds_fmt": _fmt_duration(r.samples * interval),
                "total_clicks": int(r.clicks),
                "total_keys": int(r.keys),
            })
            total_samples += r.samples
            total_idle += r.idle or 0
            total_clicks += r.clicks
            total_keys += r.keys

        active_samples = total_samples - total_idle

        return {
            "hours": hours,
            "cutoff": cutoff.isoformat(),
            "now": now.isoformat(),
            "top_apps": top_apps,
            "total_active_seconds": float(active_samples * interval),
            "total_active_fmt": _fmt_duration(active_samples * interval),
            "total_idle_seconds": float(total_idle * interval),
            "total_idle_fmt": _fmt_duration(total_idle * interval),
            "total_clicks": total_clicks,
            "total_keys": total_keys,
            "total_samples": total_samples,
        }
    finally:
        session.close()


def generate_weekly_report(week_ending: date | None = None) -> dict[str, Any]:
    """Build a structured weekly report aggregating 7 days."""
    if week_ending is None:
        week_ending = _today()

    week_start = week_ending - timedelta(days=6)

    session = get_session()
    try:
        # Fetch all summaries for the week in one query
        all_summaries = (
            session.query(DailySummary)
            .filter(
                DailySummary.date >= week_start,
                DailySummary.date <= week_ending,
            )
            .all()
        )

        # Group by date
        by_date: dict[date, list[DailySummary]] = defaultdict(list)
        for s in all_summaries:
            by_date[s.date].append(s)

        days = []
        for i in range(7):
            d = week_start + timedelta(days=i)
            day_summaries = by_date.get(d, [])
            day_total = sum(s.total_seconds for s in day_summaries)
            day_clicks = sum(s.total_clicks for s in day_summaries)
            day_keys = sum(s.total_keys for s in day_summaries)
            days.append({
                "date": d.isoformat(),
                "weekday": d.strftime("%A"),
                "total_seconds": day_total,
                "total_seconds_fmt": _fmt_duration(day_total),
                "total_clicks": day_clicks,
                "total_keys": day_keys,
            })

        # Top apps across the week
        app_rows = (
            session.query(
                DailySummary.process_name,
                func.sum(DailySummary.total_seconds).label("total_secs"),
                func.sum(DailySummary.total_clicks).label("total_clicks"),
                func.sum(DailySummary.total_keys).label("total_keys"),
            )
            .filter(
                DailySummary.date >= week_start,
                DailySummary.date <= week_ending,
            )
            .group_by(DailySummary.process_name)
            .order_by(func.sum(DailySummary.total_seconds).desc())
            .all()
        )

        top_apps = [
            {
                "process_name": r.process_name,
                "total_seconds": float(r.total_secs),
                "total_seconds_fmt": _fmt_duration(float(r.total_secs)),
                "total_clicks": int(r.total_clicks),
                "total_keys": int(r.total_keys),
            }
            for r in app_rows
        ]

        # Prior week for comparison
        prior_start = week_start - timedelta(days=7)
        prior_end = week_start - timedelta(days=1)
        prior_total = (
            session.query(func.sum(DailySummary.total_seconds))
            .filter(
                DailySummary.date >= prior_start,
                DailySummary.date <= prior_end,
            )
            .scalar()
        ) or 0.0

        week_total = sum(d["total_seconds"] for d in days)

        return {
            "week_start": week_start.isoformat(),
            "week_ending": week_ending.isoformat(),
            "days": days,
            "top_apps": top_apps,
            "total_seconds": week_total,
            "total_seconds_fmt": _fmt_duration(week_total),
            "prior_week_seconds": float(prior_total),
            "prior_week_fmt": _fmt_duration(float(prior_total)),
            "total_clicks": sum(d["total_clicks"] for d in days),
            "total_keys": sum(d["total_keys"] for d in days),
        }
    finally:
        session.close()


def render_html(report_data: dict[str, Any], template_type: str) -> str:
    """Render a report dict as email-safe HTML."""
    if template_type == "daily":
        return _render_daily_html(report_data)
    elif template_type == "weekly":
        return _render_weekly_html(report_data)
    raise ValueError(f"Unknown template_type: {template_type}")


def _render_daily_html(r: dict[str, Any]) -> str:
    rows = _render_app_rows_html(r["top_apps"], limit=20)

    return f"""\
<html><body style="font-family:Segoe UI,Arial,sans-serif;color:#333;max-width:600px;margin:auto">
<h2 style="color:#2c5282">Trackyr Daily Report — {escape(r['date'])}</h2>
<table style="margin-bottom:16px">
  <tr><td style="padding:2px 8px"><strong>Active time:</strong></td><td>{r['total_active_fmt']}</td></tr>
  <tr><td style="padding:2px 8px"><strong>Idle time:</strong></td><td>{r['total_idle_fmt']}</td></tr>
  <tr><td style="padding:2px 8px"><strong>Clicks:</strong></td><td>{r['total_clicks']:,}</td></tr>
  <tr><td style="padding:2px 8px"><strong>Key presses:</strong></td><td>{r['total_keys']:,}</td></tr>
  <tr><td style="padding:2px 8px"><strong>App sessions:</strong></td><td>{r['session_count']}</td></tr>
</table>
<h3 style="color:#2c5282">Top Apps</h3>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#f7fafc">
    <th style="padding:6px 12px;text-align:left;border-bottom:2px solid #cbd5e0">App</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Time</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Clicks</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Keys</th>
  </tr>
  {rows}
</table>
<p style="color:#999;font-size:12px;margin-top:24px">Generated by Trackyr</p>
</body></html>"""


def _render_weekly_html(r: dict[str, Any]) -> str:
    day_parts = []
    for d in r["days"]:
        day_parts.append(
            f"<tr>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee'>{escape(d['weekday'])}</td>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee'>{escape(d['date'])}</td>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee;text-align:right'>{d['total_seconds_fmt']}</td>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee;text-align:right'>{d['total_clicks']}</td>"
            f"<td style='padding:4px 12px;border-bottom:1px solid #eee;text-align:right'>{d['total_keys']}</td>"
            f"</tr>"
        )
    day_rows = "".join(day_parts)
    app_rows = _render_app_rows_html(r["top_apps"], limit=15)

    return f"""\
<html><body style="font-family:Segoe UI,Arial,sans-serif;color:#333;max-width:600px;margin:auto">
<h2 style="color:#2c5282">Trackyr Weekly Report</h2>
<p>{escape(r['week_start'])} to {escape(r['week_ending'])}</p>
<table style="margin-bottom:16px">
  <tr><td style="padding:2px 8px"><strong>Total active:</strong></td><td>{r['total_seconds_fmt']}</td></tr>
  <tr><td style="padding:2px 8px"><strong>Prior week:</strong></td><td>{r['prior_week_fmt']}</td></tr>
  <tr><td style="padding:2px 8px"><strong>Clicks:</strong></td><td>{r['total_clicks']:,}</td></tr>
  <tr><td style="padding:2px 8px"><strong>Key presses:</strong></td><td>{r['total_keys']:,}</td></tr>
</table>
<h3 style="color:#2c5282">Day-by-Day</h3>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#f7fafc">
    <th style="padding:6px 12px;text-align:left;border-bottom:2px solid #cbd5e0">Day</th>
    <th style="padding:6px 12px;text-align:left;border-bottom:2px solid #cbd5e0">Date</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Time</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Clicks</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Keys</th>
  </tr>
  {day_rows}
</table>
<h3 style="color:#2c5282">Top Apps</h3>
<table style="border-collapse:collapse;width:100%">
  <tr style="background:#f7fafc">
    <th style="padding:6px 12px;text-align:left;border-bottom:2px solid #cbd5e0">App</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Time</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Clicks</th>
    <th style="padding:6px 12px;text-align:right;border-bottom:2px solid #cbd5e0">Keys</th>
  </tr>
  {app_rows}
</table>
<p style="color:#999;font-size:12px;margin-top:24px">Generated by Trackyr</p>
</body></html>"""
