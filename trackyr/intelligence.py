"""Intelligence engine — derived metrics and pattern analysis."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Integer, func
from sqlalchemy.sql.expression import cast

from trackyr.config import cfg
from trackyr.db.engine import get_session
from trackyr.db.models import ActivitySample, AppSession, DailySummary

log = logging.getLogger(__name__)

# Try to import models being added by another agent; gracefully degrade if
# they don't exist yet.
try:
    from trackyr.db.models import AppCategory  # type: ignore[attr-defined]
except ImportError:
    AppCategory = None  # type: ignore[assignment,misc]

try:
    from trackyr.db.models import FocusSession  # type: ignore[attr-defined]
except ImportError:
    FocusSession = None  # type: ignore[assignment,misc]


def _fmt_duration(seconds: float) -> str:
    """Format seconds as 'Xh Ym'."""
    h, remainder = divmod(int(seconds), 3600)
    m = remainder // 60
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


def _today() -> date:
    """Return today's date in UTC."""
    return datetime.now(timezone.utc).date()


def _day_bounds(target_date: date) -> tuple[datetime, datetime]:
    """Return (start, end) datetimes for a given date in UTC."""
    day_start = datetime(
        target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc
    )
    day_end = day_start + timedelta(days=1)
    return day_start, day_end


# ---------------------------------------------------------------------------
# 1. detect_focus_sessions
# ---------------------------------------------------------------------------

def detect_focus_sessions(target_date: date | None = None) -> list[dict]:
    """Find deep-focus sessions (>=30 min on a single app) and score them.

    Quality score breakdown (0-100):
      - Base: 50
      - Duration bonus: up to 30 (linear, capped at 2 h)
      - Input intensity bonus: up to 20 (clicks+keys per minute, capped at 10/min)
    """
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)
    min_duration = 1800  # 30 minutes

    session = get_session()
    try:
        sessions = (
            session.query(AppSession)
            .filter(
                AppSession.started_at >= day_start,
                AppSession.started_at < day_end,
                AppSession.duration_seconds >= min_duration,
            )
            .order_by(AppSession.started_at)
            .all()
        )

        results: list[dict] = []
        for s in sessions:
            # Duration bonus: linear 0-30, capped at 7200s (2h)
            duration_ratio = min(s.duration_seconds / 7200.0, 1.0)
            duration_bonus = duration_ratio * 30.0

            # Input intensity bonus: (clicks+keys)/min, capped at 10/min
            minutes = s.duration_seconds / 60.0
            if minutes > 0:
                intensity = (s.total_clicks + s.total_keys) / minutes
            else:
                intensity = 0.0
            intensity_ratio = min(intensity / 10.0, 1.0)
            intensity_bonus = intensity_ratio * 20.0

            quality_score = int(round(50.0 + duration_bonus + intensity_bonus))
            quality_score = max(0, min(100, quality_score))

            results.append({
                "started_at": s.started_at.isoformat(),
                "ended_at": s.ended_at.isoformat(),
                "duration_seconds": s.duration_seconds,
                "duration_fmt": _fmt_duration(s.duration_seconds),
                "primary_app": s.process_name,
                "total_clicks": s.total_clicks,
                "total_keys": s.total_keys,
                "quality_score": quality_score,
            })

        return results
    except Exception:
        log.exception("Error detecting focus sessions for %s", target_date)
        return []
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 2. context_switch_count
# ---------------------------------------------------------------------------

def context_switch_count(target_date: date | None = None) -> dict:
    """Count app context switches and compare to 7-day average."""
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)

    session = get_session()
    try:
        # Sessions for the target date, sorted by start time
        day_sessions = (
            session.query(AppSession)
            .filter(
                AppSession.started_at >= day_start,
                AppSession.started_at < day_end,
            )
            .order_by(AppSession.started_at)
            .all()
        )

        total_switches = max(len(day_sessions) - 1, 0)

        # Group by hour
        switches_per_hour: dict[int, int] = defaultdict(int)
        for s in day_sessions:
            hour = s.started_at.hour
            switches_per_hour[hour] += 1

        # Convert to plain dict with all hours that have activity
        switches_per_hour_dict = dict(sorted(switches_per_hour.items()))

        hours_with_activity = len(switches_per_hour_dict)
        avg_switches_per_hour = (
            round(total_switches / hours_with_activity, 1)
            if hours_with_activity > 0
            else 0.0
        )

        # 7-day average for comparison (excluding target date)
        week_start = day_start - timedelta(days=7)
        week_counts = (
            session.query(
                func.count(AppSession.id)
            )
            .filter(
                AppSession.started_at >= week_start,
                AppSession.started_at < day_start,
            )
            .scalar()
        ) or 0

        # Count distinct days with activity in the prior 7 days.
        # We pull start timestamps and group in Python to avoid DB-specific
        # date extraction functions.
        week_sessions = (
            session.query(AppSession.started_at)
            .filter(
                AppSession.started_at >= week_start,
                AppSession.started_at < day_start,
            )
            .all()
        )
        active_dates = {s.started_at.date() for s in week_sessions}
        active_days = len(active_dates)

        # Average switches per day over the prior week
        week_total_switches = max(week_counts - active_days, 0) if active_days > 0 else 0
        week_avg_switches = (
            round(week_total_switches / active_days, 1)
            if active_days > 0
            else 0.0
        )

        # Percentage difference vs weekly average
        if week_avg_switches > 0:
            vs_average_pct = round(
                ((total_switches - week_avg_switches) / week_avg_switches) * 100, 1
            )
        else:
            vs_average_pct = 0.0

        return {
            "date": target_date.isoformat(),
            "total_switches": total_switches,
            "switches_per_hour": switches_per_hour_dict,
            "avg_switches_per_hour": avg_switches_per_hour,
            "week_avg_switches": week_avg_switches,
            "vs_average_pct": vs_average_pct,
        }
    except Exception:
        log.exception("Error computing context switches for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "total_switches": 0,
            "switches_per_hour": {},
            "avg_switches_per_hour": 0.0,
            "week_avg_switches": 0.0,
            "vs_average_pct": 0.0,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 3. parse_window_title
# ---------------------------------------------------------------------------

# Regex patterns for window title parsing
_VSCODE_RE = re.compile(
    r"^(?P<file>.+?)\s+[-\u2014]\s+(?P<project>.+?)\s+[-\u2014]\s+Visual Studio Code$"
)
_BROWSER_TITLE_RE = re.compile(
    r"^(?P<page_title>.+?)\s+[-\u2014]\s+(?:Google Chrome|Microsoft Edge|Mozilla Firefox|Brave|Opera|Vivaldi)$"
)
_GITHUB_REPO_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/\s]+)"
)
_DOMAIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?P<domain>[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,})"
)
_EXPLORER_PATH_RE = re.compile(
    r"^(?P<path>[A-Z]:\\[^|*?\"<>]+)$"
)
_SLACK_CHANNEL_RE = re.compile(
    r"^(?:(?P<channel>#?\S+)\s+[-\u2014|]\s+)?(?P<workspace>.+?)\s+[-\u2014|]\s+Slack$"
)
_DISCORD_RE = re.compile(
    r"^(?:#?(?P<channel>\S+)\s+[-\u2014|]\s+)?(?P<server>.+?)\s+[-\u2014]\s+Discord$"
)
_TEAMS_RE = re.compile(
    r"^(?P<context>.+?)\s+[-\u2014|]\s+Microsoft Teams$"
)


