"""A log file, for the failures that leave no other trace.

A tray notification says "the rewrite was rejected" and disappears. That is
enough to know something went wrong and useless for working out what: the one
thing worth seeing — what the model actually replied — is gone. The same is
true of a recording that silently drops events, or a document that generates
without the labels it should have had.

So: one file, rotated, in the application's data directory, and a menu entry
that opens it. Nothing is logged that the user has not already produced —
their own captured text and the model's replies — and it stays on the machine.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import Optional

from . import paths

NAME = "multycapture"

#: Kept small: this is for reading, not for archiving.
MAX_BYTES = 1_000_000
BACKUPS = 3

_configured = False


def log_file() -> Path:
    return paths.data_dir() / "logs" / "multycapture.log"


def setup(level: Optional[int] = None) -> logging.Logger:
    """Configure the log file once; return the application's logger.

    ``MULTYCAPTURE_DEBUG=1`` in the environment turns on the detail — full
    payloads and replies — which is off otherwise because a rewrite request
    carries the whole procedure.
    """
    global _configured
    logger = logging.getLogger(NAME)
    if _configured:
        return logger

    if level is None:
        level = logging.DEBUG if os.environ.get("MULTYCAPTURE_DEBUG") else logging.INFO
    logger.setLevel(level)
    logger.propagate = False

    try:
        target = log_file()
        paths.ensure(target.parent)
        handler = logging.handlers.RotatingFileHandler(
            target, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        logger.addHandler(handler)
    except OSError:
        # A read-only or missing data directory must not stop the application;
        # it only means this particular failure will be harder to diagnose.
        logger.addHandler(logging.NullHandler())

    _configured = True
    return logger


def get(suffix: str = "") -> logging.Logger:
    """The logger for a part of the application, e.g. ``get("ai")``."""
    setup()
    return logging.getLogger(f"{NAME}.{suffix}" if suffix else NAME)


def excerpt(text: str, limit: int = 2000) -> str:
    """A reply trimmed for the log, with the trimming made obvious."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… [{len(text) - limit} more characters]"
