"""Where an API key is kept.

Three places are consulted, in this order:

1. ``MULTYCAPTURE_<PROVIDER>_API_KEY`` — explicit and app-specific, for someone
   running from a script or a CI job.
2. The backend's conventional variable (``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``,
   ``GOOGLE_API_KEY``) — most people who already use these services have one set,
   and it would be rude to make them type it again.
3. The system keyring — Credential Manager on Windows, GNOME Keyring or KWallet
   on Linux — or, where there is no keyring, a private file under the app's data
   directory with owner-only permissions. This is what the settings dialog
   writes to.

The file fallback exists because of packaging: keyring finds its backends
through entry-point metadata, which does not survive PyInstaller, so a frozen
build has no keyring at all. Without a fallback the packaged app could not
store a key and the cloud backends would be unusable in exactly the build most
people run.

Keys are never written to QSettings. That would put them in the registry on
Windows and a plain ini file on Linux, both readable by anything running as the
user, and both easy to leak into a backup or a screen share.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional

from .. import paths

_SERVICE = "MultyCapture"

# The variable each service's own documentation tells people to set.
_CONVENTIONAL = {
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GOOGLE_API_KEY",
}


def keyring_available() -> bool:
    """Whether the OS keyring can be used; the file fallback always can."""
    try:
        import keyring

        # A missing or broken backend raises here rather than on first use.
        keyring.get_keyring()
        return True
    except Exception:
        return False


def _file() -> Path:
    """The fallback store: one JSON object, owner-readable only."""
    return paths.data_dir() / "credentials.json"


def _read_file() -> dict:
    try:
        return json.loads(_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_file(data: dict) -> None:
    path = paths.ensure(paths.data_dir()) / "credentials.json"
    # Create with tight permissions before writing, not after: a world-readable
    # moment is all it takes.
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def get(provider_id: str) -> Optional[str]:
    """The key for ``provider_id``, from wherever it is."""
    explicit = os.environ.get(f"MULTYCAPTURE_{provider_id.upper()}_API_KEY")
    if explicit:
        return explicit

    conventional = _CONVENTIONAL.get(provider_id)
    if conventional:
        from_env = os.environ.get(conventional)
        if from_env:
            return from_env

    try:
        import keyring

        stored = keyring.get_password(_SERVICE, provider_id)
        if stored:
            return stored
    except Exception:
        # No keyring, locked keyring, no D-Bus session: fall through to the
        # file, and if that is empty too, having no key is a normal state.
        pass

    return _read_file().get(provider_id) or None


def store(provider_id: str, key: str) -> None:
    """Save ``key``, preferring the system keyring over the private file.

    Raises :class:`RuntimeError` only when neither works, so the settings
    dialog can say so instead of silently forgetting the key.
    """
    try:
        import keyring

        keyring.set_password(_SERVICE, provider_id, key)
        return
    except Exception:
        pass  # no keyring, or it refused — the file below is the fallback

    try:
        data = _read_file()
        data[provider_id] = key
        _write_file(data)
    except OSError as exc:
        raise RuntimeError(f"Could not save the key: {exc}") from exc


def forget(provider_id: str) -> None:
    """Remove a stored key from both stores. Absent is not an error."""
    try:
        import keyring

        keyring.delete_password(_SERVICE, provider_id)
    except Exception:
        pass

    data = _read_file()
    if data.pop(provider_id, None) is not None:
        try:
            _write_file(data)
        except OSError:
            pass


def source(provider_id: str) -> Optional[str]:
    """Where the key in use came from, for showing in the settings dialog."""
    if os.environ.get(f"MULTYCAPTURE_{provider_id.upper()}_API_KEY"):
        return f"MULTYCAPTURE_{provider_id.upper()}_API_KEY"
    conventional = _CONVENTIONAL.get(provider_id)
    if conventional and os.environ.get(conventional):
        return conventional
    try:
        import keyring

        if keyring.get_password(_SERVICE, provider_id):
            return "system keyring"
    except Exception:
        pass
    if _read_file().get(provider_id):
        return str(_file())
    return None
