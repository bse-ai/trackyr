# Trackyr

Personal Windows desktop activity tracker. Logs mouse clicks, keyboard activity, active/idle state, foreground app, and window titles to PostgreSQL.

## Features

- **5-second sampling** of foreground window, idle state, mouse clicks, and keystroke counts
- **System tray** icon with color-coded status (green=active, yellow=idle, red=DB error)
- **REST API** for querying activity data (today, by date, last N hours, weekly, current app)
- **Email reports** — daily and weekly HTML summaries via Gmail
- **[OpenClaw](https://github.com/bse-ai/openclaw) integration** — AI assistant skill for natural language activity queries
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

The API server runs on `http://localhost:8099` inside the `trackyr-server` container.

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/summary/today` | Today's activity breakdown |
| `GET /api/v1/summary/{date}` | Specific date (YYYY-MM-DD) |
| `GET /api/v1/summary/hours/{n}` | Last N hours (1-72) |
| `GET /api/v1/weekly` | Last 7 days with day-by-day + top apps |
| `GET /api/v1/current` | Currently active app and window |

```bash
curl http://localhost:8099/api/v1/summary/today
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

Times are configurable via `DAILY_REPORT_HOUR`, `WEEKLY_REPORT_DAY`, `WEEKLY_REPORT_HOUR`.

## OpenClaw Integration

Trackyr includes an [OpenClaw](https://github.com/bse-ai/openclaw) skill that lets your AI assistant query activity data using natural language.

### Setup

Copy the skill into your OpenClaw skills directory:

```bash
cp -r skills/trackyr-activity/ /path/to/openclaw/skills/
```

OpenClaw auto-discovers the skill on next agent load. Then ask:

- *"What did I work on today?"*
- *"How long was I in VS Code this week?"*
- *"What am I doing right now?"*
- *"Show my last 2 hours of activity"*

### Automation

Trackyr's API can drive OpenClaw automations:

- **Cron jobs** can query the API to generate productivity insights on a schedule
- **Pattern detection** — trigger notifications when idle too long, or surface focus time stats
- **Workflow suggestions** — feed app usage data into OpenClaw to suggest task automation based on repetitive patterns

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

## Architecture

```
┌─────────────────────────────┐     ┌─────────────────────────────────┐
│  Host (Windows)             │     │  Docker (trackyr group)         │
│                             │     │                                 │
│  python -m trackyr          │     │  trackyr-db (PostgreSQL:5434)   │
│  ├─ Main: system tray       │────▶│                                 │
│  └─ Daemon: collector loop  │     │  trackyr-server (:8099)         │
│     (5s samples)            │     │  ├─ FastAPI API                 │
│                             │     │  └─ APScheduler (email jobs)    │
└─────────────────────────────┘     └─────────────────────────────────┘
                                                   │
                                    ┌──────────────┘
                                    ▼
                              OpenClaw Agent
                              "What did I work on today?"
```

## License

MIT
