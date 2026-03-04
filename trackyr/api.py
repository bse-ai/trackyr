"""FastAPI server exposing activity data for ClawdBot integration."""

from __future__ import annotations

import csv
import io
import logging
import threading
from datetime import date, datetime, timedelta, timezone

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, text

from trackyr.config import cfg
from trackyr.db.engine import get_session
from trackyr.db.models import (
    ActivitySample,
    AppCategory,
    AppSession,
    Baseline,
    DailyNote,
    DailySummary,
    FocusSession,
    Goal,
)
from trackyr.intelligence import (
    anomaly_detection,
    compute_baselines,
    context_switch_count,
    context_switch_patterns,
    current_context,
    daily_narrative,
    detect_focus_sessions,
    engagement_curve,
    hourly_heatmap,
    idle_pattern_analysis,
    productivity_score,
    trend_comparison,
    workday_detection,
)
from trackyr.reports import generate_daily_report, generate_hours_report, generate_weekly_report

log = logging.getLogger(__name__)

app = FastAPI(title="Trackyr API", version="0.1.0")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CategoryIn(BaseModel):
    process_name: str
    category: str = "other"
    is_productive: bool = True


class GoalIn(BaseModel):
    name: str
    goal_type: str  # "min_time", "max_time", "min_productive_pct"
    target_process: str | None = None
    target_category: str | None = None
    target_value: float  # seconds for time goals, 0-100 for percentage


class NoteIn(BaseModel):
    date: str  # YYYY-MM-DD
    note_text: str
    source: str = "user"


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/summary/today")
def summary_today():
    """Today's activity breakdown."""
    return generate_daily_report()


@app.get("/api/v1/summary/hours/{n}")
def summary_hours(n: int):
    """Activity breakdown for the last N hours."""
    if n < 1 or n > 72:
        raise HTTPException(status_code=400, detail="Hours must be between 1 and 72")
    return generate_hours_report(n)


@app.get("/api/v1/summary/{target_date}")
def summary_date(target_date: date):
    """Activity breakdown for a specific date (YYYY-MM-DD)."""
    return generate_daily_report(target_date)


@app.get("/api/v1/weekly")
def weekly_summary():
    """Current week summary (last 7 days)."""
    return generate_weekly_report()


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


# ---------------------------------------------------------------------------
# New endpoints
# ---------------------------------------------------------------------------


def _fmt_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym'."""
    h, remainder = divmod(int(seconds), 3600)
    m = remainder // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


@app.get("/api/v1/timeline/{target_date}")
def timeline(
    target_date: date,
    app_name: str | None = Query(None, alias="app"),
    category: str | None = None,
    limit: int = 500,
):
    """Chronological list of activity samples for a date."""
    if limit > 1000:
        limit = 1000

    day_start = datetime(
        target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc
    )
    day_end = day_start + timedelta(days=1)

    session = get_session()
    try:
        query = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .order_by(ActivitySample.sampled_at)
        )

        if app_name:
            query = query.filter(ActivitySample.process_name == app_name)

        if category:
            cat_processes = (
                session.query(AppCategory.process_name)
                .filter(AppCategory.category == category)
                .subquery()
            )
            query = query.filter(ActivitySample.process_name.in_(cat_processes))

        samples = query.limit(limit).all()

        return [
            {
                "sampled_at": s.sampled_at.isoformat(),
                "process_name": s.process_name,
                "window_title": (s.window_title or "")[:100],
                "is_idle": s.is_idle,
                "mouse_clicks": s.mouse_clicks,
                "key_presses": s.key_presses,
            }
            for s in samples
        ]
    finally:
        session.close()


@app.get("/api/v1/health")
def health():
    """System health check."""
    session = get_session()
    try:
        # Check DB connectivity
        try:
            session.execute(text("SELECT 1"))
            db_connected = True
        except Exception:
            db_connected = False

        # Most recent sample
        latest = (
            session.query(ActivitySample)
            .order_by(ActivitySample.sampled_at.desc())
            .first()
        )
        if latest:
            last_sample_age = (
                datetime.now(timezone.utc) - latest.sampled_at
            ).total_seconds()
        else:
            last_sample_age = None

        # Today's sample count
        today = datetime.now(timezone.utc).date()
        day_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        today_count = (
            session.query(func.count(ActivitySample.id))
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .scalar()
        ) or 0

        collector_running = (
            last_sample_age is not None and last_sample_age < 30
        )

        if not db_connected:
            status = "error"
        elif not collector_running:
            status = "degraded"
        else:
            status = "healthy"

        return {
            "status": status,
            "db_connected": db_connected,
            "last_sample_age_seconds": (
                round(last_sample_age, 1) if last_sample_age is not None else None
            ),
            "today_sample_count": today_count,
            "collector_running": collector_running,
        }
    finally:
        session.close()


