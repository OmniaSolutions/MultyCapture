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
from .http import first_text, post_json

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_MODEL = "llama3.1"

# A self-hosted model is as fast as the machine under it, and that machine is
# often a spare box without a GPU. One measured at 0.66 prompt tokens a second:
# a procedure of a dozen steps is around 700 tokens of request, so twenty
# minutes before it even starts answering. The cloud backends keep the shorter
# default; here the wait is the normal case rather than a symptom.
TIMEOUT = 3600.0

# Ollama defaults to a small context window. A long procedure overflows it
# silently and the model then answers about the part it can still see, which
# looks like the model being bad rather than the request being truncated.
CONTEXT_TOKENS = 8192


class OllamaProvider:
    id = "ollama"
    label = "Ollama (local)"
    #: What the menu says before a host is configured — the default is local.
    local = True
    #: Ollama authenticates nothing, wherever it runs.
    needs_key = False

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        host: str = DEFAULT_HOST,
        timeout: float = TIMEOUT,
    ) -> None:
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    @property
    def is_local(self) -> bool:
        """Whether *this* instance really keeps the text on this machine.

        Ollama is commonly run on another box on the network. Reporting the
        class default in that case would tell the user their captured text
        stays put while it is being sent to a server — in the very dialog
        whose job is to let them decide.
        """
        host = self.host.lower()
        return "//localhost" in host or "//127.0.0.1" in host or "//[::1]" in host

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
