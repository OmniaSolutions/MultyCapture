"""What gets sent to a model, and what is accepted back.

The scope is deliberately narrow: a model may **rewrite the wording of each
step**, and nothing else. It does not merge steps, reorder them, drop them, or
invent new ones. That narrowness is what makes the result checkable — since the
only legal change is the text, :func:`apply` can verify that the reply has the
same steps in the same order and reject anything else. A model that
misbehaves costs a rewrite, never a corrupted document.

Nothing leaves the machine but text. The screenshots stay local; what the model
receives is what the capture already knew (action, application) plus the click
label read locally by :mod:`..ocr`.
"""

from __future__ import annotations

import json
from typing import Iterable, Optional

from ..generate.condense import Step
from ..generate.steps import app_label


def build(steps: Iterable[Step], labels: Optional[dict[int, str]] = None) -> list[dict]:
    """The per-step facts a model needs in order to improve the wording."""
    labels = labels or {}
    out: list[dict] = []
    for step in steps:
        event = step.event
        item = {
            "index": step.index,
            "action": event.type.value,
            "text": step.instruction,
        }
        app = app_label(event.window)
        if app:
            item["app"] = app
        target = labels.get(event.seq)
        if target:
            item["target"] = target
        if step.count > 1:
            item["repeats"] = step.count
        out.append(item)
    return out


def as_json(steps: Iterable[Step], labels: Optional[dict[int, str]] = None) -> str:
    """The payload as compact JSON, ready to drop into a prompt."""
    return json.dumps(build(steps, labels), ensure_ascii=False, indent=1)


class RewriteRejected(Exception):
    """The reply did not describe the same steps it was given."""


def parse(reply: str, expected: list[int]) -> dict[int, str]:
    """Read a model reply into ``{step index: new text}``.

    Accepts a bare JSON array, or one wrapped in prose or a ``` fence, since
    models vary in how much they decorate a structured answer.

    Raises :class:`RewriteRejected` when the reply is not parseable, or does not
    cover exactly the steps that were sent. Partial or creative answers are
    refused outright rather than merged: a half-applied rewrite is harder to
    notice than one that plainly didn't happen.
    """
    data = _extract_array(reply)
    if data is None:
        raise RewriteRejected("no JSON array found in the reply")

    rewritten: dict[int, str] = {}
    for item in data:
        if not isinstance(item, dict):
            raise RewriteRejected("array contains something other than objects")
        index, text = item.get("index"), item.get("text")
        if not isinstance(index, int) or not isinstance(text, str):
            raise RewriteRejected("an entry is missing a numeric index or text")
        if index in rewritten:
            raise RewriteRejected(f"step {index} appears twice")
        rewritten[index] = text.strip()

    if set(rewritten) != set(expected):
        missing = sorted(set(expected) - set(rewritten))
        extra = sorted(set(rewritten) - set(expected))
        raise RewriteRejected(
            f"steps do not match: missing {missing or 'none'}, unexpected {extra or 'none'}"
        )
    if any(not text for text in rewritten.values()):
        raise RewriteRejected("a step came back empty")
    return rewritten


def apply(steps: list[Step], rewritten: dict[int, str]) -> list[Step]:
    """Replace each step's wording, leaving everything else untouched."""
    for step in steps:
        new_text = rewritten.get(step.index)
        if new_text:
            step.instruction = new_text
    return steps


def _extract_array(reply: str) -> Optional[list]:
    """Find the JSON array in a reply that may be wrapped in prose or a fence."""
    text = reply.strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else None
    except ValueError:
        pass

    # Fall back to the outermost [...] span.
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, list) else None
