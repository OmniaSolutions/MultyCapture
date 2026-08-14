"""The user guide must describe the program that exists.

Documentation rots quietly: an option is renamed, the guide keeps the old name,
and the person who believes it is a user rather than a developer. The parts
that can be checked mechanically are checked here — not the prose, but every
command-line option the guide promises, and the internal links it offers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from multycapture.cli import build_parser

DOCS = Path(__file__).resolve().parent.parent / "docs"
GUIDE = DOCS / "USER_GUIDE.md"
README = Path(__file__).resolve().parent.parent / "README.md"


def _documented_options(text: str) -> set[str]:
    """Every long option the document names, wherever it appears.

    Scanned across the whole text rather than inside code spans: pairing
    backticks looks tidier and is wrong, because a fenced block opens with
    three of them, which puts every pairing after the first block out of step.
    An option is worth checking whether it is in a table, a command or a
    sentence.
    """
    return set(re.findall(r"--[a-z][a-z-]+", text))


def _parser_options() -> set[str]:
    known = set()
    parser = build_parser()
    subparsers = [
        sub
        for action in parser._actions
        if hasattr(action, "choices") and isinstance(action.choices, dict)
        for sub in action.choices.values()
    ]
    for target in [parser, *subparsers]:
        for action in target._actions:
            known.update(o for o in action.option_strings if o.startswith("--"))
    return known


def test_every_documented_option_exists():
    documented = _documented_options(GUIDE.read_text(encoding="utf-8"))
    unknown = documented - _parser_options()
    assert not unknown, f"USER_GUIDE.md documents options the CLI does not have: {sorted(unknown)}"


def test_the_guide_covers_the_options_that_change_the_document():
    """The flags a reader would go looking for, rather than all of them."""
    documented = _documented_options(GUIDE.read_text(encoding="utf-8"))
    for option in ("--no-ocr", "--no-outcomes", "--template", "--last"):
        assert option in documented, f"{option} is not mentioned in the user guide"


@pytest.mark.parametrize("source", [GUIDE, README])
def test_internal_links_point_somewhere(source: Path):
    """A link to a heading that was renamed is worse than no link."""
    text = source.read_text(encoding="utf-8")

    headings = {
        # GitHub's anchor rule, near enough: lowercase, punctuation dropped,
        # spaces to hyphens.
        re.sub(r"[^a-z0-9 -]", "", line.lstrip("#").strip().lower()).replace(" ", "-")
        for line in text.splitlines()
        if line.startswith("#")
    }

    for target in re.findall(r"\]\(#([^)]+)\)", text):
        assert target in headings, f"{source.name}: link to #{target} matches no heading"

    for target in re.findall(r"\]\((?!#|https?:)([^)#]+)", text):
        assert (source.parent / target).exists(), f"{source.name}: {target} does not exist"
