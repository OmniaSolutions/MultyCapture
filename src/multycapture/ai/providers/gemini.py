"""Google's Gemini, over the Generative Language API.

Request shape::

    POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
    x-goog-api-key: <key>
    {"contents": [{"parts": [{"text": ...}]}]}

Reply::

    {"candidates": [{"content": {"parts": [{"text": ...}]},
                     "finishReason": "STOP"}]}

The key goes in a header rather than the ``?key=`` query parameter both
services document: a URL travels into logs and proxies, a header does not.
"""

from __future__ import annotations

from typing import Optional

from .base import MissingCredential, ProviderError
from .http import first_text, post_json

DEFAULT_MODEL = "gemini-2.0-flash"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider:
    id = "gemini"
    label = "Gemini (Google)"
    local = False
    #: A hosted service is never local, whatever else changes.
    is_local = False
    needs_key = True

    def __init__(self, model: str = DEFAULT_MODEL, api_key: Optional[str] = None) -> None:
        self.model = model
        self.api_key = api_key

    def complete(self, message: str) -> str:
        if not self.api_key:
            raise MissingCredential("No Google API key configured.")

        data = post_json(
            f"{API_ROOT}/{self.model}:generateContent",
            {"contents": [{"parts": [{"text": message}]}]},
            {"x-goog-api-key": self.api_key},
            service=self.label,
        )

        candidates = data.get("candidates") or []
        if not candidates:
            # A prompt blocked before generation comes back with no candidates
            # and the reason somewhere else entirely.
            reason = (data.get("promptFeedback") or {}).get("blockReason")
            raise ProviderError(
                f"Gemini returned nothing ({reason})" if reason
                else "Gemini returned no candidates"
            )

        first = candidates[0]
        if first.get("finishReason") in ("SAFETY", "BLOCKLIST", "PROHIBITED_CONTENT"):
            raise ProviderError(
                f"Gemini stopped: {first['finishReason']}. The captured text may "
                "have tripped a safety filter."
            )

        parts = (first.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        return first_text(text, self.label)
