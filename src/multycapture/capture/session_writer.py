"""Writes a capture session to disk per docs/CAPTURE_SPEC.md.

Layout produced::

    <root>/session_<YYYYMMDD_HHMMSS>/
        session.json      (written on start, rewritten on close with totals)
        events.jsonl       (appended, one JSON object per line)
        shots/NNNNNN.png

The writer owns the ``seq`` counter and screenshot filenames so they always stay
in lock-step. It is deliberately dumb: it does not know how events are produced,
only how they are persisted.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from ..model import Event, Session

if TYPE_CHECKING:
    from PIL.Image import Image


class SessionWriter:
    def __init__(self, session: Session, root: os.PathLike | str) -> None:
        self.session = session
        self.dir = Path(root) / session.id
        self.shots_dir = self.dir / "shots"
        self._events_fh = None
        self._seq = 0

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def open(self) -> "SessionWriter":
        self.shots_dir.mkdir(parents=True, exist_ok=True)
        self._write_session_json()
        # line-buffered append so each event hits disk promptly (crash-safe).
        self._events_fh = open(
            self.dir / "events.jsonl", "a", encoding="utf-8", buffering=1
        )
        return self

    def close(self) -> None:
        if self._events_fh is not None:
            self._events_fh.flush()
            os.fsync(self._events_fh.fileno())
            self._events_fh.close()
            self._events_fh = None
        # rewrite session.json with end time + total, from model state.
        self._write_session_json()

    def __enter__(self) -> "SessionWriter":
        return self.open()

    def __exit__(self, *exc) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # writing
    # ------------------------------------------------------------------ #
    def next_seq(self) -> int:
        """Reserve and return the next sequence number."""
        self._seq += 1
        return self._seq

    def shot_path_for(self, seq: int) -> Path:
        return self.shots_dir / f"{seq:06d}.png"

    def save_shot(self, image: "Image", seq: int) -> str:
        """Persist a screenshot for ``seq``; return its session-relative path."""
        path = self.shot_path_for(seq)
        image.save(path, format="PNG")
        return f"shots/{path.name}"

    def append_event(self, event: Event) -> None:
        """Append one event as a JSON line and update the running count."""
        assert self._events_fh is not None, "SessionWriter not open"
        self._events_fh.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        self.session.event_count = event.seq

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _write_session_json(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.dir / "session.json.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.session.to_dict(), fh, ensure_ascii=False, indent=2)
        os.replace(tmp, self.dir / "session.json")  # atomic on Windows + POSIX
