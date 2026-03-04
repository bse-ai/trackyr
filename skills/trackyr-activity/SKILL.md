---
name: trackyr-activity
description: "Query desktop activity tracking data from Trackyr. Use when the user asks about: what they worked on, app usage time, productivity, activity history, focus sessions, context switching, goals, time tracking, or what app is currently active."
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
```

## Automation

Trackyr ships with cron templates for OpenClaw automation in `cron-templates/`:
- **Hourly productivity check** — nudge if distracted
- **Morning standup** — auto-generate yesterday's summary
- **Break reminder** — alert after 90 min continuous activity
- **Daily reflection** — end-of-day summary with suggestions

Install with: `forge-orchestrator cron add --from-file cron-templates/hourly-productivity.json`

## Notes

- Trackyr must be running (`python -m trackyr` + `docker compose up -d`)
- API runs on `http://localhost:8099`
- Data is sampled every 5 seconds; keystroke counts only (no content captured)
- Set app categories via `POST /api/v1/categories` to enable productivity scoring
