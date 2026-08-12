"""The "which template?" chooser.

Kept out of :mod:`.tray` so it can be exercised without standing up a tray
icon, and reused from anywhere else that needs the same question answered.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem, QVBoxLayout,
)

from .. import templates

# Qt.UserRole payload for the "no template" row.
_BLANK = "__blank__"


class TemplateDialog(QDialog):
    """Pick the .docx to build on, or a blank document.

    ``selected()`` is the chosen template path, or ``None`` for a blank
    document — which is also what a rejected dialog leaves behind, so callers
    check the exec() result rather than the value to tell "blank" from
    "cancelled".
    """

    def __init__(self, found: list[Path], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MultyCapture — template")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Start the document from:"))

        self.list = QListWidget()
        blank = QListWidgetItem("Blank document")
        blank.setData(Qt.UserRole, _BLANK)
        self.list.addItem(blank)
        for path in found:
            item = QListWidgetItem(templates.label(path))
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(str(path))
            self.list.addItem(item)
        self.list.setCurrentRow(0)
        # double-click is the fast path: pick and close in one gesture
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self.list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected(self) -> Optional[str]:
        """Chosen template path, or ``None`` for a blank document."""
        item = self.list.currentItem()
        if item is None:
            return None
        value = item.data(Qt.UserRole)
        return None if value == _BLANK else value


def ask(found: list[Path], parent=None) -> tuple[bool, Optional[str]]:
    """Run the chooser. Returns ``(the user answered, template or None)``.

    With no templates installed there is nothing to choose between, so the
    dialog is skipped and a blank document is reported straight back.
    """
    if not found:
        return True, None
    dialog = TemplateDialog(found, parent)
    if dialog.exec() != QDialog.Accepted:
        return False, None
    return True, dialog.selected()
