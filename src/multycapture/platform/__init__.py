"""Platform abstraction package.

Import ``get_backend`` to obtain the right :class:`PlatformBackend` for the
current OS. Concrete backends are imported lazily by the factory so that, e.g.,
Windows never imports ``python-xlib``.
"""

from .base import PlatformBackend, PlatformError, get_backend

__all__ = ["PlatformBackend", "PlatformError", "get_backend"]
