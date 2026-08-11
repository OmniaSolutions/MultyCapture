"""Linux backend (X11) with Wayland detection.

X11 exposes the active window and its geometry via EWMH, and permits the global
input hooks the recorder relies on. Wayland deliberately blocks both, so under a
Wayland session we fail fast with an actionable message rather than capturing
broken data.

Requires ``python-xlib`` and ``ewmh`` (installed only on Linux via environment
markers in requirements).
"""

from __future__ import annotations

import os
from typing import Optional

from ..model import MonitorInfo, Rect, WindowInfo
from .base import PlatformBackend, PlatformError


def make_linux_backend() -> PlatformBackend:
    """Construct the X11 backend, or raise if the session is unsupported."""
    session = (os.environ.get("XDG_SESSION_TYPE") or "").lower()
    if session == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
        raise PlatformError(
            "MultyCapture cannot capture under a Wayland session: Wayland blocks "
            "global input hooks and cross-window geometry reads for security.\n"
            "Log out and choose an 'Xorg' / 'X11' session at the login screen "
            "(the gear icon), then try again."
        )
    if not os.environ.get("DISPLAY"):
        raise PlatformError(
            "No X11 DISPLAY found. MultyCapture needs a running X11 session."
        )
    return LinuxX11Backend()


class LinuxX11Backend(PlatformBackend):
    name = "linux"

    def __init__(self) -> None:
        try:
            from Xlib import display as xdisplay
            from ewmh import EWMH
        except ImportError as exc:  # pragma: no cover - dep presence is env-specific
            raise PlatformError(
                "Linux capture needs 'python-xlib' and 'ewmh'. Install with:\n"
                "    pip install python-xlib ewmh"
            ) from exc
        self._display = xdisplay.Display()
        self._root = self._display.screen().root
        self._ewmh = EWMH(self._display, self._root)

    def set_high_dpi_awareness(self) -> None:
        # X11 apps are generally rendered at 1x with a global scale; nothing to
        # opt into per-process. Scale is reported per-monitor in enumerate_monitors.
        return None

    # ------------------------------------------------------------------ #
    # Monitors (via RandR through Xlib)
    # ------------------------------------------------------------------ #
    def enumerate_monitors(self) -> list[MonitorInfo]:
        monitors: list[MonitorInfo] = []
        try:
            res = self._root.xrandr_get_monitors()
            for i, mon in enumerate(res.monitors):
                monitors.append(MonitorInfo(
                    index=i,
                    x=mon.x, y=mon.y,
                    width=mon.width_in_pixels, height=mon.height_in_pixels,
                    primary=bool(mon.primary),
                    scale=1.0,
                ))
        except Exception:
            # Fall back to the single root geometry if RandR is unavailable.
            geo = self._root.get_geometry()
            monitors.append(MonitorInfo(0, 0, 0, geo.width, geo.height, True, 1.0))

        monitors.sort(key=lambda m: (not m.primary, m.x, m.y))
        for i, m in enumerate(monitors):
            m.index = i
        return monitors

    # ------------------------------------------------------------------ #
    # Active window
    # ------------------------------------------------------------------ #
    def get_active_window(self) -> Optional[WindowInfo]:
        try:
            win = self._ewmh.getActiveWindow()
        except Exception:
            win = None
        if win is None:
            return None

        title = self._title(win)
        rect = self._abs_rect(win)
        if rect is None:
            return None
        pid = self._pid(win)
        process = self._process_name(pid) if pid else ""
        return WindowInfo(title=title, process=process, pid=pid or 0, rect=rect)

    def _title(self, win) -> str:
        try:
            name = self._ewmh.getWmName(win)
            if isinstance(name, bytes):
                name = name.decode("utf-8", "replace")
            if name:
                return name
        except Exception:
            pass
        try:
            wm = win.get_wm_name()
            return wm or ""
        except Exception:
            return ""

    def _abs_rect(self, win) -> Optional[Rect]:
        try:
            geo = win.get_geometry()
            # Translate window-local origin to absolute root coordinates.
            trans = win.translate_coords(self._root, 0, 0)
            abs_x = -trans.x
            abs_y = -trans.y
            return Rect(abs_x, abs_y, geo.width, geo.height)
        except Exception:
            return None

    def _pid(self, win) -> Optional[int]:
        try:
            pid = self._ewmh.getWmPid(win)
            return int(pid) if pid else None
        except Exception:
            return None

    @staticmethod
    def _process_name(pid: int) -> str:
        try:
            with open(f"/proc/{pid}/comm", "r", encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""
