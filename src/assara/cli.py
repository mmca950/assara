"""Command line: `assara <command> ...`.

Each command lives in its own module, which exposes `configure(subparsers)`. That function adds one
sub-command and sets `func(args, cfg)` as its handler. Commands that do not need a library (init,
version) set `needs_library = False`.
"""

from __future__ import annotations

import argparse
import sys
import traceback

from . import __version__
from .config import Config, find_root
from .library import AssaraError, SafeStream, terminal_safe

COMMAND_MODULES = (
    "init",
    "status",
    "extract",
    "transcribe",
    "link",
    "regroup",
    "rebuild",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assara",
        description="Turn sources (PDF, EPUB, audio, video, web pages) into units of raw text, ready to be "
        "distilled into notes and syntheses by Claude Code. See `assara <command> -h`.",
    )
    parser.add_argument("--version", action="version", version=f"assara {__version__}")
    parser.add_argument("--library", help="library root (default: ASSARA_HOME or current folder)")
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for name in COMMAND_MODULES:
        module = __import__(f"assara.commands.{name}", fromlist=["configure"])
        module.configure(sub)
    return parser


def safe_excepthook(kind, value, tb) -> None:
    """Print an unexpected error's traceback with control characters shown as '?'."""
    if sys.__stderr__ is not None:
        sys.__stderr__.write(terminal_safe("".join(traceback.format_exception(kind, value, tb))))


def main(argv: list[str] | None = None) -> int:
    if sys.excepthook is sys.__excepthook__:
        # The traceback of an unexpected error is printed after main() has returned the streams.
        sys.excepthook = safe_excepthook
    saved = sys.stdout, sys.stderr
    # A stream is None when Python starts without it (closed descriptor, no console): keep it None.
    sys.stdout, sys.stderr = (None if s is None else SafeStream(s) for s in saved)
    try:
        return run(argv)
    except AssaraError as e:
        raise AssaraError(terminal_safe(str(e))) from e
    finally:
        sys.stdout, sys.stderr = saved


def run(argv: list[str] | None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    cfg = None
    if getattr(args, "needs_library", True):
        cfg = Config.load(find_root(args.library))
    result = args.func(args, cfg)
    return int(result or 0)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
