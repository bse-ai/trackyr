"""Foreground window info via ctypes Win32 API."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
from dataclasses import dataclass

import psutil

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Win32 constants
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


@dataclass
class WindowInfo:
    title: str
    process_name: str
    pid: int


def get_foreground_window() -> WindowInfo:
    """Return info about the currently focused window."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return WindowInfo(title="", process_name="unknown", pid=0)

    # Window title
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    title = buf.value

    # Process ID
    pid = ctypes.wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    pid_val = pid.value

    # Process name via psutil (handles permission errors gracefully)
    process_name = "unknown"
    try:
        proc = psutil.Process(pid_val)
        process_name = proc.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        # Elevated/UAC windows — fall back
        process_name = _get_process_name_ctypes(pid_val)

    return WindowInfo(title=title, process_name=process_name, pid=pid_val)


def _get_process_name_ctypes(pid: int) -> str:
    """Fallback: get process image name via kernel32."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return "unknown"
    try:
        buf = ctypes.create_unicode_buffer(260)
        size = ctypes.wintypes.DWORD(260)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
        if ok:
            # Return just the filename
            return buf.value.rsplit("\\", 1)[-1]
        return "unknown"
    finally:
        kernel32.CloseHandle(handle)
