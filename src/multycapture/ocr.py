"""Reading the label the user clicked on, locally.

A capture records *where* a click landed — coordinates, window title, process —
but not *what* was clicked. That gap is why generated instructions read "click
at 742, 318" instead of "click Save". This module closes it by reading a small
region of the screenshot around the click point.

Deliberately not a general OCR pass over the screenshot: the whole screen takes
about three times as long per event and returns a paragraph of surrounding
chrome, when the useful answer is one or two words. Everything else the model
needs — window title, application — the capture already knows.

Three things the measurements forced, none of them obvious:

* **Grayscale is required, not an optimisation.** A colour crop of white text on
  a blue button reads as nothing at all; the same crop in grayscale reads
  "Salva". Primary buttons are light-on-coloured almost everywhere, so skipping
  this silently loses exactly the clicks that matter most.
* **Upscaling helps.** UI text is small; tesseract does better on a 3x crop.
* **Per-word confidence is needed to clean the edges.** A crop clips whatever
  borders the control, and those fragments come back as characters — "a Salva",
  "Annulla |". Confidence separates them: the real word scores in the 90s, the
  fragment in the 40s.

OCR is optional. Without tesseract installed every function here returns
nothing and the caller carries on with what the capture already had.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from PIL.Image import Image

# Region read around the click, in screenshot pixels. Wide enough for a button
# label or a field caption, tight enough to exclude the neighbouring control.
BOX = (240, 64)

# Tesseract's own scale: 0-100, with anything genuine on crisp UI text scoring
# well above this and clipped border fragments well below.
MIN_CONFIDENCE = 60

# Page segmentation mode 7: "treat the image as a single text line", which is
# what a control label is.
_PSM = "--psm 7"

# Mode 6: "a uniform block of text". What a dialog or a panel is — reading one
# with the single-line mode above returns the first line and drops the rest.
_PSM_BLOCK = "--psm 6"

_UPSCALE = 3


@lru_cache(maxsize=1)
def available() -> bool:
    """Whether OCR can run at all. Cached — the answer cannot change mid-run."""
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        # Not installed, not on PATH, or the wrapper is missing entirely.
        return False


def label_at(
    image: "Image",
    point: tuple[int, int],
    *,
    box: tuple[int, int] = BOX,
    min_confidence: int = MIN_CONFIDENCE,
) -> Optional[str]:
    """Read the control label at ``point`` (in ``image`` pixels).

    Returns the text, or ``None`` when OCR is unavailable, the point is outside
    the image, or nothing legible was found.
    """
    if not available():
        return None

    crop = _crop_around(image, point, box)
    if crop is None:
        return None

    words = _read(crop, min_confidence)
    return " ".join(words) if words else None


def read_region(
    image: "Image",
    *,
    min_confidence: int = MIN_CONFIDENCE,
    max_words: int = 24,
) -> Optional[str]:
    """Read a whole region as a block of text — a dialog, a panel, a message.

    Unlike :func:`label_at` this expects several lines, and caps the result:
    a large region can hold a screenful of prose, and an instruction quoting
    all of it helps nobody.
    """
    if not available():
        return None
    words = _read(image, min_confidence, psm=_PSM_BLOCK)
    if not words:
        return None
    return " ".join(words[:max_words])


def _crop_around(
    image: "Image", point: tuple[int, int], box: tuple[int, int]
) -> Optional["Image"]:
    """The region around ``point``, clamped to the image, or None if outside."""
    x, y = point
    if not (0 <= x < image.width and 0 <= y < image.height):
        return None

    half_w, half_h = box[0] // 2, box[1] // 2
    left = max(0, x - half_w)
    top = max(0, y - half_h)
    right = min(image.width, x + half_w)
    bottom = min(image.height, y + half_h)
    if right <= left or bottom <= top:
        return None
    return image.crop((left, top, right, bottom))


def _read(crop: "Image", min_confidence: int, psm: str = _PSM) -> list[str]:
    """Grayscale, upscale, OCR, and keep only what scored well enough."""
    import pytesseract
    from PIL import Image as PILImage, ImageOps

    prepared = ImageOps.grayscale(
        crop.resize((crop.width * _UPSCALE, crop.height * _UPSCALE), PILImage.LANCZOS)
    )
    try:
        data = pytesseract.image_to_data(
            prepared, config=psm, output_type=pytesseract.Output.DICT
        )
    except Exception:
        # A failed read is a missing label, not a failed document.
        return []

    words = []
    for text, confidence in zip(data.get("text", []), data.get("conf", [])):
        text = (text or "").strip()
        if not text:
            continue
        try:
            score = int(float(confidence))
        except (TypeError, ValueError):
            continue
        if score < min_confidence:
            continue
        if not _is_word(text):
            continue
        words.append(text)
    return words


def _is_word(text: str) -> bool:
    """Reject lone punctuation.

    A crop that clips a control's border yields tokens like "|" or "/" which can
    still score above the confidence threshold. Anything with no alphanumeric
    character in it is border, not label.
    """
    return any(ch.isalnum() for ch in text)
