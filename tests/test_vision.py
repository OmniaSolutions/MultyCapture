"""Telling what happened between two screenshots."""

from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from multycapture import vision

SIZE = (800, 600)


def _screen(extra=None) -> Image.Image:
    """A plain window, optionally with something drawn on top."""
    image = Image.new("RGB", SIZE, (240, 240, 242))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, SIZE[0], 30], fill=(45, 45, 48))
    draw.rectangle([40, 100, 500, 140], fill=(255, 255, 255), outline=(160, 160, 160))
    if extra:
        extra(draw)
    return image


def _dialog(draw):
    draw.rectangle([200, 200, 600, 400], fill=(250, 250, 252), outline=(120, 120, 120))


def _tiny_badge(draw):
    """A notification dot: a real change, and none of the user's doing."""
    draw.ellipse([770, 5, 782, 17], fill=(220, 50, 50))


# --------------------------------------------------------------------------- #
def test_identical_screens_report_nothing():
    assert vision.what_changed(_screen(), _screen()) is None


def test_a_new_dialog_is_found_and_measured():
    change = vision.what_changed(_screen(), _screen(_dialog))
    assert change is not None
    assert change.width == pytest.approx(401, abs=2)
    assert change.height == pytest.approx(201, abs=2)
    # The box is where the dialog was drawn.
    assert change.box[0] == pytest.approx(200, abs=2)
    assert change.box[1] == pytest.approx(200, abs=2)


def test_area_is_reported_as_a_share_of_the_screen():
    change = vision.what_changed(_screen(), _screen(_dialog))
    expected = 100.0 * (401 * 201) / (SIZE[0] * SIZE[1])
    assert change.area_pct == pytest.approx(expected, abs=0.5)


def test_density_separates_a_replaced_view_from_anything_partial():
    """Density says how much of the box really differs — and little else.

    It does *not* tell a panel from scattered text: a dialog only a shade off
    the background registers as its border alone, scoring lower than a few
    lines of dark text on white. The one thing it reliably separates is a
    screen that was wholly replaced from one that was not, so nothing else is
    built on it.
    """
    replaced = vision.what_changed(_screen(), Image.new("RGB", SIZE, (10, 10, 40)))
    dialog = vision.what_changed(_screen(), _screen(_dialog))

    assert replaced.density_pct > 95     # every pixel differs
    assert dialog.density_pct < 50       # only parts of the region do


def test_the_box_locates_the_change_whatever_its_density():
    """Low contrast changes the density, not where the change is."""
    def faint(draw):
        # A panel a shade off the background: only its border clears the
        # colour threshold, yet the region is still found in full.
        draw.rectangle([200, 200, 600, 400], fill=(243, 243, 245),
                       outline=(120, 120, 120))

    change = vision.what_changed(_screen(), _screen(faint))
    assert change is not None
    assert change.box[0] == pytest.approx(200, abs=2)
    assert change.box[2] == pytest.approx(601, abs=2)
    assert change.density_pct < 10       # sparse, but correctly located


# --------------------------------------------------------------------------- #
# the noise floor
# --------------------------------------------------------------------------- #
def test_a_notification_badge_is_below_the_floor():
    """A clock ticking over is a real difference, not a consequence."""
    assert vision.what_changed(_screen(), _screen(_tiny_badge)) is None


def test_the_floor_can_be_lowered_to_see_it():
    change = vision.what_changed(
        _screen(), _screen(_tiny_badge), min_area_pct=0.0
    )
    assert change is not None and change.width < 20


def test_imperceptible_shifts_are_ignored():
    """Compression and antialiasing move a few levels; that is not a change."""
    before = _screen()
    after = before.point(lambda level: min(255, level + 5))
    assert vision.what_changed(before, after) is None


def test_the_threshold_can_be_lowered_to_see_them():
    before = _screen()
    after = before.point(lambda level: min(255, level + 5))
    assert vision.what_changed(before, after, threshold=1) is not None


# --------------------------------------------------------------------------- #
# refusing to guess
# --------------------------------------------------------------------------- #
def test_different_sizes_report_nothing():
    """A moved window or a different monitor makes the comparison meaningless.

    Aligning them would invent differences that were never on screen.
    """
    small = _screen().resize((400, 300))
    assert vision.what_changed(_screen(), small) is None
    assert vision.what_changed(small, _screen()) is None


def test_whole_view_replacement_is_recognised():
    replaced = Image.new("RGB", SIZE, (10, 10, 40))
    change = vision.what_changed(_screen(), replaced)
    assert change is not None
    assert vision.is_whole_view(change) is True


def test_a_dialog_is_not_a_whole_view_replacement():
    change = vision.what_changed(_screen(), _screen(_dialog))
    assert vision.is_whole_view(change) is False


# --------------------------------------------------------------------------- #
def test_the_changed_region_is_readable_by_ocr():
    """The point of locating the change: read only that part.

    This is the combination the document depends on — find where something
    appeared, then read what it says, without OCRing the whole screen.
    """
    from multycapture import ocr

    if not ocr.available():
        pytest.skip("tesseract is not installed")

    def dialog_with_text(draw):
        _dialog(draw)
        draw.text((260, 280), "Save changes?", fill=(20, 20, 20))

    after = _screen(dialog_with_text)
    change = vision.what_changed(_screen(), after)
    crop = after.crop(change.box)

    text = ocr.label_at(crop, (crop.width // 2, crop.height // 2), box=crop.size)
    assert text and "changes" in text.lower()
