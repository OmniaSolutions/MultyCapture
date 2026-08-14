"""Running one rewrite, and leaving a trace of it.

The interesting failure is not "it didn't work" but *what the model said* —
prose instead of JSON, an invented step, a truncated array. That reply is the
only thing that explains a rejection, and a tray notification cannot carry it.
So this is the one place a rewrite happens, and it writes the reply to the log
whenever the reply is refused.
"""

from __future__ import annotations

import time
from typing import Optional

from .. import logs
from ..generate.condense import Step
from . import payload
from .prompt import compose


def improve(
    provider,
    instructions: str,
    steps: list[Step],
    labels: Optional[dict[int, str]] = None,
) -> int:
    """Reword ``steps`` in place. Returns how many were changed.

    Raises :class:`payload.RewriteRejected` if the reply does not describe the
    same steps, or the provider's own error if the model could not be reached.
    Either way the steps are left exactly as they were.
    """
    log = logs.get("ai")
    message = compose(instructions, payload.as_json(steps, labels))

    log.info(
        "rewrite via %s (model=%s): %d steps, %d characters",
        getattr(provider, "id", "?"), getattr(provider, "model", "?"),
        len(steps), len(message),
    )
    log.debug("request sent:\n%s", message)

    started = time.monotonic()
    reply = provider.complete(message)
    elapsed = time.monotonic() - started

    log.info("replied in %.1fs, %d characters", elapsed, len(reply or ""))
    log.debug("reply received:\n%s", reply)

    try:
        rewritten = payload.parse(reply, [s.index for s in steps])
    except payload.RewriteRejected as exc:
        # The whole reason this function exists: without the reply, a rejection
        # is unexplainable.
        log.warning("reply rejected: %s", exc)
        log.warning("the model replied:\n%s", logs.excerpt(reply))
        raise

    payload.apply(steps, rewritten)
    log.info("wording replaced on %d steps", len(rewritten))
    return len(rewritten)
