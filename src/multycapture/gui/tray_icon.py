"""The tray icon: the application's camera mark, tinted by state.

Drawn rather than loaded, because the tile has to change colour — blue when
idle, amber while counting down, red while recording — and recolouring a PNG
at runtime is worse than drawing the shape. The geometry mirrors
``packaging/assets/multycapture.svg`` so the tray and the desktop entry are
recognisably the same mark.

Every icon carries several sizes, which matters more than it sounds. A panel
asks for the size it wants: handing it one 64px pixmap leaves it to scale, and
on a 22px panel that turns a crisp mark into mush. Under StatusNotifierItem —
what XFCE, KDE and GNOME-with-extension all use now — the icon is also
serialised over D-Bus rather than painted into the panel's own window, and a
single-size icon travels through that badly. :data:`SIZES` covers what panels
actually ask for.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap

# The sizes a panel is likely to ask for.
SIZES = (16, 22, 24, 32, 48, 64, 128)

# Fixed parts of the mark, from the SVG.
_BODY = "#ffffff"
_LENS_RING = "#1e3a8a"
_LENS_GLASS = "#ffffff"
_LENS_LINES = "#2563eb"


#: Built icons, kept because the countdown asks for one every second and each
#: is seven drawn pixmaps. Bounded by the states that exist: three colours and
#: the seconds a countdown can show.
_CACHE: dict[tuple[str, Optional[str]], QIcon] = {}


def build(colour: str, text: Optional[str] = None) -> QIcon:
    """The camera mark on a ``colour`` tile, at every size a panel may want.

    ``text`` replaces the lens contents — used for the countdown, where the
    seconds remaining belong where the eye already is rather than floating
    over the whole icon.
    """
    key = (colour, text)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached

    icon = QIcon()
    for size in SIZES:
        icon.addPixmap(_pixmap(size, colour, text))
    _CACHE[key] = icon
    return icon


def _pixmap(size: int, colour: str, text: Optional[str] = None) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)

    s = size / 256.0  # the SVG's coordinate system

    # ---- tile: the state colour ------------------------------------------
    painter.setBrush(QColor(colour))
    painter.drawRoundedRect(QRectF(0, 0, size, size), 58 * s, 58 * s)

    # ---- camera body, with the viewfinder bump ---------------------------
    body = QPainterPath()
    body.addRoundedRect(QRectF(36 * s, 88 * s, 184 * s, 120 * s), 24 * s, 24 * s)
    bump = QPainterPath()
    bump.moveTo(84 * s, 90 * s)
    bump.lineTo(98 * s, 60 * s)
    bump.lineTo(142 * s, 60 * s)
    bump.lineTo(156 * s, 90 * s)
    bump.closeSubpath()
    painter.setBrush(QColor(_BODY))
    painter.drawPath(body.united(bump))

    # ---- lens -------------------------------------------------------------
    centre_x, centre_y = 128 * s, 148 * s
    _circle(painter, centre_x, centre_y, 48 * s, _LENS_RING)
    _circle(painter, centre_x, centre_y, 35 * s, _LENS_GLASS)

    if text:
        _draw_countdown(painter, text, centre_x, centre_y, s)
    elif size >= 32:
        # The document in the lens. Below 32px it is a smudge, so it is left
        # out rather than drawn as noise.
        painter.setBrush(QColor(_LENS_LINES))
        painter.drawRoundedRect(QRectF(107 * s, 136 * s, 42 * s, 10 * s), 5 * s, 5 * s)
        painter.drawRoundedRect(QRectF(107 * s, 153 * s, 28 * s, 10 * s), 5 * s, 5 * s)

    painter.end()
    return pixmap


def _circle(painter: QPainter, x: float, y: float, r: float, colour: str) -> None:
    painter.setBrush(QColor(colour))
    painter.drawEllipse(QRectF(x - r, y - r, r * 2, r * 2))


def _draw_countdown(
    painter: QPainter, text: str, x: float, y: float, s: float
) -> None:
    """The seconds remaining, inside the lens."""
    font = QFont()
    # Two digits have to fit the same circle as one.
    font.setPixelSize(int(max(6, (44 if len(text) < 2 else 32) * s)))
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor(_LENS_RING))
    box = QRectF(x - 40 * s, y - 40 * s, 80 * s, 80 * s)
    painter.drawText(box, Qt.AlignCenter, text)
