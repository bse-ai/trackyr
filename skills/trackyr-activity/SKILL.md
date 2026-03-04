---
name: trackyr-activity
description: "Query desktop activity tracking data from Trackyr. Use when the user asks about: what they worked on today, app usage time, productivity summary, activity history, time spent on tasks, what app is currently active, or weekly work patterns."
---

# Trackyr Activity

Query the Trackyr desktop activity tracker running on localhost.

## Usage

Run the bundled script to fetch activity data:

```bash
python C:/projects/clawdbot/skills/trackyr-activity/scripts/trackyr_query.py --mode <MODE> [--date YYYY-MM-DD] [--hours N] [--format text|json]
```

### Modes

| Mode | Description |
|------|-------------|
| `today` | Today's activity summary — top apps, active/idle time, click/key totals |
| `date` | Specific date summary (requires `--date YYYY-MM-DD`) |
| `hours` | Last N hours of activity (default 1, use `--hours N`, max 72) |
| `weekly` | Last 7 days — day-by-day breakdown + top apps for the week |
| `current` | What app is in the foreground right now |

### Examples

```bash
# What did I work on today?
python C:/projects/clawdbot/skills/trackyr-activity/scripts/trackyr_query.py --mode today

# What was I doing last Friday?
python C:/projects/clawdbot/skills/trackyr-activity/scripts/trackyr_query.py --mode date --date 2026-02-27

# What was I doing the last 2 hours?
python C:/projects/clawdbot/skills/trackyr-activity/scripts/trackyr_query.py --mode hours --hours 2

# Weekly overview
python C:/projects/clawdbot/skills/trackyr-activity/scripts/trackyr_query.py --mode weekly

# What am I doing right now?
python C:/projects/clawdbot/skills/trackyr-activity/scripts/trackyr_query.py --mode current

# Get raw JSON for further processing
python C:/projects/clawdbot/skills/trackyr-activity/scripts/trackyr_query.py --mode today --format json
```

## Notes

- Trackyr must be running (`python -m trackyr` from `C:\projects\autarkic\trackyr`)
- API runs on `http://localhost:8099`
- If the API is unreachable, the script prints an error — suggest the user start Trackyr
- Data is sampled every 5 seconds; keystroke counts only (no content captured)
