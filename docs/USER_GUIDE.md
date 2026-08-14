# MultyCapture — User Guide

Applies to version 0.2.0.

MultyCapture watches you do something once and writes down how you did it. It
records every click and keystroke with a screenshot and the name of the window
you were in, then turns that into a numbered Word document with the screenshots
in place.

This guide covers the things you cannot work out by clicking around: where your
files go, what is optional and what you lose by not having it, and what happens
to your text if you switch the AI on.

---

## Contents

1. [Installing](#installing)
2. [Recording](#recording)
3. [The document you get](#the-document-you-get)
4. [Where everything is kept](#where-everything-is-kept)
5. [Templates](#templates)
6. [Click labels, and the optional OCR](#click-labels-and-the-optional-ocr)
7. [Improving the wording with an AI model](#improving-the-wording-with-an-ai-model)
8. [The log](#the-log)
9. [Command line](#command-line)
10. [When something goes wrong](#when-something-goes-wrong)

---

## Installing

**Debian / Ubuntu**

```bash
sudo dpkg -i multycapture_0.2.0_amd64.deb
sudo apt-get -f install      # only if dpkg reports missing dependencies
```

**Windows** — run the installer. It offers to start MultyCapture with Windows;
that is a shortcut in the Startup folder, which you can remove later without
uninstalling.

**From source** (any platform):

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -e .
mc tray
```

### X11 only

On Linux, MultyCapture needs an **Xorg** session. Wayland does not let one
application see another's windows or read the pointer globally — that is a
deliberate security boundary, not something an application can work around — so
MultyCapture detects Wayland and refuses to start rather than recording
something useless. Log out and pick "Xorg" or "X11" on the login screen.

### One optional package

`tesseract-ocr` is **recommended, not required**. Without it everything works
and the steps simply do not name what you clicked; see
[Click labels](#click-labels-and-the-optional-ocr). On Debian/Ubuntu:

```bash
sudo apt-get install tesseract-ocr
```

**Nothing needs to be installed for the AI features.** MultyCapture talks to
every backend over plain HTTP, so there is no `pip install anthropic` or
similar — see [Improving the wording](#improving-the-wording-with-an-ai-model).

---

## Recording

Start the tray application (`mc tray`, or the desktop entry). The icon is a
camera: **blue** when idle, **amber** while counting down with the seconds shown
in the lens, **red** while recording.

- **Start recording** — or left-click the icon. There is a **start delay**
  (5 seconds by default) so you can get to the right window first. Change it
  under **Start delay**; presets, or *Custom…*.
- **Stop recording** — from the menu, or press **Ctrl+Alt+Q** from anywhere.
- When a recording stops, the document is generated and opened in whatever your
  desktop uses for `.docx`. Turn that off with **Generate .docx when recording
  stops**.
- An empty recording produces no document. Opening an editor on a document with
  no steps in it is worse than doing nothing.

Keystrokes are consolidated: typing `ACME Ltd` is one step that says so, rather
than eight. Shortcuts and special keys — Enter, Tab, Ctrl+S — stay separate,
because they are actions rather than text.

---

## The document you get

Each step is a heading, a sentence, and the screenshot taken at the moment of
the click, with the click point highlighted. A step reads like this:

> **Step 4**
> Click "Save" in "Orders".
> "Save changes?" appears.

The first line says what you did. The second says what happened, and comes from
comparing that screenshot with the next one — the two images a reader has in
front of them. It is on by default and needs no AI. Turn it off with
`--no-outcomes` on the command line.

The last step never has an outcome line, because there is no later screenshot to
compare against.

---

## Where everything is kept

| What | Linux | Windows |
|---|---|---|
| Generated documents | `~/Documents/MultyCapture` | `Documents\MultyCapture` |
| Recordings | `~/.local/share/MultyCapture/captures` | `%LOCALAPPDATA%\MultyCapture\captures` |
| Templates | `~/.local/share/MultyCapture/templates` | `%LOCALAPPDATA%\MultyCapture\templates` |
| Log | `~/.local/share/MultyCapture/logs` | `%LOCALAPPDATA%\MultyCapture\logs` |

(Windows and Linux are the supported platforms; MultyCapture refuses to start
anywhere else.)

Documents and recordings are deliberately apart. A recording is one screenshot
per event and can run to hundreds of megabytes; your Documents folder is often
synced to OneDrive or a cloud drive, and that is not somewhere to put them.

If your desktop is not in English, the Documents folder is found by its real
name — `Documenti`, `Dokumente` — rather than creating a second `Documents`
beside it. On Windows a Documents folder redirected into OneDrive is followed
correctly.

**Recordings are never deleted automatically.** Use **Open captures folder** in
the menu and remove the ones you no longer need.

---

## Templates

Put any `.docx` into the templates folder — **Open templates folder…** in the
Template submenu takes you there — and it is a template. There is no import
step and no list to maintain: the folder *is* the list.

The template's **content is kept**, not only its styles. A cover page, a header,
a preamble — all of it survives, and the generated steps are appended after a
page break.

Choosing one, under **Template**:

- Pick a template (or **Blank document**) and it is used every time, silently.
- Leave it on **Ask every time** and you are asked at each generation,
  including when a recording stops.
- With no templates installed you are never asked. A dialog offering one
  option is not a choice.

If a template you selected is later deleted or renamed, MultyCapture falls back
to asking rather than failing the document.

A template that lacks Word's `Title` and `Heading` styles still works — the
headings are written in bold instead of styled. Company templates are often
built by cleaning up an old document, and Word drops styles that nothing is
using.

---

## Click labels, and the optional OCR

With `tesseract-ocr` installed, MultyCapture reads the text under each click and
names it:

| | |
|---|---|
| without OCR | `Click in "Orders".` |
| with OCR | `Click "Save" in "Orders".` |

That is the whole difference. Nothing else changes, nothing fails, and no
warning is shown — the documents are simply less specific. The reading is done
while the document is generated, not while recording, so it never costs you
dropped events.

It reads a small region around the click rather than the whole screen, so it
returns the button you pressed instead of a paragraph of surrounding menus.
Expect it to miss occasionally: icon-only buttons have no text to read, and very
low-contrast themes are hard.

Turn it off for a faster generation with `--no-ocr`.

---

## Improving the wording with an AI model

**Off by default, and it is the only feature that is.** Everything else added
recently is on, because nothing else has consequences beyond your document. This
one can send your captured text to another computer, and that is not a decision
to make on your behalf.

### What is sent, and what is not

Only the **step sentences** — the text you can read in the document. No
screenshots, no mouse coordinates, no file paths, no window handles.

Note what that includes: the step sentences contain **whatever you typed while
recording**. If you typed a password, a customer name or an internal reference,
it is in there. That is the reason for the confirmation dialog before each send.

### What the model is allowed to do

Reword steps, and nothing else. It cannot merge, split, reorder, drop or invent
steps. A reply that tries is **rejected whole** — never applied in part — and
the document is written with your original wording. A partly-rewritten document
is much harder to notice than one that plainly was not rewritten.

So a failed rewrite costs you the rewording and nothing else. You always get a
document.

### Choosing a backend

**AI → Backend…**

| Backend | Key needed | Where the text goes |
|---|---|---|
| Ollama | no | the machine you point it at |
| Claude (Anthropic) | yes | Anthropic |
| OpenAI-compatible | yes | whichever URL you set |
| Gemini (Google) | yes | Google |

"OpenAI-compatible" is one backend for many services — OpenAI, Groq, DeepSeek,
Mistral, OpenRouter, LM Studio — because they speak the same protocol and only
the URL differs. Presets are in the dropdown.

**"Local" means the text stays on this computer, not "Ollama".** An Ollama
server on another machine on your network needs no key but is *not* local, and
the dialog says so. It tells you where your text is actually going, not what
kind of software is receiving it.

### Keys

Whatever you type is stored in your system keyring. If there is no keyring —
common on a minimal Linux install, and inside the packaged Windows build — it
goes to a file readable only by you, and the dialog tells you which happened.
On Linux that file is created owner-only; on Windows it is inside your profile
folder, which other accounts cannot read.

**Keys are never written to the settings**, which are the registry on Windows
and a plain text file on Linux.

Before asking, MultyCapture looks for a key you already have, in this order:

1. `MULTYCAPTURE_CLAUDE_API_KEY`, `MULTYCAPTURE_OPENAI_API_KEY`,
   `MULTYCAPTURE_GEMINI_API_KEY` — explicit, for keeping a MultyCapture key
   separate from your shell's.
2. The service's usual variable: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
   `GOOGLE_API_KEY`.
3. The system keyring.
4. The private file.

If one of these is already set you are not asked to type anything, and the
dialog says where the key was found.

### Test it before you rely on it

The **Test this backend** button sends two invented steps and reports one of
three things, because their remedies have nothing in common:

- **Not reached** — wrong address, service not running, or the model has not
  been pulled.
- **Reached, but unusable** — the server answers, but this model does not
  produce the requested format, so every rewrite will be refused. It shows you
  what the model actually replied. A larger model usually fixes it.
- **Works** — with an estimate of how long a real procedure would take.

That estimate is worth reading. A model without a GPU behind it can be very
slow: one measured during development managed 0.66 tokens a second, which is
about twenty minutes for a twelve-step procedure *before the model starts
answering*. This is why the Ollama timeout is an hour — that wait is normal for
self-hosted hardware, not a fault. If the estimate is unacceptable, use a
smaller model (`ollama pull qwen2.5:1.5b`) or a hosted backend.

### Each run

With **Improve the wording** on, you see the instructions before every send and
can edit them for that run, or keep the new version as your default. The payload
itself is summarised rather than shown: it is machine-written, and an edited
payload is the one thing that could put text in your document that was never
captured.

---

## The log

**Open log** in the menu. It records what happened on each rewrite: the size of
the request, how long the model took, and — when a reply is rejected — **what
the model actually said**. That reply is usually the whole answer. The common
case is a model that writes

> Certainly! Here are the improved steps:
> 1. Click Save

instead of the structured format it was asked for. The rewrite is refused, your
document keeps its original wording, and the log is where you find out why.

The file is capped at 1 MB and rotated, so it will not grow without bound.

For much more detail — the full request and every reply, not just rejected ones
— start MultyCapture with `MULTYCAPTURE_DEBUG=1` in the environment. It is off
by default because a rewrite request contains your entire procedure, including
everything you typed while recording.

---

## Command line

```bash
mc tray                     # the tray application
mc record                   # record; stop with Ctrl+Alt+Q or Ctrl+C
mc doc --last               # build a document from the most recent recording
```

`mc record`:

| Option | Meaning |
|---|---|
| `--out DIR` | where recordings go (defaults to the captures folder above) |
| `--scope monitor\|window\|virtual_desktop` | what each screenshot covers (default `monitor`) |
| `--keyboard consolidate\|every_key\|shortcuts_only` | how keystrokes are recorded (default `consolidate`) |
| `--stop COMBO` | stop hotkey (default `ctrl+alt+q`) |

`mc doc [SESSION]`:

| Option | Meaning |
|---|---|
| `--last` | use the most recent recording |
| `-o, --out PATH` | where to write the `.docx` |
| `--template PATH` | start from this template |
| `--title TEXT` | document title |
| `--raw` | one step per event, no condensing |
| `--no-ocr` | do not name what was clicked (faster) |
| `--no-outcomes` | do not describe what changed after each step |
| `--no-annotate` | do not highlight the click point on screenshots |
| `--max-width PX` | screenshot width limit (default 1200) |

The command line does not use an AI backend. Rewriting is a tray feature,
because it needs the confirmation dialog.

---

## When something goes wrong

**MultyCapture refuses to start on Linux.** You are on Wayland. Log out and
choose an Xorg session — see [X11 only](#x11-only).

**The steps do not say what I clicked.** `tesseract-ocr` is not installed; see
[Click labels](#click-labels-and-the-optional-ocr).

**The document did not open.** It was still written — the menu says where. Your
desktop has nothing registered for `.docx`; install a word processor or open it
by hand.

**A template gives an error.** Templates that lack heading styles are handled
as of 0.2.0. If a template still fails, check it opens in Word, and that it is
not a `.dotx` — MultyCapture reads `.docx`. Word's `~$name.docx` lock files are
ignored, so a template open in Word will not confuse it.

**The AI rewrite says it was rejected.** The model did not answer in the
requested format. Open the log to see what it did answer, and use
**Test this backend** to confirm — see [The log](#the-log).

**The AI rewrite never finishes.** A slow self-hosted model. Use
**Test this backend** for an estimate before waiting again.

**The tray icon looks wrong or disappears.** Fixed in 0.2.0. On 0.1.2 and
earlier the icon was replaced by a generic information icon as soon as a
notification appeared, and stayed that way; upgrade.

---

## See also

- [CAPTURE_SPEC.md](CAPTURE_SPEC.md) — the event stream and storage format.
- [decisions.md](decisions.md) — why things are built the way they are, and
  which alternatives were tried and dropped.
