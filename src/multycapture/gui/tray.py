"""PySide6 system-tray control for MultyCapture.

A tray icon drives recording: Start (after a configurable countdown), Stop, choose
the start delay, generate a .docx, and quit. The icon colour reflects state — idle
(blue), counting down (amber, with the seconds remaining drawn on it), and
recording (red) — the application's camera mark, tinted; see .tray_icon.

Two routes produce a document, both opening it in the system's default editor
when it is done:

* automatically when a recording stops, written to the user's documents folder
  — on by default, switched off with "Generate .docx when recording stops";
* on demand via "Generate .docx…", which asks where to put the file first and
  only then builds it.

Both routes answer the template question the same way: the "Template" submenu
either names the .docx to build on (or an explicit blank document), in which
case nothing is asked, or leaves it at "ask every time" and the chooser opens.

The Recorder already runs its input hooks on background threads, so it coexists
with the Qt event loop: the tray just calls ``start()`` / ``stop()`` and polls
``is_running`` so a hotkey-triggered stop is reflected in the UI too.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSettings
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QInputDialog, QMenu, QMessageBox, QSystemTrayIcon,
)

from .. import ai, paths, templates
from ..ai import credentials, providers
from ..capture import Recorder, SessionReader
from . import ai_dialog, notify, tray_icon
from .template_dialog import ask as ask_template

# Preset start-delay choices (seconds) offered in the menu.
_DELAY_PRESETS = [0, 3, 5, 10]
_DEFAULT_DELAY = 5

# Build and open a document as soon as a recording stops, unless switched off.
_DEFAULT_AUTO_DOC = True

# Template selection modes, stored under "template_mode".
_ASK = "ask"      # put the question to the user each time (the default)
_BLANK = "blank"  # always start from an empty document, never ask
_FILE = "file"    # always start from "template_file", never ask

_IDLE = "#3b82f6"       # blue
_COUNTDOWN = "#f59e0b"  # amber
_RECORDING = "#ef4444"  # red


class TrayApp:
    def __init__(self, root: Optional[str] = None) -> None:
        # Resolved here rather than as a default argument so tests can point it
        # somewhere else without the module-import-time value getting baked in.
        self.root = root if root is not None else str(paths.captures_dir())
        self.settings = QSettings("MultyCapture", "MultyCapture")
        self.start_delay = int(self.settings.value("start_delay", _DEFAULT_DELAY))
        self.auto_doc = self.settings.value("auto_doc", _DEFAULT_AUTO_DOC, type=bool)
        # Which .docx to build on. "ask" (the default) means put the question to
        # the user every time; the other two answer it in advance.
        self.template_mode = self.settings.value("template_mode", _ASK) or _ASK
        self.template_file: Optional[str] = self.settings.value("template_file") or None
        # AI rewording: off unless asked for, since it sends the captured text
        # somewhere unless the chosen backend is the local one.
        self.ai_enabled = self.settings.value("ai_enabled", False, type=bool)
        self.ai_provider = self.settings.value("ai_provider", providers.DEFAULT_ID)
        self.ai_model = self.settings.value("ai_model", "") or ""
        self.ai_base_url = self.settings.value("ai_base_url", "") or ""
        self.ai_prompt = self.settings.value("ai_prompt", "") or ai.DEFAULT_PROMPT
        # remembered destination for "Generate .docx…" (None until first use)
        self._last_doc_dir: Optional[str] = self.settings.value("last_doc_dir") or None

        self._recorder: Optional[Recorder] = None
        self._recording = False
        self._counting = False
        self._remaining = 0
        self._doc_thread: Optional[threading.Thread] = None
        # (succeeded, path-or-error, open-when-done), handed from worker to UI
        self._doc_result: Optional[tuple[bool, str, bool]] = None
        # set by the rewrite pass when it could not do its job
        self._ai_warning: Optional[str] = None

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

        self.act_doc = QAction("Generate .docx…", self.menu)
        self.act_doc.triggered.connect(self.generate_doc)
        self.menu.addAction(self.act_doc)

        self.act_auto_doc = QAction("Generate .docx when recording stops",
                                    self.menu, checkable=True)
        self.act_auto_doc.setChecked(self.auto_doc)
        self.act_auto_doc.toggled.connect(self.set_auto_doc)
        self.menu.addAction(self.act_auto_doc)

        # Rebuilt each time it opens: templates are just files in a folder, so
        # one dropped in while the app runs should show up without a restart.
        self.template_menu = self.menu.addMenu("Template")
        self.template_menu.aboutToShow.connect(self._rebuild_template_menu)
        self._rebuild_template_menu()

        self.ai_menu = self.menu.addMenu("AI")
        self.act_ai = QAction("Improve the wording", self.ai_menu, checkable=True)
        self.act_ai.setChecked(self.ai_enabled)
        self.act_ai.toggled.connect(self.set_ai_enabled)
        self.ai_menu.addAction(self.act_ai)
        self.act_ai_settings = QAction("Backend…", self.ai_menu)
        self.act_ai_settings.triggered.connect(self._configure_ai)
        self.ai_menu.addAction(self.act_ai_settings)
        self._refresh_ai_title()

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

    def set_auto_doc(self, on: bool) -> None:
        self.auto_doc = bool(on)
        self.settings.setValue("auto_doc", self.auto_doc)

    # ------------------------------------------------------------------ #
    # template setting
    # ------------------------------------------------------------------ #
    def _rebuild_template_menu(self) -> None:
        self.template_menu.clear()
        self._template_group = QActionGroup(self.template_menu)
        self._template_group.setExclusive(True)

        def entry(text: str, mode: str, path: Optional[str] = None) -> None:
            act = QAction(text, self.template_menu, checkable=True)
            act.setChecked(
                self.template_mode == mode
                and (mode != _FILE or self.template_file == path)
            )
            act.triggered.connect(
                lambda _=False, m=mode, p=path: self.set_template(m, p)
            )
            self._template_group.addAction(act)
            self.template_menu.addAction(act)

        entry("Ask every time", _ASK)
        entry("Blank document", _BLANK)

        found = templates.available()
        if found:
            self.template_menu.addSeparator()
            for path in found:
                entry(templates.label(path), _FILE, str(path))

        self.template_menu.addSeparator()
        act_open = QAction("Open templates folder…", self.template_menu)
        act_open.triggered.connect(self._open_templates)
        self.template_menu.addAction(act_open)

        self.template_menu.setTitle(f"Template ({self._template_label()})")

    def _template_label(self) -> str:
        if self.template_mode == _BLANK:
            return "blank document"
        if self.template_mode == _FILE and self.template_file:
            return templates.label(Path(self.template_file))
        return "ask every time"

    def set_template(self, mode: str, path: Optional[str] = None) -> None:
        self.template_mode = mode
        self.template_file = path
        self.settings.setValue("template_mode", mode)
        self.settings.setValue("template_file", path or "")
        self.template_menu.setTitle(f"Template ({self._template_label()})")

    def _resolve_template(self) -> tuple[bool, Optional[str]]:
        """Decide the template. Returns ``(go ahead, template or None)``.

        The rule is the same on both routes to a document: a configured
        template is used without asking, and no configured template means the
        question gets asked.
        """
        if self.template_mode == _BLANK:
            return True, None
        if self.template_mode == _FILE and self.template_file:
            if Path(self.template_file).is_file():
                return True, self.template_file
            # Configured template has since been deleted or renamed. Don't fail
            # the document over it — fall through and ask.
            self._notify(
                "Template not found",
                f"{Path(self.template_file).name} is gone — pick another.",
                QSystemTrayIcon.Warning,
            )
        return ask_template(templates.available())

    def _open_templates(self) -> None:
        webbrowser.open(paths.ensure(paths.templates_dir()).as_uri())

    # ------------------------------------------------------------------ #
    # AI setting
    # ------------------------------------------------------------------ #
    def _refresh_ai_title(self) -> None:
        label = next(
            (lbl for pid, lbl, _ in providers.CATALOG if pid == self.ai_provider),
            self.ai_provider,
        )
        self.ai_menu.setTitle(f"AI ({label})" if self.ai_enabled else "AI (off)")

    def set_ai_enabled(self, on: bool) -> None:
        self.ai_enabled = bool(on)
        self.settings.setValue("ai_enabled", self.ai_enabled)
        self._refresh_ai_title()

    def _configure_ai(self) -> None:
        saved, values = ai_dialog.ask_settings(
            self.ai_provider, self.ai_model, self.ai_base_url
        )
        if not saved:
            return
        self.ai_provider = values["provider"]
        self.ai_model = values["model"]
        self.ai_base_url = values["base_url"]
        for key, value in (
            ("ai_provider", self.ai_provider),
            ("ai_model", self.ai_model),
            ("ai_base_url", self.ai_base_url),
        ):
            self.settings.setValue(key, value)

        # The key is the one thing that does not go into settings.
        if values["api_key"]:
            try:
                credentials.store(self.ai_provider, values["api_key"])
            except RuntimeError as exc:
                self._notify("Could not store the key", str(exc),
                             QSystemTrayIcon.Warning)
        self._refresh_ai_title()

    def _resolve_rewrite(self, session_dir: str):
        """Build the rewording pass, asking the user to confirm the wording.

        Returns ``(go ahead, callable or None)``. The dialog runs here, on the
        UI thread, before any worker starts — a dialog cannot be opened from
        the thread that generates the document.
        """
        if not self.ai_enabled:
            return True, None

        try:
            reader = SessionReader(session_dir)
            session = reader.load_session()
            # Counting steps needs no screenshots, so this is cheap enough to
            # do here just to tell the user how much is about to be sent.
            from ..generate.condense import condense
            step_count = len(condense(session, reader.events()))
        except Exception:
            step_count = 0

        # Built before the dialog, because only the configured instance knows
        # whether the text actually stays on this machine: Ollama pointed at
        # another box on the network is not local, whatever the menu says.
        provider = providers.build(
            self.ai_provider,
            model=self.ai_model or None,
            api_key=credentials.get(self.ai_provider),
            base_url=self.ai_base_url or None,
        )

        entry = next(
            (e for e in providers.CATALOG if e[0] == self.ai_provider), None
        )
        label = entry[1] if entry else self.ai_provider
        local = bool(getattr(provider, "is_local", False))

        proceed, instructions, remember = ai_dialog.ask(
            self.ai_prompt, step_count, label, local
        )
        if not proceed:
            return False, None
        if remember:
            self.ai_prompt = instructions
            self.settings.setValue("ai_prompt", instructions)

        def rewrite(step_list, label_map) -> None:
            # Never raises: a document with the original wording beats no
            # document at all, so a failed or rejected rewrite is reported
            # afterwards and the steps are left as they were.
            try:
                message = ai.compose(instructions, ai.as_json(step_list, label_map))
                reply = provider.complete(message)
                ai.apply(step_list, ai.parse(reply, [s.index for s in step_list]))
            except (providers.ProviderError, ai.RewriteRejected) as exc:
                self._ai_warning = str(exc)
            except Exception as exc:  # unforeseen client-library failure
                self._ai_warning = f"AI rewrite failed: {exc}"

        return True, rewrite

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
        self._maybe_auto_doc(session_dir, count)

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
            self._maybe_auto_doc(session_dir, count)
        self._check_doc_result()

    # ------------------------------------------------------------------ #
    # docx generation (off the UI thread)
    # ------------------------------------------------------------------ #
    def generate_doc(self) -> None:
        """Ask where the document should go, then build it there and open it."""
        if self._doc_thread and self._doc_thread.is_alive():
            self._notify("Please wait", "A document is already being generated.")
            return
        try:
            session_dir = Path(SessionReader.latest(self.root).dir)
        except FileNotFoundError:
            self._notify("No sessions", "Record something first.",
                         QSystemTrayIcon.Warning)
            return

        # What to build on, then where to put it.
        proceed, template = self._resolve_template()
        if not proceed:
            return  # cancelled at the template step

        proceed, rewrite = self._resolve_rewrite(str(session_dir))
        if not proceed:
            return  # cancelled at the wording step

        # Ask first, build second: the .docx is assembled straight into the
        # chosen folder rather than written somewhere else and moved.
        start_at = self._last_doc_dir or str(paths.ensure(paths.documents_dir()))
        folder = QFileDialog.getExistingDirectory(
            None, "MultyCapture — save the document in…", start_at,
        )
        if not folder:
            return  # cancelled
        self._last_doc_dir = folder
        self.settings.setValue("last_doc_dir", folder)

        # the session directory is named for the session id
        out = Path(folder) / f"{session_dir.name}.docx"
        self._start_doc_job(str(session_dir), str(out), template, rewrite)

    def _maybe_auto_doc(self, session_dir, count: int) -> None:
        """Generate and open a document for a just-finished recording."""
        if not self.auto_doc:
            return
        if count <= 0:
            # nothing was captured; an empty document is worse than none
            self._notify("Nothing captured", "No events recorded, so no document.")
            return
        proceed, template = self._resolve_template()
        if not proceed:
            return  # cancelled at the template step
        proceed, rewrite = self._resolve_rewrite(str(session_dir))
        if not proceed:
            return  # cancelled at the wording step
        self._start_doc_job(str(session_dir), None, template, rewrite)

    def _start_doc_job(
        self, session_dir: str, out_path: Optional[str],
        template: Optional[str] = None, rewrite=None,
    ) -> None:
        """Build a .docx on a worker thread.

        ``out_path`` of ``None`` sends it to the user's documents folder.
        """
        if self._doc_thread and self._doc_thread.is_alive():
            self._notify("Please wait", "A document is already being generated.")
            return
        self._notify("Generating .docx", "This can take a moment…")

        def worker():
            try:
                from ..generate import generate_docx
                out = generate_docx(
                    session_dir, out_path, template=template, rewrite=rewrite
                )
                self._doc_result = (True, str(out), True)
            except Exception as exc:
                self._doc_result = (False, str(exc), False)

        self._doc_thread = threading.Thread(target=worker, daemon=True)
        self._doc_thread.start()

    def _check_doc_result(self) -> None:
        if self._doc_result is None:
            return
        ok, payload, open_when_done = self._doc_result
        self._doc_result = None
        if ok:
            warning, self._ai_warning = self._ai_warning, None
            if warning:
                # The document exists; only the rewording didn't happen.
                self._notify("Document ready (original wording)", warning,
                             QSystemTrayIcon.Warning)
            else:
                self._notify("Document ready", payload)
            if open_when_done:
                self._open_in_editor(payload)
        else:
            self._notify("Generation failed", payload, QSystemTrayIcon.Critical)

    def _open_in_editor(self, path: str) -> None:
        """Hand the file to whatever the desktop uses for .docx."""
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: SIM115 - Windows-only API
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as exc:  # no handler registered, xdg-open missing, …
            # the document exists either way, so this is not a failure
            webbrowser.open(Path(path).as_uri())
            self._notify("Could not open the document", str(exc),
                         QSystemTrayIcon.Warning)

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
        """Say something, without costing the icon.

        The tooltip always carries it. The popup goes through the notification
        service directly on Linux: routing it through the tray icon there puts
        the item into NeedsAttention and the panel replaces our mark with
        ``dialog-information`` permanently. See :mod:`.notify`.
        """
        self.tray.setToolTip(f"{title} — {msg}")

        if notify.send(title, msg):
            return
        if notify.uses_tray_message() and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, msg, icon, 4000)

    # ------------------------------------------------------------------ #
    # icons (drawn per state — see .tray_icon)
    # ------------------------------------------------------------------ #
    def _update_countdown_icon(self) -> None:
        self.tray.setIcon(self._icon(_COUNTDOWN, text=str(self._remaining)))
        self.tray.setToolTip(f"MultyCapture — starting in {self._remaining}s")

    @staticmethod
    def _icon(color: str, text: Optional[str] = None) -> QIcon:
        """The camera mark tinted for the current state.

        Idle is blue, counting down amber with the seconds in the lens, and
        recording red — so the state reads at a glance without a tooltip.
        """
        return tray_icon.build(color, text)


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
