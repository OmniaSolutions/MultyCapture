"""The one thing every model backend has to do.

A provider takes a fully-composed message and returns the model's reply as
text. Everything else — what goes in the message, what a valid reply looks
like, what happens to it — lives in :mod:`..payload`, so adding a backend is a
matter of moving one string across the network, and no backend can influence
what the document ends up containing beyond the wording it returns.

Every backend is one JSON POST over :mod:`.http`, with no client library, so
that a packaged build behaves exactly like one run from source.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class ProviderError(Exception):
    """The model could not be reached, or refused to answer.

    Carries a message meant for the user, not a stack trace: this surfaces in a
    tray notification.
    """


class MissingCredential(ProviderError):
    """No API key is configured for the backend."""


@runtime_checkable
class Provider(Protocol):
    """A model backend."""

    #: Stable identifier, stored in settings.
    id: str
    #: Name shown in the menu.
    label: str
    #: Whether the request leaves this machine.
    local: bool

    def complete(self, message: str) -> str:
        """Send ``message``, return the reply text.

        Raises :class:`ProviderError` for anything the user could act on:
        unreachable host, missing key, refusal, quota.
        """
        ...
