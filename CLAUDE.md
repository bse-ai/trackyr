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
- **Docker container** (`trackyr-server`): FastAPI API server + APScheduler email jobs

## Key Directories

- `trackyr/collectors/` — window.py (ctypes Win32), idle.py (GetLastInputInfo), input.py (pynput counters)
- `trackyr/db/` — models.py (SQLAlchemy ORM), engine.py, writer.py (batched writer with deque buffer)
- `trackyr/tray.py` — system tray with green/yellow/red/gray circle icons
- `trackyr/app.py` — orchestrator tying collector + tray together
- `trackyr/api.py` — FastAPI endpoints for activity queries
- `trackyr/reports.py` — daily/weekly/hourly report generation + HTML rendering
- `trackyr/email_send.py` — Gmail SMTP sender
- `trackyr/scheduler.py` — APScheduler cron jobs for email reports
- `trackyr/server.py` — Docker container entrypoint (API + scheduler)

## Database

PostgreSQL 16 on port 5434 in dedicated `trackyr-db` container. Four tables:
- `activity_samples` — one row per 5-sec sample (source of truth)
- `app_sessions` — contiguous time on one app
- `daily_summaries` — one row per app per day
- `tracker_events` — system events (start/stop/pause/error)

## API Endpoints

Running on port 8099 via `trackyr-server` container:
- `GET /api/v1/summary/today` — today's activity breakdown
- `GET /api/v1/summary/{date}` — specific date (YYYY-MM-DD)
- `GET /api/v1/summary/hours/{n}` — last N hours (1-72)
- `GET /api/v1/weekly` — last 7 days summary
- `GET /api/v1/current` — currently active app

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

## OpenClaw Integration

Trackyr connects to [OpenClaw](https://github.com/bse-ai/openclaw) (AI assistant platform) via the `trackyr-activity` skill:

- **Skill location**: Install to OpenClaw skills directory (see `skills/trackyr-activity/`)
- **How it works**: OpenClaw's agent autonomously invokes the skill when users ask about activity, productivity, or time spent
- **Data flow**: User asks OpenClaw → agent triggers skill → skill queries Trackyr API → structured activity data returned to conversation
- **Automation feed**: Trackyr data can drive OpenClaw automations — cron jobs can query the API to generate productivity insights, detect patterns (e.g., "you've been idle for 2 hours"), or trigger workflow suggestions based on app usage
- **Queries supported**: "What did I work on today?", "How long was I in VS Code?", "Show my weekly breakdown", "What am I doing right now?"

### Setting up the skill

```bash
# Copy skill to OpenClaw skills directory
cp -r skills/trackyr-activity/ /path/to/openclaw/skills/

# Ensure Trackyr containers are running
docker compose up -d

# OpenClaw will auto-discover the skill on next agent load
```
