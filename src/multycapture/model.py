"""Capture data model for MultyCapture.

This module is the single source of truth for the on-disk schema described in
``docs/CAPTURE_SPEC.md``. The recorder produces these objects; every consumer
(screencast builder, doc generator) reads them back.

Design goals:
- Plain dataclasses, no third-party deps, so any part of the app can import them.
- ``to_dict`` / ``from_dict`` round-trip losslessly to the JSON/JSONL on disk.
- ``None`` is a valid, meaningful value (e.g. no foreground window, failed shot).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


SCHEMA_VERSION = "0.1"


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #

class EventType(str, Enum):
    CLICK = "click"
    SCROLL = "scroll"
    TYPE = "type"
    KEY = "key"


class MouseButton(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class MouseAction(str, Enum):
    DOWN = "down"
    UP = "up"


class ShotScope(str, Enum):
    MONITOR = "monitor"
    WINDOW = "window"
    VIRTUAL_DESKTOP = "virtual_desktop"


class KeyboardMode(str, Enum):
    CONSOLIDATE = "consolidate"
    EVERY_KEY = "every_key"
    SHORTCUTS_ONLY = "shortcuts_only"


# --------------------------------------------------------------------------- #
# Geometry primitives
# --------------------------------------------------------------------------- #

@dataclass
class Point:
    x: int
    y: int

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Point":
        return cls(x=d["x"], y=d["y"])


@dataclass
class Rect:
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Rect":
        return cls(x=d["x"], y=d["y"], width=d["width"], height=d["height"])


@dataclass
class RelativePoint:
    """Mouse position relative to the active window.

    ``x``/``y`` are pixels from the window's top-left; ``nx``/``ny`` are the same
    point normalized to 0..1 within the window, so it survives a resolution change.
    """
    x: int
    y: int
    nx: float
    ny: float

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "nx": self.nx, "ny": self.ny}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RelativePoint":
        return cls(x=d["x"], y=d["y"], nx=d["nx"], ny=d["ny"])


# --------------------------------------------------------------------------- #
# Context objects
# --------------------------------------------------------------------------- #

@dataclass
class WindowInfo:
    title: str
    process: str
    pid: int
    rect: Rect

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "process": self.process,
            "pid": self.pid,
            "rect": self.rect.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WindowInfo":
        return cls(
            title=d["title"],
            process=d["process"],
            pid=d["pid"],
            rect=Rect.from_dict(d["rect"]),
        )


@dataclass
class MonitorInfo:
    index: int
    x: int
    y: int
    width: int
    height: int
    primary: bool = False
    scale: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "primary": self.primary,
            "scale": self.scale,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "MonitorInfo":
        return cls(
            index=d["index"],
            x=d["x"],
            y=d["y"],
            width=d["width"],
            height=d["height"],
            primary=d.get("primary", False),
            scale=d.get("scale", 1.0),
        )


# --------------------------------------------------------------------------- #
# Event-detail variants
# --------------------------------------------------------------------------- #
# ``detail`` is a small type-specific payload. We keep the variants as separate
# dataclasses for clarity but serialize them to a plain dict; the parent event's
# ``type`` field determines how to read them back.

@dataclass
class ClickDetail:
    button: MouseButton
    action: MouseAction
    click_count: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "button": self.button.value,
            "action": self.action.value,
            "click_count": self.click_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ClickDetail":
        return cls(
            button=MouseButton(d["button"]),
            action=MouseAction(d["action"]),
            click_count=d.get("click_count", 1),
        )


@dataclass
class ScrollDetail:
    dx: int
    dy: int

    def to_dict(self) -> dict[str, Any]:
        return {"dx": self.dx, "dy": self.dy}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScrollDetail":
        return cls(dx=d["dx"], dy=d["dy"])


@dataclass
class TypeDetail:
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TypeDetail":
        return cls(text=d["text"])


@dataclass
class KeyDetail:
    key: str
    modifiers: list[str] = field(default_factory=list)
    combo: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "modifiers": list(self.modifiers), "combo": self.combo}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "KeyDetail":
        return cls(
            key=d["key"],
            modifiers=list(d.get("modifiers", [])),
            combo=d.get("combo", ""),
        )


_DETAIL_PARSERS = {
    EventType.CLICK: ClickDetail.from_dict,
    EventType.SCROLL: ScrollDetail.from_dict,
    EventType.TYPE: TypeDetail.from_dict,
    EventType.KEY: KeyDetail.from_dict,
}


# --------------------------------------------------------------------------- #
# The event
# --------------------------------------------------------------------------- #

@dataclass
class Event:
    """One recorded user action — a single line in ``events.jsonl``."""

    seq: int
    t: float                       # seconds since session start (monotonic)
    ts: str                        # wall-clock ISO-8601
    type: EventType
    screenshot: Optional[str]      # relative path, or None if capture failed
    mouse: Point                   # absolute, virtual-desktop pixels
    monitor: int
    window: Optional[WindowInfo]
    mouse_rel: Optional[RelativePoint]
    detail: Any                    # one of the *Detail dataclasses above

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "t": round(self.t, 3),
            "ts": self.ts,
            "type": self.type.value,
            "screenshot": self.screenshot,
            "mouse": self.mouse.to_dict(),
            "monitor": self.monitor,
            "window": self.window.to_dict() if self.window else None,
            "mouse_rel": self.mouse_rel.to_dict() if self.mouse_rel else None,
            "detail": self.detail.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Event":
        etype = EventType(d["type"])
        return cls(
            seq=d["seq"],
            t=d["t"],
            ts=d["ts"],
            type=etype,
            screenshot=d.get("screenshot"),
            mouse=Point.from_dict(d["mouse"]),
            monitor=d["monitor"],
            window=WindowInfo.from_dict(d["window"]) if d.get("window") else None,
            mouse_rel=RelativePoint.from_dict(d["mouse_rel"]) if d.get("mouse_rel") else None,
            detail=_DETAIL_PARSERS[etype](d["detail"]),
        )


# --------------------------------------------------------------------------- #
# Session metadata (session.json)
# --------------------------------------------------------------------------- #

@dataclass
class CaptureConfig:
    shot_scope: ShotScope = ShotScope.MONITOR
    image_format: str = "png"
    keyboard_mode: KeyboardMode = KeyboardMode.CONSOLIDATE
    typing_idle_flush_ms: int = 800
    capture_on: MouseAction = MouseAction.DOWN

    def to_dict(self) -> dict[str, Any]:
        return {
            "shot_scope": self.shot_scope.value,
            "image_format": self.image_format,
            "keyboard_mode": self.keyboard_mode.value,
            "typing_idle_flush_ms": self.typing_idle_flush_ms,
            "capture_on": self.capture_on.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CaptureConfig":
        return cls(
            shot_scope=ShotScope(d.get("shot_scope", "monitor")),
            image_format=d.get("image_format", "png"),
            keyboard_mode=KeyboardMode(d.get("keyboard_mode", "consolidate")),
            typing_idle_flush_ms=d.get("typing_idle_flush_ms", 800),
            capture_on=MouseAction(d.get("capture_on", "down")),
        )


@dataclass
class Session:
    id: str
    created_at: str
    os: str
    app_version: str
    monitors: list[MonitorInfo] = field(default_factory=list)
    capture_config: CaptureConfig = field(default_factory=CaptureConfig)
    ended_at: Optional[str] = None
    event_count: int = 0
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "os": self.os,
            "app_version": self.app_version,
            "schema_version": self.schema_version,
            "monitors": [m.to_dict() for m in self.monitors],
            "capture_config": self.capture_config.to_dict(),
            "ended_at": self.ended_at,
            "event_count": self.event_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Session":
        return cls(
            id=d["id"],
            created_at=d["created_at"],
            os=d["os"],
            app_version=d["app_version"],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
            monitors=[MonitorInfo.from_dict(m) for m in d.get("monitors", [])],
            capture_config=CaptureConfig.from_dict(d.get("capture_config", {})),
            ended_at=d.get("ended_at"),
            event_count=d.get("event_count", 0),
        )
