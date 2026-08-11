"""Condense a raw event stream into meaningful documentation steps.

The recorder is deliberately granular (every click and keystroke). Good docs are
not: a run of four Backspaces is one step, slow typing split across idle flushes
is one "Type …" step, and pointer-only arrow keys are usually noise. This module
collapses those patterns into a list of :class:`Step` objects.

A ``Step`` is the unit a future editor will manipulate: it carries a
representative event (for the screenshot and the highlight point), the rendered
instruction text, a repeat ``count``, and the original event ``seqs`` it came
from (so edits can be traced back to the capture).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..model import Event, EventType, Session
from .steps import app_label, pretty_combo

# Keys that are navigation-only; dropped when pressed without a shortcut modifier.
_NAV_KEYS = {
    "up", "down", "left", "right",
    "page_up", "page_down", "home", "end",
}
_SHORTCUT_MODS = {"ctrl", "alt", "win", "cmd"}

# Two clicks within this pixel radius (and adjacent) are treated as the same target.
_CLICK_RADIUS = 8


@dataclass
class Step:
    index: int
    event: Event                       # representative event (screenshot + point)
    instruction: str
    count: int = 1
    seqs: list[int] = field(default_factory=list)


def _in_app(event: Event) -> str:
    app = app_label(event.window)
    return f" in “{app}”" if app else ""


def _same_window(a: Event, b: Event) -> bool:
    if a.window is None or b.window is None:
        return a.window is None and b.window is None
    return a.window.pid == b.window.pid


def _is_nav_key(event: Event) -> bool:
    if event.type != EventType.KEY:
        return False
    d = event.detail
    if set(d.modifiers) & _SHORTCUT_MODS:
        return False  # e.g. Ctrl+Home is a real action, keep it
    return d.key.lower() in _NAV_KEYS


def _near(a: Event, b: Event) -> bool:
    return math.hypot(a.mouse.x - b.mouse.x, a.mouse.y - b.mouse.y) <= _CLICK_RADIUS


def _scroll_dir(event: Event) -> str:
    dy, dx = event.detail.dy, event.detail.dx
    if dy < 0:
        return "down"
    if dy > 0:
        return "up"
    if dx < 0:
        return "right"
    return "left"


def condense(session: Session, events: list[Event]) -> list[Step]:
    # Drop navigation-only keystrokes up front so surrounding runs merge cleanly.
    ev = [e for e in events if not _is_nav_key(e)]
    steps: list[Step] = []
    i, n = 0, len(ev)

    while i < n:
        e = ev[i]

        if e.type == EventType.TYPE:
            j = i
            texts: list[str] = []
            while j < n and ev[j].type == EventType.TYPE and _same_window(ev[j], e):
                texts.append(ev[j].detail.text)
                j += 1
            rep = ev[j - 1]  # last shot shows the fully typed text
            text = "".join(texts)
            steps.append(_mk(steps, rep, f"Type “{text}”{_in_app(rep)}.", j - i, ev[i:j]))
            i = j

        elif e.type == EventType.KEY:
            combo = e.detail.combo
            j = i
            while (j < n and ev[j].type == EventType.KEY
                   and ev[j].detail.combo == combo and _same_window(ev[j], e)):
                j += 1
            rep = ev[j - 1]
            cnt = j - i
            times = f" {cnt}×" if cnt > 1 else ""
            steps.append(_mk(steps, rep, f"Press {pretty_combo(combo)}{times}{_in_app(rep)}.", cnt, ev[i:j]))
            i = j

        elif e.type == EventType.CLICK:
            btn = e.detail.button
            j = i
            while (j < n and ev[j].type == EventType.CLICK
                   and ev[j].detail.button == btn
                   and _same_window(ev[j], e) and _near(ev[j], e)):
                j += 1
            rep = ev[i]  # first shot shows the target before the UI reacts
            cnt = j - i
            steps.append(_mk(steps, rep, _click_text(btn.value, cnt, rep), cnt, ev[i:j]))
            i = j

        elif e.type == EventType.SCROLL:
            direction = _scroll_dir(e)
            j = i
            while (j < n and ev[j].type == EventType.SCROLL
                   and _scroll_dir(ev[j]) == direction and _same_window(ev[j], e)):
                j += 1
            rep = ev[j - 1]  # last shot shows the final scrolled position
            steps.append(_mk(steps, rep, f"Scroll {direction}{_in_app(rep)}.", j - i, ev[i:j]))
            i = j

        else:
            i += 1

    return steps


def raw_steps(events: list[Event]) -> list[Step]:
    """One Step per event, no merging — used when condensing is disabled."""
    from .steps import describe
    out: list[Step] = []
    for idx, e in enumerate(events, start=1):
        out.append(Step(index=idx, event=e, instruction=describe(e), count=1, seqs=[e.seq]))
    return out


def _click_text(button: str, cnt: int, rep: Event) -> str:
    in_app = _in_app(rep)
    if button == "left":
        if cnt == 2:
            return f"Double-click{in_app}."
        if cnt > 2:
            return f"Click{in_app} ({cnt}×)."
        return f"Click{in_app}."
    verb = {"right": "Right-click", "middle": "Middle-click"}.get(button, "Click")
    times = f" ({cnt}×)" if cnt > 1 else ""
    return f"{verb}{in_app}{times}."


def _mk(steps: list[Step], rep: Event, instruction: str, count: int, group: list[Event]) -> Step:
    return Step(
        index=len(steps) + 1,
        event=rep,
        instruction=instruction,
        count=count,
        seqs=[e.seq for e in group],
    )
