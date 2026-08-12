"""One JSON POST, with errors a user can act on.

Every backend is a single non-streaming request returning a block of text, so
the standard library covers it and no client library is needed. That is not a
micro-optimisation: PyInstaller follows imports inside functions, so a client
library installed on the build machine ends up inside the installer — the
Anthropic SDK alone adds 16 MB along with pydantic_core, jiter and its own copy
of libssl. Worse, an installed-but-not-bundled library leaves the packaged app
telling users to "pip install" something they have no way to install.

The cost of this choice is that protocol details are maintained here rather
than absorbed by a vendor's client. Each backend module documents the shape it
depends on, so a break has one obvious place to look.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Optional

from .base import ProviderError

# Rewriting a long procedure is slow, especially on a local model.
DEFAULT_TIMEOUT = 300.0


def post_json(
    url: str,
    body: dict,
    headers: dict[str, str],
    *,
    service: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict:
    """POST ``body`` as JSON and return the decoded reply.

    ``service`` names the backend in error messages, since "connection refused"
    is not much use without knowing what refused it.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise _from_status(exc, service) from exc
    except urllib.error.URLError as exc:
        raise ProviderError(f"Cannot reach {service}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise ProviderError(f"{service} did not answer within {timeout:.0f}s") from exc
    except OSError as exc:
        raise ProviderError(f"Network error talking to {service}: {exc}") from exc
    except ValueError as exc:
        raise ProviderError(f"{service} sent something that isn't JSON: {exc}") from exc


def _from_status(exc: urllib.error.HTTPError, service: str) -> ProviderError:
    """Turn an HTTP status into something worth reading."""
    detail = _detail(exc)
    if exc.code in (401, 403):
        return ProviderError(f"{service} rejected the API key ({exc.code}).")
    if exc.code == 404:
        return ProviderError(f"{service}: no such model or endpoint. {detail}")
    if exc.code == 429:
        return ProviderError(f"{service} rate limit reached — try again shortly.")
    if exc.code >= 500:
        return ProviderError(f"{service} is having trouble ({exc.code}). Try again later.")
    return ProviderError(f"{service} returned {exc.code}: {detail}")


def _detail(exc: urllib.error.HTTPError) -> str:
    """The server's own explanation, when it sent one.

    Every one of these services nests its message differently, so all the
    shapes seen in the wild are tried before falling back to the status text.
    """
    try:
        payload = json.loads(exc.read().decode("utf-8"))
    except Exception:
        return exc.reason or "no detail"

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error.get("type") or error)
        if isinstance(error, str):
            return error
        if "message" in payload:
            return str(payload["message"])
    return exc.reason or "no detail"


def first_text(value: Optional[str], service: str) -> str:
    """Reject an empty completion rather than writing a blank document."""
    if not value or not value.strip():
        raise ProviderError(f"{service} returned an empty reply")
    return value
