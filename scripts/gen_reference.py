"""Generate docs/reference/cli.md and docs/reference/environment.md from the code, or check that they are current.

- CLI: the installer's argparse tree (`rf_harness.installer.cli.build_parser`).
- Environment: the `rf_harness.config.VARIABLES` registry, plus a scan of the source for `RFH_*` names: every name the
  code uses must be registered with a non-empty doc line (otherwise `--check` fails and names it).

    python scripts/gen_reference.py            # write both pages
    python scripts/gen_reference.py --check    # exit 1 if a page is stale or a variable is undocumented
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DOCS = ROOT / "docs" / "reference"
# names in the source that are not registry variables: launcher/installer test switches use RF_HARNESS_*, and the
# vendored desktop package keeps its own table (`desktop/_env.py`) but must still be registered in config.py
VAR_RE = re.compile(r"\bRFH_[A-Z][A-Z0-9_]*\b")
SCAN_DIRS = [ROOT / "src" / "rf_harness", ROOT / "plugins" / "rf-harness"]
IGNORE_NAMES = {"RFH_"}


def _cli_markdown() -> str:
    from rf_harness.installer.cli import build_parser

    parser = build_parser()
    out = ["# CLI reference", "",
           "Generated from the installer's argument parser (`scripts/gen_reference.py`); do not edit by hand.", "",
           "Run with zero install as `uvx robotframework-harness <command>`; installed, the commands are",
           "`rf-harness` and `robotframework-harness`.", "", "```text", parser.format_help().rstrip(), "```", ""]
    subs = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]  # noqa: SLF001
    for action in subs:
        for name, sp in action.choices.items():
            out += [f"## `{name}`", "", "```text", sp.format_help().rstrip(), "```", ""]
    return "\n".join(out)


def _used_names() -> set[str]:
    names: set[str] = set()
    for base in SCAN_DIRS:
        for path in base.rglob("*"):
            if path.is_file() and path.suffix in {".py", ".js", ".json", ""} and "__pycache__" not in path.parts:
                try:
                    names |= set(VAR_RE.findall(path.read_text(encoding="utf-8", errors="ignore")))
                except OSError:
                    continue
    return names - IGNORE_NAMES


def _env_markdown() -> str:
    from rf_harness import config

    out = ["# Environment variables", "",
           "Generated from `src/rf_harness/config.py` (`scripts/gen_reference.py`); do not edit by hand. Set them in the",
           "agent's environment, or as defaults in `.rf/harness.json` under `\"env\"` (the process environment wins).", ""]
    by_cat: dict[str, list] = {}
    for var in sorted(config.VARIABLES.values(), key=lambda v: v.name):
        by_cat.setdefault(var.category, []).append(var)
    for cat in sorted(by_cat):
        out += [f"## {cat}", "", "| variable | default | meaning |", "|---|---|---|"]
        for var in by_cat[cat]:
            default = f"`{var.default}`" if var.default != "" else "(empty)"
            out.append(f"| `{var.name}` | {default} | {var.doc.replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    from rf_harness import config

    problems: list[str] = []
    missing = sorted(n for n in _used_names() if n not in config.VARIABLES)
    if missing:
        problems.append("used but not registered in rf_harness.config: " + ", ".join(missing))
    undocumented = sorted(n for n, v in config.VARIABLES.items() if not v.doc.strip())
    if undocumented:
        problems.append("registered without a doc line: " + ", ".join(undocumented))
    pages = {DOCS / "cli.md": _cli_markdown(), DOCS / "environment.md": _env_markdown()}
    for path, text in pages.items():
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != text:
                problems.append(f"{path.relative_to(ROOT)} is stale: run python scripts/gen_reference.py")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    for p in problems:
        print(p, file=sys.stderr)
    if not args.check:
        print(f"wrote {', '.join(str(p.relative_to(ROOT)) for p in pages)}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
