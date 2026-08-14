"""The "?" entry, and the address it opens.

Small, but the one menu item a user reaches for when nothing else is working —
so it must not depend on the application being in a good state, and the link
must not be a guess.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from multycapture.gui import tray as tray_mod

REPO = Path(__file__).resolve().parent.parent


def test_the_menu_has_it(tray):
    assert "?" in [a.text() for a in tray.menu.actions()]


def test_it_opens_the_guide(tray, monkeypatch):
    opened = []
    monkeypatch.setattr(tray_mod.webbrowser, "open", lambda url: opened.append(url) or True)

    tray.act_help.trigger()

    assert opened == [tray_mod.DOCS_URL]


def test_no_browser_shows_the_address_instead(tray, monkeypatch):
    """A machine with no browser is exactly where the link matters most."""
    monkeypatch.setattr(tray_mod.webbrowser, "open", lambda url: False)
    said = []
    monkeypatch.setattr(tray, "_notify", lambda title, body, *a: said.append((title, body)))

    tray.act_help.trigger()

    assert said and tray_mod.DOCS_URL in said[0][1]


def test_a_browser_that_raises_is_not_a_crash(tray, monkeypatch):
    def boom(url):
        raise RuntimeError("no DISPLAY")

    monkeypatch.setattr(tray_mod.webbrowser, "open", boom)
    monkeypatch.setattr(tray, "_notify", lambda *a: None)

    tray.act_help.trigger()      # must not raise


def test_the_url_points_at_a_document_that_exists_in_this_repo():
    """Catches a renamed or moved guide before a user finds the 404.

    Only the path within the repository is checkable offline; that the
    repository itself is right is not something a test can know.
    """
    match = re.fullmatch(
        r"https://github\.com/[^/]+/[^/]+/blob/main/(.+)", tray_mod.DOCS_URL
    )
    assert match, f"unexpected documentation URL shape: {tray_mod.DOCS_URL}"
    assert (REPO / match.group(1)).is_file(), (
        f"{match.group(1)} is not in the repository, so the ? menu leads nowhere"
    )
