"""The log, and the dry run against a backend.

Both exist for the same reason: a rewrite that fails leaves nothing behind. The
notification says it was refused and vanishes; the reply that would explain why
is gone. These two put it somewhere it can be read, and let it be found before
a twenty-minute wait rather than after.
"""

from __future__ import annotations

import datetime
import logging

import pytest

from multycapture import logs
from multycapture.ai import check, payload, rewrite
from multycapture.ai.providers import ProviderError
from multycapture.generate.condense import Step
from multycapture.model import (
    ClickDetail, Event, EventType, MouseAction, MouseButton, Point, Rect,
    WindowInfo,
)


@pytest.fixture
def log_file(monkeypatch, tmp_path):
    """A log in a scratch directory, configured from scratch each time."""
    from multycapture import paths

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(logs, "_configured", False)
    logger = logging.getLogger(logs.NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logs.setup(level=logging.DEBUG)
    yield tmp_path / "logs" / "multycapture.log"
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


def _steps(n: int = 2) -> list[Step]:
    def event(i):
        return Event(
            seq=i, t=float(i), ts=datetime.datetime.now().isoformat(),
            type=EventType.CLICK, screenshot=None, mouse=Point(1, 1), monitor=0,
            window=WindowInfo("App", "app", 1, Rect(0, 0, 10, 10)),
            mouse_rel=None, detail=ClickDetail(MouseButton.LEFT, MouseAction.DOWN),
        )
    return [
        Step(index=i, event=event(i), instruction=f"Click ({i}).", seqs=[i])
        for i in range(1, n + 1)
    ]


class _Model:
    id, model = "ollama", "test"

    def __init__(self, reply):
        self._reply = reply

    def complete(self, message):
        if isinstance(self._reply, Exception):
            raise self._reply
        return self._reply


# --------------------------------------------------------------------------- #
# the log
# --------------------------------------------------------------------------- #
def test_the_log_is_written_where_it_can_be_found(log_file):
    logs.get("x").info("hello")
    assert log_file.is_file()
    assert "hello" in log_file.read_text(encoding="utf-8")


def test_a_broken_data_directory_does_not_stop_anything(monkeypatch, tmp_path):
    """A log that cannot be written is a diagnosis problem, not a crash."""
    from multycapture import paths

    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path / "nope")
    monkeypatch.setattr(paths, "ensure", lambda p: (_ for _ in ()).throw(OSError("read-only")))
    monkeypatch.setattr(logs, "_configured", False)
    logs.setup().info("still fine")   # must not raise


def test_long_replies_are_trimmed_visibly():
    trimmed = logs.excerpt("x" * 5000, limit=100)
    assert trimmed.startswith("x" * 100)
    assert "more characters" in trimmed


# --------------------------------------------------------------------------- #
# a rewrite leaves a trace
# --------------------------------------------------------------------------- #
def test_a_rejected_reply_is_written_to_the_log(log_file):
    """The point of the whole exercise.

    Without the reply in the log, "rejected" is unexplainable — prose instead
    of JSON looks the same as an invented step.
    """
    steps = _steps()
    chatty = _Model("Certainly! Here are the improved steps:\n1. Click Save")

    with pytest.raises(payload.RewriteRejected):
        rewrite.improve(chatty, "instructions", steps, {})

    written = log_file.read_text(encoding="utf-8")
    assert "reply rejected" in written
    assert "Certainly! Here are the improved steps" in written
    # and the document keeps its own words
    assert [s.instruction for s in steps] == ["Click (1).", "Click (2)."]


def test_a_good_rewrite_is_logged_too(log_file):
    steps = _steps()
    good = _Model('[{"index": 1, "text": "Click Save."}, {"index": 2, "text": "Confirm."}]')

    assert rewrite.improve(good, "instructions", steps, {}) == 2

    written = log_file.read_text(encoding="utf-8")
    assert "rewrite via ollama" in written
    assert "wording replaced on 2 steps" in written
    assert [s.instruction for s in steps] == ["Click Save.", "Confirm."]


def test_an_unreachable_model_is_logged_and_raised(log_file):
    steps = _steps()
    with pytest.raises(ProviderError):
        rewrite.improve(_Model(ProviderError("Cannot reach Ollama")), "i", steps, {})


# --------------------------------------------------------------------------- #
# the dry run
# --------------------------------------------------------------------------- #
def test_a_working_backend_reports_working(log_file):
    good = _Model('[{"index": 1, "text": "a"}, {"index": 2, "text": "b"}]')
    result = check.run(good, "instructions")
    assert (result.reached, result.understood, result.ok) == (True, True, True)


def test_an_unreachable_backend_is_told_apart(log_file):
    result = check.run(_Model(ProviderError("connection refused")), "i")
    assert result.reached is False
    assert "refused" in result.detail
    assert "server address" in check.advice(result)


def test_a_model_that_cannot_follow_the_format_is_told_apart(log_file):
    """Reached and useless is a different problem from unreachable."""
    result = check.run(_Model("Sure! Step one: click Save."), "i")

    assert result.reached is True
    assert result.understood is False
    assert "does not keep to the requested format" in check.advice(result)
    # the reply is carried back so the dialog can show it
    assert "Sure!" in result.reply


def test_a_slow_but_working_backend_is_called_slow(log_file):
    result = check.Result(reached=True, understood=True, seconds=300.0, detail="")
    assert "minutes" in check.advice(result, steps_in_a_real_run=8)


def test_a_quick_backend_is_reported_in_seconds(log_file):
    result = check.Result(reached=True, understood=True, seconds=1.5, detail="")
    assert "seconds" in check.advice(result, steps_in_a_real_run=8)
