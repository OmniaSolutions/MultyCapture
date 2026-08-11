"""Screen grabber abstraction.

The recorder captures a rectangular region of the virtual desktop for each event.
*How* that region is grabbed is pluggable: ``MssGrabber`` (default, tiny/fast) is
used now, but a ``QtGrabber`` backed by ``QScreen.grabWindow`` could be dropped in
later if the project adopts a PySide6 GUI — the recorder only sees this interface.

A grabber returns a Pillow ``Image`` so downstream annotation/thumbnailing is
uniform regardless of source.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING

from ..model import Rect

if TYPE_CHECKING:  # avoid importing PIL at module load for type hints only
    from PIL.Image import Image


class ScreenGrabber(abc.ABC):
    """Grabs pixels from the virtual desktop. Not thread-safe by default."""

    @abc.abstractmethod
    def grab(self, region: Rect) -> "Image":
        """Return an RGB Pillow Image of ``region`` (virtual-desktop pixels)."""

    def close(self) -> None:
        """Release any held resources. Safe to call multiple times."""

    def __enter__(self) -> "ScreenGrabber":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class MssGrabber(ScreenGrabber):
    """Fast screenshots via the ``mss`` library (Windows, Linux/X11, macOS).

    An ``mss`` instance is not shareable across threads, so we lazily create one
    per calling thread. The recorder grabs from a single worker, so in practice
    this is one instance.
    """

    def __init__(self) -> None:
        import threading
        self._local = threading.local()

    def _sct(self):
        sct = getattr(self._local, "sct", None)
        if sct is None:
            import mss
            sct = mss.mss()
            self._local.sct = sct
        return sct

    def grab(self, region: Rect) -> "Image":
        from PIL import Image
        bbox = {
            "left": region.x,
            "top": region.y,
            "width": region.width,
            "height": region.height,
        }
        shot = self._sct().grab(bbox)
        # mss returns BGRA; Image.frombytes with "raw","BGRX" gives correct RGB.
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

    def close(self) -> None:
        sct = getattr(self._local, "sct", None)
        if sct is not None:
            try:
                sct.close()
            finally:
                self._local.sct = None
