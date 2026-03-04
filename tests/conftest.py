"""Shared test fixtures."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Override DATABASE_URL for tests before importing trackyr modules
os.environ.setdefault("DATABASE_URL", "postgresql://trackyr:trackyr@localhost:5432/trackyr_test")

from trackyr.db.models import (
    ActivitySample,
    AppCategory,
    AppSession,
    Base,
    DailySummary,
    FocusSession,
    Goal,
    TrackerEvent,
)


@pytest.fixture(scope="session")
def db_engine():
    """Create test database engine and tables."""
    url = os.environ["DATABASE_URL"]
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a fresh database session, rolling back after each test."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def seed_activity(db_session):
    """Seed sample activity data for testing."""
    now = datetime.now(timezone.utc)
    today = now.date()

    # Create activity samples spanning 2 hours
    samples = []
    for i in range(120):  # 120 samples = 10 minutes at 5-sec intervals
        samples.append(ActivitySample(
            sampled_at=now - timedelta(seconds=(120 - i) * 5),
            process_name="Code.exe" if i < 80 else "chrome.exe",
            window_title="main.py - trackyr - Visual Studio Code" if i < 80 else "GitHub - Google Chrome",
            is_idle=i % 20 == 0,  # idle every 20th sample
            idle_seconds=5.0 if i % 20 == 0 else 0.0,
            mouse_clicks=2 if i % 3 == 0 else 0,
            key_presses=5 if i % 2 == 0 else 0,
            mouse_distance_px=100.0,
        ))
    db_session.add_all(samples)

    # Daily summaries
    db_session.add(DailySummary(
        date=today, process_name="Code.exe",
        total_seconds=14400, total_clicks=500, total_keys=2000, session_count=3,
    ))
    db_session.add(DailySummary(
        date=today, process_name="chrome.exe",
        total_seconds=3600, total_clicks=200, total_keys=100, session_count=5,
    ))

    # App sessions
    db_session.add(AppSession(
        process_name="Code.exe",
        window_title="main.py - trackyr - Visual Studio Code",
        started_at=now - timedelta(hours=2),
        ended_at=now - timedelta(minutes=30),
        duration_seconds=5400,
        sample_count=1080,
        total_clicks=300,
        total_keys=1500,
    ))
    db_session.add(AppSession(
        process_name="chrome.exe",
        window_title="GitHub - Google Chrome",
        started_at=now - timedelta(minutes=30),
        ended_at=now,
        duration_seconds=1800,
        sample_count=360,
        total_clicks=100,
        total_keys=50,
    ))

    # Categories
    db_session.add(AppCategory(process_name="Code.exe", category="development", is_productive=True))
    db_session.add(AppCategory(process_name="chrome.exe", category="browsing", is_productive=False))

    db_session.commit()
    return {"today": today, "now": now}
