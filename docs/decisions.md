# Decisions

Choices that a reader cannot recover from the code, because the code only shows
what was chosen and not what was rejected. Each entry records the alternatives
that were considered and set aside, so that a later change can tell "this was
never tried" from "this was tried and it did not work".

Entries are chronological. Everything before 2026-08-14 was reconstructed from
commit messages after the fact and cites the commit it came from; where a
rejected alternative is recorded there it is repeated here, and where the
commit records only the choice, no alternative is invented to fill the column.
Entries from 2026-08-14 onward were written as the decisions were taken.

---

## 2026-08-11 — Build the Linux bundle on the oldest distribution we support

**Decision.** The Linux CI job builds inside a `python:3.12-bullseye` container
(glibc 2.31) and packs the `.deb` with `dpkg-deb -Zxz` explicitly.
(`38cbca0`)

**Rationale.** The published `.deb` could neither be installed nor run on
Debian 11, for two independent reasons that both came from inheriting the build
host's defaults. `dpkg-deb` on `ubuntu-latest` compresses with zstd, which dpkg
only learned to read in 1.21.18 — Debian 11 ships 1.20.13 and refused the
archive outright. Behind that, PyInstaller bundles the glibc-linked libraries
it finds on the build host, so freezing on glibc 2.39 produced a bundle
demanding `GLIBC_2.38` at runtime. glibc is backward- but not
forward-compatible, so the build host sets the floor for every machine that
will ever run the result.

**Alternatives rejected.**

- *Inherit the host's compression default.* Convenient on the runner and
  unreadable on the target — the failure appears only on the oldest supported
  distribution, which is the one least likely to be tested on.
- *Keep building on `ubuntu-latest`.* Produces a bundle that runs on the
  runner and nowhere older, and nothing in CI notices.

**Consequence worth knowing.** The bullseye image is minimal where the Ubuntu
one was not, which exposed missing build-time dependencies — `xauth`, plus the
xcb/gtk libraries Qt's platform plugins link against. PyInstaller silently
drops libraries it cannot resolve at freeze time, so these would have gone
missing from the bundle rather than failing the build.

---

## 2026-08-11 — Windows autostart as a Startup shortcut, not a registry Run key

**Decision.** The Inno Setup installer's optional autostart writes a
`{commonstartup}` shortcut instead of an `HKCU\...\Run` value. (`74325f4`)

**Rationale.** Under an administrative install the `HKCU` hive belongs to the
elevated account, not to the user who will actually run the application, so the
Run key is written for the wrong user and the option silently does nothing.

**Alternatives rejected.**

- *The `HKCU` Run key.* The obvious mechanism, and wrong for exactly the
  install mode most likely to be used in a managed environment.

---

## 2026-08-11 — The SVG icon is the source of truth; the tray icon is not an asset

**Decision.** The application mark is authored as SVG; the `.png` for the
desktop entry and the `.ico` for the Windows executable are rendered from it.
The `.ico` is assembled from PNG frames rather than ImageMagick's default. The
tray icon is drawn programmatically and reads no asset file. (`d6e0899`)

**Rationale.** One source keeps the desktop entry, the executable and the
installer from drifting apart. ImageMagick writes small `.ico` frames as
uncompressed BMP, which quintupled the file for no visible gain.

**Alternatives rejected.**

- *Hand-maintained raster assets per platform.* Three files to update, and
  nothing that fails when one is forgotten.
- *ImageMagick's default `.ico` assembly.* Five times the size, identical
  appearance.
- *Driving the tray icon from the same asset.* The tray needs a different
  mark per state and a crisp rendering at whatever size a panel asks for;
  see the 2026-08-13 entry on drawing it at seven sizes.

---

## 2026-08-11 — Turn a finished recording into a document without being asked

