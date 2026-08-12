"""The tray's AI rewording.

The interesting behaviour is not the happy path — it is that everything which
can go wrong (no key, unreachable model, a reply that changed the structure,
the user having second thoughts) leaves a usable document behind.
"""

from __future__ import annotations

import pytest
from docx import Document

from multycapture import ai
from multycapture.ai import providers
from multycapture.gui import ai_dialog
from multycapture.gui import tray as traymod

from conftest import SESSION_ID, wait_for_doc


@pytest.fixture
def prompt(monkeypatch):
    """Answer the wording dialog without showing it."""
    calls: list[tuple] = []
    answer = [(True, ai.DEFAULT_PROMPT, False)]

    def fake_ask(instructions, step_count, provider_label, local, parent=None):
        calls.append((instructions, step_count, provider_label, local))
        return answer[0]

    monkeypatch.setattr(ai_dialog, "ask", fake_ask)
    return calls, answer


@pytest.fixture
def fake_model(monkeypatch):
    """A backend that replies with whatever is queued."""
    replies: list = [None]

    class Fake:
        id, label, local = "ollama", "Ollama (local)", True

        def __init__(self, *a, **k):
            pass

        def complete(self, message):
            self.sent = message
            outcome = replies[0]
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        model = "test"

    monkeypatch.setattr(providers, "build", lambda *a, **k: Fake())
    monkeypatch.setattr(traymod.providers, "build", lambda *a, **k: Fake())
    return replies


def _rewritten_reply(count: int) -> str:
    entries = ", ".join(
        f'{{"index": {i}, "text": "Rewritten step {i}."}}'
        for i in range(1, count + 1)
    )
    return f"[{entries}]"


def _doc_text(path) -> str:
    return " ".join(p.text for p in Document(str(path)).paragraphs)


# --------------------------------------------------------------------------- #
# the setting
# --------------------------------------------------------------------------- #
def test_ai_is_off_unless_asked_for(tray):
    """It sends captured text somewhere; that should never be the default."""
    assert tray.ai_enabled is False


def test_turning_it_on_is_remembered(tray):
    from PySide6.QtCore import QSettings

    tray.set_ai_enabled(True)
    tray.settings.sync()
    assert QSettings("MultyCapture", "MultyCapture").value("ai_enabled", False, type=bool)


def test_the_default_backend_is_the_local_one(tray):
    assert tray.ai_provider == providers.DEFAULT_ID
    assert providers.DEFAULT_ID == "ollama"


def test_disabled_ai_asks_nothing_and_rewrites_nothing(tray, capture, prompt):
    calls, _ = prompt
    _, session_dir = capture
    proceed, rewrite = tray._resolve_rewrite(str(session_dir))
    assert (proceed, rewrite) == (True, None)
    assert calls == []


# --------------------------------------------------------------------------- #
# the wording dialog
# --------------------------------------------------------------------------- #
def test_the_dialog_is_told_what_will_be_sent(tray, capture, prompt, fake_model):
    calls, _ = prompt
    _, session_dir = capture
    tray.set_ai_enabled(True)
    tray._resolve_rewrite(str(session_dir))

    instructions, step_count, label, local = calls[0]
    assert instructions == ai.DEFAULT_PROMPT
    assert step_count >= 1           # so the user knows the size of the send
    assert local is True             # and whether it leaves the machine


def test_cancelling_the_dialog_stops_the_document(tray, capture, prompt, fake_model):
    _, answer = prompt
    _, session_dir = capture
    tray.set_ai_enabled(True)
    answer[0] = (False, "", False)
    assert tray._resolve_rewrite(str(session_dir))[0] is False


def test_edited_wording_can_be_remembered(tray, capture, prompt, fake_model):
    _, answer = prompt
    _, session_dir = capture
    tray.set_ai_enabled(True)
    answer[0] = (True, "Write it in Italian.", True)

    tray._resolve_rewrite(str(session_dir))
    assert tray.ai_prompt == "Write it in Italian."
    tray.settings.sync()

    from PySide6.QtCore import QSettings
    assert QSettings("MultyCapture", "MultyCapture").value("ai_prompt") == "Write it in Italian."


