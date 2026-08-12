"""Where MultyCapture keeps its files on each platform.

Two roots, deliberately separate:

* **Application data** — templates and captured sessions. Private to the app,
  and potentially large: one session is a screenshot per event.
* **Documents** — the generated ``.docx`` only. This is the user's own folder,
  often synced to OneDrive or a cloud drive, so nothing bulky goes here.

Both come from :mod:`platformdirs` rather than being assembled by hand, because
the obvious guesses are wrong in the two most common setups: a Documents folder
is *localised* on a non-English Linux desktop (``Documenti``, ``Dokumente``),
and redirected under OneDrive on Windows. platformdirs reads the former from
``user-dirs.dirs`` and asks the shell for the latter.

No Qt import: the capture engine and the CLI use this module too, and neither
should pull in PySide6 just to find a directory. (Qt's QStandardPaths would
otherwise do the same job.)
"""

from __future__ import annotations

from pathlib import Path

import platformdirs

APP_NAME = "MultyCapture"

# appauthor=False, or Windows nests the app under a same-named vendor folder:
# %APPDATA%\MultyCapture\MultyCapture. platformdirs defaults the author to the
# app name when it isn't given.
_dirs = platformdirs.PlatformDirs(APP_NAME, appauthor=False)


# --------------------------------------------------------------------------- #
# application data
# --------------------------------------------------------------------------- #
def data_dir() -> Path:
    """Root for app-owned data (templates, captured sessions)."""
    return Path(_dirs.user_data_dir)


def templates_dir() -> Path:
    """Where .docx templates live. May not exist yet."""
    return data_dir() / "templates"


def captures_dir() -> Path:
    """Where recorded sessions are written.

    Under application data rather than Documents: a recording is one PNG per
    event, and Documents is commonly cloud-synced.
    """
    return data_dir() / "captures"


# --------------------------------------------------------------------------- #
# documents
# --------------------------------------------------------------------------- #
def documents_dir() -> Path:
    """``<the user's Documents>/MultyCapture`` — output for generated files."""
    return Path(platformdirs.user_documents_dir()) / APP_NAME


# --------------------------------------------------------------------------- #
def ensure(path: Path) -> Path:
    """Create ``path`` (and parents) if missing; return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path