**Decision.** When a recording stops, the `.docx` is generated and handed to
the system's default editor. It is a checkable menu item, on by default and
remembered. Separately, "Generate .docx from last session" became
"Generate .docx…", which asks for a destination folder *before* building
anything. (`ad09e1b`)

**Rationale.** Finishing a recording and then hunting through the menu to turn
it into a document was the common case; the menu item existed only to serve it.
The on-demand route wrote the document silently beside the capture, which is a
poor place to find it.

**Alternatives rejected.**

- *Writing beside the capture and telling the user where it went.* A path in
  a notification still leaves them navigating to it.
- *Building the document first and asking where to save it afterwards.* The
  build is the slow part; asking first means a cancelled dialog costs nothing.
- *Opening the editor on an empty recording.* Popping open a document with no
  steps in it is worse than doing nothing, so an empty recording is skipped.

**Consequence.** Opening is best-effort per platform (`os.startfile`,
`open(1)`, `xdg-open`, browser fallback). A desktop with no `.docx` handler is
not a generation failure, so it warns rather than reporting that the document
failed.

---

## 2026-08-12 — Test isolation happens at import time, and covers all three platforms

**Decision.** `tests/conftest.py` fixes `HOME` and the Qt platform at import
time rather than in a fixture, and forces `QSettings` into plain ini files in a
scratch directory. A separate fixture redirects the Documents lookup.
(`698cb93`, `48ab125`, `f2547de`)

**Rationale.** pytest imports test modules — and therefore PySide6 — during
collection, and neither the settings location nor the platform plugin can be
changed once a `QApplication` exists. Pointing `HOME` at a scratch directory
only isolates the XDG backend: `QSettings` uses the registry on Windows and
`~/Library/Preferences` on macOS, so a suite run there would have read and
cleared the developer's real settings, and a `.docx` test would have written
into their real Documents folder.

**Alternatives rejected.**

- *Isolating in a fixture.* Runs after the import that already fixed the
  location. Correct-looking and too late.
- *Redirecting `HOME` alone.* Works on the developer's Linux machine and
  damages the two platforms nobody runs the suite on daily.

---

## 2026-08-12 — Resolve every path through `platformdirs`, and split captures from documents

**Decision.** A `paths` module resolves three locations: templates and captures
under application data, generated documents under the user's Documents folder
in a `MultyCapture` subfolder. (`f2547de`)

**Rationale.** The captures root was the *relative* path `"captures"`, so
recordings landed wherever the working directory happened to be and the tray
and the CLI disagreed whenever they were started from different places.
Documents and captures are then separated deliberately: a recording is one
screenshot per event, and Documents is commonly synced to a cloud drive.

**Alternatives rejected.**

- *Building the path from `~/Documents`.* Both obvious guesses are wrong. The
  folder is localised on a non-English desktop (Documenti, Dokumente) and
  redirected under OneDrive on Windows, so string concatenation quietly
  creates a second folder beside the real one.
- *Keeping captures alongside the generated documents.* Pushes hundreds of
  screenshots into a synced folder.

---

## 2026-08-12 — The templates folder is the list of templates

**Decision.** Any `.docx` in the templates folder is a template. There is no
registry, no index and no import step. The template's *content* is kept, not
only its styles: a cover page or preamble survives and the generated steps are
appended after a page break. (`f2547de`)

**Rationale.** The folder is a list the user already knows how to edit, with a
file manager. Keeping content means a company template's cover page works the
way its author intended.

**Alternatives rejected.**

- *A registry of installed templates.* A second source of truth that can
  disagree with the folder, plus an import step for what is otherwise a
  file copy.
- *Applying only the template's styles.* Discards the preamble, which is
  usually the reason a company template exists.

**Details that only show up in use.** Word's `~$name.docx` lock files are
skipped, and an empty template gets no page break so the document does not open
on a blank page.

---

## 2026-08-12 — One rule for choosing a template, on both routes to a document

