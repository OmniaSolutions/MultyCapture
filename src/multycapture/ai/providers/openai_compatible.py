"""Anything that speaks the OpenAI chat API.

One backend covers a lot of ground, because that request shape became the
de-facto interface: ChatGPT itself, Groq, DeepSeek, Mistral, Together,
OpenRouter, and local servers like LM Studio and llama.cpp all accept it. Only
the base URL and the model name change.

Request shape::

    POST {base_url}/chat/completions
    Authorization: Bearer <key>
    {"model": ..., "messages": [{"role": "user", "content": ...}], "max_tokens": N}

Reply::

    {"choices": [{"message": {"content": ...}}]}
"""

from __future__ import annotations

from typing import Optional

from .base import MissingCredential, ProviderError
from .http import first_text, post_json

# Known endpoints, so the common cases are a menu choice rather than a URL to
# look up. Anything not listed still works by typing its base URL.
PRESETS = {
    "OpenAI": "https://api.openai.com/v1",
    "Groq": "https://api.groq.com/openai/v1",
    "DeepSeek": "https://api.deepseek.com/v1",
    "Mistral": "https://api.mistral.ai/v1",
    "OpenRouter": "https://openrouter.ai/api/v1",
    "LM Studio (local)": "http://localhost:1234/v1",
}

DEFAULT_BASE_URL = PRESETS["OpenAI"]
DEFAULT_MODEL = "gpt-4o-mini"
MAX_TOKENS = 16000


class OpenAICompatibleProvider:
    id = "openai"
    label = "OpenAI-compatible"
    local = False

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @property
    def is_local(self) -> bool:
        """A base URL on this machine means nothing leaves it."""
        return "localhost" in self.base_url or "127.0.0.1" in self.base_url

    def complete(self, message: str) -> str:
        # Local servers accept any token, but still expect the header.
        key = self.api_key or ("local" if self.is_local else None)
        if not key:
            raise MissingCredential(f"No API key configured for {self.base_url}.")

        data = post_json(
            f"{self.base_url}/chat/completions",
            {
                "model": self.model,
                "max_tokens": MAX_TOKENS,
                "messages": [{"role": "user", "content": message}],
            },
            {"Authorization": f"Bearer {key}"},
            service=self.base_url,
        )

        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(f"{self.base_url} returned no choices")
        content = (choices[0].get("message") or {}).get("content", "")
        return first_text(content, self.base_url)
