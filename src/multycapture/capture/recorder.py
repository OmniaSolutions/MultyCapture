"""The recorder: live input hooks -> Event stream on disk.

Ties together the platform backend (window context, monitors, DPI), the grabber
(screenshots) and the session writer (persistence). Input comes from ``pynput``
global listeners, which is cross-platform on Windows and Linux/X11.

Threading model
---------------
``pynput`` delivers mouse and keyboard callbacks on their own listener threads.
Every mutation of recorder state and every write goes through ``self._lock`` so
the two listener threads plus the idle-flush timer never interleave. Screenshots
are grabbed inside the lock; ``mss`` grabs are sub-10ms so this is fine and keeps
event ordering strictly correct.

Keyboard consolidation
----------------------
Printable characters accumulate into a pending ``type`` buffer instead of emitting
one event per keystroke. The buffer is flushed — producing a single ``type`` event
plus one screenshot — when a discrete event occurs (click, shortcut, special key)
or after ``typing_idle_flush_ms`` of inactivity. Scroll events are coalesced the
same way. Modifier combos and non-printable keys are emitted as discrete ``key``
events.
"""

from __future__ import annotations

import datetime
import platform
import threading
import time
from typing import Optional

from pynput import mouse, keyboard

from ..model import (
    CaptureConfig, ClickDetail, Event, EventType, KeyboardMode, KeyDetail,
    MonitorInfo, MouseAction, MouseButton, Point, Rect, RelativePoint,
    ScrollDetail, Session, ShotScope, TypeDetail, WindowInfo,
)
from ..platform import PlatformBackend, get_backend
from .grabber import MssGrabber, ScreenGrabber
from .session_writer import SessionWriter

# Modifiers that turn a keystroke into a shortcut (shift alone does not).
_SHORTCUT_MODS = {"ctrl", "alt", "win"}

_BUTTON_MAP = {
    mouse.Button.left: MouseButton.LEFT,
    mouse.Button.right: MouseButton.RIGHT,
    mouse.Button.middle: MouseButton.MIDDLE,
}


