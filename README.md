# Trackyr

Personal Windows desktop activity tracker. Logs mouse clicks, keyboard activity, active/idle state, foreground app, and window titles to PostgreSQL.

## Features

- **5-second sampling** of foreground window, idle state, mouse clicks, and keystroke counts
- **System tray** icon with color-coded status (green=active, yellow=idle, red=DB error)
- **REST API** with 46 endpoints — summaries, timeline, focus sessions, productivity scoring, heatmaps, anomaly detection, projects, streaks, report cards, tags, SSE streaming
- **Intelligence engine** — focus sessions, context switching, productivity scoring, heatmaps, workday detection, narratives, anomaly detection, engagement curves, project detection, period comparison, streaks, report cards, title metadata extraction
- **Email reports** — daily and weekly HTML summaries via Gmail
- **[OpenClaw](https://github.com/bse-ai/openclaw) integration** — AI assistant skill + webhook events + cron automation templates
- **Privacy-first** — keystroke counts only, never which keys. No screenshots, no network traffic.
- **Resilient** — buffers ~83 minutes of data if the database goes down, auto-recovers

## Quick Start

### 1. Start the database and API server

```bash
docker compose up -d
```

This starts two containers (grouped as **trackyr** in Docker Desktop):
- `trackyr-db` — PostgreSQL 16 on port 5434
- `trackyr-server` — FastAPI API + email scheduler on port 8099

### 2. Install Python dependencies and run migrations

```bash
pip install -r requirements.txt
alembic upgrade head
```

### 3. Start the activity tracker

```bash
python -m trackyr
```

A system tray icon appears. Trackyr is now recording your desktop activity.

## API

The API server runs on `http://localhost:8099` inside the `trackyr-server` container. Interactive docs at `/docs`.

### Core Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/summary/today` | Today's activity breakdown |
| `GET /api/v1/summary/{date}` | Specific date (YYYY-MM-DD) |
| `GET /api/v1/summary/hours/{n}` | Last N hours (1-72) |
| `GET /api/v1/weekly` | Last 7 days with day-by-day + top apps |
| `GET /api/v1/current` | Currently active app and window |

### Intelligence Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/focus-sessions/{date}` | Detected deep work sessions (>30 min) with quality scores |
| `GET /api/v1/context-switches/{date}` | App switching frequency vs weekly average |
| `GET /api/v1/context-switches/{date}/patterns` | Detailed switching patterns (bursts, triggers, calm periods) |
| `GET /api/v1/productivity/{date}` | Productivity score based on app categories |
| `GET /api/v1/trends?days=7` | Compare activity to previous period |
| `GET /api/v1/timeline/{date}?app=&category=` | Granular activity timeline with filtering |
| `GET /api/v1/heatmap/{date}` | Hourly activity heatmap (clicks, keys, active minutes) |
| `GET /api/v1/heatmap/week` | 7-day heatmap grid |
| `GET /api/v1/workday/{date}` | Detected work start/end, core hours, overtime |
| `GET /api/v1/narrative/{date}` | AI-ready natural language daily narrative |
| `GET /api/v1/anomalies/{date}` | Anomalies vs 30-day baseline (7 anomaly types) |
| `GET /api/v1/engagement/{date}` | Per-hour engagement score (0-100) |
| `GET /api/v1/baselines` | Current 30-day rolling baselines |
| `GET /api/v1/context` | Compact AI-ready context snapshot |
| `GET /api/v1/standup` | Yesterday's standup-ready summary |
| `GET /api/v1/search?q=term` | Search by window title or process name |
| `GET /api/v1/health` | System health check |

### Configuration & Data Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET/POST /api/v1/categories` | Manage app categories (development, browsing, etc.) |
| `GET/POST /api/v1/goals` | Set daily goals (min/max time, productivity %) |
| `GET /api/v1/goals/progress` | Real-time goal progress tracking |
| `GET/POST /api/v1/notes/{date}` | Daily notes / annotations |
| `POST /api/v1/focus/start` | Manually start a focus session |
| `POST /api/v1/focus/stop` | Manually stop a focus session |
| `GET /api/v1/focus/active` | Check if a focus session is active |
| `GET /api/v1/export/samples?start=&end=&format=` | Export raw samples (CSV or JSON) |
| `GET /api/v1/export/sessions?start=&end=&format=` | Export app sessions (CSV or JSON) |

### Projects, Tags, & Gamification

| Endpoint | Description |
|----------|-------------|
| `GET/POST /api/v1/projects` | Manage project definitions (name, color, matching rules) |
| `GET /api/v1/projects/{date}/breakdown` | Time per project with auto-detection |
| `GET/POST /api/v1/tags` | Create/list activity tags |
| `GET /api/v1/tags/{date}` | Tags for a specific date |
| `DELETE /api/v1/tags/{id}` | Delete a tag |
| `GET /api/v1/compare?start1=&end1=&start2=&end2=` | Compare two date ranges side-by-side |
| `GET /api/v1/streaks` | Consecutive day streaks (productive, active, focus, early start) |
| `GET /api/v1/report-card/{date}` | Letter-grade report card (A-F) with GPA |
| `GET /api/v1/titles/{date}` | Extract ticket IDs, repos, files from window titles |
| `GET /api/v1/stream` | Server-Sent Events for live activity (real-time) |
| `GET /api/v1/stream/snapshot` | Current stream state for SSE client init |

```bash
# Quick examples
curl http://localhost:8099/api/v1/summary/today
curl http://localhost:8099/api/v1/productivity/2026-03-03
curl http://localhost:8099/api/v1/focus-sessions/2026-03-03
curl -X POST http://localhost:8099/api/v1/categories \
  -H 'Content-Type: application/json' \
  -d '{"process_name":"Code.exe","category":"development","is_productive":true}'
```

## Email Reports

Trackyr sends daily activity reports at 9 PM and weekly summaries every Sunday at 9 PM.

To enable, add Gmail app password credentials to `.env`:

```env
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-16-char-app-password
EMAIL_TO=your-email@gmail.com
```

Get an app password at https://myaccount.google.com/apppasswords (requires 2-Step Verification).

## OpenClaw Integration

Trackyr integrates with [OpenClaw](https://github.com/bse-ai/openclaw) (AI assistant platform) in three ways:

### 1. Skill — Natural Language Queries

Copy the skill into your OpenClaw skills directory:

```bash
cp -r skills/trackyr-activity/ /path/to/openclaw/skills/
```

OpenClaw auto-discovers the skill on next agent load. Then ask:

- *"What did I work on today?"*
- *"How productive was I this week?"*
- *"Any deep focus sessions today?"*
- *"Am I context switching too much?"*
- *"Generate my standup"*

The skill supports 34 query modes — see `skills/trackyr-activity/SKILL.md` for the full list.

### 2. Cron Automation — Proactive Insights

Pre-built cron templates in `skills/trackyr-activity/cron-templates/`:

| Template | Schedule | What it does |
|----------|----------|-------------|
| `hourly-productivity.json` | Every hour (9-6 weekdays) | Nudge if distracted, acknowledge focus |
| `morning-standup.json` | 9 AM weekdays | Auto-generate yesterday's standup |
| `break-reminder.json` | Every 30 min (9-6) | Alert after 90 min continuous activity |
| `daily-reflection.json` | 6 PM weekdays | End-of-day summary with suggestions |

Install with:

```bash
forge-orchestrator cron add --from-file skills/trackyr-activity/cron-templates/hourly-productivity.json
```

### 3. Webhooks — Push Events to OpenClaw

Enable webhook events to push real-time activity signals to OpenClaw:

```env
WEBHOOK_ENABLED=true
WEBHOOK_URL=http://127.0.0.1:18789/tools/invoke
```

Events: `focus_session_ended`, `long_idle_started`, `daily_summary_ready`, `goal_progress_update`, `overwork_alert`, `break_needed`, `anomaly_detected`

### Data Flow

```
User asks OpenClaw ──→ Agent runs trackyr-activity skill
                       ──→ Script queries Trackyr API (localhost:8099)
                       ──→ Structured data returned to conversation

Trackyr cron jobs   ──→ OpenClaw generates insights on schedule
                       ──→ Delivered via Slack/Discord/WhatsApp

Trackyr webhooks    ──→ Real-time events pushed to OpenClaw gateway
                       ──→ Agent acts on activity changes proactively
```

## Configuration

All settings via `.env` file (see `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://trackyr:trackyr@localhost:5434/trackyr` | PostgreSQL connection |
| `SAMPLE_INTERVAL` | `5` | Seconds between samples |
| `IDLE_THRESHOLD` | `300` | Seconds before marking as idle |
| `BUFFER_MAX_SIZE` | `1000` | Max buffered samples when DB is down |
| `LOG_LEVEL` | `INFO` | Logging level |
| `API_PORT` | `8099` | API server port |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP server |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` | | Gmail address |
| `SMTP_PASSWORD` | | Gmail app password |
| `EMAIL_TO` | | Report recipient |
| `DAILY_REPORT_HOUR` | `21` | Hour to send daily report (24h) |
| `WEEKLY_REPORT_DAY` | `sun` | Day to send weekly report |
| `WEEKLY_REPORT_HOUR` | `21` | Hour to send weekly report (24h) |
| `WEBHOOK_URL` | `http://127.0.0.1:18789/tools/invoke` | OpenClaw gateway URL |
| `WEBHOOK_ENABLED` | `false` | Enable webhook events |
| `DEVICE_ID` | `default` | Device identifier (multi-device) |

## Architecture

```
┌─────────────────────────────┐     ┌─────────────────────────────────┐
│  Host (Windows)             │     │  Docker (trackyr group)         │
│                             │     │                                 │
│  python -m trackyr          │     │  trackyr-db (PostgreSQL:5434)   │
│  ├─ Main: system tray       │────▶│                                 │
│  └─ Daemon: collector loop  │     │  trackyr-server (:8099)         │
│     (5s samples)            │     │  ├─ FastAPI API (46 endpoints)  │
│                             │     │  ├─ Intelligence engine         │
│                             │     │  └─ APScheduler (email jobs)    │
└─────────────────────────────┘     └──────────────┬──────────────────┘
                                                   │
                                    ┌──────────────┼──────────────┐
                                    ▼              ▼              ▼
                              OpenClaw Agent   Cron Jobs     Webhooks
                              (skill queries)  (proactive)   (push events)
```

## Database

PostgreSQL 16 with 12 tables:

| Table | Purpose |
|-------|---------|
| `activity_samples` | One row per 5-sec sample (source of truth) |
| `app_sessions` | Contiguous time on one app |
| `daily_summaries` | One row per app per day |
| `tracker_events` | System events (start/stop/error) |
| `app_categories` | User-defined app categorization |
| `goals` | Daily productivity goals |
| `focus_sessions` | Detected deep work periods |
| `daily_notes` | User/AI annotations per day |
| `baselines` | 30-day rolling metric averages for anomaly detection |
| `projects` | User-defined projects with JSON matching rules |
| `activity_tags` | Time-range tags from users, AI, or automation |
| `streaks` | Consecutive-day streak records |

## License

MIT