**Decision.** The Template submenu either names a template (or an explicit
blank document), in which case nothing is asked, or sits at "ask every time",
in which case the chooser opens — including when a recording stops. With no
templates installed the chooser is skipped entirely. (`f2547de`)

**Rationale.** The rule is the user's own: set a default and never be asked,
or leave it unset and be asked every time. One rule covers both the automatic
and the on-demand route, so the two cannot drift.

**Alternatives rejected.**

- *Asking on the on-demand route only.* Makes the automatic route silently
  pick something, which is the route that runs most often.
- *Showing the chooser when only one option exists.* A dialog offering one
  choice is not a choice.
- *Failing when a configured template has been deleted.* It falls back to
  asking instead — a missing template should not cost the document.

---

## 2026-08-12 — Read the clicked label with OCR, at generation time, over a small region

**Decision.** Steps name their target — `Click "Save" in "Orders".` — by
running OCR over a small region around the click point, during document
generation. (`1f3214f`)

**Rationale.** A capture recorded where a click landed but not what it hit, so
every step read `Click in "Some App".` — true, and useless to anyone following
it. The text was already English and already imperative; what it lacked was the
target.

**Alternatives rejected.**

- *OCR over the whole screenshot.* About three times slower per event, and it
  returns a paragraph of surrounding chrome when the useful answer is one or
  two words.
- *OCR during recording.* A tenth of a second per event is not something a
  recorder can spend without dropping events.

**Three things the measurements forced.** Grayscale is required rather than an
optimisation — a colour crop of white text on a blue button reads as nothing at
all, and primary buttons are light-on-coloured nearly everywhere, so skipping
it loses precisely the clicks that matter most. Upscaling 3×, because UI text
is small. Per-word confidence, because a crop clips whatever borders the
control and those fragments come back as characters (`a Salva`, `Annulla |`) —
the real word scores in the 90s, the fragment in the 40s.

---

## 2026-08-12 — OCR is optional, and CI must not silently skip it

**Decision.** No tesseract means no labels and a document that reads exactly as
it did before. The package `Recommends: tesseract-ocr` rather than depending on
it, and CI sets `MULTYCAPTURE_REQUIRE_OCR` so the OCR tests fail rather than
skip. (`1f3214f`)

**Rationale.** The feature degrades cleanly, so it should not be a hard
dependency. But a test that skips when a package is missing reports success for
a workflow that lost the package, which is the one case worth catching.

**Alternatives rejected.**

- *`Depends: tesseract-ocr`.* Forces a large dependency for a feature that
  degrades to exactly the previous behaviour.
- *Letting the OCR tests skip in CI.* Green for the wrong reason.

**Related.** `condense()` stays a pure function of the event stream — labels
are read by `generate.labels` and passed in — so the module that writes the
text needs no files and no OCR to test.

---

## 2026-08-12 — A model may reword steps and do nothing else, and a bad reply is rejected whole

**Decision.** The AI feature rewords steps only. `payload.parse` refuses a
reply that merges, reorders, drops, duplicates or invents steps, and a refused
reply leaves the document with its original text. Only text is sent — no
screenshots, no coordinates, no paths. (`1f3214f`, `ffd0503`)

**Rationale.** Restricting the model to wording is what makes the result
checkable: the reply must describe the same steps, by index, and that is a
property a parser can enforce. Rejecting whole rather than in part matters
because a half-applied rewrite is far harder to notice than one that plainly
did not happen.

**Alternatives rejected.**

- *Letting the model restructure the procedure.* Nothing left to check the
  reply against; an invented step reads exactly like a good one.
- *Applying the steps that parsed and skipping the rest.* Produces a document
  that is partly rewritten and gives no signal that anything was dropped.

---

## 2026-08-12 — The AI feature is off by default

**Decision.** Off by default, unlike every other option added around it.
(`ffd0503`)

**Rationale.** The other options have no consequences beyond the document. This
one sends captured text off the machine unless the chosen backend is local, and
that is not a decision to make on someone's behalf.

