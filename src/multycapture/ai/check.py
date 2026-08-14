"""A dry run against a configured backend.

Three things can be wrong and they need telling apart, because the remedies
have nothing in common:

* the server cannot be reached — wrong address, service down, model not pulled;
* the server answers, but slowly enough that a real procedure is impractical;
* the server answers promptly and the model cannot produce the format, so
  every rewrite will be refused.

The third is the one worth catching early. A rewrite of a real session can take
twenty minutes on a CPU-only machine, and discovering only then that the model
writes prose instead of JSON is a bad way to spend an afternoon. So the probe
asks for exactly the shape a rewrite asks for, and puts the reply through the
same parser.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from .. import logs
from . import payload
from .prompt import compose

#: Two invented steps: enough to prove the model can follow the contract,
#: small enough to answer quickly even on slow hardware.
PROBE = [
    {"index": 1, "action": "click", "text": "Click.", "target": "Save",
     "app": "Example"},
    {"index": 2, "action": "type", "text": "Type “ACME”.", "app": "Example"},
]


@dataclass
class Result:
    reached: bool
    understood: bool
    seconds: float
    detail: str
    #: What came back, for showing when it could not be used.
    reply: str = ""

    @property
    def ok(self) -> bool:
        return self.reached and self.understood


def run(provider, instructions: str) -> Result:
    """Send the probe and report what happened. Never raises."""
    log = logs.get("ai.check")
    import json

    message = compose(instructions, json.dumps(PROBE, ensure_ascii=False, indent=1))
    log.info(
        "checking %s (model=%s)",
        getattr(provider, "id", "?"), getattr(provider, "model", "?"),
    )

    started = time.monotonic()
    try:
        reply = provider.complete(message)
    except Exception as exc:
        elapsed = time.monotonic() - started
        log.warning("could not be reached after %.1fs: %s", elapsed, exc)
        return Result(False, False, elapsed, str(exc))

    elapsed = time.monotonic() - started
    log.info("answered in %.1fs", elapsed)
    log.debug("probe reply:\n%s", reply)

    try:
        payload.parse(reply, [1, 2])
    except payload.RewriteRejected as exc:
        log.warning("answered but did not follow the format: %s", exc)
        log.warning("the model replied:\n%s", logs.excerpt(reply))
        return Result(True, False, elapsed, str(exc), logs.excerpt(reply, 400))

    return Result(True, True, elapsed, "the model answered in the expected format")


def advice(result: Result, steps_in_a_real_run: int = 8) -> str:
    """A sentence about what the timing means for real use."""
    if not result.reached:
        return "Check the server address, and that the model has been pulled."
    if not result.understood:
        return (
            "The server works, but this model does not keep to the requested "
            "format. Rewrites will be refused and the document will keep its "
            "original wording. A larger model usually fixes this."
        )
    # The probe is roughly a fifth of a real request.
    estimate = result.seconds * steps_in_a_real_run / 2.0
    if estimate > 600:
        return (
            f"Working, but slow: a procedure of {steps_in_a_real_run} steps "
            f"would take roughly {estimate / 60:.0f} minutes."
        )
    return f"Working. A {steps_in_a_real_run}-step procedure should take about " \
           f"{estimate:.0f} seconds."
