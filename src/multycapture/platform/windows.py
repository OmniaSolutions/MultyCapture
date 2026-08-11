"""Windows backend — implemented with pure ``ctypes`` (no pywin32 dependency)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Optional

from ..model import MonitorInfo, Rect, WindowInfo
from .base import PlatformBackend

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# DwmGetWindowAttribute lives in dwmapi; load lazily/defensively.
try:
    dwmapi = ctypes.windll.dwmapi
except OSError:  # pragma: no cover - dwmapi should exist on Win Vista+
    dwmapi = None

DWMWA_EXTENDED_FRAME_BOUNDS = 9
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
MONITORINFOF_PRIMARY = 0x1


class WindowsBackend(PlatformBackend):
    name = "windows"

    # ------------------------------------------------------------------ #
    # DPI
    # ------------------------------------------------------------------ #
    def set_high_dpi_awareness(self) -> None:
        # Prefer Per-Monitor v2 (Win10 1703+); fall back gracefully.
        DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)
        try:
            if user32.SetProcessDpiAwarenessContext(
                DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            ):
                return
        except (AttributeError, OSError):
            pass
        try:  # Win 8.1+: PROCESS_PER_MONITOR_DPI_AWARE = 2
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
            return
        except (AttributeError, OSError):
            pass
        try:  # Vista+: system-DPI aware
            user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass

    # ------------------------------------------------------------------ #
    # Monitors
    # ------------------------------------------------------------------ #
    def enumerate_monitors(self) -> list[MonitorInfo]:
        monitors: list[MonitorInfo] = []

        class MONITORINFOEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
                ("szDevice", wintypes.WCHAR * 32),
            ]

        MonitorEnumProc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
            ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
        )

        index_holder = {"i": 0}

        def _cb(hmon, hdc, lprect, lparam):
            info = MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(MONITORINFOEXW)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(info)):
                r = info.rcMonitor
                scale = self._monitor_scale(hmon)
                monitors.append(MonitorInfo(
                    index=index_holder["i"],
                    x=r.left, y=r.top,
                    width=r.right - r.left, height=r.bottom - r.top,
                    primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                    scale=scale,
                ))
                index_holder["i"] += 1
            return True

        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_cb), 0)
        # Ensure the primary monitor is index 0 for stable, intuitive ordering.
        monitors.sort(key=lambda m: (not m.primary, m.x, m.y))
        for i, m in enumerate(monitors):
            m.index = i
        return monitors

    @staticmethod
    def _monitor_scale(hmon) -> float:
        # GetDpiForMonitor: MDT_EFFECTIVE_DPI = 0; 96 dpi == 100%.
        try:
            dpi_x = wintypes.UINT()
            dpi_y = wintypes.UINT()
            if ctypes.windll.shcore.GetDpiForMonitor(
                hmon, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y)
            ) == 0:
                return round(dpi_x.value / 96.0, 4)
        except (AttributeError, OSError):
            pass
        return 1.0

    # ------------------------------------------------------------------ #
    # Active window
    # ------------------------------------------------------------------ #
    def get_active_window(self) -> Optional[WindowInfo]:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        title = self._window_title(hwnd)
        rect = self._window_rect(hwnd)
        if rect is None:
            return None
        pid = self._window_pid(hwnd)
        process = self._process_name(pid) if pid else ""

        return WindowInfo(title=title, process=process, pid=pid or 0, rect=rect)

    @staticmethod
    def _window_title(hwnd) -> str:
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value

    @staticmethod
    def _window_rect(hwnd) -> Optional[Rect]:
        rc = wintypes.RECT()
        # Prefer the true visible frame (excludes the invisible resize border).
        if dwmapi is not None:
            try:
                if dwmapi.DwmGetWindowAttribute(
                    hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                    ctypes.byref(rc), ctypes.sizeof(rc),
                ) == 0:
                    return Rect(rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)
            except OSError:
                pass
        if user32.GetWindowRect(hwnd, ctypes.byref(rc)):
            return Rect(rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top)
        return None

    @staticmethod
    def _window_pid(hwnd) -> Optional[int]:
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value or None

    @staticmethod
    def _process_name(pid: int) -> str:
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            return ""
        try:
            size = wintypes.DWORD(260)
            buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                full = buf.value
                return full.rsplit("\\", 1)[-1]  # basename, e.g. "Code.exe"
        finally:
            kernel32.CloseHandle(h)
        return ""
