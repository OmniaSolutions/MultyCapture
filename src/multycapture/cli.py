"""MultyCapture command-line interface.

Usage:
    mc record [--out DIR] [--scope monitor|window|virtual_desktop]
              [--keyboard consolidate|every_key|shortcuts_only] [--stop COMBO]

``mc record`` starts a global capture session and writes a session folder under
``--out`` (default: the per-user captures directory, see :mod:`.paths`). Stop it
with the stop hotkey (default Ctrl+Alt+Q) or Ctrl+C.
"""

from __future__ import annotations

import argparse
import sys

from . import paths
from .model import CaptureConfig, KeyboardMode, ShotScope
from .platform import PlatformError


def _cmd_record(args: argparse.Namespace) -> int:
    from .capture import Recorder

    config = CaptureConfig(
        shot_scope=ShotScope(args.scope),
        keyboard_mode=KeyboardMode(args.keyboard),
    )
    try:
        rec = Recorder(root=args.out, config=config, stop_combo=args.stop)
        writer = rec.start()
    except PlatformError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(f"Recording -> {writer.dir}")
    print(f"Scope: {args.scope} | keyboard: {args.keyboard}")
    print(f"Stop with {args.stop.upper()} or Ctrl+C.")
    try:
        rec.wait()
    except KeyboardInterrupt:
        print("\nStopping (Ctrl+C)...")
        rec.stop()

    print(f"Done. {rec.event_count} events written to {rec.session_dir}")
    return 0


def _cmd_doc(args: argparse.Namespace) -> int:
    from .capture import SessionReader
    from .generate import generate_docx

    if args.last or not args.session:
        try:
            session_dir = str(SessionReader.latest(args.root).dir)
        except FileNotFoundError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    else:
        session_dir = args.session

    print(f"Generating docx from {session_dir} ...")
    out = generate_docx(
        session_dir,
        out_path=args.out,
        template=args.template,
        title=args.title,
        annotate=not args.no_annotate,
        condense_steps=not args.raw,
        max_width=args.max_width,
    )
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"Wrote {out}  ({size_mb:.1f} MB)")
    return 0


def _cmd_tray(args: argparse.Namespace) -> int:
    from .gui.tray import main as tray_main
    return tray_main()


def _cmd_selftest(args: argparse.Namespace) -> int:
    """Import every heavy module so a frozen build can verify its bundle."""
    import importlib
    mods = [
        "multycapture.model", "multycapture.platform",
        "multycapture.capture.recorder", "multycapture.capture.grabber",
        "multycapture.capture.session_reader", "multycapture.generate.docx_writer",
        "multycapture.generate.condense", "multycapture.gui.tray",
        "mss", "pynput.mouse", "pynput.keyboard", "PySide6.QtWidgets",
    ]
    for m in mods:
        importlib.import_module(m)
        print("ok", m)
    print("SELFTEST OK")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mc", description="MultyCapture")
    sub = parser.add_subparsers(dest="command", required=True)

    rec = sub.add_parser("record", help="record a capture session")
    rec.add_argument(
        "--out", default=str(paths.captures_dir()),
        help=f"output root dir (default: {paths.captures_dir()})",
    )
    rec.add_argument(
        "--scope", default="monitor",
        choices=[s.value for s in ShotScope],
        help="what each screenshot captures (default: monitor)",
    )
    rec.add_argument(
        "--keyboard", default="consolidate",
        choices=[k.value for k in KeyboardMode],
        help="keyboard recording mode (default: consolidate)",
    )
    rec.add_argument("--stop", default="ctrl+alt+q", help="stop hotkey combo (default: ctrl+alt+q)")
    rec.set_defaults(func=_cmd_record)

    doc = sub.add_parser("doc", help="generate a .docx from a captured session")
    doc.add_argument("session", nargs="?", help="session directory (default: latest)")
    doc.add_argument(
        "--root", default=str(paths.captures_dir()),
        help=f"sessions root for --last (default: {paths.captures_dir()})",
    )
    doc.add_argument("--last", action="store_true", help="use the most recent session")
    doc.add_argument(
        "-o", "--out", default=None,
        help=f"output .docx path (default: under {paths.documents_dir()})",
    )
    doc.add_argument(
        "--template", default=None,
        help=f"start from this .docx (templates live in {paths.templates_dir()})",
    )
    doc.add_argument("--title", default=None, help="document title")
    doc.add_argument("--no-annotate", action="store_true", help="do not draw click highlights")
    doc.add_argument("--raw", action="store_true", help="one step per event (disable condensing)")
    doc.add_argument("--max-width", type=int, default=1200, help="max screenshot width in px (default: 1200)")
    doc.set_defaults(func=_cmd_doc)

    tray = sub.add_parser("tray", help="run the system-tray control app (PySide6)")
    tray.set_defaults(func=_cmd_tray)

    st = sub.add_parser("selftest", help="verify all modules import (used by packaging CI)")
    st.set_defaults(func=_cmd_selftest)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
