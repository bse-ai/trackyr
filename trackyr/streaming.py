"""Real-time Server-Sent Events (SSE) streaming for live activity data."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from sqlalchemy import desc

from trackyr.db.engine import get_session
from trackyr.db.models import ActivitySample

log = logging.getLogger(__name__)

# In-memory state for connected clients
_last_sample_id: int = 0


async def activity_stream(interval: float = 5.0) -> AsyncGenerator[str, None]:
    """Yield SSE events with the latest activity sample every `interval` seconds.

    SSE format: data: {json}\n\n
    Event types:
    - "sample": new activity sample
    - "heartbeat": keepalive every 30s if no new data
    """
    global _last_sample_id
    heartbeat_counter = 0

    # Get initial last sample ID
    try:
        session = get_session()
        try:
            row = session.query(ActivitySample.id).order_by(desc(ActivitySample.id)).first()
            if row:
                _last_sample_id = row[0]
        finally:
            session.close()
    except Exception:
        pass

    while True:
        try:
            session = get_session()
            try:
                # Query for new samples since last check
                new_samples = (
                    session.query(ActivitySample)
                    .filter(ActivitySample.id > _last_sample_id)
                    .order_by(ActivitySample.id)
                    .limit(20)
                    .all()
                )

                if new_samples:
                    for sample in new_samples:
                        _last_sample_id = sample.id
                        data = {
                            "event": "sample",
                            "id": sample.id,
                            "sampled_at": sample.sampled_at.isoformat() if sample.sampled_at else None,
                            "process_name": sample.process_name,
                            "window_title": sample.window_title,
                            "is_idle": sample.is_idle,
                            "mouse_clicks": sample.mouse_clicks,
                            "key_presses": sample.key_presses,
                        }
                        yield f"event: sample\ndata: {json.dumps(data)}\n\n"
                    heartbeat_counter = 0
                else:
                    heartbeat_counter += 1
                    # Send heartbeat every ~30s (6 intervals of 5s)
                    if heartbeat_counter >= 6:
                        yield f"event: heartbeat\ndata: {json.dumps({'ts': datetime.now(timezone.utc).isoformat()})}\n\n"
                        heartbeat_counter = 0
            finally:
                session.close()
        except Exception as exc:
            log.warning("SSE stream error: %s", exc)
            yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"

        await asyncio.sleep(interval)


def format_sse_summary() -> dict:
    """Get a snapshot suitable for initializing an SSE client."""
    try:
        session = get_session()
        try:
            latest = (
                session.query(ActivitySample)
                .order_by(desc(ActivitySample.sampled_at))
                .first()
            )
            if not latest:
                return {"status": "no_data"}
            return {
                "status": "ok",
                "latest_sample": {
                    "id": latest.id,
                    "sampled_at": latest.sampled_at.isoformat() if latest.sampled_at else None,
                    "process_name": latest.process_name,
                    "window_title": latest.window_title,
                    "is_idle": latest.is_idle,
                },
            }
        finally:
            session.close()
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
