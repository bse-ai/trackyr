"""Main orchestrator: tray on main thread, collector on daemon thread.

API server + scheduler run in the trackyr-server Docker container.
"""

from __future__ import annotations

import logging
import threading
import time

from trackyr.collectors.idle import get_idle_seconds
from trackyr.collectors.input import InputCollector
from trackyr.collectors.window import get_foreground_window
from trackyr.config import cfg
from trackyr.db.writer import BatchWriter
from trackyr.tray import TrayApp

log = logging.getLogger(__name__)


class Trackyr:
    def __init__(self) -> None:
        self._writer = BatchWriter()
        self._input = InputCollector()
        self._paused = threading.Event()  # clear = not paused
        self._stop = threading.Event()
        self._tray = TrayApp(
            on_pause=self._on_pause,
            on_resume=self._on_resume,
            on_quit=self._on_quit,
        )

    def run(self) -> None:
        """Start the collector daemon thread, then run the tray on main."""
        logging.basicConfig(
            level=getattr(logging, cfg.log_level, logging.INFO),
            format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        log.info("Trackyr starting (interval=%ds)", cfg.sample_interval)

        self._input.start()
        self._writer.log_event("start")

        collector_thread = threading.Thread(
            target=self._collector_loop, daemon=True, name="collector"
        )
        collector_thread.start()

        # Main thread: tray message loop (blocks until quit)
        self._tray.run()

        # Cleanup after tray exits
        self._stop.set()
        self._input.stop()
        self._writer.log_event("stop")
        log.info("Trackyr stopped")

    def _collector_loop(self) -> None:
        """Sample every SAMPLE_INTERVAL seconds."""
        while not self._stop.is_set():
            if not self._paused.is_set():
                try:
                    self._collect_sample()
                except Exception:
                    log.exception("Error in collector loop")

            self._stop.wait(timeout=cfg.sample_interval)

    def _collect_sample(self) -> None:
        """Take one sample: window + idle + input counters."""
        window = get_foreground_window()
        idle_secs = get_idle_seconds()
        is_idle = idle_secs >= cfg.idle_threshold
        input_snap = self._input.flush()

        self._writer.add_sample(window, idle_secs, is_idle, input_snap)

        # Update tray icon based on state
        if not self._writer.db_healthy:
            self._tray.set_error()
        elif is_idle:
            self._tray.set_idle()
        else:
            self._tray.set_active()

        log.debug(
            "%s | %s | idle=%.0fs | clicks=%d keys=%d",
            window.process_name,
            window.title[:50] if window.title else "",
            idle_secs,
            input_snap.mouse_clicks,
            input_snap.key_presses,
        )

    def _on_pause(self) -> None:
        self._paused.set()
        self._writer.log_event("pause")

    def _on_resume(self) -> None:
        self._paused.clear()
        self._writer.log_event("resume")

    def _on_quit(self) -> None:
        self._stop.set()
        self._input.stop()
        self._writer.log_event("stop")
