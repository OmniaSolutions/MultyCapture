"""What changed on screen between two moments.

A capture says what the user *did*. This says what *happened* — a dialog
appeared, a panel filled in, the view was replaced — which is the half a
procedure normally has to spell out and which no amount of reading a single
screenshot can recover.

Only Pillow is involved, and only its C primitives, so this needs no new
dependency and no pixel loops. That is enough because a user interface is a
synthetic image: flat fills, axis-aligned edges, hard contrast. Two things were
tried and rejected on the way here:

* Flood-filling from the click point to measure the widget under it. Fragile —
  a click landing on a button's *letter* rather than its fill grows a 1x6 pixel
  region — and slow, up to 2.9 seconds on a large uniform area, against 95 ms
  for reading a label.
* Describing a single screenshot. There is nothing to compare it against, so it
  says what is on screen, which the window title and the click label already
  cover.

Differencing is both the cheapest (about 20 ms for a 1920x1080 pair) and the
most informative, because it isolates the consequence of one action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from PIL import ImageChops

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL.Image import Image

# Per-channel difference below this is treated as identical. Screenshots of the
# same static screen are not bit-identical: compression, subpixel antialiasing
# and cursor shadows all move a few levels.
THRESHOLD = 24

# Ignore changes smaller than this share of the screen. A clock ticking over or
# a notification badge is a real difference and not the consequence of the
# user's action.
MIN_AREA_PCT = 0.05


@dataclass(frozen=True)
class Change:
    """The region that differs between two screenshots."""

    box: tuple[int, int, int, int]
    #: Share of the whole image covered by the region's bounding box.
    area_pct: float
    #: Share of that box which actually differs. Reliable only for telling a
    #: wholly replaced view from anything partial: a panel a shade off the
    #: background registers as its border alone and scores *lower* than a few
    #: lines of text, so do not read it as "solid versus scattered".
    density_pct: float

    @property
    def width(self) -> int:
        return self.box[2] - self.box[0]

    @property
    def height(self) -> int:
        return self.box[3] - self.box[1]


def what_changed(
    before: "Image",
    after: "Image",
    *,
    threshold: int = THRESHOLD,
    min_area_pct: float = MIN_AREA_PCT,
) -> Optional[Change]:
    """The changed region, or ``None`` if there is nothing worth reporting.

    ``None`` also covers the case the two images are not the same size: a
    window-scoped capture that moved or a change of monitor makes a pixel
    comparison meaningless, and guessing an alignment would invent differences
    that were never on screen.
    """
    if before.size != after.size:
        return None

    difference = ImageChops.difference(
        before.convert("RGB"), after.convert("RGB")
    ).convert("L")
    # Flatten to changed / unchanged before measuring, so a large faint shift
    # counts the same as a large obvious one.
    binary = difference.point(lambda level: 255 if level > threshold else 0)

    box = binary.getbbox()
    if box is None:
        return None

    width, height = box[2] - box[0], box[3] - box[1]
    total = before.width * before.height
    area_pct = 100.0 * width * height / total if total else 0.0
    if area_pct < min_area_pct:
        return None

    changed_pixels = sum(binary.histogram()[128:])
    density_pct = 100.0 * changed_pixels / max(1, width * height)
    return Change(box=box, area_pct=area_pct, density_pct=density_pct)


def is_whole_view(change: Change) -> bool:
    """Whether the change covers enough to count as a different screen."""
    return change.area_pct >= 50.0