def parse_window_title(title: str | None, process_name: str | None) -> dict:
    """Extract structured info from a window title string.

    Returns a dict that always includes 'process' and 'context' keys, plus
    optional keys like 'project', 'file', 'page_title', 'domain', 'repo',
    'channel', 'server', 'workspace'.
    """
    result: dict[str, Any] = {
        "process": process_name or "unknown",
        "context": title or "",
    }

    if not title:
        return result

    pname = (process_name or "").lower()

    # VS Code
    if "code" in pname or "visual studio code" in title.lower():
        m = _VSCODE_RE.match(title)
        if m:
            result["project"] = m.group("project")
            result["file"] = m.group("file")
            result["context"] = f"{m.group('file')} in {m.group('project')}"
            return result

    # Browsers
    if any(b in pname for b in ("chrome", "msedge", "firefox", "brave", "opera", "vivaldi")):
        m = _BROWSER_TITLE_RE.match(title)
        if m:
            page_title = m.group("page_title")
            result["page_title"] = page_title
            result["context"] = page_title

            # GitHub repo extraction
            gh = _GITHUB_REPO_RE.search(title)
            if gh:
                result["repo"] = f"{gh.group('owner')}/{gh.group('repo')}"

            # Domain extraction
            dm = _DOMAIN_RE.search(page_title)
            if dm:
                result["domain"] = dm.group("domain")

            return result

    # Explorer
    if "explorer" in pname:
        m = _EXPLORER_PATH_RE.match(title)
        if m:
            result["path"] = m.group("path")
            result["context"] = m.group("path")
            return result

    # Slack
    if "slack" in pname:
        m = _SLACK_CHANNEL_RE.match(title)
        if m:
            if m.group("channel"):
                result["channel"] = m.group("channel")
            result["workspace"] = m.group("workspace")
            result["context"] = title
            return result

    # Discord
    if "discord" in pname:
        m = _DISCORD_RE.match(title)
        if m:
            if m.group("channel"):
                result["channel"] = m.group("channel")
            result["server"] = m.group("server")
            result["context"] = title
            return result

    # Microsoft Teams
    if "teams" in pname:
        m = _TEAMS_RE.match(title)
        if m:
            result["channel"] = m.group("context")
            result["context"] = m.group("context")
            return result

    # General fallback — context is the raw title
    result["context"] = title
    return result


# ---------------------------------------------------------------------------
# 4. productivity_score
# ---------------------------------------------------------------------------

def _get_app_categories(session: Any, process_names: list[str]) -> dict[str, dict]:
    """Look up AppCategory for a list of process names.

    Returns {process_name: {"category": str, "is_productive": bool}}.
    Falls back to "uncategorized" if the AppCategory model is unavailable.
    """
    categories: dict[str, dict] = {}

    if AppCategory is None:
        # Model not yet available — everything is uncategorized
        for pn in process_names:
            categories[pn] = {"category": "uncategorized", "is_productive": False}
        return categories

    try:
        rows = (
            session.query(AppCategory)
            .filter(AppCategory.process_name.in_(process_names))
            .all()
        )
        for row in rows:
            categories[row.process_name] = {
                "category": row.category,
                "is_productive": bool(row.is_productive),
            }
    except Exception:
        log.warning("AppCategory table query failed; treating all apps as uncategorized")

    # Fill in any missing ones as uncategorized
    for pn in process_names:
        if pn not in categories:
            categories[pn] = {"category": "uncategorized", "is_productive": False}

    return categories