@app.get("/api/v1/focus-sessions/{target_date}")
def focus_sessions(target_date: date):
    """Detected focus sessions for a given date."""
    return detect_focus_sessions(target_date)


@app.get("/api/v1/context-switches/{target_date}/patterns")
def switch_patterns(target_date: date):
    """Context switch patterns for a given date."""
    return context_switch_patterns(target_date)


@app.get("/api/v1/context-switches/{target_date}")
def context_switches(target_date: date):
    """Context switch count for a given date."""
    return context_switch_count(target_date)


@app.get("/api/v1/productivity/{target_date}")
def productivity(target_date: date):
    """Productivity score for a given date."""
    return productivity_score(target_date)


@app.get("/api/v1/trends")
def trends(days: int = 7):
    """Trend comparison over N days."""
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 90")
    return trend_comparison(days=days)


@app.get("/api/v1/context")
def ai_context():
    """Current context summary for AI prompt injection."""
    return current_context()


@app.get("/api/v1/standup")
def standup():
    """Generate a standup summary from yesterday's activity."""
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)

    daily = generate_daily_report(yesterday)
    sessions = detect_focus_sessions(yesterday)
    prod = productivity_score(yesterday)

    # Build standup text
    top_5 = daily.get("top_apps", [])[:5]
    lines = []
    for a in top_5:
        lines.append(f"- {a['process_name']}: {a.get('total_seconds_fmt', _fmt_duration(a.get('total_seconds', 0)))}")

    productivity_pct = prod.get("productivity_pct", prod.get("score", 0))

    standup_text = (
        f"Yesterday I was active for {daily.get('total_active_fmt', '0m')} "
        f"and idle for {daily.get('total_idle_fmt', '0m')}.\n"
        f"Top apps:\n" + "\n".join(lines) + "\n"
        f"Productivity: {productivity_pct}%"
    )

    return {
        "date": yesterday.isoformat(),
        "summary": {
            "active_time": daily.get("total_active_fmt", "0m"),
            "idle_time": daily.get("total_idle_fmt", "0m"),
            "top_apps": top_5,
        },
        "focus_sessions": sessions,
        "productivity_pct": productivity_pct,
        "standup_text": standup_text,
    }


@app.get("/api/v1/categories")
def list_categories():
    """List all app categories."""
    session = get_session()
    try:
        cats = session.query(AppCategory).all()
        return [
            {
                "process_name": c.process_name,
                "category": c.category,
                "is_productive": c.is_productive,
            }
            for c in cats
        ]
    finally:
        session.close()


@app.post("/api/v1/categories")
def set_category(cat: CategoryIn):
    """Create or update an app category."""
    session = get_session()
    try:
        existing = (
            session.query(AppCategory)
            .filter(AppCategory.process_name == cat.process_name)
            .first()
        )
        if existing:
            existing.category = cat.category
            existing.is_productive = cat.is_productive
            session.commit()
            return {
                "process_name": existing.process_name,
                "category": existing.category,
                "is_productive": existing.is_productive,
            }
        else:
            new_cat = AppCategory(
                process_name=cat.process_name,
                category=cat.category,
                is_productive=cat.is_productive,
            )
            session.add(new_cat)
            session.commit()
            return {
                "process_name": new_cat.process_name,
                "category": new_cat.category,
                "is_productive": new_cat.is_productive,
            }
    finally:
        session.close()


@app.get("/api/v1/goals")
def list_goals(active_only: bool = True):
    """List goals, optionally filtered to active only."""
    session = get_session()
    try:
        query = session.query(Goal)
        if active_only:
            query = query.filter(Goal.active == True)  # noqa: E712
        goals = query.all()
        return [
            {
                "id": g.id,
                "name": g.name,
                "goal_type": g.goal_type,
                "target_process": g.target_process,
                "target_category": g.target_category,
                "target_value": g.target_value,
                "active": g.active,
            }
            for g in goals
        ]
    finally:
        session.close()


@app.post("/api/v1/goals")
def create_goal(goal: GoalIn):
    """Create a new goal."""
    session = get_session()
    try:
        new_goal = Goal(
            name=goal.name,
            goal_type=goal.goal_type,
            target_process=goal.target_process,
            target_category=goal.target_category,
            target_value=goal.target_value,
        )
        session.add(new_goal)
        session.commit()
        return {
            "id": new_goal.id,
            "name": new_goal.name,
            "goal_type": new_goal.goal_type,
            "target_process": new_goal.target_process,
            "target_category": new_goal.target_category,
            "target_value": new_goal.target_value,
            "active": new_goal.active,
        }
    finally:
        session.close()


