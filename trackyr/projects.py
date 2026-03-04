"""Project detection — map activity to user-defined projects."""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func

from trackyr.db.engine import get_session
from trackyr.db.models import ActivitySample, DailySummary

log = logging.getLogger(__name__)

# Try importing Project model (may not exist until migration 004 runs)
try:
    from trackyr.db.models import Project
except ImportError:
    Project = None


# Built-in heuristic rules when no user-defined projects exist
_DEFAULT_RULES: list[dict] = [
    {"name": "Development", "color": "#22c55e", "rules": [
        {"type": "process", "pattern": "Code.exe"},
        {"type": "process", "pattern": "devenv.exe"},
        {"type": "process", "pattern": "rider64.exe"},
        {"type": "process", "pattern": "pycharm64.exe"},
        {"type": "process", "pattern": "idea64.exe"},
        {"type": "process", "pattern": "WindowsTerminal.exe"},
        {"type": "process", "pattern": "cmd.exe"},
        {"type": "process", "pattern": "powershell.exe"},
        {"type": "process", "pattern": "python.exe"},
        {"type": "process", "pattern": "node.exe"},
    ]},
    {"name": "Communication", "color": "#3b82f6", "rules": [
        {"type": "process", "pattern": "Slack.exe"},
        {"type": "process", "pattern": "Teams.exe"},
        {"type": "process", "pattern": "Discord.exe"},
        {"type": "process", "pattern": "Outlook.exe"},
        {"type": "title_contains", "pattern": "Gmail"},
        {"type": "title_contains", "pattern": "Outlook"},
    ]},
    {"name": "Browsing", "color": "#f59e0b", "rules": [
        {"type": "process", "pattern": "chrome.exe"},
        {"type": "process", "pattern": "firefox.exe"},
        {"type": "process", "pattern": "msedge.exe"},
    ]},
    {"name": "Documents", "color": "#8b5cf6", "rules": [
        {"type": "process", "pattern": "WINWORD.EXE"},
        {"type": "process", "pattern": "EXCEL.EXE"},
        {"type": "process", "pattern": "POWERPNT.EXE"},
        {"type": "process", "pattern": "Notion.exe"},
        {"type": "process", "pattern": "Obsidian.exe"},
    ]},
]


def _match_sample(process_name: str | None, window_title: str | None, rules: list[dict]) -> bool:
    """Check if a sample matches any of the given rules."""
    pname = (process_name or "").lower()
    wtitle = (window_title or "").lower()

    for rule in rules:
        rtype = rule.get("type", "")
        pattern = rule.get("pattern", "")

        if rtype == "process" and pname == pattern.lower():
            return True
        elif rtype == "title_contains" and pattern.lower() in wtitle:
            return True
        elif rtype == "title_regex":
            try:
                if re.search(pattern, window_title or "", re.IGNORECASE):
                    return True
            except re.error:
                pass
    return False


def detect_projects(target_date: date | None = None) -> dict:
    """Map activity samples to projects for a given date.

    Uses user-defined project rules from the DB, falling back to built-in heuristics.
    Returns breakdown by project with time totals and percentages.
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    day_start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    session = get_session()
    try:
        # Get samples for the day
        samples = (
            session.query(ActivitySample)
            .filter(
                ActivitySample.sampled_at >= day_start,
                ActivitySample.sampled_at < day_end,
                ActivitySample.is_idle == False,
            )
            .order_by(ActivitySample.sampled_at)
            .all()
        )

        if not samples:
            return {"date": str(target_date), "projects": [], "unmatched_seconds": 0, "unmatched_formatted": "0m"}

        # Load project rules
        projects_config: list[dict] = []
        if Project is not None:
            try:
                db_projects = session.query(Project).filter(Project.is_active == True).all()
                for p in db_projects:
                    projects_config.append({
                        "name": p.name,
                        "color": p.color,
                        "rules": p.rules or [],
                    })
            except Exception:
                pass

        # Fall back to defaults if no user projects
        if not projects_config:
            projects_config = _DEFAULT_RULES

        # Bucket for each project
        from trackyr.config import cfg
        interval = cfg.sample_interval

        project_data: dict[str, dict[str, Any]] = {}
        for pc in projects_config:
            project_data[pc["name"]] = {
                "name": pc["name"],
                "color": pc["color"],
                "total_seconds": 0.0,
                "sample_count": 0,
                "windows": defaultdict(int),
            }

        unmatched_seconds = 0.0
        total_seconds = 0.0

        for sample in samples:
            total_seconds += interval
            matched = False
            for pc in projects_config:
                if _match_sample(sample.process_name, sample.window_title, pc["rules"]):
                    pd = project_data[pc["name"]]
                    pd["total_seconds"] += interval
                    pd["sample_count"] += 1
                    if sample.window_title:
                        pd["windows"][sample.window_title[:80]] += 1
                    matched = True
                    break  # first match wins
            if not matched:
                unmatched_seconds += interval

        # Build result
        result_projects = []
        for pd in project_data.values():
            if pd["sample_count"] == 0:
                continue
            top_windows = sorted(pd["windows"].items(), key=lambda x: -x[1])[:5]
            h, rem = divmod(int(pd["total_seconds"]), 3600)
            m = rem // 60
            fmt = f"{h}h {m}m" if h > 0 else f"{m}m"
            result_projects.append({
                "name": pd["name"],
                "color": pd["color"],
                "total_seconds": pd["total_seconds"],
                "total_formatted": fmt,
                "percentage": round(pd["total_seconds"] / total_seconds * 100, 1) if total_seconds else 0,
                "top_windows": [w[0] for w in top_windows],
                "sample_count": pd["sample_count"],
            })

        result_projects.sort(key=lambda x: -x["total_seconds"])

        h, rem = divmod(int(unmatched_seconds), 3600)
        m = rem // 60
        unmatched_fmt = f"{h}h {m}m" if h > 0 else f"{m}m"

        return {
            "date": str(target_date),
            "projects": result_projects,
            "unmatched_seconds": unmatched_seconds,
            "unmatched_formatted": unmatched_fmt,
            "total_seconds": total_seconds,
        }
    except Exception as exc:
        log.error("detect_projects failed: %s", exc)
        return {"date": str(target_date), "projects": [], "unmatched_seconds": 0, "unmatched_formatted": "0m", "error": str(exc)}
    finally:
        session.close()
