"""What each step caused, read from the screenshots either side of it.

A capture says what was done; comparing consecutive screenshots says what
happened as a result — a dialog opened, a panel filled in, the view was
replaced. That is the half a written procedure normally has to supply from
memory, and it is the difference between "Click Save." and "Click Save. A
confirmation appears: “Save changes?”".

The comparison is between the screenshot of one step and the screenshot of the
**next**, which is deliberate: those are the two images the reader has in front
of them in the document, so the sentence explains a difference they can see
rather than one recorded between moments they never saw.
"""

from __future__ import annotations

from typing import Optional

from .. import ocr, vision
from ..capture import SessionReader
from ..model import Session
from .condense import Step

# A changed region smaller than this is not worth reading: the text in it is
# usually the caret, a hover highlight, or the few characters just typed.
MIN_READABLE_PCT = 0.4


def read_outcomes(
    reader: SessionReader,
    session: Session,
    steps: list[Step],
) -> dict[int, str]:
    """Map step index to a sentence describing what the step caused.

    Steps with nothing to say are absent rather than present and empty. The
    last step is always absent: there is no later screenshot to compare it to.
    """
    if len(steps) < 2:
        return {}

    from PIL import Image

    found: dict[int, str] = {}
    for current, following in zip(steps, steps[1:]):
        before_path = reader.shot_path(current.event.screenshot)
        after_path = reader.shot_path(following.event.screenshot)
        if not before_path or not after_path:
            continue
        if not before_path.exists() or not after_path.exists():
            continue

        try:
            with Image.open(before_path) as before, Image.open(after_path) as after:
                before.load()
                after.load()
                sentence = _describe(before, after, current.instruction)
        except Exception:
            # A missing outcome costs a sentence; a raised exception would cost
            # the document.
            continue

        if sentence:
            found[current.index] = sentence
    return found


def _describe(before, after, instruction: str) -> Optional[str]:
    """One sentence for the difference, or nothing worth saying."""
    change = vision.what_changed(before, after)
    if change is None:
        return None

    if vision.is_whole_view(change):
        return "The view changes."

    if change.area_pct < MIN_READABLE_PCT:
        # Real, but too small to describe usefully.
        return None

    text = ocr.read_region(after.crop(change.box))
    if not text:
        return None
    if _already_said(text, instruction):
        # After a "Type ..." step the changed region holds exactly what was
        # typed; repeating it adds nothing.
        return None
    return f"“{text}” appears."


def _already_said(text: str, instruction: str) -> bool:
    """Whether the instruction already contains what was read."""
    words = [w for w in _normalise(text).split() if len(w) > 2]
    if not words:
        return True
    said = _normalise(instruction)
    return sum(word in said for word in words) >= len(words) * 0.6


def _normalise(text: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else " " for ch in text)