def test_edited_wording_is_not_remembered_unless_asked(tray, capture, prompt, fake_model):
    _, answer = prompt
    _, session_dir = capture
    tray.set_ai_enabled(True)
    answer[0] = (True, "Just this once.", False)
    tray._resolve_rewrite(str(session_dir))
    assert tray.ai_prompt == ai.DEFAULT_PROMPT


# --------------------------------------------------------------------------- #
# rewriting, and failing to
# --------------------------------------------------------------------------- #
def test_a_good_reply_reaches_the_document(tray, capture, prompt, fake_model, tmp_path):
    _, session_dir = capture
    tray.set_ai_enabled(True)
    fake_model[0] = _rewritten_reply(1)

    _, rewrite = tray._resolve_rewrite(str(session_dir))
    out = tmp_path / "ai.docx"
    from multycapture.generate import generate_docx
    generate_docx(str(session_dir), str(out), rewrite=rewrite)

    assert "Rewritten step 1." in _doc_text(out)
    assert tray._ai_warning is None


def test_an_unreachable_model_still_produces_the_document(
    tray, capture, prompt, fake_model, tmp_path
):
    _, session_dir = capture
    tray.set_ai_enabled(True)
    fake_model[0] = providers.ProviderError("Cannot reach Ollama at localhost")

    from multycapture.generate import generate_docx

    _, rewrite = tray._resolve_rewrite(str(session_dir))
    out = tmp_path / "failed.docx"
    generate_docx(str(session_dir), str(out), rewrite=rewrite)

    # Identical to what the same session produces with no AI at all: the
    # failure cost the rewording and nothing else.
    untouched = tmp_path / "untouched.docx"
    generate_docx(str(session_dir), str(untouched))

    assert out.is_file()
    assert _doc_text(out) == _doc_text(untouched)
    assert "Cannot reach Ollama" in tray._ai_warning


def test_a_reply_that_changed_the_structure_is_refused(
    tray, capture, prompt, fake_model, tmp_path
):
    """A model that invents steps must not get them into the document."""
    _, session_dir = capture
    tray.set_ai_enabled(True)
    fake_model[0] = (
        '[{"index": 1, "text": "Rewritten."},'
        ' {"index": 2, "text": "And then I made this one up."}]'
    )

    _, rewrite = tray._resolve_rewrite(str(session_dir))
    out = tmp_path / "invented.docx"
    from multycapture.generate import generate_docx
    generate_docx(str(session_dir), str(out), rewrite=rewrite)

    text = _doc_text(out)
    assert "made this one up" not in text
    assert "Rewritten." not in text           # all-or-nothing, not partial
    assert tray._ai_warning is not None


def test_an_unexpected_client_error_is_contained(
    tray, capture, prompt, fake_model, tmp_path
):
    """Client libraries raise things we have not catalogued; none may escape."""
    _, session_dir = capture
    tray.set_ai_enabled(True)
    fake_model[0] = ValueError("something the SDK never documented")

    _, rewrite = tray._resolve_rewrite(str(session_dir))
    out = tmp_path / "weird.docx"
    from multycapture.generate import generate_docx
    generate_docx(str(session_dir), str(out), rewrite=rewrite)

    assert out.is_file()
    assert "AI rewrite failed" in tray._ai_warning


def test_the_warning_is_reported_once_then_cleared(tray, capture, prompt, fake_model):
    tray._ai_warning = "something went wrong"
    tray._doc_result = (True, "/tmp/x.docx", False)
    tray._check_doc_result()
    assert tray._ai_warning is None


# --------------------------------------------------------------------------- #
def test_no_screenshots_are_ever_sent(tray, capture, prompt, fake_model, tmp_path):
    """Only text leaves — the payload must carry no image data or paths."""
    _, session_dir = capture
    tray.set_ai_enabled(True)
    captured = {}

    class Recorder:
        id, label, local = "ollama", "Ollama", True
        model = "test"

        def complete(self, message):
            captured["message"] = message
            return _rewritten_reply(1)

    import multycapture.gui.tray as t
    monkey = Recorder()
    t.providers.build = lambda *a, **k: monkey

    _, rewrite = tray._resolve_rewrite(str(session_dir))
    from multycapture.generate import generate_docx
    generate_docx(str(session_dir), str(tmp_path / "x.docx"), rewrite=rewrite)

    message = captured["message"]
    assert ".png" not in message
    assert "shots/" not in message
    assert "screenshot" not in message
