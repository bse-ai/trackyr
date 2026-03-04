# Trackyr

Personal Windows desktop activity tracker. Logs mouse clicks, keyboard activity, active/idle state, foreground app, and window titles to PostgreSQL in Docker.

## Quick Start

```bash
docker compose up -d            # Start PostgreSQL + API server
pip install -r requirements.txt
alembic upgrade head            # Run migrations
python -m trackyr               # Start tracker (system tray app)
```

## Architecture

Two components:
- **Host process** (`python -m trackyr`): pystray system tray + collector daemon thread sampling every 5 seconds
- **Docker container** (`trackyr-server`): FastAPI API server + intelligence engine + APScheduler email jobs

## Key Directories

- `trackyr/collectors/` — window.py (ctypes Win32), idle.py (GetLastInputInfo), input.py (pynput counters)
- `trackyr/db/` — models.py (SQLAlchemy ORM), engine.py, writer.py (batched writer with deque buffer)
- `trackyr/tray.py` — system tray with green/yellow/red/gray circle icons
- `trackyr/app.py` — orchestrator tying collector + tray together
- `trackyr/api.py` — FastAPI endpoints (67 routes) for activity queries, intelligence, projects, tags, Pomodoro, limits, SSE streaming
- `trackyr/intelligence.py` — 25 functions: focus sessions, context switching, productivity, trends, idle patterns, heatmaps, workday detection, narratives, anomalies, engagement curves, baselines, project detection, comparison, streaks, report cards, title metadata, highlights, momentum, switch cost, monthly rollups, session classification, weekly digests
- `trackyr/projects.py` — project detection with configurable rules + built-in heuristics
- `trackyr/streaming.py` — Server-Sent Events for real-time activity streaming
- `trackyr/pomodoro.py` — Pomodoro timer state machine (start/pause/resume/skip/stop/interrupt)
- `trackyr/reports.py` — daily/weekly/hourly report generation + HTML rendering
- `trackyr/email_send.py` — Gmail SMTP sender
- `trackyr/webhooks.py` — push events to OpenClaw gateway
- `trackyr/scheduler.py` — APScheduler cron jobs for email reports
- `trackyr/server.py` — Docker container entrypoint (API + scheduler)

## Database

PostgreSQL 16 on port 5434 in dedicated `trackyr-db` container. Sixteen tables:
- `activity_samples` — one row per 5-sec sample (source of truth), includes device_id
- `app_sessions` — contiguous time on one app
- `daily_summaries` — one row per app per day
- `tracker_events` — system events (start/stop/pause/error)
- `app_categories` — user-defined app categorization (process_name → category + is_productive)
- `goals` — daily productivity goals (min_time, max_time, min_productive_pct)
- `focus_sessions` — detected deep work periods with quality scores
- `daily_notes` — user/AI annotations per day (text + source tag)
- `baselines` — 30-day rolling metric averages (nightly computed at 3 AM)
- `projects` — user-defined projects with JSON matching rules (process, title_contains, title_regex)
- `activity_tags` — time-range tags from users, AI, or automation
- `streaks` — consecutive-day streak records (productive, active, focus, early_start)
- `pomodoro_timers` — active Pomodoro timer state (status, phase timing, counts)
- `pomodoro_records` — completed Pomodoro phases (work/break history)
- `app_limits` — per-app daily time budgets with warning thresholds
- `limit_alerts` — fired limit alerts (warn/exceeded)

## API Endpoints

Running on port 8099 via `trackyr-server` container:

### Core
- `GET /api/v1/summary/today` — today's activity breakdown
- `GET /api/v1/summary/{date}` — specific date (YYYY-MM-DD)
- `GET /api/v1/summary/hours/{n}` — last N hours (1-72)
- `GET /api/v1/weekly` — last 7 days summary
- `GET /api/v1/current` — currently active app

### Intelligence
- `GET /api/v1/focus-sessions/{date}` — detected deep work sessions
- `GET /api/v1/context-switches/{date}` — app switching frequency
- `GET /api/v1/context-switches/{date}/patterns` — switching bursts, triggers, calm periods
- `GET /api/v1/productivity/{date}` — productivity score by app category
- `GET /api/v1/trends?days=7` — compare to previous period
- `GET /api/v1/timeline/{date}?app=&category=` — granular timeline with filtering
- `GET /api/v1/heatmap/{date}` — hourly activity heatmap
- `GET /api/v1/heatmap/week` — 7-day heatmap grid
- `GET /api/v1/workday/{date}` — detected work start/end, core hours
- `GET /api/v1/narrative/{date}` — natural language daily narrative
- `GET /api/v1/anomalies/{date}` — anomalies vs 30-day baseline
- `GET /api/v1/engagement/{date}` — per-hour engagement score (0-100)
- `GET /api/v1/baselines` — current 30-day rolling baselines
- `GET /api/v1/context` — compact AI-ready context snapshot
- `GET /api/v1/standup` — yesterday's standup summary
- `GET /api/v1/search?q=term` — search by window title or process name
- `GET /api/v1/health` — system health check

