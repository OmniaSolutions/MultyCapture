"""The tray's two routes to a .docx.

Covers the automatic one that fires when a recording stops, and the on-demand
one that asks where the file should go before building it.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog

from multycapture import paths

from conftest import SESSION_ID, wait_for_doc


# --------------------------------------------------------------------------- #
# the option itself
# --------------------------------------------------------------------------- #
def test_option_is_on_by_default(tray):
    assert tray.auto_doc is True
    assert tray.act_auto_doc.isCheckable()
    assert tray.act_auto_doc.isChecked()


def test_menu_wording(tray):
    labels = [a.text() for a in tray.menu.actions()]
    assert "Generate .docx when recording stops" in labels
    # the ellipsis is the promise that it asks before doing anything
    assert "Generate .docx…" in labels
    assert not any("last session" in label for label in labels)


def test_toggle_is_remembered(tray):
    from PySide6.QtCore import QSettings

    tray.act_auto_doc.setChecked(False)
    assert tray.auto_doc is False
    tray.settings.sync()
    stored = QSettings("MultyCapture", "MultyCapture")
    assert stored.value("auto_doc", True, type=bool) is False

    tray.act_auto_doc.setChecked(True)
    assert tray.auto_doc is True


# --------------------------------------------------------------------------- #
# automatic generation when a recording stops
# --------------------------------------------------------------------------- #
def test_disabled_option_generates_nothing(tray, capture):
    _, session_dir = capture
    tray.auto_doc = False
    tray._maybe_auto_doc(str(session_dir), 5)
    assert tray._doc_thread is None


def test_empty_recording_generates_nothing(tray, capture):
    """An editor opening on a document with no steps is worse than nothing."""
    _, session_dir = capture
    tray._maybe_auto_doc(str(session_dir), 0)
    assert tray._doc_thread is None


def test_stop_generates_into_documents_and_opens_it(tray, capture):
    """The automatic route writes to the user's documents folder.

    Not beside the capture: captures live in application data, which is not a
    place anyone browses to.
    """
    _, session_dir = capture
    tray._maybe_auto_doc(str(session_dir), 2)
    assert tray._doc_thread is not None
    assert wait_for_doc(tray)

    written = paths.documents_dir() / f"{SESSION_ID}.docx"
    assert written.is_file()
    assert written.read_bytes()[:2] == b"PK"  # a .docx is a zip container
    assert tray.opened == [str(written)]
    assert not (session_dir / f"{SESSION_ID}.docx").exists()


# --------------------------------------------------------------------------- #
# on-demand generation into a chosen folder
# --------------------------------------------------------------------------- #
def test_asks_for_a_folder_then_builds_there(tray, capture, tmp_path, monkeypatch):
    destination = tmp_path / "chosen folder"
    destination.mkdir()
    asked: list[str] = []

    def fake_dialog(parent, caption, directory, *args, **kwargs):
        asked.append(directory)
        # nothing may exist yet: the document is built only once we answer
        assert not list(destination.glob("*.docx"))
        return str(destination)

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", fake_dialog)

    tray.generate_doc()
    assert len(asked) == 1
    assert wait_for_doc(tray)

    written = destination / f"{SESSION_ID}.docx"
    assert written.is_file()
    assert written.read_bytes()[:2] == b"PK"
    assert tray.opened == [str(written)]
    assert tray._last_doc_dir == str(destination)


def test_cancelling_the_dialog_does_nothing(tray, monkeypatch):
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda *a, **k: ""
    )
    tray.generate_doc()
    assert tray._doc_thread is None
    assert tray.opened == []


def test_no_sessions_is_reported_not_crashed(qapp, tmp_path, monkeypatch):
    """An empty captures root must not raise out of the menu handler."""
    from multycapture.gui.tray import TrayApp

    empty = tmp_path / "empty"
    empty.mkdir()
    app = TrayApp(root=str(empty))
    try:
        monkeypatch.setattr(
            QFileDialog, "getExistingDirectory",
            lambda *a, **k: pytest_fail_if_called(),
        )
        app.generate_doc()  # must return quietly, without asking for a folder
        assert app._doc_thread is None
    finally:
        app.tray.hide()


def pytest_fail_if_called():
    raise AssertionError("should not have asked for a folder with no sessions")


# --------------------------------------------------------------------------- #
# notifications
# --------------------------------------------------------------------------- #
def test_the_tray_never_carries_the_popup_on_linux(tray, monkeypatch):
    """Regression: this is what made the icon vanish.

    showMessage under StatusNotifierItem flips the item to NeedsAttention and
    the panel then draws dialog-information instead of the camera, for good.
    """
    import sys

    from multycapture.gui import notify

    shown: list = []
    monkeypatch.setattr(tray.tray, "showMessage", lambda *a, **k: shown.append(a))
    monkeypatch.setattr(notify.sys, "platform", "linux")
    monkeypatch.setattr(notify, "send", lambda *a, **k: True)

    tray._notify("Recording", "Starting in 5s")

    assert shown == []
    assert "Recording" in tray.tray.toolTip()


def test_the_tooltip_carries_it_even_with_no_notifier(tray, monkeypatch):
    """No gdbus, no notify-send: the words must still reach the user."""
    from multycapture.gui import notify

    shown: list = []
    monkeypatch.setattr(tray.tray, "showMessage", lambda *a, **k: shown.append(a))
    monkeypatch.setattr(notify.sys, "platform", "linux")
    monkeypatch.setattr(notify, "send", lambda *a, **k: False)

    tray._notify("Document ready", "/tmp/x.docx")

    assert shown == []                      # still not through the tray
    assert "Document ready" in tray.tray.toolTip()