class Recorder:
    def __init__(
        self,
        root: str = "captures",
        config: Optional[CaptureConfig] = None,
        app_version: str = "0.1.0",
        backend: Optional[PlatformBackend] = None,
        grabber: Optional[ScreenGrabber] = None,
        stop_combo: str = "ctrl+alt+q",
    ) -> None:
        self.root = root
        self.config = config or CaptureConfig()
        self.app_version = app_version
        self.backend = backend or get_backend()
        self.grabber = grabber or MssGrabber()
        self.stop_combo = stop_combo

        self._lock = threading.RLock()
        self._writer: Optional[SessionWriter] = None
        self._monitors: list[MonitorInfo] = []
        self._start_mono = 0.0

        self._mouse_listener: Optional[mouse.Listener] = None
        self._kbd_listener: Optional[keyboard.Listener] = None
        self._mouse_ctrl = mouse.Controller()

        # pending-buffer state (guarded by _lock)
        self._pending_kind: Optional[str] = None   # None | "type" | "scroll"
        self._pending_text: list[str] = []
        self._pending_scroll = [0, 0]
        self._idle_timer: Optional[threading.Timer] = None

        # modifier state (guarded by _lock)
        self._mods: set[str] = set()

        # stop hotkey (built in start(); fed via pynput's canonical() machinery)
        self._hotkey: Optional[keyboard.HotKey] = None
        self._stop_requested = False
        self._stopping = False

        self._stopped = threading.Event()

    # ------------------------------------------------------------------ #
    # lifecycle
    # ------------------------------------------------------------------ #
    def start(self) -> SessionWriter:
        self.backend.set_high_dpi_awareness()
        self._monitors = self.backend.enumerate_monitors()
        self._start_mono = time.monotonic()

        now = datetime.datetime.now()
        session = Session(
            id="session_" + now.strftime("%Y%m%d_%H%M%S"),
            created_at=now.isoformat(),
            os=platform.platform(),
            app_version=self.app_version,
            monitors=self._monitors,
            capture_config=self.config,
        )
        self._writer = SessionWriter(session, self.root).open()

        self._mouse_listener = mouse.Listener(
            on_click=self._on_click, on_scroll=self._on_scroll
        )
        self._kbd_listener = keyboard.Listener(
            on_press=self._on_press, on_release=self._on_release
        )
        # Build the stop hotkey using pynput's own parser so modifier combos are
        # matched by canonical key identity, not by an unreliable char string.
        try:
            spec = self._pynput_hotkey_spec(self.stop_combo)
            self._hotkey = keyboard.HotKey(keyboard.HotKey.parse(spec), self._trigger_stop)
        except ValueError:
            self._hotkey = None  # unparseable combo -> rely on Ctrl+C

        self._mouse_listener.start()
        self._kbd_listener.start()
        return self._writer

    def stop(self) -> None:
        with self._lock:
            if self._stopping:
                return  # idempotent: hotkey and Ctrl+C can both race here
            self._stopping = True
            self._cancel_idle_timer()
            self._flush_pending()
        if self._mouse_listener is not None:
            self._mouse_listener.stop()
        if self._kbd_listener is not None:
            self._kbd_listener.stop()
        if self._writer is not None:
            self._writer.session.ended_at = datetime.datetime.now().isoformat()
            self._writer.close()
        self.grabber.close()
        self._stopped.set()

    def wait(self) -> None:
        """Block until stop() is triggered (by the stop hotkey or externally).

        Uses a short polling wait rather than an indefinite one so a Ctrl+C
        (SIGINT) is actually delivered to the main thread on Windows, where a
        no-timeout ``Event.wait()`` swallows it.
        """
        while not self._stopped.wait(0.2):
            pass

    def _trigger_stop(self) -> None:
        """HotKey callback: request stop from off the listener thread."""
        self._stop_requested = True
        threading.Thread(target=self.stop, daemon=True).start()

    @staticmethod
    def _pynput_hotkey_spec(combo: str) -> str:
        """Convert 'ctrl+alt+q' to pynput's '<ctrl>+<alt>+q' HotKey syntax."""
        mod_map = {
            "ctrl": "<ctrl>", "control": "<ctrl>",
            "alt": "<alt>", "shift": "<shift>",
            "win": "<cmd>", "cmd": "<cmd>", "super": "<cmd>", "meta": "<cmd>",
        }
        parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
        return "+".join(mod_map.get(p, p) for p in parts)

    @property
    def session_dir(self) -> Optional[str]:
        return str(self._writer.dir) if self._writer else None

    @property
    def event_count(self) -> int:
        return self._writer.session.event_count if self._writer else 0

    @property
    def is_running(self) -> bool:
        """True while capturing; becomes False after stop() (hotkey or manual)."""
        return self._writer is not None and not self._stopping

    # ------------------------------------------------------------------ #
    # mouse callbacks
    # ------------------------------------------------------------------ #
    def _on_click(self, x: int, y: int, button, pressed: bool) -> None:
        want_down = self.config.capture_on == MouseAction.DOWN
        if pressed != want_down:
            return  # only capture the configured edge
        btn = _BUTTON_MAP.get(button, MouseButton.LEFT)
        action = MouseAction.DOWN if pressed else MouseAction.UP
        with self._lock:
            if self._stopping:
                return
            self._flush_pending()
            self._emit(
                EventType.CLICK,
                ClickDetail(btn, action, 1),
                Point(int(x), int(y)),
            )

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        with self._lock:
            if self._stopping:
                return
            if self._pending_kind == "type":
                self._flush_pending()
            self._pending_kind = "scroll"
            self._pending_scroll[0] += int(dx)
            self._pending_scroll[1] += int(dy)
            self._pending_point = Point(int(x), int(y))
            self._restart_idle_timer()

    # ------------------------------------------------------------------ #
    # keyboard callbacks
    # ------------------------------------------------------------------ #
    def _on_press(self, key) -> None:
        # Feed the stop hotkey first, outside the lock. This must see modifier
        # keys too, so it happens before the modifier early-return below.
        if self._hotkey is not None:
            try:
                self._hotkey.press(self._kbd_listener.canonical(key))
            except Exception:
                pass
            if self._stop_requested:
                return  # stop combo completed; don't record its keys

        with self._lock:
            if self._stopping:
                return
            mod = self._modifier_name(key)
            if mod is not None:
                self._mods.add(mod)
                return

            printable = self._printable_char(key)
            mode = self.config.keyboard_mode

            if printable is not None and mode == KeyboardMode.CONSOLIDATE:
                if self._pending_kind == "scroll":
                    self._flush_pending()
                self._pending_kind = "type"
                self._pending_text.append(printable)
                self._restart_idle_timer()
                return

            if printable is not None and mode == KeyboardMode.SHORTCUTS_ONLY:
                return  # ignore plain typing entirely

            # discrete key / shortcut (or every_key mode)
            self._flush_pending()
            self._emit(
                EventType.KEY,
                KeyDetail(
                    key=self._key_name(key),
                    modifiers=self._ordered_mods(),
                    combo=combo,
                ),
                self._cursor_point(),
            )

    def _on_release(self, key) -> None:
        if self._hotkey is not None:
            try:
                self._hotkey.release(self._kbd_listener.canonical(key))
            except Exception:
                pass
        with self._lock:
            mod = self._modifier_name(key)
            if mod is not None:
                self._mods.discard(mod)

    # ------------------------------------------------------------------ #
    # pending buffer
    # ------------------------------------------------------------------ #
    def _restart_idle_timer(self) -> None:
        self._cancel_idle_timer()
        secs = max(self.config.typing_idle_flush_ms, 1) / 1000.0
        self._idle_timer = threading.Timer(secs, self._on_idle_flush)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _cancel_idle_timer(self) -> None:
        if self._idle_timer is not None:
            self._idle_timer.cancel()
            self._idle_timer = None

    def _on_idle_flush(self) -> None:
        with self._lock:
            self._flush_pending()

    def _flush_pending(self) -> None:
        """Emit and clear whichever buffer is pending. Caller holds the lock."""
        kind = self._pending_kind
        if kind is None:
            return
        self._pending_kind = None
        self._cancel_idle_timer()
        if kind == "type":
            text = "".join(self._pending_text)
            self._pending_text = []
            if text:
                self._emit(EventType.TYPE, TypeDetail(text), self._cursor_point())
        elif kind == "scroll":
            dx, dy = self._pending_scroll
            self._pending_scroll = [0, 0]
            point = getattr(self, "_pending_point", None) or self._cursor_point()
            self._emit(EventType.SCROLL, ScrollDetail(dx, dy), point)

    # ------------------------------------------------------------------ #
    # emit one event (screenshot + context + write). Caller holds the lock.
    # ------------------------------------------------------------------ #
    def _emit(self, etype: EventType, detail, point: Point) -> None:
        assert self._writer is not None
        seq = self._writer.next_seq()
        window = self.backend.get_active_window()
        monitor_idx = self._monitor_index_at(point)
        region = self._region_for(point, window, monitor_idx)

        shot_rel: Optional[str] = None
        try:
            image = self.grabber.grab(region)
            shot_rel = self._writer.save_shot(image, seq)
        except Exception:
            shot_rel = None  # record the event even if the grab failed

        event = Event(
            seq=seq,
            t=time.monotonic() - self._start_mono,
            ts=datetime.datetime.now().isoformat(),
            type=etype,
            screenshot=shot_rel,
            mouse=point,
            monitor=monitor_idx,
            window=window,
            mouse_rel=self._relative(point, window),
            detail=detail,
        )
        self._writer.append_event(event)

    # ------------------------------------------------------------------ #
    # geometry helpers
    # ------------------------------------------------------------------ #
    def _monitor_index_at(self, p: Point) -> int:
        for m in self._monitors:
            if m.x <= p.x < m.x + m.width and m.y <= p.y < m.y + m.height:
                return m.index
        return 0

    def _region_for(self, point: Point, window: Optional[WindowInfo], monitor_idx: int) -> Rect:
        scope = self.config.shot_scope
        if scope == ShotScope.WINDOW and window is not None:
            return self._clamp_to_desktop(window.rect)
        if scope == ShotScope.VIRTUAL_DESKTOP and self._monitors:
            xs = [m.x for m in self._monitors]
            ys = [m.y for m in self._monitors]
            xe = [m.x + m.width for m in self._monitors]
            ye = [m.y + m.height for m in self._monitors]
            return Rect(min(xs), min(ys), max(xe) - min(xs), max(ye) - min(ys))
        # default: the monitor the action happened on
        for m in self._monitors:
            if m.index == monitor_idx:
                return Rect(m.x, m.y, m.width, m.height)
        return Rect(0, 0, 1, 1)

    def _clamp_to_desktop(self, r: Rect) -> Rect:
        if not self._monitors:
            return r
        left = min(m.x for m in self._monitors)
        top = min(m.y for m in self._monitors)
        right = max(m.x + m.width for m in self._monitors)
        bottom = max(m.y + m.height for m in self._monitors)
        x = max(left, r.x)
        y = max(top, r.y)
        w = max(1, min(r.x + r.width, right) - x)
        h = max(1, min(r.y + r.height, bottom) - y)
        return Rect(x, y, w, h)

    @staticmethod
    def _relative(point: Point, window: Optional[WindowInfo]) -> Optional[RelativePoint]:
        if window is None:
            return None
        rx = point.x - window.rect.x
        ry = point.y - window.rect.y
        nx = round(rx / window.rect.width, 3) if window.rect.width else 0.0
        ny = round(ry / window.rect.height, 3) if window.rect.height else 0.0
        return RelativePoint(rx, ry, nx, ny)

    def _cursor_point(self) -> Point:
        try:
            x, y = self._mouse_ctrl.position
            return Point(int(x), int(y))
        except Exception:
            return Point(0, 0)

    # ------------------------------------------------------------------ #
    # key parsing helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _modifier_name(key) -> Optional[str]:
        K = keyboard.Key
        if key in (K.ctrl, K.ctrl_l, K.ctrl_r):
            return "ctrl"
        if key in (K.alt, K.alt_l, K.alt_r):
            return "alt"
        if key in (K.cmd, getattr(K, "cmd_l", None), getattr(K, "cmd_r", None)):
            return "win"
        if key in (K.shift, K.shift_l, K.shift_r):
            return "shift"
        return None

    def _printable_char(self, key) -> Optional[str]:
        """Return the character this key types, or None if it is not typing.

        Returns None when a shortcut modifier (ctrl/alt/win) is held, so combos
        are treated as discrete key events rather than text.
        """
        if self._mods & _SHORTCUT_MODS:
            return None
        if key == keyboard.Key.space:
            return " "
        char = getattr(key, "char", None)
        if char is not None and char.isprintable():
            return char
        return None

    @staticmethod
    def _key_name(key) -> str:
        name = getattr(key, "name", None)
        if name:
            return name
        # With Ctrl/Alt held, key.char is often a control code (or None), so it is
        # unusable as a name. Prefer a printable char, else decode the virtual key.
        char = getattr(key, "char", None)
        if char is not None and char.isprintable():
            return char.lower()
        vk = getattr(key, "vk", None)
        if vk is not None:
            if 65 <= vk <= 90:            # A-Z
                return chr(vk).lower()
            if 48 <= vk <= 57:            # 0-9
                return chr(vk)
            if 96 <= vk <= 105:           # numpad 0-9
                return str(vk - 96)
            return f"vk_{vk}"
        return "unknown"

    def _ordered_mods(self) -> list[str]:
        order = ["ctrl", "alt", "shift", "win"]
        return [m for m in order if m in self._mods]

    def _combo_for(self, key) -> str:
        parts = self._ordered_mods() + [self._key_name(key)]
        return "+".join(parts)
