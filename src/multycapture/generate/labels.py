"""Reading the on-screen label each click landed on.

This is the bridge between :mod:`..ocr`, which knows how to read a region of an
image, and :mod:`.condense`, which writes the instructions. Keeping it separate
means ``condense`` stays a pure function of the event stream — no file access,
no OCR, trivially testable — and this module owns the messy part: locating the
click within its screenshot and handling images that fail to open.
"""

from __future__ import annotations

from typing import Optional

from .. import ocr
from ..capture import SessionReader
from ..model import Event, Session
from . import steps


def read_labels(
    reader: SessionReader,
    session: Session,
    events: list[Event],
) -> dict[int, str]:
    """Map event ``seq`` to the label clicked, for events that have one.

    Only events that point at something are read — a keystroke has no target on
    screen — and only when OCR is available. Events whose screenshot is missing
    or unreadable are skipped rather than failing the document: a label is an
    enhancement, and its absence must cost nothing but the label itself.
    """
    if not ocr.available():
        return {}

    from PIL import Image

    found: dict[int, str] = {}
    for event in events:
        if not steps.is_pointed(event) or not event.screenshot:
            continue
        path = reader.shot_path(event.screenshot)
        if path is None or not path.exists():
            continue

        origin = steps.shot_origin(session, event)
        point = (event.mouse.x - origin.x, event.mouse.y - origin.y)
        try:
            with Image.open(path) as image:
                image.load()
                label = ocr.label_at(image, point)
        except Exception:
            continue
        if label:
            found[event.seq] = label
    return found


def quoted(label: Optional[str]) -> str:
    """The label as it appears inside an instruction, or nothing at all."""
    return f" “{label}”" if label else ""
