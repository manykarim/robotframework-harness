#!/usr/bin/env python3
"""Scrub and pack the session transcripts of each round into a release asset with a manifest (stdlib + zstd CLI).

    python3 evidence/pack_transcripts.py --transcripts ~/workspace/rf-mcp-robotcode/experiments/robotcode-remote/ab/harness
    python3 evidence/pack_transcripts.py --transcripts DIR --rounds 07-v31-v32 --format gz

For every A/B round (``rounds/<NN>/config.json`` lists its ``transcript_dirs``) this writes:
  * ``_release_assets/evidence-transcripts-<round>.tar.zst`` (``.tar.gz`` when the ``zstd`` CLI is missing or
    ``--format gz``): every transcript, decompressed and scrubbed, as ``<round>/<transcript_dir>/<agent>/<cell>.jsonl``, and
    ``<round>/manifest.json`` as the last member;
  * ``transcripts/<round>.manifest.json`` (committed): per transcript the path in the asset, its sha256 and size,
    the transcript path the result row refers to, the results file and row key, the row status
    (``scored`` / ``not_scored_in_results_file`` / ``excluded:<reason>`` / ``backup_only`` / ``unreferenced``)
    and the scrub substitutions;
  * ``transcripts/assets.json`` (committed): asset file name, size and sha256 per round.

The asset is not built when the scrub cannot clean a transcript (auth file, binary with a secret) or when the
scrubbed content still has findings. Tar members are written in sorted order with fixed metadata, so the same
input gives the same tar. ``_release_assets/`` is git-ignored; nothing is uploaded.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scrub  # noqa: E402

ASSETS = HERE / "_release_assets"
MANIFESTS = HERE / "transcripts"
ZSTD_LEVEL = "-12"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ab_rounds(root: Path) -> list[tuple[str, dict]]:
    out = []
    for cfg in sorted((root / "rounds").glob("*/config.json")):
        meta = json.loads(cfg.read_text(encoding="utf-8"))
        if meta.get("transcript_dirs"):
            out.append((cfg.parent.name, meta))
    return out


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def row_index(rdir: Path) -> dict[str, dict]:
    """transcript path (as in result rows) -> {results_file, key, status} with the most authoritative status."""
    index: dict[str, dict] = {}
    rank = {"scored": 0, "not_scored_in_results_file": 1, "excluded": 2, "backup_only": 3}

    def put(tx: str | None, info: dict) -> None:
        if not tx:
            return
        old = index.get(tx)
        if old is None or rank[info["_rank"]] < rank[old["_rank"]]:
            index[tx] = info

    for f in sorted((rdir / "results").glob("results_*.jsonl")):
        for row in _jsonl(f):
            scored = row.get("status") == "ok" and not row.get("contaminated")
            put(row.get("transcript"), {"results_file": f"results/{f.name}", "key": row.get("key"),
                                        "status": "scored" if scored else "not_scored_in_results_file",
                                        "_rank": "scored" if scored else "not_scored_in_results_file"})
    for f in sorted((rdir / "excluded").glob("excluded_*.jsonl")) if (rdir / "excluded").is_dir() else []:
        for rec in _jsonl(f):
            if rec.get("in_results_file"):
                continue
            put(rec["row"].get("transcript"), {"results_file": f"excluded/{f.name}", "key": rec.get("key"),
                                               "status": f"excluded:{rec['reason']}", "_rank": "excluded"})
    for f in sorted((rdir / "backups").glob("*.jsonl")) if (rdir / "backups").is_dir() else []:
        for row in _jsonl(f):
            put(row.get("transcript"), {"results_file": f"backups/{f.name}", "key": row.get("key"),
                                        "status": "backup_only", "_rank": "backup_only"})
    return index


def _tarinfo(name: str, size: int) -> tarfile.TarInfo:
    ti = tarfile.TarInfo(name)
    ti.size, ti.mtime, ti.mode, ti.uid, ti.gid, ti.uname, ti.gname = size, 0, 0o644, 0, 0, "", ""
    return ti


def build_round(round_name: str, meta: dict, transcripts: Path, root: Path, rules: list[scrub.Rule],
                fmt: str, assets: Path, manifests: Path | None = None) -> dict | None:
    """Stream the scrubbed transcripts into <asset>.tar (manifest last), then compress; None if blocked."""
    rdir = root / "rounds" / round_name
    index = row_index(rdir)
    entries: list[dict] = []
    totals: dict[str, int] = {}
    blocked: list[str] = []
    assets.mkdir(parents=True, exist_ok=True)
    asset = assets / f"evidence-transcripts-{round_name}.tar.{'zst' if fmt == 'zst' else 'gz'}"
    tmp_tar = assets / f".{round_name}.tar.partial"
    with tarfile.open(tmp_tar, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for tdir in meta["transcript_dirs"]:
            for src in sorted((transcripts / tdir).rglob("*")):
                if not src.is_file():
                    continue
                rel = src.relative_to(transcripts).as_posix()
                if scrub.path_issue(Path(rel).parts):
                    blocked.append(f"{rel}: auth file / agent home")
                    continue
                report = scrub.Report("apply", rel)
                data, _ = scrub.read_payload(src)
                clean = scrub.scrub_bytes(data, rel, rules, report)
                if clean is None:
                    blocked.append(f"{rel}: binary with a secret")
                    continue
                recheck = scrub.Report("check", rel)
                scrub.scan_text(scrub._decode(clean), rules, rel, recheck)
                if recheck.findings:
                    blocked.append(f"{rel}: findings remain after the scrub: {dict(recheck.rule_counts)}")
                    continue
                inner = rel[: -len(".gz")] if rel.endswith(".gz") else rel
                info = index.get(rel)
                entry = {"file": inner, "transcript": rel, "sha256": sha256(clean), "bytes": len(clean)}
                if info:
                    entry.update({k: v for k, v in info.items() if not k.startswith("_")})
                else:
                    entry.update({"results_file": None, "key": None, "status": "unreferenced"})
                subs = dict(sorted(report.rule_counts.items()))
                entry["scrub"] = subs
                for k, v in subs.items():
                    totals[k] = totals.get(k, 0) + v
                entries.append(entry)
                tar.addfile(_tarinfo(f"{round_name}/{inner}", len(clean)), io.BytesIO(clean))
        status_counts: dict[str, int] = {}
        for e in entries:
            status_counts[e["status"]] = status_counts.get(e["status"], 0) + 1
        manifest = {
            "round": round_name,
            "asset_format": "tar.zst" if fmt == "zst" else "tar.gz",
            "transcript_dirs": meta["transcript_dirs"],
            "files": len(entries),
            "status_counts": dict(sorted(status_counts.items())),
            "scrub_substitutions": dict(sorted(totals.items())),
            "scrub_py_sha256": sha256((HERE / "scrub.py").read_bytes()),
            "entries": entries,
        }
        mbytes = (json.dumps(manifest, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
        tar.addfile(_tarinfo(f"{round_name}/manifest.json", len(mbytes)), io.BytesIO(mbytes))
    if blocked:
        tmp_tar.unlink()
        print(f"{round_name}: asset NOT built, the scrub could not clean {len(blocked)} transcripts:")
        for b in blocked[:20]:
            print(f"  {b}")
        return None
    tar_bytes = tmp_tar.stat().st_size
    if fmt == "zst":
        subprocess.run(["zstd", "-q", "-f", ZSTD_LEVEL, "-T0", "--rm", str(tmp_tar), "-o", str(asset)], check=True)
    else:
        with tmp_tar.open("rb") as fin, asset.open("wb") as raw_out, \
                gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0, compresslevel=9) as gz:
            shutil.copyfileobj(fin, gz, 1 << 20)
        tmp_tar.unlink()
    (asset.parent / (asset.name + ".manifest.json")).write_bytes(mbytes)
    manifests = manifests or root / "transcripts"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / f"{round_name}.manifest.json").write_bytes(mbytes)
    digest = hashlib.sha256()
    with asset.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    size = asset.stat().st_size
    print(f"{round_name}: {len(entries)} transcripts, {tar_bytes / 1e6:.1f} MB tar -> {asset.name} "
          f"{size / 1e6:.1f} MB; status {manifest['status_counts']}; scrub {manifest['scrub_substitutions']}")
    return {"round": round_name, "asset": asset.name, "bytes": size, "sha256": digest.hexdigest(),
            "files": len(entries), "tar_bytes": tar_bytes, "manifest": f"transcripts/{round_name}.manifest.json"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--transcripts", type=Path, required=True, help="directory holding the transcripts_* folders")
    ap.add_argument("--rounds", default="", help="comma-separated round folders (default: every A/B round)")
    ap.add_argument("--format", choices=("auto", "zst", "gz"), default="auto")
    ap.add_argument("--out", type=Path, default=ASSETS)
    args = ap.parse_args(argv)
    fmt = args.format
    if fmt == "auto":
        fmt = "zst" if shutil.which("zstd") else "gz"
    elif fmt == "zst" and not shutil.which("zstd"):
        ap.error("--format zst needs the zstd CLI on PATH")
    wanted = {r.strip() for r in args.rounds.split(",") if r.strip()}
    rules = scrub.build_rules()
    index_path = MANIFESTS / "assets.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {"assets": []}
    by_round = {a["round"]: a for a in index["assets"]}
    failed = 0
    for name, meta in ab_rounds(HERE):
        if wanted and name not in wanted:
            continue
        res = build_round(name, meta, args.transcripts.expanduser(), HERE, rules, fmt, args.out)
        if res is None:
            failed += 1
            continue
        by_round[name] = res
    index = {"about": ("Release assets with the scrubbed session transcripts, one per A/B round. Download them "
                       "into evidence/_release_assets/ and run evidence/verify_assets.py."),
             "assets": [by_round[k] for k in sorted(by_round)]}
    MANIFESTS.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
    total = sum(a["bytes"] for a in index["assets"])
    print(f"assets: {len(index['assets'])}, {total / 1e6:.1f} MB total" + (f"; {failed} NOT built" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
