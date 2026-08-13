"""Desktop notifications that do not break the tray icon.

``QSystemTrayIcon.showMessage`` is the obvious way to do this and cannot be
used on Linux. Under StatusNotifierItem — XFCE, KDE, GNOME-with-extension — Qt
implements it by putting the tray item into ``NeedsAttention`` and setting the
*attention icon* to the message's icon. The panel then stops drawing the
application's icon and draws ``dialog-information`` instead, and it stays that
way. Measured on the wire:

    before  Status = "Active"          AttentionIconName = ""
    after   Status = "NeedsAttention"  AttentionIconName = "dialog-information"

So the notification is sent to the notification service directly, which has no
connection to the tray item and cannot disturb it. PySide6 cannot make that
call itself: ``Notify`` wants a uint32 for ``replaces_id`` and PySide6
marshals Python integers as int32, which the service rejects outright
("(sisssasa{sv}i)" against the expected "(susssasa{sv}i)"). Hence the command
line tools, tried in turn.

When none of them is available the caller still has the tooltip, which carries
the same words. A missing popup is a small loss; an application whose icon
disappears is not.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

#: The installed icon name, so the popup carries the application's mark.
ICON = "multycapture"

DEFAULT_TIMEOUT_MS = 4000


def uses_tray_message() -> bool:
    """Whether ``QSystemTrayIcon.showMessage`` is safe on this platform.

    Only off on Linux, where it is the tray icon's undoing.
    """
    return not sys.platform.startswith("linux")


def send(title: str, body: str, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> bool:
    """Post a desktop notification. Returns whether one was actually sent."""
    if uses_tray_message():
        return False  # the caller shows it through the tray instead

    for attempt in (_via_gdbus, _via_notify_send):
        if attempt(title, body, timeout_ms):
            return True
    return False


def _via_gdbus(title: str, body: str, timeout_ms: int) -> bool:
    if not shutil.which("gdbus"):
        return False
    return _run([
        "gdbus", "call", "--session",
        "--dest", "org.freedesktop.Notifications",
        "--object-path", "/org/freedesktop/Notifications",
        "--method", "org.freedesktop.Notifications.Notify",
        "MultyCapture", "0", ICON, title, body, "[]", "{}", str(timeout_ms),
    ])


def _via_notify_send(title: str, body: str, timeout_ms: int) -> bool:
    if not shutil.which("notify-send"):
        return False
    return _run([
        "notify-send", "-a", "MultyCapture", "-i", ICON,
        "-t", str(timeout_ms), title, body,
    ])


def _run(command: list[str]) -> bool:
    """Fire the command off without waiting on it.

    Not waiting is deliberate: this is called from the UI thread, and a
    notification daemon that has wedged must not take the tray with it.
    """
    try:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        return True
    except OSError:
        return False
