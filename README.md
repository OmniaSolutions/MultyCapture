# MultyCapture

Fast-track screencasts into step-by-step documentation. MultyCapture records
every mouse click and keystroke — each with a screenshot and the active
application's window context — into a compact, replayable event stream. That
stream is the base layer from which screencasts and Markdown/HTML documentation
are generated.

## Status

Early development (v0.1). The **capture engine** is implemented and working:

- Cross-platform capture layer (Windows via pure `ctypes`; Linux/X11 via
  `python-xlib`). Wayland is detected and refused with instructions to switch to
  an Xorg session.
- Screenshot grabber behind a swappable interface (`mss` today; a Qt grabber can
  be dropped in later).
- Recorder with smart keyboard consolidation (typed text batched; shortcuts and
  special keys kept discrete) and scroll coalescing.
- Append-only, crash-safe session storage (`events.jsonl` + `shots/`).

See [docs/CAPTURE_SPEC.md](docs/CAPTURE_SPEC.md) for the full data & storage spec.

## Platform support

| Platform      | Status                                             |
|---------------|----------------------------------------------------|
| Windows 10/11 | Supported (no extra system deps)                   |
| Linux / X11   | Supported (`python-xlib`, `ewmh`)                  |
| Linux/Wayland | Not supported — log into an Xorg/X11 session       |

## Quick start

```bash
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1
# Linux:    source .venv/bin/activate
pip install -e .
```

### System tray (recommended)

```bash
mc tray
```

Runs a PySide6 tray icon. Left-click (or the menu) to **Start** / **Stop**.
Starting waits a configurable **start delay** (default 5s) so you can get to the
right window first — the icon shows an amber countdown, then turns red while
recording. Change the delay under **Start delay** in the menu (presets or
*Custom…*); the choice is remembered.

When a recording stops, the `.docx` is generated and opened in your default
editor. Turn that off with **Generate .docx when recording stops** — the choice
is remembered. **Generate .docx…** builds one on demand: it asks for a
destination folder first, writes the document there, then opens it. The menu
also opens the captures folder.

### Command line

Record a session (stop with Ctrl+Alt+Q or Ctrl+C):

```bash
mc record
```

Options:

```
mc record --out captures --scope monitor --keyboard consolidate --stop ctrl+alt+q
```

- `--scope`: `monitor` (default) | `window` | `virtual_desktop`
- `--keyboard`: `consolidate` (default) | `every_key` | `shortcuts_only`

Output lands in `captures/session_<timestamp>/`.
