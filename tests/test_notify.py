"""Notifications must never travel through the tray icon on Linux.

Routing them there is what made the icon disappear: Qt implements
``showMessage`` under StatusNotifierItem by putting the item into
NeedsAttention and setting its attention icon to the message's, so the panel
draws ``dialog-information`` in place of the application's mark — and keeps
drawing it. Measured on the session bus before this was changed:

    before  Status = "Active"          AttentionIconName = ""
    after   Status = "NeedsAttention"  AttentionIconName = "dialog-information"
"""

from __future__ import annotations

import pytest

from multycapture.gui import notify


@pytest.fixture
def commands(monkeypatch):
    """Record what would have been run, and control what appears installed."""
    runs: list[list[str]] = []
    available = {"gdbus", "notify-send"}

    monkeypatch.setattr(
        notify.shutil, "which", lambda name: f"/usr/bin/{name}" if name in available else None
    )
    monkeypatch.setattr(
        notify.subprocess, "Popen", lambda cmd, **kw: runs.append(cmd)
    )
    monkeypatch.setattr(notify.sys, "platform", "linux")
    return runs, available


# --------------------------------------------------------------------------- #
def test_linux_does_not_use_the_tray_message():
    """The whole point: on Linux the tray must not carry the popup."""
    import sys

    if sys.platform.startswith("linux"):
        assert notify.uses_tray_message() is False


def test_other_platforms_keep_the_tray_message(monkeypatch):
    """Windows has no StatusNotifierItem, so showMessage is fine there."""
    monkeypatch.setattr(notify.sys, "platform", "win32")
    assert notify.uses_tray_message() is True
    assert notify.send("t", "b") is False   # caller falls back to the tray


def test_gdbus_is_preferred(commands):
    runs, _ = commands
    assert notify.send("Recording", "Starting in 5s") is True
    assert runs[0][0] == "gdbus"
    assert "org.freedesktop.Notifications.Notify" in runs[0]
    assert "Recording" in runs[0] and "Starting in 5s" in runs[0]


def test_the_notification_carries_the_app_icon(commands):
    runs, _ = commands
    notify.send("t", "b")
    assert notify.ICON in runs[0]


def test_notify_send_is_the_fallback(commands):
    runs, available = commands
    available.discard("gdbus")
    assert notify.send("Recording", "Starting") is True
    assert runs[0][0] == "notify-send"


def test_no_tool_is_not_an_error(commands):
    """Without either, the caller still has the tooltip."""
    runs, available = commands
    available.clear()
    assert notify.send("t", "b") is False
    assert runs == []


def test_a_failing_tool_is_not_an_error(monkeypatch):
    def explode(*args, **kwargs):
        raise OSError("no such thing")

    monkeypatch.setattr(notify.sys, "platform", "linux")
    monkeypatch.setattr(notify.shutil, "which", lambda n: "/usr/bin/" + n)
    monkeypatch.setattr(notify.subprocess, "Popen", explode)
    assert notify.send("t", "b") is False


def test_the_call_does_not_wait(commands):
    """A wedged notification daemon must not take the tray with it.

    Popen without communicate(): if this ever becomes subprocess.run, a
    notification service that stops answering freezes the UI thread.
    """
    import inspect

    source = inspect.getsource(notify._run)
    assert "Popen" in source
    assert "communicate" not in source
    assert "subprocess.run" not in source
