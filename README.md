# MultyCapture

Do something once; get a written procedure out of it.

MultyCapture records every mouse click and keystroke — each with a screenshot
and the active window's context — and turns that into a numbered Word document
with the screenshots in place:

> **Step 4**
> Click "Save" in "Orders".
> "Save changes?" appears.

Both lines are written without any AI: the first from the recorded event, the
second by comparing the screenshots either side of the step.

**→ [User Guide](docs/USER_GUIDE.md)** — installing, where your files go, what
is optional, and the AI features.

## Platform support

| Platform | Status |
|---|---|
| Windows 10/11 | Supported, no extra system dependencies |
| Linux / X11 | Supported |
| Linux / Wayland | Not supported — log into an Xorg session |

Wayland does not let one application observe another's windows or read the
pointer globally. MultyCapture detects it and refuses to start rather than
recording something useless.

## Quick start

Install the `.deb` or the Windows installer, then run **MultyCapture** — or
from a source checkout:

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .
mc tray
```

Left-click the tray icon to start; **Ctrl+Alt+Q** stops. There is a 5-second
start delay so you can get to the right window first. When you stop, the
document is written to `Documents/MultyCapture` and opened.

### Command line

```bash
mc record        # stop with Ctrl+Alt+Q or Ctrl+C
mc doc --last    # build a document from the most recent recording
```

Full options in the [User Guide](docs/USER_GUIDE.md#command-line).

## Optional extras

- **`tesseract-ocr`** makes steps name what was clicked — `Click "Save"…`
  rather than `Click in…`. Recommended by the `.deb`, not required; without it
  nothing fails and the steps are simply less specific.
- **An AI model** can improve the wording of the steps, and nothing else. Off
  by default, because it can send your captured text off the machine. Nothing
  needs installing for it: every backend (Ollama, Claude, OpenAI-compatible,
  Gemini) is reached over plain HTTP.

## Documentation

| | |
|---|---|
| [USER_GUIDE.md](docs/USER_GUIDE.md) | How to use it, and what it does with your files |
| [CAPTURE_SPEC.md](docs/CAPTURE_SPEC.md) | The event stream and storage format |
| [decisions.md](docs/decisions.md) | Why it is built this way, and what was tried and dropped |

## Development

```bash
pip install -e ".[test]"
pytest                          # Linux: xvfb-run -a pytest
```

The version lives in `src/multycapture/_version.py` and nowhere else; the
packaging scripts read it with `installer/version.sh`, and CI refuses to build
a tag that disagrees with it.
