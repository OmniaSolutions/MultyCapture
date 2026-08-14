"""The two AI windows: what to send, and where to send it.

The pre-send dialog shows the *instructions* — the part worth reading and
editing — and summarises the payload rather than displaying it. The payload is
machine-written JSON: showing it invites editing it, and an edited payload is
the one thing that could put something in the document that was never captured.
"""

from __future__ import annotations

import threading
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ..ai import check, credentials, providers
from ..ai.prompt import DEFAULT as DEFAULT_PROMPT


class PromptDialog(QDialog):
    """Confirm — or reword — the instructions before they are sent."""

    def __init__(
        self, instructions: str, step_count: int, provider_label: str,
        local: bool, parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("MultyCapture — improve the wording")
        self.setMinimumSize(600, 460)

        layout = QVBoxLayout(self)

        where = (
            "stays on this machine" if local
            else "is sent to " + provider_label
        )
        summary = QLabel(
            f"{step_count} steps will be described to <b>{provider_label}</b>, "
            f"as text only — no screenshots. The wording {where}."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        layout.addWidget(QLabel("Instructions:"))
        self.editor = QPlainTextEdit(instructions)
        layout.addWidget(self.editor)

        self.remember = QCheckBox("Use this wording from now on")
        layout.addWidget(self.remember)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.button(QDialogButtonBox.Ok).setText("Send")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def instructions(self) -> str:
        return self.editor.toPlainText().strip()

    def remember_as_default(self) -> bool:
        return self.remember.isChecked()


def ask(
    instructions: str, step_count: int, provider_label: str, local: bool, parent=None
) -> tuple[bool, str, bool]:
    """Run the dialog. Returns ``(send it, instructions, remember them)``."""
    dialog = PromptDialog(instructions, step_count, provider_label, local, parent)
    if dialog.exec() != QDialog.Accepted:
        return False, instructions, False
    text = dialog.instructions() or instructions
    return True, text, dialog.remember_as_default()


class SettingsDialog(QDialog):
    """Which backend, which model, and the key to reach it."""

    def __init__(
        self, provider_id: str, model: str, base_url: str, parent=None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("MultyCapture — AI backend")
        self.setMinimumWidth(460)

        form = QFormLayout(self)

        self.provider = QComboBox()
        for pid, label, is_local in providers.CATALOG:
            self.provider.addItem(f"{label} — local" if is_local else label, pid)
        index = self.provider.findData(provider_id)
        self.provider.setCurrentIndex(max(0, index))
        self.provider.currentIndexChanged.connect(self._provider_changed)
        form.addRow("Backend:", self.provider)

        self.model = QLineEdit(model)
        form.addRow("Model:", self.model)

        self.base_url = QLineEdit(base_url)
        self.base_url.setPlaceholderText("leave empty for the default")
        # The note below depends on this field, so it follows every keystroke.
        self.base_url.textChanged.connect(self._provider_changed)
        form.addRow("Server URL:", self.base_url)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("leave empty to keep the stored key")
        form.addRow("API key:", self.api_key)

        self.key_note = QLabel()
        self.key_note.setWordWrap(True)
        form.addRow("", self.key_note)

        # A dry run, because the alternative is discovering after twenty
        # minutes that the model cannot produce the format.
        self.test_button = QPushButton("Test this backend")
        self.test_button.clicked.connect(self._start_test)
        form.addRow("", self.test_button)

        self.test_note = QLabel()
        self.test_note.setWordWrap(True)
        self.test_note.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("", self.test_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._provider_changed()

    def _provider_changed(self) -> None:
        """Reflect what the chosen backend actually needs.

        "Local" is decided from the server URL as typed, not from the backend's
        label: Ollama pointed at another machine on the network sends the
        captured text there, and saying otherwise here — in the dialog where
        that is chosen — would be a plain untruth.
        """
        pid = self.selected_provider()
        probe = self._probe(pid)
        is_local = bool(getattr(probe, "is_local", False))
        needs_key = bool(getattr(probe, "needs_key", True))

        self.api_key.setEnabled(needs_key)
        self.model.setPlaceholderText(providers.default_model(pid))

        # Two separate questions, and they do not move together: Ollama on
        # another machine needs no key and still sends the text there.
        if not needs_key:
            where = (
                "nothing leaves this machine"
                if is_local else f"the captured text is sent to {self._host()}"
            )
            self.key_note.setText(f"No key needed — {where}.")
            return

        found = credentials.source(pid)
        if found:
            self.key_note.setText(f"A key is already in use, from {found}.")
        elif credentials.keyring_available():
            self.key_note.setText("No key stored yet. It will go to the system keyring.")
        else:
            # Still storable — just in a private file rather than the OS vault.
            self.key_note.setText(
                "No system keyring here. The key will be saved to a file readable "
                "only by you."
            )

    # ------------------------------------------------------------------ #
    # trying the backend out
    # ------------------------------------------------------------------ #
    def _start_test(self) -> None:
        """Run the probe on a worker thread and poll for its answer.

        Off the UI thread deliberately: a model on a CPU-only machine can take
        minutes to answer, and a frozen dialog looks like a crash.
        """
        if getattr(self, "_test_thread", None) and self._test_thread.is_alive():
            return

        values = self.values()
        try:
            provider = providers.build(
                values["provider"],
                model=values["model"] or None,
                api_key=values["api_key"] or credentials.get(values["provider"]),
                base_url=values["base_url"] or None,
            )
        except Exception as exc:
            self.test_note.setText(f"Cannot use this backend: {exc}")
            return

        self._test_result = None
        self.test_button.setEnabled(False)
        self.test_note.setText("Asking the model to answer a two-step example…")

        def worker():
            self._test_result = check.run(provider, DEFAULT_PROMPT)

        self._test_thread = threading.Thread(target=worker, daemon=True)
        self._test_thread.start()

        self._test_timer = QTimer(self)
        self._test_timer.setInterval(400)
        self._test_timer.timeout.connect(self._poll_test)
        self._test_timer.start()

    def _poll_test(self) -> None:
        if self._test_thread.is_alive():
            return
        self._test_timer.stop()
        self.test_button.setEnabled(True)

        result = self._test_result
        if result is None:
            self.test_note.setText("The test did not finish.")
            return

        headline = (
            "Works" if result.ok
            else ("Reached, but unusable" if result.reached else "Not reached")
        )
        lines = [f"<b>{headline}</b> — {result.detail}",
                 check.advice(result)]
        if result.reply:
            lines.append(f"<i>It replied:</i> {result.reply}")
        self.test_note.setText("<br>".join(lines))

    def _probe(self, provider_id: str):
        """A backend built from the fields as they stand, to ask it about itself."""
        try:
            return providers.build(
                provider_id, base_url=self.base_url.text().strip() or None
            )
        except Exception:
            return None

    def _host(self) -> str:
        """The server as typed, for saying plainly where the text goes."""
        return self.base_url.text().strip() or "the configured server"

    def selected_provider(self) -> str:
        return self.provider.currentData()

    def values(self) -> dict:
        return {
            "provider": self.selected_provider(),
            "model": self.model.text().strip(),
            "base_url": self.base_url.text().strip(),
            "api_key": self.api_key.text().strip(),
        }


def ask_settings(
    provider_id: str, model: str, base_url: str, parent=None
) -> tuple[bool, dict]:
    """Run the backend dialog. Returns ``(saved, values)``.

    Wrapped like :func:`ask` so callers never touch a Qt enum: comparing
    ``exec()`` against ``dialog.Accepted`` — on the instance rather than the
    class — raises AttributeError under PySide6's enum handling, which is a
    crash the type checker does not catch and only a real run reveals.
    """
    dialog = SettingsDialog(provider_id, model, base_url, parent)
    if dialog.exec() != QDialog.Accepted:
        return False, {}
    return True, dialog.values()