@app.get("/api/v1/goals/progress")
def goal_progress():
    """Check progress on all active goals."""
    session = get_session()
    try:
        goals = session.query(Goal).filter(Goal.active == True).all()  # noqa: E712
        today = datetime.now(timezone.utc).date()

        results = []
        for g in goals:
            current_value = 0.0
            target = g.target_value

            if g.goal_type in ("min_time", "max_time") and g.target_process:
                summary = (
                    session.query(DailySummary)
                    .filter(
                        DailySummary.date == today,
                        DailySummary.process_name == g.target_process,
                    )
                    .first()
                )
                if summary:
                    current_value = summary.total_seconds

            elif g.goal_type == "min_productive_pct":
                prod = productivity_score(today)
                current_value = prod.get("productivity_pct", prod.get("score", 0))

            if target > 0:
                progress_pct = round(min(current_value / target * 100, 100), 1)
            else:
                progress_pct = 100.0

            if g.goal_type == "max_time":
                met = current_value <= target
            else:
                met = current_value >= target

            results.append({
                "goal": {
                    "name": g.name,
                    "type": g.goal_type,
                    "target": target,
                },
                "current_value": round(current_value, 1),
                "target_value": target,
                "progress_pct": progress_pct,
                "met": met,
            })

        return results
    finally:
        session.close()


