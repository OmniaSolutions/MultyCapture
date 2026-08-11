"""Turn events into human-readable documentation steps.

Kept separate from any output format (docx/markdown/html) so every generator
shares one consistent phrasing.
"""

from __future__ import annotations

import re
from typing import Optional

from ..model import Event, EventType, MonitorInfo, Point, Session, ShotScope, WindowInfo

_CLICK_VERB = {"left": "Click", "right": "Right-click", "middle": "Middle-click"}

# Pretty names for non-letter keys in shortcuts / key events.
_KEY_PRETTY = {
    "enter": "Enter", "return": "Enter", "esc": "Esc", "escape": "Esc",
    "tab": "Tab", "space": "Space", "backspace": "Backspace", "delete": "Delete",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "home": "Home", "end": "End", "page_up": "PgUp", "page_down": "PgDn",
    "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "win": "Win", "cmd": "Cmd",
}


def app_label(window: Optional[WindowInfo]) -> str:
    """A short, readable name for the active application."""
    if window is None:
        return ""
    if window.title:
        return window.title
    if window.process:
        return window.process.rsplit(".", 1)[0]
    return ""


_VK_RE = re.compile(r"vk_(\d+)$")


def _pretty_key(p: str) -> str:
    """Render one key token: named keys, vk_NN codes, and Ctrl+letter control codes."""
    low = p.lower()
    if low in _KEY_PRETTY:
        return _KEY_PRETTY[low]

    m = _VK_RE.match(low)
    if m:
        n = int(m.group(1))
        if 65 <= n <= 90 or 48 <= n <= 57:   # A-Z, 0-9
            return chr(n)
        if 96 <= n <= 105:                    # numpad 0-9
            return str(n - 96)
        return f"VK{n}"

    # Ctrl+letter can arrive as a raw control code (e.g. '\x11' for Q).
    if len(p) == 1 and ord(p) < 32:
        return chr(ord(p) + 64)

    return p.upper() if len(p) == 1 else p.capitalize()


def pretty_combo(combo: str) -> str:
    return "+".join(_pretty_key(p) for p in combo.split("+") if p)


def describe(event: Event) -> str:
    """A single imperative instruction for one event."""
    app = app_label(event.window)
    in_app = f" in “{app}”" if app else ""

    if event.type == EventType.CLICK:
        verb = _CLICK_VERB.get(event.detail.button.value, "Click")
        return f"{verb}{in_app}."

    if event.type == EventType.TYPE:
        return f"Type “{event.detail.text}”{in_app}."

    if event.type == EventType.KEY:
        return f"Press {pretty_combo(event.detail.combo)}{in_app}."

    if event.type == EventType.SCROLL:
        dy, dx = event.detail.dy, event.detail.dx
        if dy < 0:
            direction = "down"
        elif dy > 0:
            direction = "up"
        elif dx < 0:
            direction = "right"
        else:
            direction = "left"
        return f"Scroll {direction}{in_app}."

    return "Action."


def is_pointed(event: Event) -> bool:
    """True if the event's mouse position marks where the action happened."""
    return event.type in (EventType.CLICK, EventType.SCROLL)


def shot_origin(session: Session, event: Event) -> Point:
    """Top-left of the captured screenshot region in virtual-desktop pixels.

    Lets a consumer map an event's absolute mouse position onto its screenshot,
    regardless of the capture scope used.
    """
    scope = session.capture_config.shot_scope
    if scope == ShotScope.WINDOW and event.window is not None:
        return Point(event.window.rect.x, event.window.rect.y)
    if scope == ShotScope.VIRTUAL_DESKTOP and session.monitors:
        return Point(
            min(m.x for m in session.monitors),
            min(m.y for m in session.monitors),
        )
    # monitor scope (default)
    for m in session.monitors:
        if m.index == event.monitor:
            return Point(m.x, m.y)
    return Point(0, 0)
