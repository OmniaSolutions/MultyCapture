"""The available model backends.

Backends are listed by id so a chosen one survives in settings. Ollama comes
first: it is the only one that needs no key and sends nothing off the machine,
which makes it the sensible thing to try first.
"""

from __future__ import annotations

from typing import Optional

from .base import MissingCredential, Provider, ProviderError
from .claude import ClaudeProvider
from .gemini import GeminiProvider
from .ollama import OllamaProvider
from .openai_compatible import PRESETS, OpenAICompatibleProvider

_CLASSES = {
    cls.id: cls
    for cls in (
        OllamaProvider,
        ClaudeProvider,
        OpenAICompatibleProvider,
        GeminiProvider,
    )
}

#: (id, label, runs locally) for building menus, in the order to show them.
CATALOG = [(cls.id, cls.label, cls.local) for cls in _CLASSES.values()]

DEFAULT_ID = OllamaProvider.id


def default_model(provider_id: str) -> str:
    """The model a backend starts out configured with."""
    cls = _CLASSES.get(provider_id)
    from . import claude, gemini, ollama, openai_compatible

    return {
        "ollama": ollama.DEFAULT_MODEL,
        "claude": claude.DEFAULT_MODEL,
        "openai": openai_compatible.DEFAULT_MODEL,
        "gemini": gemini.DEFAULT_MODEL,
    }.get(provider_id, "") if cls else ""


def build(
    provider_id: str,
    *,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Provider:
    """Construct a backend by id.

    Raises :class:`ProviderError` for an id that no longer exists — a settings
    file written by a newer version, say.
    """
    cls = _CLASSES.get(provider_id)
    if cls is None:
        raise ProviderError(f"Unknown AI provider: {provider_id!r}")

    kwargs = {"model": model or default_model(provider_id)}
    if cls is OllamaProvider:
        if base_url:
            kwargs["host"] = base_url
    else:
        kwargs["api_key"] = api_key
        if cls is OpenAICompatibleProvider and base_url:
            kwargs["base_url"] = base_url
    return cls(**kwargs)


__all__ = [
    "CATALOG",
    "DEFAULT_ID",
    "PRESETS",
    "MissingCredential",
    "Provider",
    "ProviderError",
    "build",
    "default_model",
]
