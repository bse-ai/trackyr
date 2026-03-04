# Trackyr Cron Templates for OpenClaw

Pre-built cron job configurations for OpenClaw automation. Install via `forge-orchestrator cron add`.

## Templates

| Template | Schedule | Description |
|----------|----------|-------------|
| `hourly-productivity.json` | Every hour | Check productivity score, nudge if distracted |
| `morning-standup.json` | 9 AM weekdays | Generate yesterday's standup summary |
| `break-reminder.json` | Every 90 min | Alert if continuously active without breaks |
| `daily-reflection.json` | 6 PM weekdays | End-of-day activity summary and reflection |

## Usage

```bash
# Install a template
forge-orchestrator cron add --from-file hourly-productivity.json

# Or manually via CLI
forge-orchestrator cron add \
  --name "Hourly productivity" \
  --cron "0 * * * *" \
  --session isolated \
  --message "Query Trackyr productivity..." \
  --announce --channel slack
```
