# MultyCapture — Capture & Storage Specification

Version: 0.1 (draft)
Status: agreed baseline for the recorder

## 1. Concept

Every meaningful user action is recorded as an **event**. The atomic actions are:

- a **mouse click** (or scroll),
- a **keystroke** (consolidated into typed text where sensible).

Each event carries a **screenshot** plus the **context** in which it happened
(mouse position, active application window, its size and position). Replaying the
ordered event stream reconstructs the full session — this is the base layer from
which a screencast and step-by-step documentation are generated.

Nothing above this layer (screencast, Markdown/HTML docs) stores original data;
they are all *projections* of the event stream.

## 2. What triggers a capture

| Trigger                                   | Event type | Screenshot taken |
|-------------------------------------------|------------|------------------|
| Mouse button down                         | `click`    | yes (before UI reacts) |
| Mouse scroll (settled)                    | `scroll`   | yes |
| End of a typing burst                     | `type`     | yes (after burst) |
| Special key / shortcut (Enter, Tab, Ctrl+S…) | `key`   | yes |

**Screenshot timing:** captured on mouse **down**, so the shot shows the target the
user is about to act on (cursor position is stored so a highlight can be drawn
later). The *result* of the action is captured by the next event's screenshot.

**Keyboard — smart consolidation:** consecutive printable characters are buffered
into a single `type` event (`detail.text`). The buffer is flushed — producing the
event and one screenshot — when any of these occur:
- a non-character event happens (click, scroll, special key), or
- the typing goes idle for `typing_idle_flush_ms` (default 800 ms).

Modifier combos and non-printable keys (Enter, Tab, Esc, arrows, Ctrl+S, …) are
recorded as discrete `key` events and are never merged into a `type` buffer.

## 3. What each screenshot captures

**Scope = active monitor.** The full image of the monitor where the action
occurred is stored, and the active window's rect is recorded alongside it. This
lets later stages crop to the window, zoom to the cursor, or show the full monitor
without re-capturing. Format: PNG (lossless), one file per event.

## 4. Platform abstraction & context acquisition

MultyCapture targets **Windows and Linux**. The recorder never calls an OS API
directly; it talks to a `PlatformBackend` interface, and a factory selects the
concrete backend at runtime. This keeps all OS-specific code in one place and
makes the recorder identical across platforms.

The backend provides three capabilities:

1. `set_high_dpi_awareness()` — make coordinates/screenshots consistent on scaled displays.
2. `enumerate_monitors()` → list of `MonitorInfo` (geometry, primary flag, scale).
3. `get_active_window()` → `WindowInfo` (title, process, pid, rect) or `None`.

Screenshots and global input hooks are handled by cross-platform libraries
(`mss` and `pynput`) shared across backends; only the three capabilities above are
per-OS.

### 4.1 Windows backend
- `GetForegroundWindow()` → HWND
- `GetWindowText(hwnd)` → title
- `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` (fallback `GetWindowRect`) → rect
- `GetWindowThreadProcessId(hwnd)` → PID → process image name (e.g. `Code.exe`)
- `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)` at startup
- Deps: `pywin32` (or pure `ctypes`)

### 4.2 Linux backend (X11)
- Active window via EWMH: `_NET_ACTIVE_WINDOW`
- Title via `_NET_WM_NAME` / `WM_NAME`
- Geometry via `get_geometry()` + translate-to-root for absolute rect
- PID via `_NET_WM_PID`; process name from `/proc/<pid>/comm`
- DPI/scale: read from X resources / RandR; X11 is typically unscaled (scale 1.0)
- Deps: `python-xlib`, `ewmh`

### 4.3 Wayland
Not supported for capture. Wayland blocks global input hooks and cross-window
geometry reads by design. On startup the Linux factory detects the session type
(`XDG_SESSION_TYPE` / `WAYLAND_DISPLAY`); under Wayland it raises a clear,
actionable error asking the user to log into an **Xorg/X11** session. A future
Wayland backend could use `xdg-desktop-portal` (with per-capture user consent) but
is out of scope for v0.1.

