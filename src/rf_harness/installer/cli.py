"""Command line entry point (`rf-harness` / `robotframework-harness`)."""

from __future__ import annotations

import argparse
import sys

from rf_harness import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rf-harness", description="Set up the Robot Framework agent harness for coding agents.")
    p.add_argument("--version", action="version", version=f"rf-harness {__version__}")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("version", help="print the version")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in (None, "version"):
        print(f"rf-harness {__version__}")
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