@app.get("/api/v1/search")
def search(q: str, target_date: date | None = None, limit: int = 50):
    """Search activity samples by window title or process name."""
    if limit > 200:
        limit = 200

    session = get_session()
    try:
        pattern = f"%{q}%"
        query = session.query(ActivitySample).filter(
            (ActivitySample.window_title.ilike(pattern))
            | (ActivitySample.process_name.ilike(pattern))
        )

        if target_date:
            day_start = datetime(
                target_date.year, target_date.month, target_date.day,
                tzinfo=timezone.utc,
            )
            day_end = day_start + timedelta(days=1)
            query = query.filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )

        query = query.order_by(ActivitySample.sampled_at.desc()).limit(limit)
        samples = query.all()

        return [
            {
                "sampled_at": s.sampled_at.isoformat(),
                "process_name": s.process_name,
                "window_title": (s.window_title or "")[:150],
                "is_idle": s.is_idle,
            }
            for s in samples
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Intelligence endpoints
# ---------------------------------------------------------------------------


@app.get("/api/v1/heatmap/week")
def heatmap_week():
    """Hourly heatmap for the last 7 days."""
    today = datetime.now(timezone.utc).date()
    days = []
    for i in range(6, -1, -1):
        d = today - timedelta(days=i)
        days.append({"date": d.isoformat(), "hours": hourly_heatmap(d)})
    return {"days": days}


@app.get("/api/v1/heatmap/{target_date}")
def heatmap(target_date: date):
    """Hourly heatmap for a given date."""
    return hourly_heatmap(target_date)


@app.get("/api/v1/workday/{target_date}")
def workday(target_date: date):
    """Workday detection for a given date."""
    return workday_detection(target_date)


@app.get("/api/v1/narrative/{target_date}")
def narrative(target_date: date):
    """Daily narrative for a given date."""
    return daily_narrative(target_date)


@app.get("/api/v1/anomalies/{target_date}")
def anomalies(target_date: date):
    """Anomaly detection for a given date."""
    return anomaly_detection(target_date)


@app.get("/api/v1/engagement/{target_date}")
def engagement(target_date: date):
    """Engagement curve for a given date."""
    return engagement_curve(target_date)


@app.get("/api/v1/baselines")
def get_baselines():
    """Get all baselines, computing them if none exist."""
    session = get_session()
    try:
        baselines = session.query(Baseline).all()
        if not baselines:
            compute_baselines()
            baselines = session.query(Baseline).all()
        return [
            {
                "id": b.id,
                "metric_name": b.metric_name,
                "period_days": b.period_days,
                "avg_value": b.avg_value,
                "stddev_value": b.stddev_value,
                "min_value": b.min_value,
                "max_value": b.max_value,
                "computed_at": b.computed_at.isoformat(),
                "details": b.details,
            }
            for b in baselines
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Notes CRUD
# ---------------------------------------------------------------------------


@app.get("/api/v1/notes/{target_date}")
def get_notes(target_date: date):
    """Get notes for a given date."""
    session = get_session()
    try:
        notes = (
            session.query(DailyNote)
            .filter(DailyNote.date == target_date)
            .order_by(DailyNote.created_at)
            .all()
        )
        return [
            {
                "id": n.id,
                "date": n.date.isoformat(),
                "note_text": n.note_text,
                "source": n.source,
                "created_at": n.created_at.isoformat(),
            }
            for n in notes
        ]
    finally:
        session.close()


@app.post("/api/v1/notes")
def create_note(note: NoteIn):
    """Create a new daily note."""
    try:
        note_date = date.fromisoformat(note.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")

    session = get_session()
    try:
        new_note = DailyNote(
            date=note_date,
            note_text=note.note_text,
            source=note.source,
        )
        session.add(new_note)
        session.commit()
        return {
            "id": new_note.id,
            "date": new_note.date.isoformat(),
            "note_text": new_note.note_text,
            "source": new_note.source,
            "created_at": new_note.created_at.isoformat(),
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Focus session control
# ---------------------------------------------------------------------------


@app.post("/api/v1/focus/start")
def focus_start(target_app: str | None = None, duration_minutes: int = 90):
    """Start a manual focus session."""
    now = datetime.now(timezone.utc)
    ended_at = now + timedelta(minutes=duration_minutes)
    duration_seconds = duration_minutes * 60.0

    session = get_session()
    try:
        fs = FocusSession(
            started_at=now,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            primary_app=target_app or "manual",
        )
        session.add(fs)
        session.commit()
        return {
            "id": fs.id,
            "started_at": fs.started_at.isoformat(),
            "ended_at": fs.ended_at.isoformat(),
            "duration_seconds": fs.duration_seconds,
            "primary_app": fs.primary_app,
        }
    finally:
        session.close()


@app.post("/api/v1/focus/stop")
def focus_stop():
    """Stop the currently active focus session."""
    now = datetime.now(timezone.utc)

    session = get_session()
    try:
        fs = (
            session.query(FocusSession)
            .filter(FocusSession.ended_at > now)
            .order_by(FocusSession.started_at.desc())
            .first()
        )
        if not fs:
            raise HTTPException(status_code=404, detail="No active focus session")

        fs.ended_at = now
        fs.duration_seconds = (now - fs.started_at).total_seconds()
        session.commit()
        return {
            "id": fs.id,
            "started_at": fs.started_at.isoformat(),
            "ended_at": fs.ended_at.isoformat(),
            "duration_seconds": fs.duration_seconds,
            "primary_app": fs.primary_app,
        }
    finally:
        session.close()


@app.get("/api/v1/focus/active")
def focus_active():
    """Check if a focus session is currently active."""
    now = datetime.now(timezone.utc)

    session = get_session()
    try:
        fs = (
            session.query(FocusSession)
            .filter(FocusSession.ended_at > now)
            .order_by(FocusSession.started_at.desc())
            .first()
        )
        if fs:
            return {
                "active": True,
                "session": {
                    "id": fs.id,
                    "started_at": fs.started_at.isoformat(),
                    "ended_at": fs.ended_at.isoformat(),
                    "duration_seconds": fs.duration_seconds,
                    "primary_app": fs.primary_app,
                },
            }
        return {"active": False, "session": None}
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Data export
# ---------------------------------------------------------------------------


@app.get("/api/v1/export/samples")
def export_samples(start: date, end: date, format: str = "json"):
    """Export activity samples as JSON or CSV."""
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)

    session = get_session()
    try:
        samples = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= start_dt,
                ActivitySample.sampled_at < end_dt,
            )
            .order_by(ActivitySample.sampled_at)
            .limit(50000)
            .all()
        )

        rows = [
            {
                "sampled_at": s.sampled_at.isoformat(),
                "process_name": s.process_name,
                "window_title": (s.window_title or "")[:100],
                "is_idle": s.is_idle,
                "mouse_clicks": s.mouse_clicks,
                "key_presses": s.key_presses,
            }
            for s in samples
        ]

        if format == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=["sampled_at", "process_name", "window_title", "is_idle", "mouse_clicks", "key_presses"],
            )
            writer.writeheader()
            writer.writerows(rows)
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=samples.csv"},
            )

        return rows
    finally:
        session.close()


@app.get("/api/v1/export/sessions")
def export_sessions(start: date, end: date, format: str = "json"):
    """Export app sessions as JSON or CSV."""
    start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    end_dt = datetime(end.year, end.month, end.day, tzinfo=timezone.utc) + timedelta(days=1)

    session = get_session()
    try:
        app_sessions = (
            session.query(AppSession)
            .filter(
                AppSession.started_at >= start_dt,
                AppSession.started_at < end_dt,
            )
            .order_by(AppSession.started_at)
            .limit(50000)
            .all()
        )

        rows = [
            {
                "process_name": s.process_name,
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat(),
                "duration_seconds": s.duration_seconds,
                "total_clicks": s.total_clicks,
                "total_keys": s.total_keys,
            }
            for s in app_sessions
        ]

        if format == "csv":
            output = io.StringIO()
            writer = csv.DictWriter(
                output,
                fieldnames=["process_name", "started_at", "ended_at", "duration_seconds", "total_clicks", "total_keys"],
            )
            writer.writeheader()
            writer.writerows(rows)
            return Response(
                content=output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=sessions.csv"},
            )

        return rows
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Server bootstrap
# ---------------------------------------------------------------------------


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
