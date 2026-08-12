"""The two AI windows: what to send, and where to send it.

The pre-send dialog shows the *instructions* — the part worth reading and
editing — and summarises the payload rather than displaying it. The payload is
machine-written JSON: showing it invites editing it, and an edited payload is
the one thing that could put something in the document that was never captured.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
    QLineEdit, QPlainTextEdit, QVBoxLayout,
)

from ..ai import credentials, providers


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
        form.addRow("Server URL:", self.base_url)

        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("leave empty to keep the stored key")
        form.addRow("API key:", self.api_key)

        self.key_note = QLabel()
        self.key_note.setWordWrap(True)
        form.addRow("", self.key_note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        self._provider_changed()

    def _provider_changed(self) -> None:
        """Reflect what the chosen backend actually needs."""
        pid = self.selected_provider()
        entry = next((e for e in providers.CATALOG if e[0] == pid), None)
        is_local = bool(entry and entry[2])

        self.api_key.setEnabled(not is_local)
        self.model.setPlaceholderText(providers.default_model(pid))

        if is_local:
            self.key_note.setText("Runs on this machine — no key, nothing sent out.")
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

    def selected_provider(self) -> str:
        return self.provider.currentData()

    def values(self) -> dict:
        return {
            "provider": self.selected_provider(),
            "model": self.model.text().strip(),
            "base_url": self.base_url.text().strip(),
            "api_key": self.api_key.text().strip(),
        }
