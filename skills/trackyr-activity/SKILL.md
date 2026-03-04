---
name: trackyr-activity
description: "Query desktop activity tracking data from Trackyr. Use when the user asks about: what they worked on, app usage time, productivity, activity history, focus sessions, context switching, goals, time tracking, projects, report cards, streaks, comparisons, tags, or what app is currently active."
metadata:
  forge-orchestrator:
    emoji: "\U0001F3AF"
    requires:
      bins: ["python"]
---

# Trackyr Activity

Query the Trackyr desktop activity tracker running on localhost.

## Usage

```bash
python skills/trackyr-activity/scripts/trackyr_query.py --mode <MODE> [OPTIONS]
```

### Modes

| Mode | Description | Options |
|------|-------------|---------|
| `today` | Today's activity summary — top apps, active/idle time | `--format json` |
| `date` | Specific date summary | `--date YYYY-MM-DD` |
| `hours` | Last N hours of activity | `--hours N` (default 1, max 72) |
| `weekly` | Last 7 days breakdown + top apps | |
| `current` | What app is in the foreground right now | |
| `timeline` | Granular activity timeline for a date | `--date YYYY-MM-DD --app chrome.exe` |
| `focus` | Detected deep work sessions (>30 min) | `--date YYYY-MM-DD` |
| `productivity` | Productivity score based on app categories | `--date YYYY-MM-DD` |
| `context-switches` | App switching frequency analysis | `--date YYYY-MM-DD` |
| `trends` | Compare activity to previous period | `--days N` (default 7) |
| `context` | Compact AI-ready context snapshot | |
| `standup` | Yesterday's standup-ready summary | |
| `goals` | View active goals and progress | |
| `categories` | View app categories | |
| `search` | Search activity by window title | `--query "search term" --date YYYY-MM-DD` |
| `health` | System health check | |
| `heatmap` | Hourly activity heatmap | `--date YYYY-MM-DD` |
| `heatmap-week` | 7-day heatmap grid | |
| `workday` | Work day boundaries, breaks, overtime | `--date YYYY-MM-DD` |
| `narrative` | AI-generated daily narrative | `--date YYYY-MM-DD` |
| `switch-patterns` | App transition matrix, distraction magnets | `--date YYYY-MM-DD` |
| `anomalies` | Unusual pattern detection vs baselines | `--date YYYY-MM-DD` |
| `engagement` | Per-hour engagement score curve | `--date YYYY-MM-DD` |
| `baselines` | 30-day rolling baseline metrics | |
| `notes` | Daily notes and annotations | `--date YYYY-MM-DD` |
| `export` | Export raw data as JSON | `--start, --end YYYY-MM-DD` |
| `projects` | List configured projects | |
| `project-breakdown` | Time per project for a date | `--date YYYY-MM-DD` |
| `tags` | Activity tags for a date | `--date YYYY-MM-DD` |
| `compare` | Compare two date ranges side-by-side | `--start, --end, --start2, --end2 YYYY-MM-DD` |
| `streaks` | Consecutive day streaks (productive, active, focus, early start) | |
| `report-card` | Letter-grade report card for a day | `--date YYYY-MM-DD` |
| `titles` | Extract ticket IDs, repos, files from window titles | `--date YYYY-MM-DD` |
| `stream-snapshot` | Current SSE stream state | |
| `highlight` | AI-ready daily highlight packet | `--date YYYY-MM-DD` |
| `momentum` | 4-week productivity momentum score | |
| `switch-cost` | Estimated time lost to context switching | `--date YYYY-MM-DD` |
| `monthly` | Current month rollup report | |
| `sessions` | Classified sessions (focus/meeting/break/shallow) | `--date YYYY-MM-DD` |
| `digest` | Narrative weekly digest with ranked insights | |
| `pomodoro-status` | Current Pomodoro timer state | |
| `pomodoro-today` | Today's Pomodoro summary | |
| `limits` | App time limits and current usage | |

### Examples

