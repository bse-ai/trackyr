#!/usr/bin/env python3
"""Query the Trackyr activity tracker API.

Usage:
    python trackyr_query.py --mode today
    python trackyr_query.py --mode date --date 2026-03-01
    python trackyr_query.py --mode hours --hours 2
    python trackyr_query.py --mode weekly
    python trackyr_query.py --mode current
    python trackyr_query.py --mode today --format json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8099/api/v1"


def fetch(path: str) -> dict:
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


def main():
    parser = argparse.ArgumentParser(description="Query Trackyr activity data")
    parser.add_argument(
        "--mode",
        choices=["today", "date", "hours", "weekly", "current"],
        required=True,
        help="Query mode",
    )
    parser.add_argument("--date", help="Date for 'date' mode (YYYY-MM-DD)")
    parser.add_argument("--hours", type=int, default=1, help="Number of hours for 'hours' mode (default: 1)")
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    args = parser.parse_args()

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

    # Handle unicode chars that may appear in window titles
    sys.stdout.reconfigure(errors="replace")
    print(output)


if __name__ == "__main__":
    main()