### Configuration & Data
- `GET/POST /api/v1/categories` — app category management
- `GET/POST /api/v1/goals` — goal CRUD
- `GET /api/v1/goals/progress` — real-time goal progress
- `GET/POST /api/v1/notes/{date}` — daily notes CRUD
- `POST /api/v1/focus/start` — manually start focus session
- `POST /api/v1/focus/stop` — manually stop focus session
- `GET /api/v1/focus/active` — check active focus session
- `GET /api/v1/export/samples?start=&end=&format=` — export raw samples (CSV/JSON)
- `GET /api/v1/export/sessions?start=&end=&format=` — export app sessions (CSV/JSON)

### Projects, Tags & Gamification
- `GET/POST /api/v1/projects` — project management (rules-based activity mapping)
- `GET /api/v1/projects/{date}/breakdown` — time per project
- `GET/POST /api/v1/tags`, `GET /api/v1/tags/{date}`, `DELETE /api/v1/tags/{id}` — activity tags
- `GET /api/v1/compare?start1=&end1=&start2=&end2=` — period comparison
- `GET /api/v1/streaks` — consecutive day streaks
- `GET /api/v1/report-card/{date}` — letter-grade report card with GPA
- `GET /api/v1/titles/{date}` — ticket IDs, repos, files from window titles
- `GET /api/v1/stream` — Server-Sent Events for real-time activity
- `GET /api/v1/stream/snapshot` — SSE client init snapshot

### Intelligence & Analytics
- `GET /api/v1/highlight/today`, `GET /api/v1/highlight/{date}` — AI-ready daily highlight packet
- `GET /api/v1/momentum` — 4-week productivity momentum score
- `GET /api/v1/context-switches/{date}/cost` — context switch time cost estimate
- `GET /api/v1/monthly/current`, `GET /api/v1/monthly/{year}/{month}` — monthly rollup
- `GET /api/v1/sessions/{date}/classified` — session type classification
- `GET /api/v1/weekly/digest` — narrative weekly digest with insights

### Pomodoro Timer
- `POST /api/v1/pomodoro/start|pause|resume|skip|stop|interrupt` — timer control
- `GET /api/v1/pomodoro/status` — current state
- `GET /api/v1/pomodoro/today`, `GET /api/v1/pomodoro/history/{date}` — history

### App Time Limits
- `GET/POST /api/v1/limits`, `DELETE /api/v1/limits/{id}` — limit management
- `GET /api/v1/limits/alerts/today` — fired alerts

## Email Reports

Daily report at 9 PM, weekly report Sunday 9 PM. Requires Gmail app password in `.env`.

## Privacy

Keystroke COUNT only, never which keys. No screenshots, no network traffic.

## Resilience

- `BatchWriter` uses `deque(maxlen=1000)` to buffer when DB is down (~83 min)
- `pool_pre_ping=True` handles reconnect after sleep/hibernate
- Tray icon turns red on DB errors, auto-recovers when connection returns

## Config

All via `.env` file (see `.env.example`):
- `DATABASE_URL`, `SAMPLE_INTERVAL`, `IDLE_THRESHOLD`, `BUFFER_MAX_SIZE`, `LOG_LEVEL`
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_TO`
- `API_PORT`, `DAILY_REPORT_HOUR`, `WEEKLY_REPORT_DAY`, `WEEKLY_REPORT_HOUR`
- `WEBHOOK_URL`, `WEBHOOK_ENABLED`, `DEVICE_ID`

## Testing

```bash
pip install pytest ruff
ruff check trackyr/ tests/
pytest tests/ -v
```

CI runs on GitHub Actions (lint + test with PostgreSQL service container).

## OpenClaw Integration

Trackyr connects to [OpenClaw](https://github.com/bse-ai/openclaw) (AI assistant platform) via three mechanisms:

### 1. Skill (query)
- **Location**: `skills/trackyr-activity/` — copy to OpenClaw skills directory
- **43 modes**: today, date, hours, weekly, current, timeline, focus, productivity, context-switches, trends, context, standup, goals, categories, search, health, heatmap, heatmap-week, workday, narrative, switch-patterns, anomalies, engagement, baselines, notes, export, projects, project-breakdown, tags, compare, streaks, report-card, titles, stream-snapshot, highlight, momentum, switch-cost, monthly, sessions, digest, pomodoro-status, pomodoro-today, limits
- **Data flow**: User asks OpenClaw → agent triggers skill → script queries Trackyr API → structured data returned

### 2. Cron Templates (proactive)
- **Location**: `skills/trackyr-activity/cron-templates/`
- **Templates**: hourly productivity check, morning standup, break reminder, daily reflection
- **Install**: `forge-orchestrator cron add --from-file cron-templates/hourly-productivity.json`

### 3. Webhooks (push)
- **Module**: `trackyr/webhooks.py` — fires events to OpenClaw gateway
- **Events**: focus_session_ended, long_idle_started, daily_summary_ready, goal_progress_update
- **Config**: `WEBHOOK_ENABLED=true` + `WEBHOOK_URL` in `.env`

### Setting up the skill

```bash
cp -r skills/trackyr-activity/ /path/to/openclaw/skills/
docker compose up -d
# OpenClaw will auto-discover the skill on next agent load
```
