"""Webhook emitter for pushing events to OpenClaw gateway."""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from trackyr.config import cfg

log = logging.getLogger(__name__)


class WebhookEmitter:
    """Best-effort event poster to OpenClaw gateway.

    Posts to the OpenClaw /tools/invoke endpoint to trigger agent actions.
    Runs in background threads to avoid blocking the caller.
    """

    def __init__(self) -> None:
        self._url = cfg.webhook_url
        self._enabled = cfg.webhook_enabled
        self._max_retries = 2
        self._timeout = 10

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """Fire-and-forget event emission. Runs in a background thread."""
        if not self._enabled:
            return
        thread = threading.Thread(
            target=self._post,
            args=(event_type, data or {}),
            daemon=True,
            name=f"webhook-{event_type}",
        )
        thread.start()

    def _post(self, event_type: str, data: dict[str, Any]) -> None:
        """POST event to OpenClaw gateway with retry."""
        payload = {
            "tool": "sessions_send",
            "action": "json",
            "args": {
                "target": "main",
                "message": json.dumps({
                    "source": "trackyr",
                    "event": event_type,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "device_id": cfg.device_id,
                    "data": data,
                }),
            },
        }
        body = json.dumps(payload).encode("utf-8")

        for attempt in range(self._max_retries + 1):
            try:
                req = urllib.request.Request(
                    self._url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    if resp.status < 300:
                        log.debug("Webhook %s sent successfully", event_type)
                        return
            except (urllib.error.URLError, OSError) as exc:
                if attempt < self._max_retries:
                    log.debug("Webhook %s attempt %d failed: %s", event_type, attempt + 1, exc)
                else:
                    log.debug("Webhook %s failed after %d attempts", event_type, self._max_retries + 1)


# Module-level singleton
_emitter: WebhookEmitter | None = None


def get_emitter() -> WebhookEmitter:
    """Get or create the singleton WebhookEmitter."""
    global _emitter
    if _emitter is None:
        _emitter = WebhookEmitter()
    return _emitter


def emit_event(event_type: str, data: dict[str, Any] | None = None) -> None:
    """Convenience function to emit a webhook event."""
    get_emitter().emit(event_type, data)


def emit_focus_session_ended(session_data: dict) -> None:
    """Emit when a focus session ends."""
    emit_event("focus_session_ended", session_data)


def emit_goal_progress(goal_data: dict) -> None:
    """Emit when goal progress updates."""
    emit_event("goal_progress_update", goal_data)


def emit_overwork_alert(hours_active: float) -> None:
    """Emit when user has been working too long."""
    emit_event("overwork_detected", {"hours_active": hours_active})


def emit_break_needed(minutes_since_break: float) -> None:
    """Emit when user needs a break."""
    emit_event("break_needed", {"minutes_since_break": minutes_since_break})


def emit_anomaly(anomaly_data: dict) -> None:
    """Emit when an anomaly is detected."""
    emit_event("anomaly_detected", anomaly_data)
