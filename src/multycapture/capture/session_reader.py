"""Reads a capture session written by :class:`SessionWriter`.

The inverse of the writer: loads ``session.json`` and streams ``events.jsonl``
back into the typed model. Consumers (doc/screencast generators) use this instead
of touching the files directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from ..model import Event, Session


class SessionReader:
    def __init__(self, session_dir: str) -> None:
        self.dir = Path(session_dir)
        if not (self.dir / "session.json").exists():
            raise FileNotFoundError(f"no session.json in {self.dir}")

    def load_session(self) -> Session:
        with open(self.dir / "session.json", encoding="utf-8") as fh:
            return Session.from_dict(json.load(fh))

    def iter_events(self) -> Iterator[Event]:
        path = self.dir / "events.jsonl"
        if not path.exists():
            return
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield Event.from_dict(json.loads(line))

    def events(self) -> list[Event]:
        return list(self.iter_events())

    def shot_path(self, rel: str | None) -> Path | None:
        """Resolve a screenshot's session-relative path to an absolute Path."""
        if not rel:
            return None
        return self.dir / rel

    @staticmethod
    def latest(root: str = "captures") -> "SessionReader":
        """Return a reader for the most recent session under ``root``."""
        root_path = Path(root)
        candidates = sorted(
            (p for p in root_path.glob("session_*") if (p / "session.json").exists()),
            key=lambda p: p.name,
        )
        if not candidates:
            raise FileNotFoundError(f"no sessions found under {root_path}")
        return SessionReader(str(candidates[-1]))