**Alternatives rejected.**

- *On by default, like the rest.* Would send the user's captured text on the
  first run, before they had any reason to look for the setting.

---

## 2026-08-12 — Speak HTTP to the AI backends; ship no vendor SDK

**Decision.** Four backends — Ollama, Claude, OpenAI-compatible (one backend
for ChatGPT, Groq, DeepSeek, Mistral, OpenRouter, LM Studio, where the base URL
is the only difference) and Gemini — each a single JSON POST over the standard
library. (`ffd0503`)

**Rationale.** This is a packaging decision, and it was measured. PyInstaller
follows imports inside functions, so a client library merely *installed on the
build machine* ends up in the installer: `anthropic` alone added 16 MB and
dragged in `pydantic_core`, `jiter` and its own copy of libssl — an OpenSSL
shipping to users that nobody chose. HTTP makes the packaged app behave exactly
like a source checkout.

**Alternatives rejected.**

- *Bundling the vendor SDKs.* The 16 MB and the unchosen OpenSSL, per vendor.
- *Excluding the SDKs and telling the user to `pip install anthropic`.* Not
  something that can be done inside a frozen bundle — the instruction is
  impossible to follow in the shipped app.

**Cost accepted.** Protocol details are ours to maintain, so each backend
documents the request and reply shape it depends on, and the tests exercise all
four against a real stub server rather than a mocked client.

---

## 2026-08-12 — Credentials: environment, then keyring, then a private file — never QSettings

