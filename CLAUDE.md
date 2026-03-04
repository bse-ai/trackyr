# Trackyr

Personal Windows desktop activity tracker. Logs mouse clicks, keyboard activity, active/idle state, foreground app, and window titles to PostgreSQL in Docker.

## Quick Start

```bash
docker compose up -d          # Start PostgreSQL on port 5433
pip install -r requirements.txt
alembic upgrade head          # Run migrations
python -m trackyr             # Start tracker (system tray app)
```

## Architecture

Single Python process, two threads:
- **Main thread**: pystray system tray icon (message loop)
- **Daemon thread**: collector loop sampling every 5 seconds

## Key Directories

- `trackyr/collectors/` — window.py (ctypes Win32), idle.py (GetLastInputInfo), input.py (pynput counters)
- `trackyr/db/` — models.py (SQLAlchemy ORM), engine.py, writer.py (batched writer with deque buffer)
- `trackyr/tray.py` — system tray with green/yellow/red/gray circle icons
- `trackyr/app.py` — orchestrator tying it all together

## Database

PostgreSQL 16 on port 5433 (avoids conflicts). Four tables:
- `activity_samples` — one row per 5-sec sample (source of truth)
- `app_sessions` — contiguous time on one app
- `daily_summaries` — one row per app per day
- `tracker_events` — system events (start/stop/pause/error)

## Privacy

Keystroke COUNT only, never which keys. No screenshots, no network traffic.

## Resilience

- `BatchWriter` uses `deque(maxlen=1000)` to buffer when DB is down (~83 min)
- `pool_pre_ping=True` handles reconnect after sleep/hibernate
- Tray icon turns red on DB errors, auto-recovers when connection returns

## Config

All via `.env` file (see `.env.example`):
- `DATABASE_URL`, `SAMPLE_INTERVAL`, `IDLE_THRESHOLD`, `BUFFER_MAX_SIZE`, `LOG_LEVEL`

## Future: OpenClaw Integration

Phase 2: FastAPI server exposing `/api/v1/summary/today`, `/api/v1/current`, `/api/v1/timeline` for ClawdBot tool integration at `C:\projects\clawdbot`.
