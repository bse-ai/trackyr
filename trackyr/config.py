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


cfg = Config()
