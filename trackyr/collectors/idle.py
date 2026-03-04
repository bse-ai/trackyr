"""Idle detection via GetLastInputInfo."""

from __future__ import annotations

import ctypes
import ctypes.wintypes


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.wintypes.UINT),
        ("dwTime", ctypes.wintypes.DWORD),
    ]


def get_idle_seconds() -> float:
    """Return seconds since last keyboard/mouse input."""
    lii = LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
    ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii))
    tick_count = ctypes.windll.kernel32.GetTickCount64()
    idle_ms = tick_count - lii.dwTime
    return idle_ms / 1000.0