def productivity_score(target_date: date | None = None) -> dict:
    """Calculate productivity breakdown by category for a given date."""
    if target_date is None:
        target_date = _today()

    session = get_session()
    try:
        summaries = (
            session.query(DailySummary)
            .filter(DailySummary.date == target_date)
            .all()
        )

        if not summaries:
            return {
                "date": target_date.isoformat(),
                "productivity_pct": 0.0,
                "total_active_seconds": 0.0,
                "productive_seconds": 0.0,
                "unproductive_seconds": 0.0,
                "uncategorized_seconds": 0.0,
                "by_category": {},
                "top_productive_apps": [],
                "top_unproductive_apps": [],
            }

        process_names = [s.process_name for s in summaries]
        categories = _get_app_categories(session, process_names)

        total_active_seconds = 0.0
        productive_seconds = 0.0
        unproductive_seconds = 0.0
        uncategorized_seconds = 0.0

        by_category: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"seconds": 0.0, "apps": []}
        )

        productive_apps: list[dict] = []
        unproductive_apps: list[dict] = []

        for s in summaries:
            cat_info = categories.get(
                s.process_name,
                {"category": "uncategorized", "is_productive": False},
            )
            cat_name = cat_info["category"]
            is_prod = cat_info["is_productive"]

            total_active_seconds += s.total_seconds

            if cat_name == "uncategorized":
                uncategorized_seconds += s.total_seconds
            elif is_prod:
                productive_seconds += s.total_seconds
            else:
                unproductive_seconds += s.total_seconds

            by_category[cat_name]["seconds"] += s.total_seconds
            by_category[cat_name]["apps"].append(s.process_name)

            entry = {
                "process_name": s.process_name,
                "total_seconds": s.total_seconds,
                "total_fmt": _fmt_duration(s.total_seconds),
            }
            if is_prod:
                productive_apps.append(entry)
            elif cat_name != "uncategorized":
                unproductive_apps.append(entry)

        # Finalize by_category with formatted durations and deduplicated apps
        by_category_out: dict[str, dict[str, Any]] = {}
        for cat, data in by_category.items():
            by_category_out[cat] = {
                "seconds": data["seconds"],
                "fmt": _fmt_duration(data["seconds"]),
                "apps": sorted(set(data["apps"])),
            }

        # Sort top apps by time descending
        productive_apps.sort(key=lambda x: x["total_seconds"], reverse=True)
        unproductive_apps.sort(key=lambda x: x["total_seconds"], reverse=True)

        productivity_pct = (
            round((productive_seconds / total_active_seconds) * 100, 1)
            if total_active_seconds > 0
            else 0.0
        )

        return {
            "date": target_date.isoformat(),
            "productivity_pct": productivity_pct,
            "total_active_seconds": total_active_seconds,
            "productive_seconds": productive_seconds,
            "unproductive_seconds": unproductive_seconds,
            "uncategorized_seconds": uncategorized_seconds,
            "by_category": by_category_out,
            "top_productive_apps": productive_apps[:10],
            "top_unproductive_apps": unproductive_apps[:10],
        }
    except Exception:
        log.exception("Error computing productivity score for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "productivity_pct": 0.0,
            "total_active_seconds": 0.0,
            "productive_seconds": 0.0,
            "unproductive_seconds": 0.0,
            "uncategorized_seconds": 0.0,
            "by_category": {},
            "top_productive_apps": [],
            "top_unproductive_apps": [],
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 5. trend_comparison
# ---------------------------------------------------------------------------

def trend_comparison(target_date: date | None = None, days: int = 7) -> dict:
    """Compare the last *days* period to the previous *days* period."""
    if target_date is None:
        target_date = _today()

    current_end = target_date
    current_start = target_date - timedelta(days=days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)

    session = get_session()
    try:
        # ------ current period ------
        current_rows = (
            session.query(
                DailySummary.process_name,
                func.sum(DailySummary.total_seconds).label("total_secs"),
            )
            .filter(
                DailySummary.date >= current_start,
                DailySummary.date <= current_end,
            )
            .group_by(DailySummary.process_name)
            .order_by(func.sum(DailySummary.total_seconds).desc())
            .all()
        )

        current_by_app: dict[str, float] = {}
        current_total = 0.0
        for r in current_rows:
            secs = float(r.total_secs)
            current_by_app[r.process_name] = secs
            current_total += secs

        current_top = [
            {"process_name": r.process_name, "total_seconds": float(r.total_secs),
             "total_fmt": _fmt_duration(float(r.total_secs))}
            for r in current_rows[:5]
        ]

        # ------ previous period ------
        previous_rows = (
            session.query(
                DailySummary.process_name,
                func.sum(DailySummary.total_seconds).label("total_secs"),
            )
            .filter(
                DailySummary.date >= previous_start,
                DailySummary.date <= previous_end,
            )
            .group_by(DailySummary.process_name)
            .order_by(func.sum(DailySummary.total_seconds).desc())
            .all()
        )

        previous_by_app: dict[str, float] = {}
        previous_total = 0.0
        for r in previous_rows:
            secs = float(r.total_secs)
            previous_by_app[r.process_name] = secs
            previous_total += secs

        previous_top = [
            {"process_name": r.process_name, "total_seconds": float(r.total_secs),
             "total_fmt": _fmt_duration(float(r.total_secs))}
            for r in previous_rows[:5]
        ]

        # Overall change
        if previous_total > 0:
            change_pct = round(
                ((current_total - previous_total) / previous_total) * 100, 1
            )
        else:
            change_pct = 0.0 if current_total == 0 else 100.0

        # Notable per-app changes
        all_apps = set(current_by_app.keys()) | set(previous_by_app.keys())
        notable_changes: list[dict] = []
        for app in all_apps:
            cur = current_by_app.get(app, 0.0)
            prev = previous_by_app.get(app, 0.0)
            if prev > 0:
                app_change = round(((cur - prev) / prev) * 100, 1)
            elif cur > 0:
                app_change = 100.0
            else:
                app_change = 0.0

            # Only include if there is a meaningful difference (> 60s either period)
            if cur > 60 or prev > 60:
                notable_changes.append({
                    "app": app,
                    "current_seconds": cur,
                    "previous_seconds": prev,
                    "change_pct": app_change,
                })

        # Sort by absolute change magnitude, descending
        notable_changes.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

        return {
            "current_period": {
                "start": current_start.isoformat(),
                "end": current_end.isoformat(),
            },
            "previous_period": {
                "start": previous_start.isoformat(),
                "end": previous_end.isoformat(),
            },
            "current_total_seconds": current_total,
            "previous_total_seconds": previous_total,
            "change_pct": change_pct,
            "current_top_apps": current_top,
            "previous_top_apps": previous_top,
            "notable_changes": notable_changes[:20],
        }
    except Exception:
        log.exception("Error computing trend comparison for %s", target_date)
        return {
            "current_period": {
                "start": (target_date - timedelta(days=days - 1)).isoformat(),
                "end": target_date.isoformat(),
            },
            "previous_period": {
                "start": (target_date - timedelta(days=2 * days - 1)).isoformat(),
                "end": (target_date - timedelta(days=days)).isoformat(),
            },
            "current_total_seconds": 0.0,
            "previous_total_seconds": 0.0,
            "change_pct": 0.0,
            "current_top_apps": [],
            "previous_top_apps": [],
            "notable_changes": [],
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 6. idle_pattern_analysis
# ---------------------------------------------------------------------------

def _classify_idle_block(duration_seconds: float) -> str:
    """Classify an idle block by its duration."""
    if duration_seconds < 120:
        return "micro_break"
    elif duration_seconds < 900:
        return "short_break"
    elif duration_seconds < 3600:
        return "extended_break"
    else:
        return "away"


def idle_pattern_analysis(target_date: date | None = None) -> dict:
    """Analyze idle patterns — breaks, their types, and context."""
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)

    session = get_session()
    try:
        samples = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        if not samples:
            return {
                "date": target_date.isoformat(),
                "total_idle_seconds": 0.0,
                "idle_blocks": [],
                "longest_idle": {"seconds": 0, "when": None},
                "idle_after_focus": 0,
            }

        # Identify contiguous idle blocks
        idle_blocks: list[dict] = []
        current_block_start: datetime | None = None
        current_block_samples: int = 0
        last_active_app: str | None = None
        last_active_duration: float = 0.0  # track duration of preceding active stretch

        active_stretch_start: datetime | None = None

        for sample in samples:
            if sample.is_idle:
                if current_block_start is None:
                    # Start a new idle block
                    current_block_start = sample.sampled_at
                    current_block_samples = 1
                else:
                    current_block_samples += 1
            else:
                if current_block_start is not None:
                    # End the idle block
                    block_duration = current_block_samples * cfg.sample_interval
                    idle_blocks.append({
                        "start": current_block_start,
                        "duration_seconds": block_duration,
                        "type": _classify_idle_block(block_duration),
                        "preceding_app": last_active_app,
                        "preceded_by_focus": last_active_duration >= 1800,
                    })
                    current_block_start = None
                    current_block_samples = 0
                    active_stretch_start = sample.sampled_at

                # Track active app context
                last_active_app = sample.process_name

                if active_stretch_start is None:
                    active_stretch_start = sample.sampled_at
                last_active_duration = (
                    sample.sampled_at - active_stretch_start
                ).total_seconds()

        # Close any trailing idle block
        if current_block_start is not None:
            block_duration = current_block_samples * cfg.sample_interval
            idle_blocks.append({
                "start": current_block_start,
                "duration_seconds": block_duration,
                "type": _classify_idle_block(block_duration),
                "preceding_app": last_active_app,
                "preceded_by_focus": last_active_duration >= 1800,
            })

        # Aggregate by type
        type_agg: dict[str, dict] = defaultdict(
            lambda: {"count": 0, "total_seconds": 0.0}
        )
        longest_idle_seconds = 0.0
        longest_idle_when: datetime | None = None

        idle_after_focus = 0

        for block in idle_blocks:
            btype = block["type"]
            type_agg[btype]["count"] += 1
            type_agg[btype]["total_seconds"] += block["duration_seconds"]

            if block["duration_seconds"] > longest_idle_seconds:
                longest_idle_seconds = block["duration_seconds"]
                longest_idle_when = block["start"]

            if block["preceded_by_focus"]:
                idle_after_focus += 1

        total_idle_seconds = sum(b["duration_seconds"] for b in idle_blocks)

        # Build output for idle_blocks grouped by type
        block_types_out: list[dict] = []
        for btype in ("micro_break", "short_break", "extended_break", "away"):
            agg = type_agg.get(btype)
            if agg and agg["count"] > 0:
                block_types_out.append({
                    "type": btype,
                    "count": agg["count"],
                    "total_seconds": agg["total_seconds"],
                    "total_fmt": _fmt_duration(agg["total_seconds"]),
                })

        return {
            "date": target_date.isoformat(),
            "total_idle_seconds": total_idle_seconds,
            "idle_blocks": block_types_out,
            "longest_idle": {
                "seconds": longest_idle_seconds,
                "when": longest_idle_when.isoformat() if longest_idle_when else None,
            },
            "idle_after_focus": idle_after_focus,
        }
    except Exception:
        log.exception("Error analyzing idle patterns for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "total_idle_seconds": 0.0,
            "idle_blocks": [],
            "longest_idle": {"seconds": 0, "when": None},
            "idle_after_focus": 0,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 7. current_context
# ---------------------------------------------------------------------------

def current_context() -> dict:
    """Compact snapshot of current state, optimized for AI prompt injection."""
    now = datetime.now(timezone.utc)
    today = now.date()
    day_start, day_end = _day_bounds(today)

    session = get_session()
    try:
        # Most recent sample
        latest = (
            session.query(ActivitySample)
            .order_by(ActivitySample.sampled_at.desc())
            .first()
        )

        if not latest:
            return {
                "current_app": None,
                "window_context": {},
                "active_since": None,
                "total_active_today_fmt": "0m",
                "productivity_pct": 0.0,
                "focus_sessions_today": 0,
                "is_idle": True,
                "last_activity_ago_seconds": None,
            }

        # Parse window title
        window_ctx = parse_window_title(latest.window_title, latest.process_name)

        # Time since last activity
        last_activity_ago = (now - latest.sampled_at).total_seconds()

        # First sample today = "active since"
        first_sample = (
            session.query(ActivitySample.sampled_at)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .order_by(ActivitySample.sampled_at)
            .first()
        )
        active_since = first_sample[0].isoformat() if first_sample else None

        # Total active time today (non-idle samples * interval)
        active_count = (
            session.query(func.count(ActivitySample.id))
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
                ActivitySample.is_idle == False,  # noqa: E712
            )
            .scalar()
        ) or 0
        total_active_seconds = active_count * cfg.sample_interval

        # Focus sessions today (AppSession >= 30 min)
        focus_count = (
            session.query(func.count(AppSession.id))
            .filter(
                AppSession.started_at >= day_start,
                AppSession.started_at < day_end,
                AppSession.duration_seconds >= 1800,
            )
            .scalar()
        ) or 0

        # Productivity percentage — lightweight: just fetch the number
        prod_data = _quick_productivity_pct(session, today)

        return {
            "current_app": latest.process_name,
            "window_context": window_ctx,
            "active_since": active_since,
            "total_active_today_fmt": _fmt_duration(total_active_seconds),
            "productivity_pct": prod_data,
            "focus_sessions_today": focus_count,
            "is_idle": latest.is_idle,
            "last_activity_ago_seconds": round(last_activity_ago, 1),
        }
    except Exception:
        log.exception("Error building current context")
        return {
            "current_app": None,
            "window_context": {},
            "active_since": None,
            "total_active_today_fmt": "0m",
            "productivity_pct": 0.0,
            "focus_sessions_today": 0,
            "is_idle": True,
            "last_activity_ago_seconds": None,
        }
    finally:
        session.close()


def _quick_productivity_pct(session: Any, target_date: date) -> float:
    """Lightweight productivity percentage — avoids a full productivity_score call."""
    if AppCategory is None:
        return 0.0

    try:
        summaries = (
            session.query(DailySummary)
            .filter(DailySummary.date == target_date)
            .all()
        )
        if not summaries:
            return 0.0

        process_names = [s.process_name for s in summaries]
        categories = _get_app_categories(session, process_names)

        total = 0.0
        productive = 0.0
        for s in summaries:
            total += s.total_seconds
            cat_info = categories.get(
                s.process_name,
                {"category": "uncategorized", "is_productive": False},
            )
            if cat_info["is_productive"]:
                productive += s.total_seconds

        return round((productive / total) * 100, 1) if total > 0 else 0.0
    except Exception:
        log.warning("Could not compute quick productivity percentage")
        return 0.0


# ---------------------------------------------------------------------------
# 8. hourly_heatmap
# ---------------------------------------------------------------------------

def hourly_heatmap(target_date: date | None = None) -> dict:
    """Return a 24-element hourly breakdown of activity for a given date."""
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)

    session = get_session()
    try:
        samples = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        # Bucket samples by hour
        hour_buckets: dict[int, list] = {h: [] for h in range(24)}
        for s in samples:
            hour_buckets[s.sampled_at.hour].append(s)

        # Query AppSession for context-switch counting per hour
        app_sessions = (
            session.query(AppSession)
            .filter(
                AppSession.started_at >= day_start,
                AppSession.started_at < day_end,
            )
            .order_by(AppSession.started_at)
            .all()
        )

        # Count context switches per hour: each new session is a switch from
        # the previous one (if process_name differs).
        switches_by_hour: dict[int, int] = defaultdict(int)
        for i in range(1, len(app_sessions)):
            prev = app_sessions[i - 1]
            curr = app_sessions[i]
            if curr.process_name != prev.process_name:
                switches_by_hour[curr.started_at.hour] += 1

        hours: list[dict] = []
        for h in range(24):
            bucket = hour_buckets[h]
            if not bucket:
                hours.append({
                    "hour": h,
                    "active_seconds": 0,
                    "idle_seconds": 0,
                    "dominant_app": None,
                    "switches": 0,
                    "clicks": 0,
                    "keys": 0,
                })
                continue

            active_count = sum(1 for s in bucket if not s.is_idle)
            idle_count = sum(1 for s in bucket if s.is_idle)

            # Dominant app — process_name with most samples this hour
            app_counts: dict[str, int] = defaultdict(int)
            for s in bucket:
                if s.process_name:
                    app_counts[s.process_name] += 1
            dominant_app = max(app_counts, key=app_counts.get) if app_counts else None

            clicks = sum(s.mouse_clicks for s in bucket)
            keys = sum(s.key_presses for s in bucket)

            hours.append({
                "hour": h,
                "active_seconds": active_count * cfg.sample_interval,
                "idle_seconds": idle_count * cfg.sample_interval,
                "dominant_app": dominant_app,
                "switches": switches_by_hour.get(h, 0),
                "clicks": clicks,
                "keys": keys,
            })

        # Derived metrics
        active_hours = [h for h in hours if h["active_seconds"] > 0]
        if active_hours:
            peak_hour = max(active_hours, key=lambda h: h["active_seconds"])["hour"]
            quietest_hour = min(active_hours, key=lambda h: h["active_seconds"])["hour"]
        else:
            peak_hour = None
            quietest_hour = None

        total_hours_active = len(active_hours)

        return {
            "date": target_date.isoformat(),
            "hours": hours,
            "peak_hour": peak_hour,
            "quietest_hour": quietest_hour,
            "total_hours_active": total_hours_active,
        }
    except Exception:
        log.exception("Error computing hourly heatmap for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "hours": [
                {"hour": h, "active_seconds": 0, "idle_seconds": 0,
                 "dominant_app": None, "switches": 0, "clicks": 0, "keys": 0}
                for h in range(24)
            ],
            "peak_hour": None,
            "quietest_hour": None,
            "total_hours_active": 0,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 9. workday_detection
