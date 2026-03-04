from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Config:
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql://trackyr:trackyr@localhost:5433/trackyr"
    )
    sample_interval: int = int(os.getenv("SAMPLE_INTERVAL", "5"))
    idle_threshold: int = int(os.getenv("IDLE_THRESHOLD", "300"))
    buffer_max_size: int = int(os.getenv("BUFFER_MAX_SIZE", "1000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Email (Gmail SMTP)
    smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")
    email_to: str = os.getenv("EMAIL_TO", "")

    # API server
    api_port: int = int(os.getenv("API_PORT", "8099"))

    # Scheduler
    daily_report_hour: int = int(os.getenv("DAILY_REPORT_HOUR", "21"))
    weekly_report_day: str = os.getenv("WEEKLY_REPORT_DAY", "sun")
    weekly_report_hour: int = int(os.getenv("WEEKLY_REPORT_HOUR", "21"))

    # Webhooks (OpenClaw integration)
    webhook_url: str = os.getenv("WEBHOOK_URL", "http://127.0.0.1:18789/tools/invoke")
    webhook_enabled: bool = os.getenv("WEBHOOK_ENABLED", "false").lower() in ("true", "1", "yes")

    # Device
    device_id: str = os.getenv("DEVICE_ID", "default")


cfg = Config()
