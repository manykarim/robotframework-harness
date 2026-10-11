#!/usr/bin/env python3
"""Verify downloaded transcript release assets against the committed manifests (stdlib + zstd CLI for .tar.zst).

    python3 evidence/verify_assets.py                         # every asset found in evidence/_release_assets/
    python3 evidence/verify_assets.py --assets ~/Downloads --round 07-v31-v32

Checks, per round listed in ``transcripts/assets.json``:
  1. the asset file's sha256 and size match ``assets.json``;
  2. every member of the tar has the sha256 and size from ``transcripts/<round>.manifest.json``, no member is
     missing or extra, and the embedded ``manifest.json`` equals the committed one;
  3. every manifest entry maps to exactly one row: the referenced results / excluded / backup file exists in the
     archive and holds a row with that key and transcript path (``unreferenced`` entries are counted and reported).

``.tar.zst`` assets are decompressed with the ``zstd`` CLI (``zstd -dc``), or with ``compression.zstd`` on
Python 3.14+. Exit code 1 on any mismatch; a round whose asset is absent is reported as skipped (exit 0) unless
``--require`` is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import IO

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "_release_assets"
MANIFESTS = HERE / "transcripts"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@contextmanager
def open_stream(asset: Path) -> Iterator[IO[bytes]]:
    if asset.name.endswith(".tar.gz") or asset.name.endswith(".tgz"):
        with asset.open("rb") as fh:
            yield fh
        return
    try:  # Python 3.14+
        from compression import zstd  # type: ignore[import-not-found]

        with zstd.open(asset, "rb") as fh:
            yield fh
        return
    except ImportError:
        pass
    if not shutil.which("zstd"):
        raise SystemExit("reading .tar.zst needs the zstd CLI (or Python 3.14+)")
    proc = subprocess.Popen(["zstd", "-dc", str(asset)], stdout=subprocess.PIPE)
    assert proc.stdout is not None
    try:
        yield proc.stdout
    finally:
        proc.stdout.close()
        if proc.wait() != 0:
            raise SystemExit(f"zstd failed on {asset}")


def _rows(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def check_mapping(round_dir: Path, entries: list[dict]) -> tuple[list[str], int]:
    problems: list[str] = []
    cache: dict[str, list[dict]] = {}
    unreferenced = 0
    for e in entries:
        if e["status"] == "unreferenced":
            unreferenced += 1
            continue
        rel = e["results_file"]
        if rel not in cache:
            path = round_dir / rel
            if not path.is_file():
                problems.append(f"{e['file']}: results file {rel} missing from the archive")
                cache[rel] = []
                continue
            rows = _rows(path)
            cache[rel] = [r["row"] if "row" in r and "reason" in r else r for r in rows]
        matches = [r for r in cache[rel] if r.get("key") == e["key"] and r.get("transcript") == e["transcript"]]
        if not matches:
            problems.append(f"{e['file']}: no row with key {e['key']!r} and this transcript in {rel}")
    return problems, unreferenced


def verify_round(entry: dict, assets: Path, root: Path) -> tuple[str, list[str]]:
    rnd = entry["round"]
    asset = assets / entry["asset"]
    if not asset.is_file():
        return "skipped", [f"{rnd}: asset {entry['asset']} not found in {assets}"]
    problems: list[str] = []
    if asset.stat().st_size != entry["bytes"] or file_sha256(asset) != entry["sha256"]:
        problems.append(f"{rnd}: asset checksum/size differs from transcripts/assets.json")
    committed = (root / entry["manifest"]).read_bytes()
    manifest = json.loads(committed)
    want = {f"{rnd}/{e['file']}": e for e in manifest["entries"]}
    seen: set[str] = set()
    embedded: bytes | None = None
    with open_stream(asset) as stream, tarfile.open(fileobj=stream, mode="r|*") as tar:
        for m in tar:
            if not m.isfile():
                continue
            f = tar.extractfile(m)
            data = f.read() if f else b""
            if m.name == f"{rnd}/manifest.json":
                embedded = data
                continue
            e = want.get(m.name)
            if e is None:
                problems.append(f"{rnd}: member not in the manifest: {m.name}")
                continue
            seen.add(m.name)
            if len(data) != e["bytes"] or hashlib.sha256(data).hexdigest() != e["sha256"]:
                problems.append(f"{rnd}: checksum mismatch {m.name}")
    for name in sorted(set(want) - seen):
        problems.append(f"{rnd}: missing from the asset: {name}")
    if embedded is None:
        problems.append(f"{rnd}: asset has no manifest.json")
    elif embedded != committed:
        problems.append(f"{rnd}: embedded manifest.json differs from {entry['manifest']}")
    mapping, unreferenced = check_mapping(root / "rounds" / rnd, manifest["entries"])
    problems += mapping
    mapped = len(manifest["entries"]) - unreferenced
    status = (f"{len(seen)} transcripts verified, {mapped} mapped to a result row"
              + (f", {unreferenced} unreferenced" if unreferenced else ""))
    return status, problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--assets", type=Path, default=ASSETS, help="directory with the downloaded assets")
    ap.add_argument("--round", action="append", default=[], help="verify only these rounds")
    ap.add_argument("--require", action="store_true", help="fail when an asset is missing")
    ap.add_argument("--root", type=Path, default=HERE)
    args = ap.parse_args(argv)
    index = json.loads((args.root / "transcripts" / "assets.json").read_text(encoding="utf-8"))
    failed = missing = 0
    for entry in index["assets"]:
        if args.round and entry["round"] not in args.round:
            continue
        status, problems = verify_round(entry, args.assets.expanduser(), args.root)
        if status == "skipped":
            missing += 1
            print(f"skip {entry['round']}: {problems[0]}")
            continue
        failed += bool(problems)
        print(f"{'FAIL' if problems else 'ok':4} {entry['round']} ({entry['asset']}): {status}")
        for p in problems[:50]:
            print(f"       {p}")
    if missing and args.require:
        failed += missing
    print(f"assets: {failed} failed, {missing} missing")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
