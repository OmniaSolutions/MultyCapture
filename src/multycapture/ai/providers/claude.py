"""Anthropic's Claude, over the Messages API.

Request shape this depends on::

    POST https://api.anthropic.com/v1/messages
    x-api-key: <key>
    anthropic-version: 2023-06-01
    {"model": ..., "max_tokens": N, "messages": [{"role": "user", "content": ...}]}

Reply::

    {"content": [{"type": "text", "text": ...}], "stop_reason": "end_turn"}

Two details that are easy to get wrong:

* ``stop_reason`` must be checked **before** reading ``content``. Claude Opus 5
  runs safety classifiers that can decline a request, and a decline is a
  perfectly normal HTTP 200 whose ``content`` is empty. Reading it first gives
  "empty reply" and no idea why.
* Sampling parameters (``temperature``, ``top_p``, ``top_k``) are rejected by
  this model family with a 400. There is nothing to tune here; do not add them.
"""

from __future__ import annotations

from typing import Optional

from .base import MissingCredential, ProviderError
from .http import first_text, post_json

DEFAULT_MODEL = "claude-opus-5"
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
MAX_TOKENS = 16000

# Lets the API retry a declined request on another model server-side instead of
# handing back a refusal there is nothing useful to say about.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeProvider:
    id = "claude"
    label = "Claude (Anthropic)"
    local = False
    #: A hosted service is never local, whatever else changes.
    is_local = False
    needs_key = True

    def __init__(self, model: str = DEFAULT_MODEL, api_key: Optional[str] = None) -> None:
        self.model = model
        self.api_key = api_key

    def complete(self, message: str) -> str:
        if not self.api_key:
            raise MissingCredential("No Anthropic API key configured.")

        data = post_json(
            API_URL,
            {
                "model": self.model,
                "max_tokens": MAX_TOKENS,
                "fallbacks": "default",
                "messages": [{"role": "user", "content": message}],
            },
            {
                "x-api-key": self.api_key,
                "anthropic-version": API_VERSION,
                "anthropic-beta": FALLBACK_BETA,
            },
            service=self.label,
        )

        # Before content: a refusal carries none.
        if data.get("stop_reason") == "refusal":
            raise ProviderError(
                "Claude declined to rewrite these steps — the captured text may "
                "have tripped a safety filter."
            )

        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return first_text(text, self.label)
