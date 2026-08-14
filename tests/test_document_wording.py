"""What the document says about itself.

A generated procedure is read by someone doing the task, not by whoever built
the recorder. Details that describe how the tool works — how many raw events
were collapsed, which kernel was running, how many seconds into the recording
a screenshot was taken — are noise to that reader, and they were there.
"""

from __future__ import annotations

import re

from docx import Document

from multycapture.generate import generate_docx


def _text(path) -> str:
    return " ".join(p.text for p in Document(str(path)).paragraphs)


def test_the_header_says_size_and_date(capture, tmp_path):
    _, session_dir = capture
    out = generate_docx(str(session_dir), str(tmp_path / "d.docx"))
    text = _text(out)

    assert "Captured Procedure" in text
    assert re.search(r"\d+ steps? · captured \d{4}-\d{2}-\d{2}", text)


def test_the_header_does_not_explain_how_the_tool_works(capture, tmp_path):
    """"condensed from N events" is an implementation detail."""
    _, session_dir = capture
    text = _text(generate_docx(str(session_dir), str(tmp_path / "d.docx")))

    assert "condensed" not in text
    assert "events" not in text


def test_the_header_does_not_name_the_operating_system(capture, tmp_path):
    """The reader is not debugging the machine that recorded this."""
    _, session_dir = capture
    text = _text(generate_docx(str(session_dir), str(tmp_path / "d.docx")))

    for fragment in ("Linux", "glibc", "x86_64", "Windows", "test"):
        assert fragment not in text, f"{fragment!r} leaked into the document"


def test_captions_do_not_carry_the_elapsed_time(capture, tmp_path):
    """"t+12.3s" is measured from a recording the reader never watched."""
    _, session_dir = capture
    text = _text(generate_docx(str(session_dir), str(tmp_path / "d.docx")))

    assert not re.search(r"t\+\d", text)


def test_captions_still_name_the_application(capture, tmp_path):
    """Where the reader is looking is worth keeping."""
    _, session_dir = capture
    text = _text(generate_docx(str(session_dir), str(tmp_path / "d.docx")))
    assert "Test Window" in text


def test_one_step_is_not_called_one_steps(capture, tmp_path):
    _, session_dir = capture
    out = generate_docx(
        str(session_dir), str(tmp_path / "one.docx"), condense_steps=True
    )
    text = _text(out)
    if text.startswith("Captured Procedure 1 step"):
        assert "1 steps" not in text
