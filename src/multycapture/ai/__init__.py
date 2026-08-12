"""Optional AI assistance for the generated document.

The only thing a model is asked to do is reword the steps. Everything
structural — which steps exist, their order, their screenshots — is decided
locally and stays that way, which is what lets :func:`.payload.parse` refuse a
reply that changed anything else.
"""

from .payload import RewriteRejected, apply, as_json, build, parse
from .prompt import DEFAULT as DEFAULT_PROMPT, compose

__all__ = [
    "RewriteRejected",
    "apply",
    "as_json",
    "build",
    "parse",
    "compose",
    "DEFAULT_PROMPT",
]