### 4.4 Coordinate conventions
Monitor index is resolved from the cursor position against the enumerated
monitors. All coordinates are **physical pixels** of the virtual desktop;
consumers must not assume any particular DPI.

## 5. Storage layout

```
captures/
  session_<YYYYMMDD_HHMMSS>/
    session.json        # session metadata (screen config, OS, settings)
    events.jsonl        # append-only, one JSON object per line
    shots/
      000001.png
      000002.png
      ...
```

`events.jsonl` is **JSON Lines**: each event is appended as a single line the
moment it is recorded. This is crash-safe (a kill mid-session loses at most the
in-flight event), streamable, and diff-friendly. Screenshots are referenced by
relative path and never inlined.

## 6. session.json

```jsonc
{
  "id": "session_20260811_143022",
  "created_at": "2026-08-11T14:30:22.123456",  // ISO-8601, local
  "os": "Windows-11-10.0.22000",                // platform.platform(); Linux e.g. "Linux-6.8.0-x11"
  "platform": "windows",                         // windows | linux  (backend family)
  "app_version": "0.1.0",
  "monitors": [
    { "index": 0, "x": 0, "y": 0, "width": 2560, "height": 1440,
      "primary": true, "scale": 1.5 }
  ],
  "capture_config": {
    "shot_scope": "monitor",          // monitor | window | virtual_desktop
    "image_format": "png",
    "keyboard_mode": "consolidate",   // consolidate | every_key | shortcuts_only
    "typing_idle_flush_ms": 800,
    "capture_on": "mouse_down"        // mouse_down | mouse_up
  },
  "ended_at": null,                    // filled on clean stop
  "event_count": 0                     // filled on clean stop
}
```

## 7. Event schema (events.jsonl)

Common envelope for every event:

```jsonc
{
  "seq": 42,                            // 1-based, monotonic within session
  "t": 3.482,                           // seconds since session start (monotonic clock)
  "ts": "2026-08-11T14:30:25.605",      // wall-clock ISO-8601
  "type": "click",                      // click | scroll | type | key
  "screenshot": "shots/000042.png",     // relative to session dir; null if capture failed

  "mouse":   { "x": 1204, "y": 806 },   // absolute, virtual-desktop pixels
  "monitor": 0,                         // monitor index the action occurred on

  "window": {                           // null if no foreground window resolvable
    "title":   "main.py — Visual Studio Code",
    "process": "Code.exe",
    "pid":     12345,
    "rect":    { "x": 100, "y": 50, "width": 1600, "height": 1200 }
  },

  "mouse_rel": {                        // relative to window; null if window is null
    "x": 1104, "y": 756,                // pixels from window top-left
    "nx": 0.69, "ny": 0.63             // normalized 0..1 within window (resolution-independent)
  },

  "detail": { /* type-specific, see below */ }
}
```

### detail by type

```jsonc
// click
"detail": { "button": "left", "action": "down", "click_count": 1 }
// button: left | right | middle
// action: down | up
// click_count: 1 (single) | 2 (double)

// scroll
"detail": { "dx": 0, "dy": -3 }        // wheel deltas; negative dy = scroll down

// type  (consolidated printable characters)
"detail": { "text": "hello world" }

// key   (special / shortcut)
"detail": { "key": "s", "modifiers": ["ctrl"], "combo": "ctrl+s" }
// key: canonical key name (single char or name like "enter", "tab", "esc", "up")
// modifiers: subset of ["ctrl","alt","shift","win"] (ordered as listed)
// combo: normalized human-readable shortcut string
```

## 8. Invariants

- `seq` is strictly increasing with no gaps; `shots/NNNNNN.png` matches `seq`.
- Every event line is independently valid JSON (no trailing commas, one per line).
- Coordinates are physical pixels; consumers must not assume 96 DPI.
- A missing screenshot sets `screenshot: null` but the event is still recorded.
- Privacy note: `type.text` may contain sensitive input (passwords). A future
  redaction pass may mask events whose target window/field is flagged; the raw
  recorder does **not** filter by default. (Tracked for later.)

## 9. Out of scope for this layer

Screencast rendering, step de-duplication, annotation, and doc generation all read
this event stream and are specified separately. This document governs only how raw
capture data is produced and stored.
