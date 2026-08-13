"""Key events reach the session.

A regression suite for a bug that cost every shortcut in every recording: the
key branch referenced a name that was never assigned, so pressing Enter, Tab or
Ctrl+S raised inside pynput's listener thread. pynput logs and swallows those,
so nothing failed visibly — the events were simply never written, and only the
desktop's session log knew.
"""

from __future__ import annotations

import datetime
import time

import pytest
from PIL import Image
from pynput import keyboard

from multycapture.capture import SessionReader
from multycapture.capture.recorder import Recorder
from multycapture.capture.session_writer import SessionWriter
from multycapture.model import (
    CaptureConfig, EventType, KeyboardMode, Point, Rect, Session, ShotScope,
    WindowInfo,
)


class _Backend:
    def get_active_window(self):
        return WindowInfo("Orders", "app", 1, Rect(0, 0, 800, 600))

    def get_cursor_pos(self):
        return Point(10, 20)

    def enumerate_monitors(self):
        from multycapture.model import MonitorInfo
        return [MonitorInfo(index=0, rect=Rect(0, 0, 800, 600), primary=True)]


class _Grabber:
    def grab(self, region):
        return Image.new("RGB", (40, 30), (200, 200, 200))


class _Char:
    """A printable key, as pynput reports one."""

    def __init__(self, char: str):
        self.char = char


@pytest.fixture
def recorder(tmp_path):
    """A recorder wired to fakes, ready to receive key presses.

    Deliberately not started: start() installs global input hooks, and the
    branch under test needs none of that — only somewhere to write.
    """
    rec = Recorder(
        root=str(tmp_path / "captures"),
        config=CaptureConfig(
            shot_scope=ShotScope.MONITOR, keyboard_mode=KeyboardMode.CONSOLIDATE
        ),
        backend=_Backend(),
        grabber=_Grabber(),
    )
    session = Session(
        id="session_20260813_090000",
        created_at=datetime.datetime.now().isoformat(),
        os="test", app_version="test",
        capture_config=rec.config,
    )
    rec._writer = SessionWriter(session, rec.root).open()
    rec._start_mono = time.monotonic()
    yield rec
    rec._writer.close()


def _events(rec):
    rec._flush_pending()
    return list(SessionReader(str(rec._writer.dir)).events())


# --------------------------------------------------------------------------- #
def test_a_special_key_is_recorded(recorder):
    """Enter is not printable, so it takes the discrete-key branch."""
    recorder._on_press(keyboard.Key.enter)
    events = _events(recorder)

    assert [e.type for e in events] == [EventType.KEY]
    assert events[0].detail.key == "enter"
    assert events[0].detail.combo == "enter"


def test_a_shortcut_records_its_combination(recorder):
    """Ctrl+S must arrive as "ctrl+s", not as the letter s."""
    recorder._on_press(keyboard.Key.ctrl)      # modifier: held, not emitted
    recorder._on_press(_Char("s"))
    events = _events(recorder)

    assert [e.type for e in events] == [EventType.KEY]
    detail = events[0].detail
    assert detail.combo == "ctrl+s"
    assert detail.modifiers == ["ctrl"]
    assert detail.key == "s"


def test_modifier_order_is_stable(recorder):
    """The combo has to read the same regardless of press order."""
    recorder._on_press(keyboard.Key.shift)
    recorder._on_press(keyboard.Key.ctrl)
    recorder._on_press(_Char("z"))
    assert _events(recorder)[0].detail.combo == "ctrl+shift+z"


def test_pressing_a_modifier_alone_records_nothing(recorder):
    recorder._on_press(keyboard.Key.ctrl)
    assert _events(recorder) == []


def test_plain_typing_is_still_consolidated(recorder):
    """The discrete branch must not swallow ordinary text."""
    for ch in "ciao":
        recorder._on_press(_Char(ch))
    events = _events(recorder)

    assert [e.type for e in events] == [EventType.TYPE]
    assert events[0].detail.text == "ciao"


def test_typing_then_a_shortcut_produces_both(recorder):
    for ch in "ab":
        recorder._on_press(_Char(ch))
    recorder._on_press(keyboard.Key.enter)
    events = _events(recorder)

    assert [e.type for e in events] == [EventType.TYPE, EventType.KEY]
    assert events[0].detail.text == "ab"
    assert events[1].detail.combo == "enter"


def test_every_key_mode_records_plain_letters_too(tmp_path):
    rec = Recorder(
        root=str(tmp_path / "captures"),
        config=CaptureConfig(
            shot_scope=ShotScope.MONITOR, keyboard_mode=KeyboardMode.EVERY_KEY
        ),
        backend=_Backend(), grabber=_Grabber(),
    )
    session = Session(
        id="session_20260813_100000",
        created_at=datetime.datetime.now().isoformat(),
        os="test", app_version="test", capture_config=rec.config,
    )
    rec._writer = SessionWriter(session, rec.root).open()
    rec._start_mono = time.monotonic()
    try:
        rec._on_press(_Char("x"))
        events = list(SessionReader(str(rec._writer.dir)).events())
        assert [e.type for e in events] == [EventType.KEY]
        assert events[0].detail.combo == "x"
    finally:
        rec._writer.close()
