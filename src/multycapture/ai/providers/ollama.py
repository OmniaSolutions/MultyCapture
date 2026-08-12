"""Ollama — a model running on this machine.

The backend that needs no key and no account, and the only one where the
captured text never leaves the machine. That makes it the right thing to try
first for anyone documenting something they would rather not send anywhere.

Request shape::

    POST {host}/api/chat
    {"model": ..., "messages": [...], "stream": false, "options": {...}}

Reply::

    {"message": {"content": ...}}
"""

from __future__ import annotations

from .base import ProviderError
from .http import DEFAULT_TIMEOUT, first_text, post_json

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"

# Ollama defaults to a small context window. A long procedure overflows it
# silently and the model then answers about the part it can still see, which
# looks like the model being bad rather than the request being truncated.
CONTEXT_TOKENS = 8192


class OllamaProvider:
    id = "ollama"
    label = "Ollama (local)"
    local = True

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def complete(self, message: str) -> str:
        try:
            data = post_json(
                f"{self.host}/api/chat",
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": message}],
                    "stream": False,
                    "options": {"num_ctx": CONTEXT_TOKENS},
                },
                {},
                service=f"Ollama at {self.host}",
                timeout=self.timeout,
            )
        except ProviderError as exc:
            # An unknown model is the one failure with an obvious remedy, so
            # say what it is rather than passing on "404: not found".
            if "no such model" in str(exc).lower():
                raise ProviderError(
                    f"Ollama has no model named '{self.model}'. "
                    f"Install it with: ollama pull {self.model}"
                ) from exc
            raise

        content = (data.get("message") or {}).get("content", "")
        return first_text(content, "Ollama")