```bash
# What did I work on today?
python skills/trackyr-activity/scripts/trackyr_query.py --mode today

# How productive was I?
python skills/trackyr-activity/scripts/trackyr_query.py --mode productivity

# Any deep work sessions today?
python skills/trackyr-activity/scripts/trackyr_query.py --mode focus

# Am I context switching too much?
python skills/trackyr-activity/scripts/trackyr_query.py --mode context-switches

# What was I doing between 2-4 PM? (check timeline)
python skills/trackyr-activity/scripts/trackyr_query.py --mode timeline --date 2026-03-03

# How does this week compare to last?
python skills/trackyr-activity/scripts/trackyr_query.py --mode trends --days 7

# Generate my standup
python skills/trackyr-activity/scripts/trackyr_query.py --mode standup

# Quick context for decision-making
python skills/trackyr-activity/scripts/trackyr_query.py --mode context --format json

# Search for time spent on a specific project
python skills/trackyr-activity/scripts/trackyr_query.py --mode search --query "trackyr"

# Get raw JSON for any mode
python skills/trackyr-activity/scripts/trackyr_query.py --mode today --format json

# When am I most productive?
python skills/trackyr-activity/scripts/trackyr_query.py --mode heatmap

# How was my workday structured?
python skills/trackyr-activity/scripts/trackyr_query.py --mode workday

# Tell me about my day in narrative form
python skills/trackyr-activity/scripts/trackyr_query.py --mode narrative

# What apps keep interrupting me?
python skills/trackyr-activity/scripts/trackyr_query.py --mode switch-patterns

# Any unusual patterns today?
python skills/trackyr-activity/scripts/trackyr_query.py --mode anomalies

# Show my engagement curve
python skills/trackyr-activity/scripts/trackyr_query.py --mode engagement

# What projects was I working on?
python skills/trackyr-activity/scripts/trackyr_query.py --mode project-breakdown

# My report card for the day
python skills/trackyr-activity/scripts/trackyr_query.py --mode report-card

# How long is my productive streak?
python skills/trackyr-activity/scripts/trackyr_query.py --mode streaks

# Compare this week vs last week
python skills/trackyr-activity/scripts/trackyr_query.py --mode compare --start 2026-02-24 --end 2026-02-28 --start2 2026-03-03 --end2 2026-03-07

# What tickets/repos show up in my window titles?
python skills/trackyr-activity/scripts/trackyr_query.py --mode titles

# What is Trackyr seeing right now?
python skills/trackyr-activity/scripts/trackyr_query.py --mode stream-snapshot

# Give me the daily highlight for AI context
python skills/trackyr-activity/scripts/trackyr_query.py --mode highlight

# Is my productivity trending up?
python skills/trackyr-activity/scripts/trackyr_query.py --mode momentum

# How much time did I lose to context switching?
python skills/trackyr-activity/scripts/trackyr_query.py --mode switch-cost

# Monthly summary
python skills/trackyr-activity/scripts/trackyr_query.py --mode monthly

# Show classified sessions (focus/meeting/break)
python skills/trackyr-activity/scripts/trackyr_query.py --mode sessions

# Weekly digest with top insights
python skills/trackyr-activity/scripts/trackyr_query.py --mode digest

# Am I in a Pomodoro?
python skills/trackyr-activity/scripts/trackyr_query.py --mode pomodoro-status
```

## Automation

Trackyr ships with cron templates for OpenClaw automation in `cron-templates/`:
- **Hourly productivity check** — nudge if distracted
- **Morning standup** — auto-generate yesterday's summary
- **Break reminder** — alert after 90 min continuous activity
- **Daily reflection** — end-of-day summary with suggestions

Install with: `forge-orchestrator cron add --from-file cron-templates/hourly-productivity.json`

## Notes

- Trackyr runs in Docker (`trackyr-server` container on port 8099, `trackyr-db` PostgreSQL on port 5434)
- API is reachable at `http://host.docker.internal:8099` from inside Docker containers
- Data is sampled every 5 seconds; keystroke counts only (no content captured)
- Set app categories via `POST /api/v1/categories` to enable productivity scoring