**Decision.** Keys are looked up in the environment first (including each
service's conventional variable), then the keyring, then an owner-only file.
They are never written to `QSettings`. (`ffd0503`)

**Rationale.** `keyring` finds its backends through entry-point metadata that
does not survive freezing, so a keyring-only design leaves the packaged app
unable to store a key at all. Consulting the environment first means anyone who
already has `ANTHROPIC_API_KEY` set is not asked to type it again.

**Alternatives rejected.**

- *keyring alone.* Works from a source checkout, fails in the shipped
  application — the inverse of what testing would suggest.
- *`QSettings`.* That is the registry on Windows and a plain ini file on
  Linux; neither is a place for a secret.

---

## 2026-08-12 — Show the prompt, summarise the payload

**Decision.** The prompt is shown before every send and can be edited there or
kept as the new default. The payload is summarised rather than displayed.
(`ffd0503`)

**Rationale.** The prompt is the part worth adjusting per run. The payload is
machine-written JSON, and showing it invites editing it — an edited payload is
the one thing that could put text in the document that was never captured.

**Alternatives rejected.**

- *Displaying the full payload.* Turns a review step into an editing surface
  for the one field whose integrity the whole feature rests on.
- *Showing neither.* Removes the last check before captured text leaves the
  machine.

---

## 2026-08-12 — Say what a step caused, by differencing consecutive screenshots

**Decision.** A step gains a sentence describing what happened —
`"Save changes?" appears.` — from comparing its screenshot with the *next*
step's. No model involved; on by default. (`8b271d5`)

**Rationale.** A capture records what was done; the difference between the
screenshots says what *happened*, which is the half a written procedure
normally supplies from memory. The comparison is against the next step's
screenshot deliberately: those are the two images the reader has in front of
them, so the sentence explains a difference they can see rather than one
recorded between moments they never saw.

**Alternatives rejected — all three were measured.**

- *Flood-filling from the click point to size the widget under it.* Fragile —
  a click landing on a button's letter rather than its fill grows a 1×6 pixel
  region — and up to 2.9 s on a large uniform area, against 95 ms to read a
  label.
- *Describing a single screenshot.* Nothing to compare against, so it can only
  say what is on screen, which the window title and the click label already
  cover.
- *Differencing consecutive screenshots.* About 20 ms for a 1920×1080 pair,
  and it isolates the consequence of one action. Kept.

**A metric that measured less than expected.** Density — how much of the
changed box really differs — separates a wholly replaced view from anything
partial and nothing finer: a dialog only a shade off the background registers
as its border alone and scores *lower* than a few lines of text. Nothing is
built on it beyond that, and both the field and its test say so.

**Three rules against noise, each with a test.** The last step never has an
outcome, since no later screenshot exists; what was just typed is not echoed
back, since the changed region after a "Type …" step holds exactly those words;
and screenshots of differing sizes produce nothing at all, because aligning a
window that moved would invent differences that were never on screen.

---

## 2026-08-13 — Notifications must not go through `QSystemTrayIcon.showMessage` on Linux

**Decision.** Popups go straight to the notification service via `gdbus`, with
`notify-send` behind it and the tooltip behind that. Windows keeps Qt's own
path. (`f6d1a1d`)

**Rationale.** The tray icon vanished the moment a recording started. Under
StatusNotifierItem, Qt implements `showMessage` by putting the item into
`NeedsAttention` and setting its *attention icon* to the message's, so the
panel stops drawing the application's mark and draws `dialog-information`
instead — permanently. On the session bus:

```
before  Status = "Active"          AttentionIconName = ""
after   Status = "NeedsAttention"  AttentionIconName = "dialog-information"
```

The "generic icon" being reported was literally the standard info icon.

**Alternatives rejected.**

- *Three earlier hypotheses — the icon format, the frozen build, the update
  rate.* All measured, all wrong. Recorded because they are the obvious
  places to look and each one costs an afternoon.
- *Calling `Notify` from PySide6 directly.* `replaces_id` is a uint32 and
  PySide6 marshals int32, which the service rejects.

---

## 2026-08-13 — Draw the tray mark at every size a panel might ask for

**Decision.** The tray icon is generated at seven sizes (16/22/24/32/48/64/128)
and tinted per state: blue idle, amber counting down with the seconds inside
the lens, red recording. (`f6d1a1d`)

**Rationale.** A panel asks for the size it wants, and scaling one 64px pixmap
down to 22px turns a crisp mark into mush.

**Alternatives rejected.**

- *One pixmap, scaled on demand.* Blurred at every size but the authored one.

---

## 2026-08-13 — "Local" is a property of the configured host, not of the backend class

**Decision.** `is_local` is derived from the configured host rather than being
a class attribute. (`f6d1a1d`)

**Rationale.** Ollama pointed at another machine was reported as local, so the
confirmation dialog promised the captured text stayed on this machine while
sending it to a server on the network — a false statement in the one dialog
whose job is to let the user decide.

**Alternatives rejected.**

- *A class-level `local = True` for Ollama.* True of the default
  configuration and false of the one the user actually set up.

**Followed up on 2026-08-14** by splitting `needs_key` out of it; see below.

---

## 2026-08-14 — Remove the technical labels from the generated document

**Decision.** The metadata line under the title carries the step count and the
capture date only. The line that read
`8 steps (condensed from 24 events) · captured 2026-08-12 11:23 · Linux-5.10.0-13-amd64-x86_64-with-glibc2.31`
now reads `8 steps · captured 2026-08-12 11:23`. Screenshot captions carry the
application name and no longer the elapsed time (`t+12.3s`).

**Rationale.** The reader of the document is someone following a procedure. The
condensation ratio describes how the tool works, not what they must do; the
kernel version describes the machine that recorded it, not the machine they are
sitting at; and the elapsed time is measured from the start of a recording they
never saw. All three cost nothing to remove and are noise to their only
audience.

**Alternatives rejected.**

- *Keep them behind an option.* Adds a setting for something no reader asked
  for. An option is only worth its surface when both answers have users.
- *Move the OS string into the document properties instead of the body.* The
  data is already in `session.json` next to the capture, which is where a
  developer would look for it; a second copy in a file meant for readers is
  not a better hiding place.

---

## 2026-08-14 — Headings must survive a template that has no heading styles

**Decision.** `_heading()` checks for the `Title` / `Heading N` style before
writing, uses it when present, and falls back to a directly-formatted bold
paragraph when it is not.

**Rationale.** `python-docx`'s `add_heading` resolves the style by name and
raises `KeyError` when the template defines neither. This is not an exotic
case: a company template is usually built by cleaning up an existing document,
and Word drops styles nothing is using. The one that triggered this —
`OmniaSolutions.docx` — carried only Body Text, Caption, Footer, Header,
Heading, Index, List and Normal, and every generation against it failed
outright.

Where the style exists the document inherits the template's own look and stays
navigable in Word's outline. Where it does not, the text is still visibly a
heading and no styles are added to somebody else's template.

**Alternatives rejected.**

- *Inject the missing styles into the template.* Silently modifies a design
  someone else owns, and the injected heading would clash with the template's
  typography rather than match it.
- *Refuse the template with an explanatory error.* The user chose that file
  deliberately. Making them repair a Word template to use the feature is a
  worse outcome than a heading that is bold instead of styled.
- *Call `add_heading` and catch the `KeyError`.* Tried, and wrong:
  `add_heading` inserts the paragraph and only then applies the style, so the
  failed call leaves its paragraph behind and the fallback writes every heading
  twice. Caught only by printing the real document text — the exception path
  looked correct.

---

## 2026-08-14 — A one-hour request timeout for Ollama, and the default for everyone else

**Decision.** `OllamaProvider` defaults to `TIMEOUT = 3600.0`. The cloud
providers keep the shorter shared default.

**Rationale.** A self-hosted model runs as fast as the machine under it, and
that machine is often a spare box without a GPU. The one measured during this
work reported `library=cpu` and 0.66 prompt tokens per second; a twelve-step
procedure is roughly 700 tokens of request, so around twenty minutes before the
model begins to answer. Under the shared default every real session would abort
mid-request and read as a broken integration. For a self-hosted backend the
long wait is the normal case, not a symptom — the timeout should catch a hung
server, not slow hardware.

**Alternatives rejected.**

- *Keep the shared default.* Makes the feature unusable on exactly the setup
  it was added for.
- *Expose the timeout as a setting.* The user cannot know the right number
  before their first run, which is the run that would fail.
- *Short timeout plus automatic retry.* A retry pays the same wait again, and
  the model has no memory of the abandoned attempt.

---

## 2026-08-14 — `needs_key` is a separate question from `is_local`

**Decision.** `Provider` gained a `needs_key` property alongside `is_local`.
Ollama sets `needs_key = False` unconditionally, while `is_local` stays derived
from the configured host.

**Rationale.** The two were one flag and it was wrong in both directions for
the same configuration. An Ollama instance on another machine on the LAN needs
no credential — it authenticates nothing — but the text does leave this
computer. Collapsing the two meant either prompting for a key that does not
exist, or telling the user their capture stays on their machine while it is
being sent to another host. The second is the one that matters: the promise of
a local backend is privacy, and a promise that is silently false is worse than
no promise.

**Alternatives rejected.**

- *Treat a remote Ollama as needing a key.* Asks for a secret that has no
  meaning and blocks a working configuration.
- *Treat all Ollama as local.* Keeps the honest-looking label while the data
  goes over the network — the failure this change exists to prevent.

---

## 2026-08-14 — A rotated log file in the application data directory

**Decision.** `logs.py` writes to `<data_dir>/logs/multycapture.log`, rotated at
1 MB with three backups, at INFO by default and DEBUG under
`MULTYCAPTURE_DEBUG=1`. The tray gained an **Open log** entry.
`ai/rewrite.py` became the single place a rewrite is performed, so that a
rejected reply is recorded in exactly one place.

**Rationale.** The interesting failure is not "the rewrite was rejected" but
*what the model actually replied* — prose instead of JSON, an invented step, a
truncated array. That reply is the only thing that explains the rejection and
there was nowhere for it to go: the tray notification says the rewrite failed
and disappears. The user reported a JSON error with no way to see it; the log
reproduced it on the first run.

DEBUG is off by default because a rewrite request carries the whole procedure,
including every string the user typed while recording.

**Alternatives rejected.**

- *Write to stderr.* The PyInstaller bundle is launched from a desktop entry
  with no console attached; the output goes nowhere a user can reach.
- *Put the detail in a longer notification.* A notification cannot carry a
  multi-line reply and vanishes before it can be read or copied.
- *Upload a crash report.* This is the user's own captured text and the
  model's reply about it. It stays on the machine.

---

## 2026-08-14 — One file holds the version, and a tag that disagrees fails the build

**Decision.** `src/multycapture/_version.py` contains `VERSION = "…"` and
nothing else. `__init__.py` re-exports it, `pyproject.toml` declares the version
dynamically from it, `installer/version.sh` reads it with sed, and
`.github/derive-version.sh` fails a tagged build whose tag does not match it.
The number moved to 0.2.0.

**Rationale.** Five places held a version and three defaulted to the literal
`0.1.0`, so they drifted in silence: the `.deb` under test was labelled 0.1.10
while the application inside it stamped `app_version: "0.1.2"` into every
`session.json`. Every recording made in the last few days is labelled with a
version that never existed, and nothing in the build could have noticed.

A tag is a claim about what is in the artefact, and nothing enforced it.
Bumping is a one-line edit made weeks after the code was written, which is
exactly the kind of omission CI should catch rather than a human.

**Alternatives rejected.**

- *A plain `VERSION.txt`.* Easiest of all to read from a shell, and it breaks
  the shipped application: PyInstaller follows imports, not data files, so the
  file would have to be listed in the spec and would be missing from the frozen
  build the first time someone forgot. A Python module is followed
  automatically.
- *Keeping the string in `__init__.py`.* Works, and puts the sed match in a
  file that has every reason to grow imports later. A file with one job cannot.
- *Deriving the version from the git tag alone.* Leaves a working tree with no
  version at all, and the application needs one at runtime to stamp recordings.
- *Letting a mismatched tag through with a warning.* A warning in a CI log is
  read after the release, not before it.

**Found while doing this.** The old CI step read `${GITHUB_REF_NAME#v}`, which
is the *branch* name outside a tag build, so every branch build produced a
Windows installer versioned `main` — and the `|| '0.1.0'` fallback could never
fire, because `main` is not an empty string.

---

## 2026-08-14 — A dry run against the configured backend, in the settings dialog

**Decision.** **Test this backend** sends two invented steps through the real
prompt and the real parser, on a worker thread polled by a `QTimer`, and reports
one of three outcomes: not reached; reached but the reply did not parse; or
working, with an estimate of how long a real procedure would take.

**Rationale.** Three things can be wrong and the remedies have nothing in
common — a wrong address, a model too slow to be practical, and a model that
cannot produce the requested format. The third is the expensive one: a rewrite
of a real session can take twenty minutes on CPU, and finding out at the end
that the model writes prose is a poor way to spend an afternoon. The probe is
small enough to answer quickly and shaped exactly like a real request, so it
proves the thing that actually fails. The timing estimate turns the "it is
slow" complaint into a number before the user commits to the wait.

**Alternatives rejected.**

- *Check the server with `/api/tags` or an equivalent ping.* Proves the server
  is up and the model exists, which was never the failing part. It cannot
  distinguish a model that will produce the format from one that will not.
- *Run a real rewrite as the test.* That is precisely the twenty minutes the
  test exists to avoid.
- *Run the probe on the GUI thread.* Freezes the application for the duration
  of the call — up to the full hour the Ollama timeout now allows.
