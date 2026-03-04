"""System tray icon with status indicator and menu."""

from __future__ import annotations

import logging
from typing import Callable

from PIL import Image, ImageDraw
from pystray import Icon, Menu, MenuItem

log = logging.getLogger(__name__)

# Icon size
_SIZE = 64


def _make_circle_icon(color: str) -> Image.Image:
    """Create a solid circle icon of the given color."""
    img = Image.new("RGBA", (_SIZE, _SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = 4
    draw.ellipse([margin, margin, _SIZE - margin, _SIZE - margin], fill=color)
    return img


# Pre-render the three state icons
ICON_ACTIVE = _make_circle_icon("#22c55e")   # green
ICON_IDLE = _make_circle_icon("#eab308")     # yellow
ICON_ERROR = _make_circle_icon("#ef4444")    # red
ICON_PAUSED = _make_circle_icon("#6b7280")   # gray


class TrayApp:
    """pystray wrapper with pause/resume/quit controls."""

    def __init__(
        self,
        on_pause: Callable[[], None],
        on_resume: Callable[[], None],
        on_quit: Callable[[], None],
    ) -> None:
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_quit = on_quit
        self._paused = False

        self._icon = Icon(
            name="Trackyr",
            icon=ICON_ACTIVE,
            title="Trackyr — Active",
            menu=Menu(
                MenuItem("Pause", self._toggle_pause, default=False),
                MenuItem("Quit", self._quit),
            ),
        )

    def run(self) -> None:
        """Run the tray icon (blocks on main thread)."""
        log.info("System tray started")
        self._icon.run()

    def stop(self) -> None:
        """Programmatically stop the tray."""
        self._icon.stop()

    def set_active(self) -> None:
        if not self._paused:
            self._icon.icon = ICON_ACTIVE
            self._icon.title = "Trackyr — Active"

    def set_idle(self) -> None:
        if not self._paused:
            self._icon.icon = ICON_IDLE
            self._icon.title = "Trackyr — Idle"

    def set_error(self) -> None:
        self._icon.icon = ICON_ERROR
        self._icon.title = "Trackyr — DB Error"

    def _toggle_pause(self, icon: Icon, item: MenuItem) -> None:
        if self._paused:
            self._paused = False
            self._on_resume()
            self._icon.icon = ICON_ACTIVE
            self._icon.title = "Trackyr — Active"
            log.info("Resumed")
        else:
            self._paused = True
            self._on_pause()
            self._icon.icon = ICON_PAUSED
            self._icon.title = "Trackyr — Paused"
            log.info("Paused")

    def _quit(self, icon: Icon, item: MenuItem) -> None:
        log.info("Quit requested from tray")
        self._on_quit()
        icon.stop()
