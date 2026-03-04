"""Mouse click and keystroke counters using pynput.

Privacy: only counts events, never records which keys were pressed.
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass, field

from pynput import keyboard, mouse

log = logging.getLogger(__name__)


@dataclass
class InputSnapshot:
    mouse_clicks: int
    key_presses: int
    mouse_distance_px: float


class InputCollector:
    """Accumulates input events between flush() calls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mouse_clicks = 0
        self._key_presses = 0
        self._mouse_distance_px = 0.0
        self._last_mouse_x: float | None = None
        self._last_mouse_y: float | None = None
        self._mouse_listener: mouse.Listener | None = None
        self._keyboard_listener: keyboard.Listener | None = None

    def start(self) -> None:
        """Start listening for input events in background threads."""
        self._mouse_listener = mouse.Listener(
            on_click=self._on_click,
            on_move=self._on_move,
        )
        self._keyboard_listener = keyboard.Listener(on_press=self._on_key_press)
        self._mouse_listener.start()
        self._keyboard_listener.start()
        log.debug("Input listeners started")

    def stop(self) -> None:
        """Stop listening."""
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self._keyboard_listener:
            self._keyboard_listener.stop()
        log.debug("Input listeners stopped")

    def flush(self) -> InputSnapshot:
        """Return accumulated counts since last flush and reset."""
        with self._lock:
            snapshot = InputSnapshot(
                mouse_clicks=self._mouse_clicks,
                key_presses=self._key_presses,
                mouse_distance_px=self._mouse_distance_px,
            )
            self._mouse_clicks = 0
            self._key_presses = 0
            self._mouse_distance_px = 0.0
            self._last_mouse_x = None
            self._last_mouse_y = None
        return snapshot

    def _on_click(
        self, x: int, y: int, button: mouse.Button, pressed: bool
    ) -> None:
        if pressed:
            with self._lock:
                self._mouse_clicks += 1

    def _on_move(self, x: int, y: int) -> None:
        with self._lock:
            if self._last_mouse_x is not None:
                dx = x - self._last_mouse_x
                dy = y - self._last_mouse_y
                self._mouse_distance_px += math.hypot(dx, dy)
            self._last_mouse_x = x
            self._last_mouse_y = y

    def _on_key_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        with self._lock:
            self._key_presses += 1
