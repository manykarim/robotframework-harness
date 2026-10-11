#!/usr/bin/env python3
"""Write or verify the sha256 checksums of the evidence archive (stdlib only).

    python3 evidence/checksums.py --write     # after an import or an edit of archived data
    python3 evidence/checksums.py --verify    # CI: every listed file matches, no file is missing or unlisted

Covered: the archived data, i.e. everything under ``rounds/``, ``harness-versions/``, ``eval-snapshots/``,
``upstream/`` and ``transcripts/``, plus ``incidents.md``, ``provenance.json`` and ``scrub_report.json``. Not covered:
the tooling (``*.py``), the guides (``README.md``, ``REPRODUCE.md``, ``PROVENANCE.md``), ``claims.yaml`` and the
git-ignored ``_release_assets/``.

Two kinds of files, both in ``sha256sum`` format (``<hex>  <path>``) and checkable with ``sha256sum -c``:
  * ``evidence/checksums.sha256`` -- every covered file, paths relative to ``evidence/``;
  * ``rounds/<NN>-<topic>/checksums.sha256`` -- the files of that round, paths relative to the round folder.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "checksums.sha256"
COVERED_DIRS = ("rounds", "harness-versions", "eval-snapshots", "upstream", "transcripts")
COVERED_FILES = ("incidents.md", "provenance.json", "scrub_report.json")
IGNORED_PARTS = {"__pycache__", ".pytest_cache"}


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def covered_files(root: Path) -> list[Path]:
    files = [root / f for f in COVERED_FILES if (root / f).is_file()]
    for d in COVERED_DIRS:
        base = root / d
        if base.is_dir():
            files += [p for p in base.rglob("*") if p.is_file() and not IGNORED_PARTS & set(p.parts)]
    return sorted(files, key=lambda p: p.relative_to(root).as_posix())


def round_dirs(root: Path) -> list[Path]:
    rounds = root / "rounds"
    return sorted(p for p in rounds.iterdir() if p.is_dir()) if rounds.is_dir() else []


def render(entries: list[tuple[str, str]]) -> str:
    return "".join(f"{digest}  {rel}\n" for rel, digest in entries)


def parse(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        out[rel.lstrip("*")] = digest
    return out


def write(root: Path) -> int:
    n = 0
    for rdir in round_dirs(root):  # per round first, so the global list covers them too
        files = [p for p in covered_files(root) if rdir in p.parents and p != rdir / NAME]
        entries = [(p.relative_to(rdir).as_posix(), file_sha256(p)) for p in files]
        (rdir / NAME).write_text(render(entries), encoding="utf-8", newline="\n")
        n += 1
    entries = [(p.relative_to(root).as_posix(), file_sha256(p)) for p in covered_files(root)]
    (root / NAME).write_text(render(entries), encoding="utf-8", newline="\n")
    print(f"wrote {root / NAME} ({len(entries)} files) and {n} per-round {NAME} files")
    return 0


def _compare(listed: dict[str, str], actual: dict[str, Path], label: str) -> list[str]:
    problems = []
    for rel, digest in listed.items():
        path = actual.get(rel)
        if path is None:
            problems.append(f"{label}: missing {rel}")
        elif file_sha256(path) != digest:
            problems.append(f"{label}: checksum mismatch {rel}")
    for rel in sorted(set(actual) - set(listed)):
        problems.append(f"{label}: not listed {rel}")
    return problems


def verify(root: Path) -> list[str]:
    problems: list[str] = []
    top = root / NAME
    if not top.is_file():
        return [f"{top} is missing (run checksums.py --write)"]
    files = covered_files(root)
    problems += _compare(parse(top.read_text(encoding="utf-8")),
                         {p.relative_to(root).as_posix(): p for p in files}, NAME)
    for rdir in round_dirs(root):
        listing = rdir / NAME
        mine = {p.relative_to(rdir).as_posix(): p for p in files if rdir in p.parents and p != listing}
        label = f"rounds/{rdir.name}/{NAME}"
        if not listing.is_file():
            problems.append(f"{label} is missing")
            continue
        problems += _compare(parse(listing.read_text(encoding="utf-8")), mine, label)
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", action="store_true")
    g.add_argument("--verify", action="store_true")
    ap.add_argument("--root", type=Path, default=HERE, help="archive root (default: the evidence/ folder)")
    args = ap.parse_args(argv)
    if args.write:
        return write(args.root)
    problems = verify(args.root)
    for p in problems[:200]:
        print(p)
    if len(problems) > 200:
        print(f"... {len(problems) - 200} more")
    n = len(covered_files(args.root))
    print(f"checksums: {n} files, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
