"""Shared fixtures for the MultyCapture test suite.

The environment is set up at import time, before PySide6 is pulled in by any
test module: the Qt platform plugin and the QSettings location are both fixed
once a QApplication exists, and pytest imports test modules during collection.
Pointing HOME at a scratch directory keeps a test run from reading or writing
the developer's real MultyCapture settings.
"""

from __future__ import annotations

import os
import tempfile

_SCRATCH = tempfile.mkdtemp(prefix="multycapture-tests-")
os.environ["HOME"] = _SCRATCH
os.environ["XDG_CONFIG_HOME"] = _SCRATCH
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # headless

import datetime  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from PIL import Image  # noqa: E402
from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from multycapture.capture.session_writer import SessionWriter  # noqa: E402
from multycapture.model import (  # noqa: E402
    ClickDetail, Event, EventType, MouseAction, MouseButton, Point, Rect,
    Session, WindowInfo,
)

# Scratch HOME is not enough: QSettings stores under the registry on Windows
# and under ~/Library/Preferences on macOS, neither of which follows HOME the
# way the XDG backend does. Forcing plain ini files into the scratch directory
# keeps a test run from touching real user settings on every platform. This has
# to happen before the first QSettings instance exists.
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, _SCRATCH)

SESSION_ID = "session_20260811_120000"


@pytest.fixture(scope="session")
def qapp():
    """One QApplication for the whole run — Qt allows no more than one."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def capture(tmp_path) -> tuple[Path, Path]:
    """Write a small but genuine session; return (captures root, session dir)."""
    root = tmp_path / "captures"
    session = Session(
        id=SESSION_ID,
        created_at=datetime.datetime.now().isoformat(),
        os="test",
        app_version="test",
    )
    writer = SessionWriter(session, root).open()
    for i in range(2):
        seq = writer.next_seq()
        shot = writer.save_shot(Image.new("RGB", (400, 300), (30, 90, 200)), seq)
        writer.append_event(Event(
            seq=seq,
            t=float(i),
            ts=datetime.datetime.now().isoformat(),
            type=EventType.CLICK,
            screenshot=shot,
            mouse=Point(100, 120),
            monitor=0,
            window=WindowInfo("Test Window", "test", 1, Rect(0, 0, 400, 300)),
            mouse_rel=None,
            detail=ClickDetail(MouseButton.LEFT, MouseAction.DOWN),
        ))
    session.event_count = 2
    writer.close()
    return root, writer.dir


@pytest.fixture
def tray(qapp, capture):
    """A TrayApp over a fresh session, with the editor hand-off recorded.

    Settings are cleared first so a value stored by an earlier test cannot
    change what this one sees.
    """
    from multycapture.gui.tray import TrayApp

    QSettings("MultyCapture", "MultyCapture").clear()
    root, _ = capture
    app = TrayApp(root=str(root))
    app.opened: list[str] = []            # what would have gone to the desktop
    app._open_in_editor = app.opened.append
    yield app
    app.tray.hide()


def wait_for_doc(tray, timeout: float = 120.0) -> bool:
    """Block until the generation thread finishes, then deliver its result.

    The tray normally drains the result from a QTimer; tests drive that by
    hand rather than spinning the event loop.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if tray._doc_thread is not None and tray._doc_thread.is_alive():
            time.sleep(0.1)
            continue
        tray._check_doc_result()
        return True
    return False
