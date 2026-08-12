"""What we send a model, and what we refuse to accept back.

The rejection cases matter more than the happy path: the whole reason for
limiting a model to rewording is that the limit can then be enforced, and these
tests are that enforcement.
"""

from __future__ import annotations

import datetime
import json

import pytest

from multycapture import ai
from multycapture.ai import payload
from multycapture.generate.condense import Step
from multycapture.model import (
    ClickDetail, Event, EventType, MouseAction, MouseButton, Point, Rect,
    WindowInfo,
)


def _event(seq: int) -> Event:
    return Event(
        seq=seq, t=float(seq), ts=datetime.datetime.now().isoformat(),
        type=EventType.CLICK, screenshot=f"shots/{seq}.png",
        mouse=Point(10, 20), monitor=0,
        window=WindowInfo("Gestione Ordini", "app", 1, Rect(0, 0, 800, 600)),
        mouse_rel=None, detail=ClickDetail(MouseButton.LEFT, MouseAction.DOWN),
    )


def _steps(n: int = 2) -> list[Step]:
    return [
        Step(index=i, event=_event(i), instruction=f"Click ({i}).", count=1, seqs=[i])
        for i in range(1, n + 1)
    ]


# --------------------------------------------------------------------------- #
# what goes out
# --------------------------------------------------------------------------- #
def test_payload_carries_the_facts_a_model_needs():
    steps = _steps(1)
    built = payload.build(steps, {1: "Salva"})[0]
    assert built == {
        "index": 1,
        "action": "click",
        "text": "Click (1).",
        "app": "Gestione Ordini",
        "target": "Salva",
    }


def test_payload_omits_what_it_does_not_have():
    built = payload.build(_steps(1))[0]
    assert "target" not in built  # no OCR label for this step
    assert "repeats" not in built


def test_payload_carries_no_coordinates_or_paths():
    """Only what helps the wording travels — nothing identifying the machine."""
    text = payload.as_json(_steps(2), {1: "Salva"})
    assert "shots/" not in text
    assert "screenshot" not in text
    assert "mouse" not in text


def test_repeat_count_travels_when_there_is_one():
    steps = _steps(1)
    steps[0].count = 3
    assert payload.build(steps)[0]["repeats"] == 3


# --------------------------------------------------------------------------- #
# what comes back
# --------------------------------------------------------------------------- #
def test_accepts_a_plain_array():
    reply = '[{"index": 1, "text": "Click Save."}, {"index": 2, "text": "Confirm."}]'
    assert payload.parse(reply, [1, 2]) == {1: "Click Save.", 2: "Confirm."}


def test_accepts_an_array_wrapped_in_prose_or_a_fence():
    reply = (
        "Sure! Here are the improved steps:\n```json\n"
        '[{"index": 1, "text": "Click Save."}]\n```\nHope that helps.'
    )
    assert payload.parse(reply, [1]) == {1: "Click Save."}


def test_rejects_a_missing_step():
    reply = '[{"index": 1, "text": "Click Save."}]'
    with pytest.raises(payload.RewriteRejected, match="missing"):
        payload.parse(reply, [1, 2])


def test_rejects_an_invented_step():
    """The model must not add steps that were never recorded."""
    reply = (
        '[{"index": 1, "text": "a"}, {"index": 2, "text": "b"},'
        ' {"index": 3, "text": "And finally, save your work."}]'
    )
    with pytest.raises(payload.RewriteRejected, match="unexpected"):
        payload.parse(reply, [1, 2])


def test_rejects_a_duplicated_step():
    reply = '[{"index": 1, "text": "a"}, {"index": 1, "text": "b"}]'
    with pytest.raises(payload.RewriteRejected, match="twice"):
        payload.parse(reply, [1])


def test_rejects_an_empty_rewrite():
    reply = '[{"index": 1, "text": "   "}]'
    with pytest.raises(payload.RewriteRejected, match="empty"):
        payload.parse(reply, [1])


def test_rejects_a_reply_with_no_array():
    with pytest.raises(payload.RewriteRejected, match="no JSON array"):
        payload.parse("I cannot help with that.", [1])


def test_rejects_malformed_entries():
    with pytest.raises(payload.RewriteRejected):
        payload.parse('[{"index": "one", "text": "a"}]', [1])
    with pytest.raises(payload.RewriteRejected):
        payload.parse('["just a string"]', [1])


# --------------------------------------------------------------------------- #
# applying
# --------------------------------------------------------------------------- #
def test_apply_changes_only_the_wording():
    steps = _steps(2)
    before = [(s.index, s.event.seq, s.count, s.seqs) for s in steps]

    payload.apply(steps, {1: "Click Save.", 2: "Confirm the dialog."})

    assert [s.instruction for s in steps] == ["Click Save.", "Confirm the dialog."]
    # structure untouched: same indices, same events, same provenance
    assert [(s.index, s.event.seq, s.count, s.seqs) for s in steps] == before


def test_a_rejected_reply_leaves_the_document_alone():
    """The point of the whole exercise: a bad reply costs nothing."""
    steps = _steps(2)
    original = [s.instruction for s in steps]
    try:
        payload.apply(steps, payload.parse('[{"index": 1, "text": "x"}]', [1, 2]))
    except payload.RewriteRejected:
        pass
    assert [s.instruction for s in steps] == original


# --------------------------------------------------------------------------- #
def test_prompt_is_composed_with_the_steps_after_it():
    message = ai.compose(ai.DEFAULT_PROMPT, payload.as_json(_steps(1)))
    assert message.startswith("You are improving")
    assert message.rstrip().endswith("]")
    # The prompt itself contains a bracketed example, so the payload is the part
    # after the final heading rather than "everything from the first bracket".
    steps_json = message.rsplit("Steps:", 1)[1]
    assert json.loads(steps_json)[0]["index"] == 1


def test_the_default_prompt_forbids_restructuring():
    """The instruction has to match what parse() will actually enforce."""
    text = ai.DEFAULT_PROMPT.lower()
    assert "same `index`" in ai.DEFAULT_PROMPT
    for forbidden in ("merge", "split", "reorder", "drop"):
        assert forbidden in text
