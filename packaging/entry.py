"""Frozen-app entry point.

With no arguments it launches the system-tray GUI (the primary experience). With
arguments it dispatches to the CLI, so the single bundled executable also works as
``MultyCapture record`` / ``MultyCapture doc`` / ``MultyCapture selftest``.
"""

import sys


def run() -> int:
    if len(sys.argv) > 1:
        from multycapture.cli import main
        return main()
    from multycapture.gui.tray import main as tray_main
    return tray_main()


if __name__ == "__main__":
    raise SystemExit(run())
