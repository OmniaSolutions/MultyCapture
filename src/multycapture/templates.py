"""Discovery of the user's .docx templates.

A template is any ``.docx`` dropped into :func:`paths.templates_dir`. There is
no registry and no naming convention: the folder *is* the list, so adding a
template means copying a file there.
"""

from __future__ import annotations

from pathlib import Path

from . import paths


def available() -> list[Path]:
    """Every usable template, sorted by display name.

    Word writes a ``~$name.docx`` lock file next to any document it has open;
    those are not templates and are unreadable while Word holds them, so they
    are skipped.
    """
    directory = paths.templates_dir()
    try:
        found = directory.glob("*.docx")
    except OSError:
        return []
    return sorted(
        (p for p in found if p.is_file() and not p.name.startswith("~$")),
        key=lambda p: p.stem.lower(),
    )


def label(path: Path) -> str:
    """How a template is named in menus and dialogs."""
    return path.stem
