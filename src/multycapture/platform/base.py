"""Platform abstraction for MultyCapture.

The recorder is OS-agnostic: it depends only on the ``PlatformBackend`` interface
defined here. Concrete backends live alongside this file (``windows.py``,
``linux.py``) and are selected by :func:`get_backend`.

Only three capabilities are per-OS:

1. High-DPI awareness  — so coordinates and screenshots stay aligned.
2. Monitor enumeration — geometry, primary flag, scale factor.
3. Active-window info  — title, process, pid, rect.

Screenshots (``mss``) and global input hooks (``pynput``) are cross-platform and
handled by shared recorder code, not by the backend.
"""

from __future__ import annotations

import abc
from typing import Optional

from ..model import MonitorInfo, WindowInfo


class PlatformError(RuntimeError):
    """Raised when the current environment cannot support capture.

    The message is user-facing and should say what to do (e.g. switch from a
    Wayland session to Xorg).
    """


class PlatformBackend(abc.ABC):
    """OS-specific capabilities the recorder needs. Stateless where possible."""

    #: short family name recorded in session.json ("windows" | "linux")
    name: str = "unknown"

    @abc.abstractmethod
    def set_high_dpi_awareness(self) -> None:
        """Opt the process into per-monitor DPI awareness.

        Must be called once, before any screenshot or window geometry is read.
        A no-op on platforms where it is unnecessary.
        """

    @abc.abstractmethod
    def enumerate_monitors(self) -> list[MonitorInfo]:
        """Return all monitors with virtual-desktop geometry, ordered by index."""

    @abc.abstractmethod
    def get_active_window(self) -> Optional[WindowInfo]:
        """Return the current foreground window, or ``None`` if none resolvable."""

    def monitor_index_at(self, x: int, y: int) -> int:
        """Index of the monitor containing point (x, y); 0 if none matches.

        Shared default implementation based on :meth:`enumerate_monitors`.
        """
        for m in self.enumerate_monitors():
            if m.x <= x < m.x + m.width and m.y <= y < m.y + m.height:
                return m.index
        return 0


def get_backend() -> PlatformBackend:
    """Select and construct the backend for the current OS.

    Raises :class:`PlatformError` with an actionable message on unsupported
    environments (e.g. Wayland).
    """
    import sys

    if sys.platform.startswith("win"):
        from .windows import WindowsBackend
        return WindowsBackend()

    if sys.platform.startswith("linux"):
        from .linux import make_linux_backend
        return make_linux_backend()

    raise PlatformError(
        f"MultyCapture supports Windows and Linux; unsupported platform "
        f"'{sys.platform}'."
    )
