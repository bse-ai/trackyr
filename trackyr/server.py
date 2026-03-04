"""Standalone server entrypoint: API + scheduler (no Win32 desktop deps).

Used inside Docker container. The collector (tray app) runs separately on the host.
"""

from __future__ import annotations

import logging
import signal
import sys

import uvicorn

from trackyr.api import app
from trackyr.config import cfg
from trackyr.scheduler import start_scheduler

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, cfg.log_level, logging.INFO),
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    log.info("Trackyr server starting (API + scheduler)")

    # Start scheduler in background thread
    scheduler = start_scheduler()

    # Handle graceful shutdown
    def shutdown(signum, frame):
        log.info("Shutting down...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Run API server in foreground (blocks)
    uvicorn.run(app, host="0.0.0.0", port=cfg.api_port, log_level="info")


if __name__ == "__main__":
    main()
