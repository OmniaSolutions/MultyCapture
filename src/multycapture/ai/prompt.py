"""The instruction sent with each rewrite request.

The text is a starting point, not a fixed rule: it is shown before every send
and can be edited there, and a version edited in the tray's options replaces
this default from then on. Hence :data:`DEFAULT` rather than a constant buried
in the request code — the user is expected to change it.
"""

from __future__ import annotations

# The payload is appended after this text, so the prompt ends by naming what
# follows. Kept in English to match the generated document.
DEFAULT = """\
You are improving the written steps of a software procedure manual.

Each step below was recorded automatically from a screen capture: the action
is known exactly, and `target` is the on-screen label that was clicked, read
by local OCR. Rewrite the `text` of each step so a reader who has never seen
the software can follow it.

Rules:
- Return one entry per step given, with the same `index`. Do not merge, split,
  reorder, add or drop steps.
- Write one imperative sentence per step: "Click Save to store the record."
- Use the `target` and `app` values as the names of things. Do not invent
  buttons, menus or field names that are not given to you.
- Where the purpose of an action is obvious from the label, say it. Where it
  is not, describe the action without guessing why.
- Keep it plain. No numbering, no markdown, no commentary.

Reply with a JSON array only: [{"index": 1, "text": "..."}, ...]

Steps:
"""


def compose(instructions: str, payload_json: str) -> str:
    """The full message: the instruction text followed by the steps."""
    return f"{instructions.rstrip()}\n\n{payload_json}"
