#!/usr/bin/env python3
"""Query the Trackyr activity tracker API.

Usage:
    python trackyr_query.py --mode today
    python trackyr_query.py --mode date --date 2026-03-01
    python trackyr_query.py --mode hours --hours 2
    python trackyr_query.py --mode weekly
    python trackyr_query.py --mode current
    python trackyr_query.py --mode timeline --date 2026-03-01
    python trackyr_query.py --mode focus
    python trackyr_query.py --mode productivity
    python trackyr_query.py --mode context-switches
    python trackyr_query.py --mode trends --days 7
    python trackyr_query.py --mode context --format json
    python trackyr_query.py --mode standup
    python trackyr_query.py --mode goals
    python trackyr_query.py --mode categories
    python trackyr_query.py --mode search --query "trackyr"
    python trackyr_query.py --mode health
    python trackyr_query.py --mode today --format json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date as date_type

BASE_URL = "http://localhost:8099/api/v1"

ALL_MODES = [
    "today", "date", "hours", "weekly", "current",
    "timeline", "focus", "productivity", "context-switches",
    "trends", "context", "standup", "goals", "categories",
    "search", "health",
    "heatmap", "heatmap-week", "workday", "narrative",
    "switch-patterns", "anomalies", "engagement", "baselines",
    "notes", "export",
    # Round 3
    "projects", "project-breakdown", "tags", "compare",
    "streaks", "report-card", "titles", "stream-snapshot",
]


def fetch(path: str) -> dict | list:
    """GET a JSON endpoint from the Trackyr API."""
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.URLError:
        print(f"Error: Cannot reach Trackyr API at {url}", file=sys.stderr)
        print("Make sure Trackyr is running: python -m trackyr", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt(seconds) -> str:
    """Format seconds as Xh Ym."""
    seconds = int(seconds or 0)
    h, r = divmod(seconds, 3600)
    m = r // 60
    return f"{h}h {m}m" if h else f"{m}m"


# ---------------------------------------------------------------------------
# Render functions — existing
# ---------------------------------------------------------------------------

def _render_app_table(apps: list[dict], limit: int = 15) -> list[str]:
    """Render top-apps table rows shared by daily/hours renderers."""
    lines = [
        "Top Apps:",
        f"{'App':<30} {'Time':>8} {'Clicks':>8} {'Keys':>8}",
        f"{'-' * 30} {'-' * 8} {'-' * 8} {'-' * 8}",
    ]
    for app in apps[:limit]:
        lines.append(
            f"{app['process_name']:<30} {app['total_seconds_fmt']:>8} "
            f"{app['total_clicks']:>8} {app['total_keys']:>8}"
        )
    return lines


def render_daily(data: dict) -> str:
    lines = [
        f"Activity Report for {data['date']}",
        f"{'=' * 40}",
        f"Active time:  {data['total_active_fmt']}",
        f"Idle time:    {data['total_idle_fmt']}",
        f"Clicks:       {data['total_clicks']:,}",
        f"Key presses:  {data['total_keys']:,}",
        f"App sessions: {data['session_count']}",
        "",
    ]
    lines.extend(_render_app_table(data.get("top_apps", [])))
    return "\n".join(lines)


def render_hours(data: dict) -> str:
    lines = [
        f"Activity - Last {data['hours']} Hour(s)",
        f"{'=' * 40}",
        f"Active time:  {data['total_active_fmt']}",
        f"Idle time:    {data['total_idle_fmt']}",
        f"Clicks:       {data['total_clicks']:,}",
        f"Key presses:  {data['total_keys']:,}",
        "",
    ]
    lines.extend(_render_app_table(data.get("top_apps", [])))
    return "\n".join(lines)


def render_weekly(data: dict) -> str:
    lines = [
        f"Weekly Report: {data['week_start']} to {data['week_ending']}",
        f"{'=' * 50}",
        f"Total active: {data['total_seconds_fmt']}",
        f"Prior week:   {data['prior_week_fmt']}",
        f"Clicks:       {data['total_clicks']:,}",
        f"Key presses:  {data['total_keys']:,}",
        "",
        "Day-by-Day:",
        f"{'Day':<12} {'Date':<12} {'Time':>8} {'Clicks':>8} {'Keys':>8}",
        f"{'-' * 12} {'-' * 12} {'-' * 8} {'-' * 8} {'-' * 8}",
    ]
    for d in data.get("days", []):
        lines.append(
            f"{d['weekday']:<12} {d['date']:<12} {d['total_seconds_fmt']:>8} "
            f"{d['total_clicks']:>8} {d['total_keys']:>8}"
        )
    lines.append("")
    lines.append("Top Apps (Week):")
    lines.extend(_render_app_table(data.get("top_apps", []), limit=10)[1:])
    return "\n".join(lines)


def render_current(data: dict) -> str:
    status = "idle" if data.get("is_idle") else "active"
    stale = " (stale - Trackyr may be paused)" if data.get("stale") else ""
    lines = [
        f"Current Activity{stale}",
        f"App:     {data.get('process_name', 'unknown')}",
        f"Window:  {data.get('window_title', '')[:80]}",
        f"Status:  {status}",
        f"Sampled: {data.get('sampled_at', '')}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render functions — new modes
# ---------------------------------------------------------------------------

def render_timeline(data: list[dict]) -> str:
    lines = [
        f"Activity Timeline ({len(data)} samples)",
        f"{'Time':<22} {'App':<25} {'Window':<40} {'Idle':>5}",
        f"{'-'*22} {'-'*25} {'-'*40} {'-'*5}",
    ]
    for s in data:
        time = s.get("sampled_at", "")[:19]
        app = (s.get("process_name") or "unknown")[:25]
        win = (s.get("window_title") or "")[:40]
        idle = "yes" if s.get("is_idle") else ""
        lines.append(f"{time:<22} {app:<25} {win:<40} {idle:>5}")
    return "\n".join(lines)


def render_focus(data: list[dict]) -> str:
    if not data:
        return "No focus sessions detected (>30 min on one app)."
    lines = [
        f"Focus Sessions ({len(data)} detected)",
        f"{'='*50}",
    ]
    for i, s in enumerate(data, 1):
        lines.append(f"\n  Session {i}: {s.get('primary_app', 'unknown')}")
        lines.append(f"  Duration: {s.get('duration_fmt', '?')}")
        lines.append(f"  Time:     {s.get('started_at', '')[:16]} to {s.get('ended_at', '')[:16]}")
        lines.append(f"  Quality:  {s.get('quality_score', 0):.0f}/100")
        lines.append(f"  Input:    {s.get('total_clicks', 0)} clicks, {s.get('total_keys', 0)} keys")
    return "\n".join(lines)


def render_productivity(data: dict) -> str:
    lines = [
        f"Productivity Report — {data.get('date', 'today')}",
        f"{'='*40}",
        f"Score:          {data.get('productivity_pct', 0):.1f}%",
        f"Active time:    {_fmt(data.get('total_active_seconds', 0))}",
        f"Productive:     {_fmt(data.get('productive_seconds', 0))}",
        f"Unproductive:   {_fmt(data.get('unproductive_seconds', 0))}",
        f"Uncategorized:  {_fmt(data.get('uncategorized_seconds', 0))}",
        "",
        "By Category:",
    ]
    for cat, info in (data.get("by_category") or {}).items():
        lines.append(f"  {cat:<20} {info.get('fmt', '?'):>8}  ({', '.join(info.get('apps', [])[:3])})")
    return "\n".join(lines)


def render_context_switches(data: dict) -> str:
    lines = [
        f"Context Switching — {data.get('date', 'today')}",
        f"{'='*40}",
        f"Total switches:     {data.get('total_switches', 0)}",
        f"Avg/hour:           {data.get('avg_switches_per_hour', 0):.1f}",
        f"Week avg:           {data.get('week_avg_switches', 0):.1f}",
        f"vs average:         {data.get('vs_average_pct', 0):+.0f}%",
    ]
    return "\n".join(lines)


def render_trends(data: dict) -> str:
    cur = _fmt(data.get("current_total_seconds", 0))
    prev = _fmt(data.get("previous_total_seconds", 0))
    change = data.get("change_pct", 0)
    lines = [
        f"Trend Comparison",
        f"{'='*40}",
        f"Current period:  {data.get('current_period', {}).get('start', '?')} to {data.get('current_period', {}).get('end', '?')}",
        f"Previous period: {data.get('previous_period', {}).get('start', '?')} to {data.get('previous_period', {}).get('end', '?')}",
        f"",
        f"Current total:   {cur}",
        f"Previous total:  {prev}",
        f"Change:          {change:+.1f}%",
        "",
        "Notable changes:",
    ]
    for c in (data.get("notable_changes") or [])[:5]:
        lines.append(f"  {c.get('app', '?'):<25} {c.get('change_pct', 0):+.0f}%")
    return "\n".join(lines)


def render_ai_context(data: dict) -> str:
    lines = [
        f"Current Context",
        f"App:          {data.get('current_app', 'unknown')}",
        f"Active since: {(data.get('active_since') or '')[:16]}",
        f"Active today: {data.get('total_active_today_fmt', '?')}",
        f"Productivity: {data.get('productivity_pct', 0):.0f}%",
        f"Focus today:  {data.get('focus_sessions_today', 0)} sessions",
        f"Status:       {'idle' if data.get('is_idle') else 'active'}",
    ]
    return "\n".join(lines)


def render_standup(data: dict) -> str:
    text = data.get("standup_text", "")
    if text:
        return text
    # Fallback to structured rendering
    lines = [f"Standup — {data.get('date', 'yesterday')}", f"{'='*40}"]
    summary = data.get("summary", {})
    if summary:
        lines.append(f"Active: {summary.get('total_active_fmt', '?')}, Idle: {summary.get('total_idle_fmt', '?')}")
    lines.append(f"Productivity: {data.get('productivity_pct', 0):.0f}%")
    for s in data.get("focus_sessions", [])[:3]:
        lines.append(f"  Focus: {s.get('primary_app', '?')} for {s.get('duration_fmt', '?')}")
    return "\n".join(lines)


def render_goals(data: list[dict]) -> str:
    if not data:
        return "No active goals. Set goals via POST /api/v1/goals"
    lines = ["Goals Progress", f"{'='*50}"]
    for g in data:
        goal = g.get("goal", {})
        met = "OK" if g.get("met") else ".."
        pct = g.get("progress_pct", 0)
        bar_len = int(pct / 5)
        bar = "#" * bar_len + "." * (20 - bar_len)
        lines.append(f"  [{met}] {goal.get('name', '?'):<25} [{bar}] {pct:.0f}%")
    return "\n".join(lines)


def render_categories(data: list[dict]) -> str:
    if not data:
        return "No app categories set. Configure via POST /api/v1/categories"
    lines = [
        "App Categories",
        f"{'Process':<30} {'Category':<15} {'Productive':>10}",
        f"{'-'*30} {'-'*15} {'-'*10}",
    ]
    for c in data:
        prod = "yes" if c.get("is_productive") else "no"
        lines.append(f"{c.get('process_name', '?'):<30} {c.get('category', '?'):<15} {prod:>10}")
    return "\n".join(lines)


def render_search(data: list[dict]) -> str:
    if not data:
        return "No matching activity found."
    lines = [
        f"Search Results ({len(data)} matches)",
        f"{'Time':<22} {'App':<25} {'Window':<50}",
        f"{'-'*22} {'-'*25} {'-'*50}",
    ]
    for s in data:
        time = (s.get("sampled_at") or "")[:19]
        app = (s.get("process_name") or "?")[:25]
        win = (s.get("window_title") or "")[:50]
        lines.append(f"{time:<22} {app:<25} {win:<50}")
    return "\n".join(lines)


def render_health(data: dict) -> str:
    lines = [
        f"System Health: {data.get('status', 'unknown').upper()}",
        f"DB connected:     {data.get('db_connected', False)}",
        f"Collector running: {data.get('collector_running', False)}",
        f"Last sample age:  {data.get('last_sample_age_seconds', '?')}s",
        f"Today's samples:  {data.get('today_sample_count', 0)}",
    ]
    return "\n".join(lines)


def render_heatmap(data: dict) -> str:
    lines = [f"Activity Heatmap - {data.get('date', 'today')}", f"{'='*60}"]
    lines.append(f"{'Hour':<6} {'Active':>8} {'App':<25} {'Clicks':>7} {'Keys':>7}")
    lines.append(f"{'-'*6} {'-'*8} {'-'*25} {'-'*7} {'-'*7}")
    for h in data.get("hours", []):
        active = _fmt(h.get("active_seconds", 0))
        app = (h.get("dominant_app") or "-")[:25]
        lines.append(f"{h.get('hour', 0):>4}:00 {active:>8} {app:<25} {h.get('clicks', 0):>7} {h.get('keys', 0):>7}")
    peak = data.get("peak_hour")
    if peak is not None:
        lines.append(f"\nPeak hour: {peak}:00")
    return "\n".join(lines)


def render_workday(data: dict) -> str:
    lines = [
        f"Workday - {data.get('date', 'today')}",
        f"{'='*40}",
        f"Started:      {(data.get('work_start') or '?')[:16]}",
        f"Ended:        {(data.get('work_end') or '?')[:16]}",
        f"Total span:   {data.get('total_span_fmt', '?')}",
        f"Active time:  {data.get('total_active_fmt', '?')}",
        f"Break time:   {data.get('total_break_fmt', '?')}",
        f"Overtime:     {'YES' if data.get('overtime') else 'No'}",
    ]
    lunch = data.get("lunch_break")
    if lunch:
        lines.append(f"Lunch:        {(lunch.get('start') or '')[:16]} ({_fmt(lunch.get('duration_seconds', 0))})")
    breaks = data.get("breaks", [])
    if breaks:
        lines.append(f"\nBreaks ({len(breaks)}):")
        for b in breaks[:10]:
            lines.append(f"  {(b.get('start') or '')[:16]} - {_fmt(b.get('duration_seconds', 0))}")
    return "\n".join(lines)


def render_narrative(data: dict) -> str:
    return data.get("narrative_text", "No narrative available.")


def render_switch_patterns(data: dict) -> str:
    lines = [
        f"Context Switch Patterns - {data.get('date', 'today')}",
        f"{'='*50}",
        f"Total transitions: {data.get('total_transitions', 0)}",
        "",
        "Top Transitions:",
    ]
    for t in (data.get("top_transitions") or [])[:10]:
        lines.append(f"  {t.get('from_app', '?'):<20} -> {t.get('to_app', '?'):<20} ({t.get('count', 0)}x)")
    magnets = data.get("distraction_magnets") or []
    if magnets:
        lines.append("\nDistraction Magnets:")
        for m in magnets[:5]:
            lines.append(f"  {m.get('app', '?'):<25} {m.get('interruption_count', 0)} interruptions, avg {_fmt(m.get('avg_time_spent_seconds', 0))}")
    return "\n".join(lines)


def render_anomalies(data: dict) -> str:
    anomalies = data.get("anomalies", [])
    if not anomalies:
        return "No anomalies detected today."
    severity_icons = {"info": "[i]", "warning": "[!]", "alert": "[!!]"}
    lines = [f"Anomalies - {data.get('date', 'today')}", f"{'='*50}"]
    for a in anomalies:
        icon = severity_icons.get(a.get("severity", "info"), "[?]")
        lines.append(f"  {icon} {a.get('message', '?')}")
    return "\n".join(lines)


def render_engagement(data: dict) -> str:
    lines = [
        f"Engagement Curve - {data.get('date', 'today')}",
        f"{'='*50}",
        f"Avg engagement: {data.get('avg_engagement', 0):.0f}/100",
        f"Peak hour:      {data.get('peak_engagement_hour', '?')}:00",
        f"Trend:          {data.get('engagement_trend', '?')}",
        "",
        f"{'Hour':<6} {'Score':>6} {'Bar':<22}",
    ]
    for h in data.get("hours", []):
        score = h.get("engagement_score", 0)
        bar = "#" * int(score / 5) + "." * (20 - int(score / 5))
        lines.append(f"{h.get('hour', 0):>4}:00 {score:>5.0f} [{bar}]")
    return "\n".join(lines)


def render_baselines(data: dict) -> str:
    metrics = data.get("metrics", {})
    if not metrics:
        return "No baselines computed yet."
    lines = ["Baselines (30-day rolling)", f"{'='*50}"]
    for name, vals in metrics.items():
        lines.append(f"  {name:<30} avg={vals.get('avg', 0):.1f}  std={vals.get('stddev', 0):.1f}")
    return "\n".join(lines)


def render_notes(data: list[dict]) -> str:
    if not data:
        return "No notes for this date."
    lines = ["Daily Notes", f"{'='*40}"]
    for n in data:
        lines.append(f"  [{n.get('source', '?')}] {n.get('note_text', '')}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Render functions — Round 3
# ---------------------------------------------------------------------------


def render_projects(data: list[dict]) -> str:
    if not data:
        return "No projects defined yet. Use the API to create project rules."
    lines = ["Projects", f"{'='*50}"]
    for p in data:
        rules_count = len(p.get("rules", []))
        status = "active" if p.get("is_active") else "inactive"
        lines.append(f"  {p.get('name', '?'):<25} {p.get('color', '')} ({rules_count} rules, {status})")
    return "\n".join(lines)


def render_project_breakdown(data: dict) -> str:
    projects = data.get("projects", [])
    if not projects:
        return f"No project activity on {data.get('date', '?')}."
    lines = [
        f"Project Breakdown — {data.get('date', '?')}",
        f"{'='*60}",
        f"{'Project':<25} {'Time':>8} {'%':>6}",
        f"{'-'*25} {'-'*8} {'-'*6}",
    ]
    for p in projects:
        lines.append(
            f"  {p.get('name', '?'):<23} {p.get('total_formatted', ''):>8} {p.get('percentage', 0):>5.1f}%"
        )
        for w in p.get("top_windows", [])[:3]:
            lines.append(f"    \u2514 {w[:55]}")
    unmatched = data.get("unmatched_formatted", "0m")
    lines.append(f"\n  Unmatched: {unmatched}")
    return "\n".join(lines)


def render_tags(data: list[dict]) -> str:
    if not data:
        return "No tags for this date."
    lines = ["Activity Tags", f"{'='*50}"]
    for t in data:
        start = t.get("start_time", "?")[:16]
        end = t.get("end_time", "?")[:16]
        lines.append(f"  [{t.get('source', '?')}] {t.get('tag_name', '?')} ({start} \u2014 {end})")
        if t.get("notes"):
            lines.append(f"         {t['notes']}")
    return "\n".join(lines)


def render_compare(data: dict) -> str:
    p1 = data.get("period1", {})
    p2 = data.get("period2", {})
    m1 = p1.get("metrics", {})
    m2 = p2.get("metrics", {})
    deltas = data.get("deltas", {})

    lines = [
        "Period Comparison",
        f"{'='*60}",
        f"  Period 1: {p1.get('start', '?')} \u2014 {p1.get('end', '?')}",
        f"  Period 2: {p2.get('start', '?')} \u2014 {p2.get('end', '?')}",
        "",
        f"{'Metric':<22} {'Period 1':>10} {'Period 2':>10} {'Delta':>10} {'%':>8}",
        f"{'-'*22} {'-'*10} {'-'*10} {'-'*10} {'-'*8}",
    ]
    for key in ["total_seconds", "active_seconds", "idle_seconds", "total_clicks", "total_keys", "session_count"]:
        v1 = m1.get(key, 0)
        v2 = m2.get(key, 0)
        d = deltas.get(key, 0)
        pct = deltas.get(f"{key}_pct", 0)
        label = key.replace("_", " ").title()
        if "seconds" in key:
            lines.append(f"  {label:<20} {_fmt(v1):>10} {_fmt(v2):>10} {_fmt(d):>10} {pct:>+7.1f}%")
        else:
            lines.append(f"  {label:<20} {v1:>10} {v2:>10} {d:>+10} {pct:>+7.1f}%")
    return "\n".join(lines)


def render_streaks(data: dict) -> str:
    streaks = data.get("streaks", {})
    if not streaks:
        return "No streak data."
    lines = ["Streaks", f"{'='*50}"]
    for stype, info in streaks.items():
        label = stype.replace("_", " ").title()
        current = info.get("current", 0)
        best = info.get("best", 0)
        active = "ACTIVE" if info.get("is_active") else "broken"
        lines.append(f"  {label:<20} Current: {current} days ({active})  |  Best: {best} days")
        if info.get("best_start"):
            lines.append(f"  {'':20} Best: {info['best_start']} \u2014 {info['best_end']}")
    return "\n".join(lines)


def render_report_card(data: dict) -> str:
    grades = data.get("grades", {})
    if not grades:
        return f"No data for report card on {data.get('date', '?')}."
    lines = [
        f"Report Card — {data.get('date', '?')}",
        f"{'='*50}",
        f"  Overall: {data.get('overall_grade', '?')} (GPA {data.get('gpa', 0):.2f})",
        "",
        f"  {'Metric':<22} {'Grade':>6} {'Score':>8}",
        f"  {'-'*22} {'-'*6} {'-'*8}",
    ]
    for metric, info in grades.items():
        label = metric.replace("_", " ").title()
        lines.append(f"  {label:<22} {info.get('grade', '?'):>6} {info.get('score', 0):>8.1f}")
    lines.append(f"\n  {data.get('summary', '')}")
    return "\n".join(lines)


def render_titles(data: dict) -> str:
    lines = [f"Title Metadata — {data.get('date', '?')}", f"{'='*50}"]

    tickets = data.get("ticket_ids", [])
    if tickets:
        lines.append("\nTicket IDs:")
        for t in tickets[:10]:
            lines.append(f"  {t.get('id', '?')} ({t.get('count', 0)}x) — {', '.join(t.get('apps', []))}")

    repos = data.get("repos", [])
    if repos:
        lines.append("\nRepositories:")
        for r in repos[:10]:
            lines.append(f"  {r.get('name', '?')} ({r.get('count', 0)}x, {_fmt(r.get('total_seconds', 0))})")

    files = data.get("files", [])
    if files:
        lines.append("\nFiles:")
        for f in files[:10]:
            lines.append(f"  {f.get('path', '?')} ({f.get('count', 0)}x, .{f.get('extension', '')})")

    branches = data.get("branches", [])
    if branches:
        lines.append("\nBranches:")
        for b in branches[:10]:
            lines.append(f"  {b.get('name', '?')} ({b.get('count', 0)}x)")

    if not (tickets or repos or files or branches):
        lines.append("  No metadata extracted from window titles.")

    return "\n".join(lines)


def render_stream_snapshot(data: dict) -> str:
    status = data.get("status", "?")
    if status != "ok":
        return f"Stream status: {status}"
    sample = data.get("latest_sample", {})
    return (
        f"Stream Snapshot (status: {status})\n"
        f"  Latest: {sample.get('process_name', '?')} — {(sample.get('window_title', '') or '')[:60]}\n"
        f"  Time: {sample.get('sampled_at', '?')}\n"
        f"  Idle: {sample.get('is_idle', False)}"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Query Trackyr activity data")
    parser.add_argument(
        "--mode",
        choices=ALL_MODES,
        required=True,
        help="Query mode",
    )
    parser.add_argument("--date", help="Date for date/timeline/focus/productivity/context-switches/search modes (YYYY-MM-DD)")
    parser.add_argument("--hours", type=int, default=1, help="Number of hours for 'hours' mode (default: 1)")
    parser.add_argument("--days", type=int, default=7, help="Number of days for 'trends' mode (default: 7)")
    parser.add_argument("--query", "-q", help="Search query for 'search' mode")
    parser.add_argument("--app", help="Filter by app name for 'timeline' mode")
    parser.add_argument("--start", help="Start date for 'export'/'compare' mode (YYYY-MM-DD)")
    parser.add_argument("--end", help="End date for 'export'/'compare' mode (YYYY-MM-DD)")
    parser.add_argument("--start2", help="Period 2 start date for 'compare' mode (YYYY-MM-DD)")
    parser.add_argument("--end2", help="Period 2 end date for 'compare' mode (YYYY-MM-DD)")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

    today = date_type.today().isoformat()
    target_date = args.date or today

    if args.mode == "today":
        data = fetch("/summary/today")
        output = json.dumps(data, indent=2) if args.format == "json" else render_daily(data)
    elif args.mode == "date":
        if not args.date:
            parser.error("--date is required for 'date' mode")
        data = fetch(f"/summary/{args.date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_daily(data)
    elif args.mode == "hours":
        data = fetch(f"/summary/hours/{args.hours}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_hours(data)
    elif args.mode == "weekly":
        data = fetch("/weekly")
        output = json.dumps(data, indent=2) if args.format == "json" else render_weekly(data)
    elif args.mode == "current":
        data = fetch("/current")
        output = json.dumps(data, indent=2) if args.format == "json" else render_current(data)
    elif args.mode == "timeline":
        path = f"/timeline/{target_date}"
        if args.app:
            path += f"?app={urllib.request.quote(args.app)}"
        data = fetch(path)
        output = json.dumps(data, indent=2) if args.format == "json" else render_timeline(data)
    elif args.mode == "focus":
        data = fetch(f"/focus-sessions/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_focus(data)
    elif args.mode == "productivity":
        data = fetch(f"/productivity/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_productivity(data)
    elif args.mode == "context-switches":
        data = fetch(f"/context-switches/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_context_switches(data)
    elif args.mode == "trends":
        data = fetch(f"/trends?days={args.days}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_trends(data)
    elif args.mode == "context":
        data = fetch("/context")
        output = json.dumps(data, indent=2) if args.format == "json" else render_ai_context(data)
    elif args.mode == "standup":
        data = fetch("/standup")
        output = json.dumps(data, indent=2) if args.format == "json" else render_standup(data)
    elif args.mode == "goals":
        data = fetch("/goals/progress")
        output = json.dumps(data, indent=2) if args.format == "json" else render_goals(data)
    elif args.mode == "categories":
        data = fetch("/categories")
        output = json.dumps(data, indent=2) if args.format == "json" else render_categories(data)
    elif args.mode == "search":
        if not args.query:
            parser.error("--query is required for 'search' mode")
        path = f"/search?q={urllib.request.quote(args.query)}"
        if args.date:
            path += f"&target_date={args.date}"
        data = fetch(path)
        output = json.dumps(data, indent=2) if args.format == "json" else render_search(data)
    elif args.mode == "health":
        data = fetch("/health")
        output = json.dumps(data, indent=2) if args.format == "json" else render_health(data)
    elif args.mode == "heatmap":
        data = fetch(f"/heatmap/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_heatmap(data)
    elif args.mode == "heatmap-week":
        data = fetch("/heatmap/week")
        output = json.dumps(data, indent=2) if args.format == "json" else render_heatmap(data)
    elif args.mode == "workday":
        data = fetch(f"/workday/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_workday(data)
    elif args.mode == "narrative":
        data = fetch(f"/narrative/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_narrative(data)
    elif args.mode == "switch-patterns":
        data = fetch(f"/context-switches/{target_date}/patterns")
        output = json.dumps(data, indent=2) if args.format == "json" else render_switch_patterns(data)
    elif args.mode == "anomalies":
        data = fetch(f"/anomalies/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_anomalies(data)
    elif args.mode == "engagement":
        data = fetch(f"/engagement/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_engagement(data)
    elif args.mode == "baselines":
        data = fetch("/baselines")
        output = json.dumps(data, indent=2) if args.format == "json" else render_baselines(data)
    elif args.mode == "notes":
        data = fetch(f"/notes/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_notes(data)
    elif args.mode == "export":
        start = args.start or target_date
        end = args.end or target_date
        data = fetch(f"/export/samples?start={start}&end={end}&format=json")
        output = json.dumps(data, indent=2)
    elif args.mode == "projects":
        data = fetch("/projects")
        output = json.dumps(data, indent=2) if args.format == "json" else render_projects(data)
    elif args.mode == "project-breakdown":
        data = fetch(f"/projects/{target_date}/breakdown")
        output = json.dumps(data, indent=2) if args.format == "json" else render_project_breakdown(data)
    elif args.mode == "tags":
        data = fetch(f"/tags/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_tags(data)
    elif args.mode == "compare":
        s1 = args.start or target_date
        e1 = args.end or target_date
        s2 = args.start2 or target_date
        e2 = args.end2 or target_date
        data = fetch(f"/compare?start1={s1}&end1={e1}&start2={s2}&end2={e2}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_compare(data)
    elif args.mode == "streaks":
        data = fetch("/streaks")
        output = json.dumps(data, indent=2) if args.format == "json" else render_streaks(data)
    elif args.mode == "report-card":
        data = fetch(f"/report-card/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_report_card(data)
    elif args.mode == "titles":
        data = fetch(f"/titles/{target_date}")
        output = json.dumps(data, indent=2) if args.format == "json" else render_titles(data)
    elif args.mode == "stream-snapshot":
        data = fetch("/stream/snapshot")
        output = json.dumps(data, indent=2) if args.format == "json" else render_stream_snapshot(data)

    # Handle unicode chars that may appear in window titles
    sys.stdout.reconfigure(errors="replace")
    print(output)


if __name__ == "__main__":
    main()
