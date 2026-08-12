"""Where API keys come from, and where they must never go."""

from __future__ import annotations

import sys
import types

import pytest

from multycapture.ai import credentials


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """No inherited keys — the developer running this may have real ones set."""
    for name in (
        "MULTYCAPTURE_CLAUDE_API_KEY", "MULTYCAPTURE_OPENAI_API_KEY",
        "MULTYCAPTURE_GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_keyring(monkeypatch):
    """A keyring that lives in a dict."""
    store: dict[tuple[str, str], str] = {}
    module = types.SimpleNamespace(
        get_keyring=lambda: object(),
        get_password=lambda service, user: store.get((service, user)),
        set_password=lambda service, user, key: store.__setitem__((service, user), key),
        delete_password=lambda service, user: store.pop((service, user)),
    )
    monkeypatch.setitem(sys.modules, "keyring", module)
    return store


# --------------------------------------------------------------------------- #
# lookup order
# --------------------------------------------------------------------------- #
def test_app_specific_variable_wins(monkeypatch, fake_keyring):
    monkeypatch.setenv("MULTYCAPTURE_CLAUDE_API_KEY", "from-app-var")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-conventional")
    fake_keyring[("MultyCapture", "claude")] = "from-keyring"
    assert credentials.get("claude") == "from-app-var"


def test_conventional_variable_is_used_when_the_app_one_is_absent(monkeypatch, fake_keyring):
    """Someone with ANTHROPIC_API_KEY already set shouldn't retype it."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-conventional")
    fake_keyring[("MultyCapture", "claude")] = "from-keyring"
    assert credentials.get("claude") == "from-conventional"


def test_keyring_is_the_last_resort(fake_keyring):
    fake_keyring[("MultyCapture", "claude")] = "from-keyring"
    assert credentials.get("claude") == "from-keyring"


def test_no_key_anywhere_is_none(fake_keyring):
    assert credentials.get("claude") is None


def test_each_backend_has_its_own_conventional_variable(monkeypatch, fake_keyring):
    monkeypatch.setenv("OPENAI_API_KEY", "oa")
    monkeypatch.setenv("GOOGLE_API_KEY", "gg")
    assert credentials.get("openai") == "oa"
    assert credentials.get("gemini") == "gg"
    assert credentials.get("claude") is None  # not shared between backends


def test_ollama_has_no_conventional_variable(fake_keyring):
    """The local backend needs no key, so nothing is looked up for it."""
    assert credentials.get("ollama") is None


# --------------------------------------------------------------------------- #
# storing
# --------------------------------------------------------------------------- #
def test_stored_key_is_read_back(fake_keyring):
    credentials.store("claude", "sk-secret")
    assert fake_keyring[("MultyCapture", "claude")] == "sk-secret"
    assert credentials.get("claude") == "sk-secret"


def test_forgetting_a_key_removes_it(fake_keyring):
    credentials.store("claude", "sk-secret")
    credentials.forget("claude")
    assert credentials.get("claude") is None


def test_forgetting_an_absent_key_is_not_an_error(fake_keyring):
    credentials.forget("claude")  # must not raise


def test_storing_without_a_keyring_falls_back_to_a_file(monkeypatch, tmp_path):
    """A frozen build has no keyring, and must still be able to keep a key."""
    from multycapture import paths

    monkeypatch.setitem(sys.modules, "keyring", None)
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)

    credentials.store("claude", "sk-secret")
    assert credentials.get("claude") == "sk-secret"

    saved = tmp_path / "credentials.json"
    assert saved.is_file()
    # Owner-only: the file is the fallback for the OS vault, not a plain note.
    assert saved.stat().st_mode & 0o077 == 0


def test_the_fallback_file_can_be_cleared(monkeypatch, tmp_path):
    from multycapture import paths

    monkeypatch.setitem(sys.modules, "keyring", None)
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    credentials.store("claude", "sk-secret")
    credentials.forget("claude")
    assert credentials.get("claude") is None


def test_a_broken_keyring_does_not_break_reading(monkeypatch):
    """A locked keyring, or no D-Bus session: having no key is a normal state."""
    def explode(*args, **kwargs):
        raise RuntimeError("no D-Bus session")

    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(
        get_keyring=explode, get_password=explode,
    ))
    assert credentials.get("claude") is None
    assert credentials.keyring_available() is False


# --------------------------------------------------------------------------- #
def test_the_source_is_reportable(monkeypatch, fake_keyring):
    """The settings dialog says where the key in use came from."""
    assert credentials.source("claude") is None
    fake_keyring[("MultyCapture", "claude")] = "k"
    assert credentials.source("claude") == "system keyring"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert credentials.source("claude") == "ANTHROPIC_API_KEY"
    monkeypatch.setenv("MULTYCAPTURE_CLAUDE_API_KEY", "k")
    assert credentials.source("claude") == "MULTYCAPTURE_CLAUDE_API_KEY"


def test_keys_never_reach_qsettings(fake_keyring):
    """The whole reason this module exists.

    QSettings is the registry on Windows and a plain ini file on Linux; a key
    there is readable by anything running as the user and travels into backups
    and screen shares.
    """
    from PySide6.QtCore import QSettings

    credentials.store("claude", "sk-must-not-leak")
    settings = QSettings("MultyCapture", "MultyCapture")
    settings.sync()
    for key in settings.allKeys():
        assert "sk-must-not-leak" not in str(settings.value(key))
