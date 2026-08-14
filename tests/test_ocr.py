"""Reading control labels off a screenshot.

The images here are synthesised rather than captured so the expected text is
known exactly; the cases are the ones that actually broke during design —
light-on-coloured buttons, and border fragments scoring high enough to survive.
"""

from __future__ import annotations

import os

import pytest
from PIL import Image, ImageDraw, ImageFont

from multycapture import ocr

# Skipping when tesseract is missing is right for a developer who hasn't
# installed it, and wrong for CI: a workflow that lost the package would go on
# reporting green with this file quietly skipped. CI sets the variable so the
# absence becomes a failure instead.
if not ocr.available():
    if os.environ.get("MULTYCAPTURE_REQUIRE_OCR"):
        raise RuntimeError(
            "MULTYCAPTURE_REQUIRE_OCR is set but tesseract is not installed"
        )
    pytestmark = pytest.mark.skip(reason="tesseract is not installed")


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # Windows has neither, and without an entry here these tests skip for
        # want of a font even when tesseract is installed — a second silent
        # skip, behind the one MULTYCAPTURE_REQUIRE_OCR already guards.
        r"C:\Windows\Fonts\arial.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    pytest.skip("no scalable font available to render test text")


def _button(text: str, fg, bg, size=(400, 200)) -> tuple[Image.Image, tuple[int, int]]:
    """A button centred in a light window; returns the image and the click point."""
    image = Image.new("RGB", size, (242, 242, 244))
    draw = ImageDraw.Draw(image)
    cx, cy = size[0] // 2, size[1] // 2
    draw.rectangle([cx - 80, cy - 24, cx + 80, cy + 24], fill=bg)
    draw.text((cx, cy - 11), text, font=_font(20), fill=fg, anchor="ma")
    return image, (cx, cy)


# --------------------------------------------------------------------------- #
def test_reads_dark_text_on_light_button():
    image, point = _button("Annulla", fg=(20, 20, 20), bg=(225, 225, 228))
    assert ocr.label_at(image, point) == "Annulla"


def test_reads_light_text_on_coloured_button():
    """The case that returned nothing before grayscaling was added."""
    image, point = _button("Salva", fg=(255, 255, 255), bg=(0, 120, 215))
    assert ocr.label_at(image, point) == "Salva"


def test_reads_a_two_word_label():
    image, point = _button("Ragione sociale", fg=(30, 30, 30), bg=(255, 255, 255))
    assert ocr.label_at(image, point) == "Ragione sociale"


def test_blank_area_reads_as_nothing():
    image = Image.new("RGB", (400, 200), (242, 242, 244))
    assert ocr.label_at(image, (200, 100)) is None


def test_point_outside_the_image_is_not_an_error():
    image, _ = _button("Salva", fg=(255, 255, 255), bg=(0, 120, 215))
    assert ocr.label_at(image, (5000, 5000)) is None
    assert ocr.label_at(image, (-10, 10)) is None


def test_click_near_the_edge_still_reads():
    """The crop is clamped to the image instead of running off it."""
    image = Image.new("RGB", (400, 200), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((6, 6), "File", font=_font(20), fill=(20, 20, 20))
    assert ocr.label_at(image, (20, 16)) == "File"


def test_lone_punctuation_is_dropped():
    assert ocr._is_word("|") is False
    assert ocr._is_word("/") is False
    assert ocr._is_word("—") is False
    assert ocr._is_word("Salva") is True
    assert ocr._is_word("2") is True


def test_low_confidence_words_are_dropped():
    """Raising the bar to impossible drops everything, proving the filter runs."""
    image, point = _button("Annulla", fg=(20, 20, 20), bg=(225, 225, 228))
    assert ocr.label_at(image, point, min_confidence=101) is None


# --------------------------------------------------------------------------- #
def test_absent_tesseract_degrades_quietly(monkeypatch):
    """Without OCR installed the caller gets None, not an exception."""
    monkeypatch.setattr(ocr, "available", lambda: False)
    image, point = _button("Salva", fg=(255, 255, 255), bg=(0, 120, 215))
    assert ocr.label_at(image, point) is None
