"""PySide6 system-tray control for MultyCapture.

A tray icon drives recording: Start (after a configurable countdown), Stop, choose
the start delay, generate a .docx from the last session, and quit. The icon colour
reflects state — idle (blue), counting down (amber, with the seconds remaining
drawn on it), and recording (red).

The Recorder already runs its input hooks on background threads, so it coexists
with the Qt event loop: the tray just calls ``start()`` / ``stop()`` and polls
``is_running`` so a hotkey-triggered stop is reflected in the UI too.
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication, QInputDialog, QMenu, QMessageBox, QSystemTrayIcon,
)

from ..capture import Recorder, SessionReader

# Preset start-delay choices (seconds) offered in the menu.
_DELAY_PRESETS = [0, 3, 5, 10]
_DEFAULT_DELAY = 5

_IDLE = "#3b82f6"       # blue
_COUNTDOWN = "#f59e0b"  # amber
_RECORDING = "#ef4444"  # red


class TrayApp:
    def __init__(self, root: str = "captures") -> None:
        self.root = root
        self.settings = QSettings("MultyCapture", "MultyCapture")
        self.start_delay = int(self.settings.value("start_delay", _DEFAULT_DELAY))

        self._recorder: Optional[Recorder] = None
        self._recording = False
        self._counting = False
        self._remaining = 0
        self._doc_thread: Optional[threading.Thread] = None
        self._doc_result: Optional[tuple[bool, str]] = None

        self.tray = QSystemTrayIcon()
        self.tray.setIcon(self._icon(_IDLE))
        self.tray.setToolTip("MultyCapture — idle")
        self.tray.activated.connect(self._on_activated)

        self._build_menu()
        self.tray.show()

        # countdown timer (1s ticks) and a state-poll timer (hotkey-stop detection)
        self._countdown = QTimer()
        self._countdown.setInterval(1000)
        self._countdown.timeout.connect(self._tick)

        self._poll = QTimer()
        self._poll.setInterval(400)
        self._poll.timeout.connect(self._poll_state)
        self._poll.start()

    # ------------------------------------------------------------------ #
    # menu
    # ------------------------------------------------------------------ #
    def _build_menu(self) -> None:
        self.menu = QMenu()

        self.act_start = QAction("Start recording", self.menu)
        self.act_start.triggered.connect(self.start_recording)
        self.menu.addAction(self.act_start)

        self.act_stop = QAction("Stop recording", self.menu)
        self.act_stop.triggered.connect(self.stop_recording)
        self.act_stop.setEnabled(False)
        self.menu.addAction(self.act_stop)

        self.menu.addSeparator()

        # start-delay submenu
        self.delay_menu = self.menu.addMenu("Start delay")
        self._delay_group = QActionGroup(self.menu)
        self._delay_group.setExclusive(True)
        self._delay_actions: dict[int, QAction] = {}
        for secs in _DELAY_PRESETS:
            act = QAction(self._delay_label(secs), self.menu, checkable=True)
            act.triggered.connect(lambda _=False, s=secs: self.set_delay(s))
            self._delay_group.addAction(act)
            self.delay_menu.addAction(act)
            self._delay_actions[secs] = act
        self.delay_menu.addSeparator()
        self.act_custom_delay = QAction("Custom…", self.menu)
        self.act_custom_delay.triggered.connect(self._ask_custom_delay)
        self.delay_menu.addAction(self.act_custom_delay)
        self._refresh_delay_checks()

        self.menu.addSeparator()

        self.act_doc = QAction("Generate .docx from last session", self.menu)
        self.act_doc.triggered.connect(self.generate_last_doc)
        self.menu.addAction(self.act_doc)

        self.act_open = QAction("Open captures folder", self.menu)
        self.act_open.triggered.connect(self._open_captures)
        self.menu.addAction(self.act_open)

        self.menu.addSeparator()

        self.act_quit = QAction("Quit", self.menu)
        self.act_quit.triggered.connect(self.quit)
        self.menu.addAction(self.act_quit)

        self.tray.setContextMenu(self.menu)

    @staticmethod
    def _delay_label(secs: int) -> str:
        return "No delay" if secs == 0 else f"{secs} seconds"

    def _refresh_delay_checks(self) -> None:
        # tick the matching preset; if the delay is custom, none are ticked
        for secs, act in self._delay_actions.items():
            act.setChecked(secs == self.start_delay)
        self.delay_menu.setTitle(f"Start delay ({self.start_delay}s)")

    # ------------------------------------------------------------------ #
    # delay setting
    # ------------------------------------------------------------------ #
    def set_delay(self, secs: int) -> None:
        self.start_delay = max(0, int(secs))
        self.settings.setValue("start_delay", self.start_delay)
        self._refresh_delay_checks()

    def _ask_custom_delay(self) -> None:
        value, ok = QInputDialog.getInt(
            None, "MultyCapture — start delay",
            "Seconds to wait before recording begins:",
            self.start_delay, 0, 600, 1,
        )
        if ok:
            self.set_delay(value)

    # ------------------------------------------------------------------ #
    # recording lifecycle
    # ------------------------------------------------------------------ #
    def start_recording(self) -> None:
        if self._recording or self._counting:
            return
        self.act_start.setEnabled(False)
        self.act_stop.setEnabled(True)
        if self.start_delay <= 0:
            self._begin()
            return
        self._counting = True
        self._remaining = self.start_delay
        self._update_countdown_icon()
        self._notify("Recording", f"Starting in {self._remaining}s…")
        self._countdown.start()

    def _tick(self) -> None:
        self._remaining -= 1
        if self._remaining > 0:
            self._update_countdown_icon()
        else:
            self._countdown.stop()
            self._counting = False
            self._begin()

    def _begin(self) -> None:
        try:
            self._recorder = Recorder(root=self.root)
            self._recorder.start()
        except Exception as exc:  # platform error, etc.
            self._recording = False
            self._reset_idle()
            self._notify("MultyCapture — could not start", str(exc),
                         QSystemTrayIcon.Critical)
            return
        self._recording = True
        self.tray.setIcon(self._icon(_RECORDING))
        self.tray.setToolTip("MultyCapture — recording")
        self._notify("Recording started", "Capturing clicks and keystrokes.")

    def stop_recording(self) -> None:
        # cancel a pending countdown
        if self._counting:
            self._countdown.stop()
            self._counting = False
            self._reset_idle()
            self._notify("Cancelled", "Recording did not start.")
            return
        if not self._recording or self._recorder is None:
            self._reset_idle()
            return
        count = self._recorder.event_count
        session_dir = self._recorder.session_dir
        self._recorder.stop()
        self._recording = False
        self._reset_idle()
        self._notify("Recording stopped", f"{count} events saved to {session_dir}")

    def _reset_idle(self) -> None:
        self.tray.setIcon(self._icon(_IDLE))
        self.tray.setToolTip("MultyCapture — idle")
        self.act_start.setEnabled(True)
        self.act_stop.setEnabled(False)

    def _poll_state(self) -> None:
        # detect a stop that came from the recorder's own hotkey
        if self._recording and self._recorder is not None and not self._recorder.is_running:
            count = self._recorder.event_count
            session_dir = self._recorder.session_dir
            self._recording = False
            self._reset_idle()
            self._notify("Recording stopped (hotkey)",
                         f"{count} events saved to {session_dir}")
        self._check_doc_result()

    # ------------------------------------------------------------------ #
    # docx generation (off the UI thread)
    # ------------------------------------------------------------------ #
    def generate_last_doc(self) -> None:
        if self._doc_thread and self._doc_thread.is_alive():
            self._notify("Please wait", "A document is already being generated.")
            return
        try:
            session_dir = str(SessionReader.latest(self.root).dir)
        except FileNotFoundError:
            self._notify("No sessions", "Record something first.",
                         QSystemTrayIcon.Warning)
            return
        self._notify("Generating .docx", "This can take a moment…")

        def worker():
            try:
                from ..generate import generate_docx
                out = generate_docx(session_dir)
                self._doc_result = (True, str(out))
            except Exception as exc:
                self._doc_result = (False, str(exc))

        self._doc_thread = threading.Thread(target=worker, daemon=True)
        self._doc_thread.start()

    def _check_doc_result(self) -> None:
        if self._doc_result is None:
            return
        ok, payload = self._doc_result
        self._doc_result = None
        if ok:
            self._notify("Document ready", payload)
        else:
            self._notify("Generation failed", payload, QSystemTrayIcon.Critical)

    # ------------------------------------------------------------------ #
    # misc
    # ------------------------------------------------------------------ #
    def _open_captures(self) -> None:
        path = Path(self.root).resolve()
        path.mkdir(parents=True, exist_ok=True)
        webbrowser.open(path.as_uri())

    def _on_activated(self, reason) -> None:
        # left-click toggles start/stop for convenience
        if reason == QSystemTrayIcon.Trigger:
            if self._recording or self._counting:
                self.stop_recording()
            else:
                self.start_recording()

    def quit(self) -> None:
        if self._recording and self._recorder is not None:
            self._recorder.stop()
        self.tray.hide()
        QApplication.instance().quit()

    def _notify(self, title: str, msg: str, icon=QSystemTrayIcon.Information) -> None:
        if QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, msg, icon, 4000)
        self.tray.setToolTip(f"{title} — {msg}")

    # ------------------------------------------------------------------ #
    # icons (drawn, no asset files needed)
    # ------------------------------------------------------------------ #
    def _update_countdown_icon(self) -> None:
        self.tray.setIcon(self._icon(_COUNTDOWN, text=str(self._remaining)))
        self.tray.setToolTip(f"MultyCapture — starting in {self._remaining}s")

    @staticmethod
    def _icon(color: str, text: Optional[str] = None) -> QIcon:
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(color))
        p.drawEllipse(6, 6, 52, 52)
        if text:
            p.setPen(QPen(QColor("white")))
            f = QFont()
            f.setPixelSize(34)
            f.setBold(True)
            p.setFont(f)
            p.drawText(pm.rect(), Qt.AlignCenter, text)
        p.end()
        return QIcon(pm)


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)  # tray-only app, no windows

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "MultyCapture",
                             "No system tray is available on this system.")
        return 1

    tray = TrayApp()  # noqa: F841 - kept alive by the event loop
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