# ---------------------------------------------------------------------------

def workday_detection(target_date: date | None = None) -> dict:
    """Detect workday boundaries, breaks, lunch, and overtime."""
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)
    overtime_threshold = 28800  # 8 hours in seconds

    session = get_session()
    try:
        samples = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        if not samples:
            return {
                "date": target_date.isoformat(),
                "work_start": None,
                "work_end": None,
                "total_span_seconds": 0,
                "total_span_fmt": "0m",
                "total_active_seconds": 0,
                "total_active_fmt": "0m",
                "total_break_seconds": 0,
                "total_break_fmt": "0m",
                "breaks": [],
                "lunch_break": None,
                "overtime": False,
                "overtime_seconds": 0,
            }

        # Find first and last non-idle samples
        non_idle = [s for s in samples if not s.is_idle]

        if not non_idle:
            return {
                "date": target_date.isoformat(),
                "work_start": None,
                "work_end": None,
                "total_span_seconds": 0,
                "total_span_fmt": "0m",
                "total_active_seconds": 0,
                "total_active_fmt": "0m",
                "total_break_seconds": 0,
                "total_break_fmt": "0m",
                "breaks": [],
                "lunch_break": None,
                "overtime": False,
                "overtime_seconds": 0,
            }

        work_start = non_idle[0].sampled_at
        work_end = non_idle[-1].sampled_at
        total_span_seconds = (work_end - work_start).total_seconds()

        # Detect breaks: gaps of >5 minutes between consecutive non-idle samples
        break_threshold = 300  # 5 minutes
        breaks: list[dict] = []
        for i in range(1, len(non_idle)):
            gap = (non_idle[i].sampled_at - non_idle[i - 1].sampled_at).total_seconds()
            if gap > break_threshold:
                break_start = non_idle[i - 1].sampled_at
                break_end = non_idle[i].sampled_at
                duration = gap
                breaks.append({
                    "start": break_start.isoformat(),
                    "end": break_end.isoformat(),
                    "duration_seconds": duration,
                    "duration_fmt": _fmt_duration(duration),
                })

        total_break_seconds = sum(b["duration_seconds"] for b in breaks)
        total_active_seconds = len(non_idle) * cfg.sample_interval

        # Detect lunch: the longest break between 11:00 and 14:00
        lunch_start_bound = day_start.replace(hour=11)
        lunch_end_bound = day_start.replace(hour=14)
        lunch_candidates = []
        for b in breaks:
            # Parse back to datetime for comparison
            b_start = datetime.fromisoformat(b["start"])
            b_end = datetime.fromisoformat(b["end"])
            if b_start >= lunch_start_bound and b_end <= lunch_end_bound:
                lunch_candidates.append(b)

        lunch_break = None
        if lunch_candidates:
            longest_lunch = max(lunch_candidates, key=lambda b: b["duration_seconds"])
            lunch_break = {
                "start": longest_lunch["start"],
                "end": longest_lunch["end"],
                "duration_seconds": longest_lunch["duration_seconds"],
            }

        is_overtime = total_active_seconds > overtime_threshold
        overtime_seconds = max(total_active_seconds - overtime_threshold, 0)

        return {
            "date": target_date.isoformat(),
            "work_start": work_start.isoformat(),
            "work_end": work_end.isoformat(),
            "total_span_seconds": total_span_seconds,
            "total_span_fmt": _fmt_duration(total_span_seconds),
            "total_active_seconds": total_active_seconds,
            "total_active_fmt": _fmt_duration(total_active_seconds),
            "total_break_seconds": total_break_seconds,
            "total_break_fmt": _fmt_duration(total_break_seconds),
            "breaks": breaks,
            "lunch_break": lunch_break,
            "overtime": is_overtime,
            "overtime_seconds": overtime_seconds,
        }
    except Exception:
        log.exception("Error detecting workday for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "work_start": None,
            "work_end": None,
            "total_span_seconds": 0,
            "total_span_fmt": "0m",
            "total_active_seconds": 0,
            "total_active_fmt": "0m",
            "total_break_seconds": 0,
            "total_break_fmt": "0m",
            "breaks": [],
            "lunch_break": None,
            "overtime": False,
            "overtime_seconds": 0,
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 10. daily_narrative
# ---------------------------------------------------------------------------

def daily_narrative(target_date: date | None = None) -> dict:
    """Generate an AI-friendly narrative summary of the day."""
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)

    session = get_session()
    try:
        # Gather data from other intelligence functions
        workday = workday_detection(target_date)
        focus_sessions = detect_focus_sessions(target_date)
        prod = productivity_score(target_date)
        ctx_switches = context_switch_count(target_date)

        # Query samples for time-of-day breakdown
        samples = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
                ActivitySample.is_idle == False,  # noqa: E712
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        if not samples and not workday.get("work_start"):
            return {
                "date": target_date.isoformat(),
                "narrative_text": f"No activity recorded on {target_date.isoformat()}.",
                "sections": {
                    "overview": f"No activity recorded on {target_date.isoformat()}.",
                    "morning": None,
                    "afternoon": None,
                    "evening": None,
                    "focus": None,
                    "productivity": None,
                    "context_switching": None,
                },
                "highlights": [],
            }

        # Time-of-day buckets for top app
        morning_apps: dict[str, float] = defaultdict(float)
        afternoon_apps: dict[str, float] = defaultdict(float)
        evening_apps: dict[str, float] = defaultdict(float)

        for s in samples:
            hour = s.sampled_at.hour
            app = s.process_name or "unknown"
            if hour < 12:
                morning_apps[app] += cfg.sample_interval
            elif hour < 17:
                afternoon_apps[app] += cfg.sample_interval
            else:
                evening_apps[app] += cfg.sample_interval

        def _top_app_text(apps: dict[str, float]) -> str | None:
            if not apps:
                return None
            top = max(apps, key=apps.get)
            return f"{top} ({_fmt_duration(apps[top])})"

        # Build sections
        overview = (
            f"On {target_date.isoformat()}, you worked from "
            f"{workday.get('work_start', 'N/A')} to {workday.get('work_end', 'N/A')} "
            f"({workday.get('total_span_fmt', '0m')}). "
            f"Total active time: {workday.get('total_active_fmt', '0m')}, "
            f"idle: {workday.get('total_break_fmt', '0m')}."
        )

        morning_text = None
        if morning_apps:
            top = _top_app_text(morning_apps)
            total = _fmt_duration(sum(morning_apps.values()))
            morning_text = f"Morning (before 12:00): top app was {top}. Total: {total}."

        afternoon_text = None
        if afternoon_apps:
            top = _top_app_text(afternoon_apps)
            total = _fmt_duration(sum(afternoon_apps.values()))
            afternoon_text = f"Afternoon (12:00-17:00): top app was {top}. Total: {total}."

        evening_text = None
        if evening_apps:
            top = _top_app_text(evening_apps)
            total = _fmt_duration(sum(evening_apps.values()))
            evening_text = f"Evening (after 17:00): top app was {top}. Total: {total}."

        # Focus section
        focus_text = None
        if focus_sessions:
            best = max(focus_sessions, key=lambda f: f["duration_seconds"])
            focus_text = (
                f"You had {len(focus_sessions)} focus session(s). "
                f"Best: {best['primary_app']} for {best['duration_fmt']} "
                f"(quality {best['quality_score']})."
            )
        else:
            focus_text = "No focus sessions (>=30 min) detected."

        # Productivity section
        top_prod = ", ".join(
            a["process_name"] for a in prod.get("top_productive_apps", [])[:3]
        ) or "none"
        top_unprod = ", ".join(
            a["process_name"] for a in prod.get("top_unproductive_apps", [])[:3]
        ) or "none"
        productivity_text = (
            f"Productivity score: {prod.get('productivity_pct', 0.0)}%. "
            f"Top productive: {top_prod}. Top unproductive: {top_unprod}."
        )

        # Context switching section
        vs_avg = ctx_switches.get("vs_average_pct", 0.0)
        vs_str = f"+{vs_avg}%" if vs_avg >= 0 else f"{vs_avg}%"
        switching_text = (
            f"You had {ctx_switches.get('total_switches', 0)} context switches "
            f"({vs_str} vs average)."
        )

        # Highlights
        highlights: list[str] = []
        if focus_sessions:
            best = max(focus_sessions, key=lambda f: f["duration_seconds"])
            highlights.append(
                f"Longest focus session: {best['primary_app']} for {best['duration_fmt']}."
            )
        if workday.get("overtime"):
            highlights.append(
                f"Overtime detected: {_fmt_duration(workday.get('overtime_seconds', 0))} over 8h."
            )
        if workday.get("lunch_break"):
            lb = workday["lunch_break"]
            highlights.append(
                f"Lunch break: {_fmt_duration(lb['duration_seconds'])}."
            )
        if abs(vs_avg) > 30:
            direction = "higher" if vs_avg > 0 else "lower"
            highlights.append(
                f"Context switching was {abs(vs_avg)}% {direction} than your 7-day average."
            )

        # Build full narrative text
        sections_list = [
            overview,
            morning_text,
            afternoon_text,
            evening_text,
            focus_text,
            productivity_text,
            switching_text,
        ]
        narrative_text = " ".join(s for s in sections_list if s)

        return {
            "date": target_date.isoformat(),
            "narrative_text": narrative_text,
            "sections": {
                "overview": overview,
                "morning": morning_text,
                "afternoon": afternoon_text,
                "evening": evening_text,
                "focus": focus_text,
                "productivity": productivity_text,
                "context_switching": switching_text,
            },
            "highlights": highlights,
        }
    except Exception:
        log.exception("Error generating daily narrative for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "narrative_text": f"Error generating narrative for {target_date.isoformat()}.",
            "sections": {
                "overview": None,
                "morning": None,
                "afternoon": None,
                "evening": None,
                "focus": None,
                "productivity": None,
                "context_switching": None,
            },
            "highlights": [],
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 11. context_switch_patterns
# ---------------------------------------------------------------------------

def context_switch_patterns(target_date: date | None = None) -> dict:
    """Analyze context-switch transition patterns for a given date."""
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)

    session = get_session()
    try:
        app_sessions = (
            session.query(AppSession)
            .filter(
                AppSession.started_at >= day_start,
                AppSession.started_at < day_end,
            )
            .order_by(AppSession.started_at)
            .all()
        )

        if len(app_sessions) < 2:
            return {
                "date": target_date.isoformat(),
                "total_transitions": 0,
                "top_transitions": [],
                "distraction_magnets": [],
                "most_common_workflow": [],
            }

        # Build transition matrix
        transition_counts: dict[tuple[str, str], int] = defaultdict(int)
        for i in range(1, len(app_sessions)):
            from_app = app_sessions[i - 1].process_name
            to_app = app_sessions[i].process_name
            if from_app != to_app:
                transition_counts[(from_app, to_app)] += 1

        total_transitions = sum(transition_counts.values())

        # Top transitions sorted by frequency
        sorted_transitions = sorted(
            transition_counts.items(), key=lambda x: x[1], reverse=True
        )
        top_transitions = [
            {"from_app": k[0], "to_app": k[1], "count": v}
            for k, v in sorted_transitions[:20]
        ]

        # Distraction magnets: apps that interrupt focus sessions (>=30 min)
        # Walk through sessions: if a session lasted >=30 min and the next
        # session is a different app, that next app is a "distraction".
        distraction_events: dict[str, list[float]] = defaultdict(list)
        for i in range(len(app_sessions) - 1):
            focus_session = app_sessions[i]
            if focus_session.duration_seconds >= 1800:
                next_session = app_sessions[i + 1]
                if next_session.process_name != focus_session.process_name:
                    distraction_events[next_session.process_name].append(
                        next_session.duration_seconds
                    )

        distraction_magnets = []
        for app, durations in distraction_events.items():
            distraction_magnets.append({
                "app": app,
                "interruption_count": len(durations),
                "avg_time_spent_seconds": round(
                    sum(durations) / len(durations), 1
                ) if durations else 0.0,
            })
        distraction_magnets.sort(key=lambda x: x["interruption_count"], reverse=True)

        # Most common workflow: detect sequences of 3+ apps that recur
        # Slide a window of size 3 across the session list and count sequences
        sequence_counts: dict[tuple[str, ...], int] = defaultdict(int)
        session_names = [s.process_name for s in app_sessions]
        for window_size in (3, 4):
            if len(session_names) < window_size:
                continue
            for i in range(len(session_names) - window_size + 1):
                seq = tuple(session_names[i:i + window_size])
                # Only count if not all the same app
                if len(set(seq)) > 1:
                    sequence_counts[seq] += 1

        # Filter to sequences that appear at least twice
        common_workflows = [
            {"apps": list(seq), "count": cnt}
            for seq, cnt in sequence_counts.items()
            if cnt >= 2
        ]
        common_workflows.sort(key=lambda x: x["count"], reverse=True)

        return {
            "date": target_date.isoformat(),
            "total_transitions": total_transitions,
            "top_transitions": top_transitions,
            "distraction_magnets": distraction_magnets[:10],
            "most_common_workflow": common_workflows[:10],
        }
    except Exception:
        log.exception("Error analyzing context switch patterns for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "total_transitions": 0,
            "top_transitions": [],
            "distraction_magnets": [],
            "most_common_workflow": [],
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 12. anomaly_detection
# ---------------------------------------------------------------------------

def anomaly_detection(target_date: date | None = None) -> dict:
    """Compare today's metrics to 30-day baselines and flag anomalies."""
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)
    baseline_start = target_date - timedelta(days=30)

    session = get_session()
    try:
        # ---- Today's metrics ----
        today_samples = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        today_non_idle = [s for s in today_samples if not s.is_idle]
        today_active_seconds = len(today_non_idle) * cfg.sample_interval

        today_first_hour: float | None = None
        today_last_hour: float | None = None
        if today_non_idle:
            today_first_hour = (
                today_non_idle[0].sampled_at.hour
                + today_non_idle[0].sampled_at.minute / 60.0
            )
            today_last_hour = (
                today_non_idle[-1].sampled_at.hour
                + today_non_idle[-1].sampled_at.minute / 60.0
            )

        # Today's context switches
        today_sessions = (
            session.query(AppSession)
            .filter(
                AppSession.started_at >= day_start,
                AppSession.started_at < day_end,
            )
            .order_by(AppSession.started_at)
            .all()
        )
        today_switches = max(len(today_sessions) - 1, 0)

        # Today's focus sessions (>=30 min)
        today_focus_count = sum(
            1 for s in today_sessions if s.duration_seconds >= 1800
        )

        # Today's per-app usage from DailySummary
        today_summaries = (
            session.query(DailySummary)
            .filter(DailySummary.date == target_date)
            .all()
        )
        today_app_seconds: dict[str, float] = {
            s.process_name: s.total_seconds for s in today_summaries
        }

        # ---- 30-day baseline (from DailySummary + ActivitySample) ----
        baseline_summaries = (
            session.query(DailySummary)
            .filter(
                DailySummary.date >= baseline_start,
                DailySummary.date < target_date,
            )
            .all()
        )

        # Group by date for daily totals
        daily_active: dict[date, float] = defaultdict(float)
        daily_app_seconds: dict[date, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        all_baseline_apps: set[str] = set()
        for s in baseline_summaries:
            daily_active[s.date] += s.total_seconds
            daily_app_seconds[s.date][s.process_name] += s.total_seconds
            all_baseline_apps.add(s.process_name)

        active_days = sorted(daily_active.keys())
        num_days = len(active_days) if active_days else 1

        # Baseline: average active seconds
        active_values = list(daily_active.values()) if daily_active else [0]
        avg_active = sum(active_values) / len(active_values)

        # Baseline: context switches per day (from AppSession)
        baseline_sessions = (
            session.query(AppSession.started_at)
            .filter(
                AppSession.started_at >= datetime(
                    baseline_start.year, baseline_start.month, baseline_start.day,
                    tzinfo=timezone.utc,
                ),
                AppSession.started_at < day_start,
            )
            .order_by(AppSession.started_at)
            .all()
        )
        # Count sessions per day
        sessions_per_day: dict[date, int] = defaultdict(int)
        for row in baseline_sessions:
            sessions_per_day[row.started_at.date()] += 1
        switch_values = [max(cnt - 1, 0) for cnt in sessions_per_day.values()] if sessions_per_day else [0]
        avg_switches = sum(switch_values) / len(switch_values) if switch_values else 0

        # Baseline: start/end hours from ActivitySample
        # Query first and last non-idle sample for each baseline day
        baseline_sample_rows = (
            session.query(ActivitySample.sampled_at)
            .filter(
                ActivitySample.sampled_at >= datetime(
                    baseline_start.year, baseline_start.month, baseline_start.day,
                    tzinfo=timezone.utc,
                ),
                ActivitySample.sampled_at < day_start,
                ActivitySample.is_idle == False,  # noqa: E712
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        start_hours: list[float] = []
        end_hours: list[float] = []
        if baseline_sample_rows:
            daily_samples_map: dict[date, list[datetime]] = defaultdict(list)
            for row in baseline_sample_rows:
                daily_samples_map[row.sampled_at.date()].append(row.sampled_at)
            for d, timestamps in daily_samples_map.items():
                first = min(timestamps)
                last = max(timestamps)
                start_hours.append(first.hour + first.minute / 60.0)
                end_hours.append(last.hour + last.minute / 60.0)

        avg_start_hour = sum(start_hours) / len(start_hours) if start_hours else 9.0
        avg_end_hour = sum(end_hours) / len(end_hours) if end_hours else 17.0

        # Baseline: focus sessions per day
        baseline_focus = (
            session.query(AppSession.started_at)
            .filter(
                AppSession.started_at >= datetime(
                    baseline_start.year, baseline_start.month, baseline_start.day,
                    tzinfo=timezone.utc,
                ),
                AppSession.started_at < day_start,
                AppSession.duration_seconds >= 1800,
            )
            .all()
        )
        focus_per_day: dict[date, int] = defaultdict(int)
        for row in baseline_focus:
            focus_per_day[row.started_at.date()] += 1
        avg_focus = (
            sum(focus_per_day.values()) / num_days
            if focus_per_day else 0
        )

        # Per-app 30-day daily average
        app_total_seconds: dict[str, float] = defaultdict(float)
        for d_apps in daily_app_seconds.values():
            for app, secs in d_apps.items():
                app_total_seconds[app] += secs
        app_avg_seconds: dict[str, float] = {
            app: total / num_days for app, total in app_total_seconds.items()
        }

        # ---- Detect anomalies ----
        anomalies: list[dict] = []

        # Late/early start
        if today_first_hour is not None and start_hours:
            if today_first_hour > avg_start_hour + 1.5:
                anomalies.append({
                    "type": "late_start",
                    "message": (
                        f"Started at {today_first_hour:.1f}h, "
                        f"average is {avg_start_hour:.1f}h "
                        f"(+{today_first_hour - avg_start_hour:.1f}h later)."
                    ),
                    "severity": "info",
                    "current_value": round(today_first_hour, 2),
                    "baseline_value": round(avg_start_hour, 2),
                })
            elif today_first_hour < avg_start_hour - 1.5:
                anomalies.append({
                    "type": "early_start",
                    "message": (
                        f"Started at {today_first_hour:.1f}h, "
                        f"average is {avg_start_hour:.1f}h "
                        f"({avg_start_hour - today_first_hour:.1f}h earlier)."
                    ),
                    "severity": "info",
                    "current_value": round(today_first_hour, 2),
                    "baseline_value": round(avg_start_hour, 2),
                })

        # Overwork / underwork
        if avg_active > 0:
            if today_active_seconds > avg_active * 1.3:
                anomalies.append({
                    "type": "overwork",
                    "message": (
                        f"Active time {_fmt_duration(today_active_seconds)} is "
                        f"{((today_active_seconds - avg_active) / avg_active * 100):.0f}% "
                        f"above your 30-day average of {_fmt_duration(avg_active)}."
                    ),
                    "severity": "warning",
                    "current_value": today_active_seconds,
                    "baseline_value": round(avg_active, 1),
                })
            elif today_active_seconds < avg_active * 0.7 and today_active_seconds > 0:
                anomalies.append({
                    "type": "underwork",
                    "message": (
                        f"Active time {_fmt_duration(today_active_seconds)} is "
                        f"{((avg_active - today_active_seconds) / avg_active * 100):.0f}% "
                        f"below your 30-day average of {_fmt_duration(avg_active)}."
                    ),
                    "severity": "warning",
                    "current_value": today_active_seconds,
                    "baseline_value": round(avg_active, 1),
                })

        # High switching
        if avg_switches > 0 and today_switches > avg_switches * 1.5:
            anomalies.append({
                "type": "high_switching",
                "message": (
                    f"{today_switches} context switches, "
                    f"{((today_switches - avg_switches) / avg_switches * 100):.0f}% "
                    f"above your 30-day average of {avg_switches:.0f}."
                ),
                "severity": "warning",
                "current_value": today_switches,
                "baseline_value": round(avg_switches, 1),
            })

        # No focus
        if today_focus_count == 0 and avg_focus > 1:
            anomalies.append({
                "type": "no_focus",
                "message": (
                    f"No focus sessions today, but you average "
                    f"{avg_focus:.1f} per day."
                ),
                "severity": "alert",
                "current_value": 0,
                "baseline_value": round(avg_focus, 1),
            })

        # App spike: any app used >3x its 30-day daily average
        for app, secs in today_app_seconds.items():
            avg_secs = app_avg_seconds.get(app, 0)
            if avg_secs > 0 and secs > avg_secs * 3:
                anomalies.append({
                    "type": "app_spike",
                    "message": (
                        f"{app} used for {_fmt_duration(secs)}, "
                        f"{(secs / avg_secs):.1f}x your daily average of "
                        f"{_fmt_duration(avg_secs)}."
                    ),
                    "severity": "info",
                    "current_value": secs,
                    "baseline_value": round(avg_secs, 1),
                })

        # New app: not seen in 30 days
        for app in today_app_seconds:
            if app not in all_baseline_apps:
                anomalies.append({
                    "type": "new_app",
                    "message": (
                        f"{app} appeared for the first time "
                        f"(not seen in past 30 days)."
                    ),
                    "severity": "info",
                    "current_value": today_app_seconds[app],
                    "baseline_value": 0,
                })

        return {
            "date": target_date.isoformat(),
            "anomalies": anomalies,
            "baselines": {
                "avg_active_seconds": round(avg_active, 1),
                "avg_switches": round(avg_switches, 1),
                "avg_start_hour": round(avg_start_hour, 2),
                "avg_end_hour": round(avg_end_hour, 2),
            },
        }
    except Exception:
        log.exception("Error detecting anomalies for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "anomalies": [],
            "baselines": {
                "avg_active_seconds": 0,
                "avg_switches": 0,
                "avg_start_hour": 0,
                "avg_end_hour": 0,
            },
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 13. engagement_curve
# ---------------------------------------------------------------------------

def engagement_curve(target_date: date | None = None) -> dict:
    """Calculate per-hour engagement scores based on input and focus metrics."""
    if target_date is None:
        target_date = _today()

    day_start, day_end = _day_bounds(target_date)

    session = get_session()
    try:
        samples = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        # Bucket samples by hour
        hour_buckets: dict[int, list] = {h: [] for h in range(24)}
        for s in samples:
            hour_buckets[s.sampled_at.hour].append(s)

        # Count sessions per hour for focus consistency
        app_sessions = (
            session.query(AppSession)
            .filter(
                AppSession.started_at >= day_start,
                AppSession.started_at < day_end,
            )
            .order_by(AppSession.started_at)
            .all()
        )

        sessions_per_hour: dict[int, int] = defaultdict(int)
        switches_per_hour: dict[int, int] = defaultdict(int)
        for i, s in enumerate(app_sessions):
            sessions_per_hour[s.started_at.hour] += 1
            if i > 0 and app_sessions[i - 1].process_name != s.process_name:
                switches_per_hour[s.started_at.hour] += 1

        # Compute per-hour engagement
        # First pass: find maxima for normalization
        max_input_rate = 0.0
        max_mouse_rate = 0.0
        hour_raw: dict[int, dict] = {}

        for h in range(24):
            bucket = hour_buckets[h]
            active = [s for s in bucket if not s.is_idle]
            active_count = len(active)

            if active_count == 0:
                hour_raw[h] = {
                    "input_rate": 0.0,
                    "mouse_rate": 0.0,
                    "active_count": 0,
                }
                continue

            total_clicks = sum(s.mouse_clicks for s in active)
            total_keys = sum(s.key_presses for s in active)
            total_mouse_dist = sum(s.mouse_distance_px for s in active)

            input_rate = (total_clicks + total_keys) / active_count
            mouse_rate = total_mouse_dist / active_count

            max_input_rate = max(max_input_rate, input_rate)
            max_mouse_rate = max(max_mouse_rate, mouse_rate)

            hour_raw[h] = {
                "input_rate": input_rate,
                "mouse_rate": mouse_rate,
                "active_count": active_count,
            }

        # Second pass: normalize and compute scores
        hours: list[dict] = []
        engagement_scores: list[float] = []

        for h in range(24):
            raw = hour_raw[h]
            if raw["active_count"] == 0:
                hours.append({
                    "hour": h,
                    "engagement_score": 0,
                    "input_score": 0,
                    "mouse_score": 0,
                    "focus_score": 0,
                })
                continue

            # Input intensity: normalized to 0-50
            input_score = (
                (raw["input_rate"] / max_input_rate * 50.0)
                if max_input_rate > 0 else 0.0
            )

            # Mouse activity: normalized to 0-25
            mouse_score = (
                (raw["mouse_rate"] / max_mouse_rate * 25.0)
                if max_mouse_rate > 0 else 0.0
            )

            # Focus consistency: 1 - (switches / sessions), scaled to 0-25
            total_sessions = sessions_per_hour.get(h, 1)
            total_switches_h = switches_per_hour.get(h, 0)
            if total_sessions > 0:
                focus_ratio = 1.0 - (total_switches_h / total_sessions)
            else:
                focus_ratio = 1.0
            focus_score = max(0.0, focus_ratio) * 25.0

            engagement_score = int(round(input_score + mouse_score + focus_score))
            engagement_score = max(0, min(100, engagement_score))

            hours.append({
                "hour": h,
                "engagement_score": engagement_score,
                "input_score": round(input_score, 1),
                "mouse_score": round(mouse_score, 1),
                "focus_score": round(focus_score, 1),
            })
            engagement_scores.append(engagement_score)

        # Derived metrics
        active_hours_data = [h for h in hours if h["engagement_score"] > 0]
        peak_engagement_hour = (
            max(active_hours_data, key=lambda h: h["engagement_score"])["hour"]
            if active_hours_data else None
        )
        avg_engagement = (
            round(sum(engagement_scores) / len(engagement_scores), 1)
            if engagement_scores else 0.0
        )

        # Engagement trend: compare first half vs second half of active hours
        if len(active_hours_data) >= 2:
            mid = len(active_hours_data) // 2
            first_half_avg = sum(
                h["engagement_score"] for h in active_hours_data[:mid]
            ) / mid
            second_half_avg = sum(
                h["engagement_score"] for h in active_hours_data[mid:]
            ) / (len(active_hours_data) - mid)
            if second_half_avg > first_half_avg * 1.1:
                trend = "rising"
            elif second_half_avg < first_half_avg * 0.9:
                trend = "falling"
            else:
                trend = "steady"
        else:
            trend = "steady"

        return {
            "date": target_date.isoformat(),
            "hours": hours,
            "peak_engagement_hour": peak_engagement_hour,
            "avg_engagement": avg_engagement,
            "engagement_trend": trend,
        }
    except Exception:
        log.exception("Error computing engagement curve for %s", target_date)
        return {
            "date": target_date.isoformat(),
            "hours": [
                {"hour": h, "engagement_score": 0, "input_score": 0,
                 "mouse_score": 0, "focus_score": 0}
                for h in range(24)
            ],
            "peak_engagement_hour": None,
            "avg_engagement": 0.0,
            "engagement_trend": "steady",
        }
    finally:
        session.close()


# ---------------------------------------------------------------------------
# 14. compute_baselines
# ---------------------------------------------------------------------------

def compute_baselines(days: int = 30) -> dict:
    """Compute rolling baselines over the last N days."""
    end_date = _today()
    start_date = end_date - timedelta(days=days)

    session = get_session()
    try:
        # ---- DailySummary data for per-day totals ----
        summaries = (
            session.query(DailySummary)
            .filter(
                DailySummary.date >= start_date,
                DailySummary.date < end_date,
            )
            .all()
        )

        # Group by date
        daily_totals: dict[date, float] = defaultdict(float)
        app_daily: dict[str, dict[date, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for s in summaries:
            daily_totals[s.date] += s.total_seconds
            app_daily[s.process_name][s.date] += s.total_seconds

        active_days = sorted(daily_totals.keys())
        num_days = len(active_days) if active_days else 1

        # ---- Metric: total_active_seconds ----
        active_values = list(daily_totals.values()) if daily_totals else [0.0]

        def _stats(values: list[float]) -> dict:
            """Compute avg, stddev, min, max for a list of values."""
            n = len(values)
            if n == 0:
                return {"avg": 0.0, "stddev": 0.0, "min": 0.0, "max": 0.0}
            avg = sum(values) / n
            variance = sum((v - avg) ** 2 for v in values) / n
            stddev = variance ** 0.5
            return {
                "avg": round(avg, 1),
                "stddev": round(stddev, 1),
                "min": round(min(values), 1),
                "max": round(max(values), 1),
            }

        # ---- Metric: context_switches per day ----
        baseline_sessions = (
            session.query(AppSession.started_at)
            .filter(
                AppSession.started_at >= datetime(
                    start_date.year, start_date.month, start_date.day,
                    tzinfo=timezone.utc,
                ),
                AppSession.started_at < datetime(
                    end_date.year, end_date.month, end_date.day,
                    tzinfo=timezone.utc,
                ),
            )
            .order_by(AppSession.started_at)
            .all()
        )
        sessions_per_day: dict[date, int] = defaultdict(int)
        for row in baseline_sessions:
            sessions_per_day[row.started_at.date()] += 1
        switch_values = [
            max(cnt - 1, 0) for cnt in sessions_per_day.values()
        ] if sessions_per_day else [0.0]

        # ---- Metric: focus_session_count per day ----
        focus_sessions = (
            session.query(AppSession.started_at)
            .filter(
                AppSession.started_at >= datetime(
                    start_date.year, start_date.month, start_date.day,
                    tzinfo=timezone.utc,
                ),
                AppSession.started_at < datetime(
                    end_date.year, end_date.month, end_date.day,
                    tzinfo=timezone.utc,
                ),
                AppSession.duration_seconds >= 1800,
            )
            .all()
        )
        focus_per_day: dict[date, int] = defaultdict(int)
        for row in focus_sessions:
            focus_per_day[row.started_at.date()] += 1
        # Include zero-count days for days with activity but no focus sessions
        focus_values = []
        for d in active_days:
            focus_values.append(float(focus_per_day.get(d, 0)))
        if not focus_values:
            focus_values = [0.0]

        # ---- Metric: productivity_pct per day ----
        prod_values: list[float] = []
        if AppCategory is not None:
            process_names = list({s.process_name for s in summaries})
            categories = _get_app_categories(session, process_names)

            for d in active_days:
                day_summaries = [s for s in summaries if s.date == d]
                day_total = sum(s.total_seconds for s in day_summaries)
                day_productive = sum(
                    s.total_seconds for s in day_summaries
                    if categories.get(s.process_name, {}).get("is_productive", False)
                )
                if day_total > 0:
                    prod_values.append(round(day_productive / day_total * 100, 1))
                else:
                    prod_values.append(0.0)
        if not prod_values:
            prod_values = [0.0]

        # ---- Metric: first_activity_hour / last_activity_hour ----
        non_idle_samples = (
            session.query(ActivitySample.sampled_at)
            .filter(
                ActivitySample.sampled_at >= datetime(
                    start_date.year, start_date.month, start_date.day,
                    tzinfo=timezone.utc,
                ),
                ActivitySample.sampled_at < datetime(
                    end_date.year, end_date.month, end_date.day,
                    tzinfo=timezone.utc,
                ),
                ActivitySample.is_idle == False,  # noqa: E712
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        start_hour_values: list[float] = []
        end_hour_values: list[float] = []
        if non_idle_samples:
            daily_samples_map: dict[date, list[datetime]] = defaultdict(list)
            for row in non_idle_samples:
                daily_samples_map[row.sampled_at.date()].append(row.sampled_at)
            for d, timestamps in daily_samples_map.items():
                first = min(timestamps)
                last = max(timestamps)
                start_hour_values.append(first.hour + first.minute / 60.0)
                end_hour_values.append(last.hour + last.minute / 60.0)

        if not start_hour_values:
            start_hour_values = [0.0]
        if not end_hour_values:
            end_hour_values = [0.0]

        # ---- Per-app average daily seconds ----
        app_averages: dict[str, float] = {}
        for app, daily_secs in app_daily.items():
            total = sum(daily_secs.values())
            app_averages[app] = round(total / num_days, 1)

        return {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "metrics": {
                "total_active_seconds": _stats(active_values),
                "context_switches": _stats([float(v) for v in switch_values]),
                "focus_session_count": _stats(focus_values),
                "productivity_pct": _stats(prod_values),
                "first_activity_hour": _stats(start_hour_values),
                "last_activity_hour": _stats(end_hour_values),
            },
            "app_averages": app_averages,
        }
    except Exception:
        log.exception("Error computing baselines over %d days", days)
        return {
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "metrics": {},
            "app_averages": {},
        }
    finally:
        session.close()
