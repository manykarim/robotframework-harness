#!/usr/bin/env python3
"""Recompute every indexed claim from the archived result files and fail when one differs (stdlib only).

    python3 evidence/check_claims.py                  # all claims; exit 1 on any mismatch
    python3 evidence/check_claims.py --only r7-pooled-v31 --show
    python3 evidence/check_claims.py --check-sources  # also require each claim's text in its source file

``claims.yaml`` is written in the JSON-compatible subset of YAML: full-line ``#`` comments are allowed, everything
else is JSON, so the file is read with the standard library (comments stripped, then ``json.loads``).

Row semantics follow the archived analyzer (``eval-snapshots/ab-7994ae3/harness/analyze.py``):
  * only ``status == "ok"`` rows count; per results file the last ok row per ``key`` wins;
  * ``contaminated``: ``keep`` (analyzer default, used by the published reports) or ``drop``
    (``--drop-contaminated``);
  * pass = ``primary_pass`` (all graders passed).

Metrics (``compute.metric``):
  pass_rate      passes / n                         expect: value, passes, n
  count          number of rows                     expect: value
  distinct       distinct values of ``field``       expect: value
  mean           mean of metrics.<field>            expect: value
  count_true     rows with metrics.<field> true     expect: value
  sum            sum of metrics.<field>             expect: value
  wilson         95% Wilson interval of pass rate   expect: lo, hi
  fisher         two-sided Fisher exact, arm a vs b (pooled)            expect: p
  sign_test      per (agent, scenario) cell rate a - b: +/- cells, p    expect: pos, neg, p
  excluded       rows in excluded_*.jsonl files (optional reason)       expect: value
"""
from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from fnmatch import fnmatch
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLAIMS = HERE / "claims.yaml"
EPS = 1e-9


# --------------------------------------------------------------------------- #
# statistics (same formulas as analyze.py)
# --------------------------------------------------------------------------- #
def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    n1, n2, k = a + b, c + d, a + c
    big_n = n1 + n2
    if big_n == 0 or n1 == 0 or n2 == 0:
        return 1.0
    denom = math.comb(big_n, k)

    def pr(x: int) -> float:
        return math.comb(n1, x) * math.comb(n2, k - x) / denom

    lo, hi = max(0, k - n2), min(k, n1)
    p_obs = pr(a)
    return min(1.0, sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p_obs * (1 + 1e-9)))


def sign_test(pos: int, neg: int) -> float:
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n)


def wilson(passes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    ph = passes / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load_doc(path: Path = CLAIMS) -> dict:
    text = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#"))
    return json.loads(text)


def load_claims(path: Path = CLAIMS) -> list[dict]:
    return load_doc(path)["claims"]


def load_rows(root: Path, rel: str) -> list[dict]:
    """ok rows of one results file, de-duplicated by key keeping the last (analyze.load)."""
    latest: dict[str, dict] = {}
    for line in (root / rel).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("status") == "ok":
            latest[row["key"]] = row
    return list(latest.values())


def _match(value: str, patterns: list[str] | None) -> bool:
    return patterns is None or any(fnmatch(str(value), p) for p in patterns)


def select(rows: list[dict], flt: dict | None, contaminated: str) -> list[dict]:
    flt = flt or {}
    out = []
    for r in rows:
        if contaminated == "drop" and r.get("contaminated"):
            continue
        if not (_match(r["agent"], flt.get("agents")) and _match(r["arm"], flt.get("arms"))
                and _match(r["scenario"], flt.get("scenarios")) and _match(str(r.get("kind")), flt.get("kinds"))):
            continue
        out.append(r)
    return out


def _metric(r: dict, field: str):
    v = (r.get("metrics") or {}).get(field)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _passes(rows: list[dict]) -> tuple[int, int]:
    return sum(1 for r in rows if r.get("primary_pass")), len(rows)


# --------------------------------------------------------------------------- #
# compute
# --------------------------------------------------------------------------- #
def compute(claim: dict, root: Path) -> dict:
    spec = claim["compute"]
    metric = spec["metric"]
    if metric == "excluded":
        rows = []
        for rel in claim["files"]:
            rows += [json.loads(ln) for ln in (root / rel).read_text(encoding="utf-8").splitlines() if ln.strip()]
        if spec.get("reason"):
            rows = [r for r in rows if r.get("reason") == spec["reason"]]
        return {"value": len(rows)}
    rows = [r for rel in claim["files"] for r in load_rows(root, rel)]
    contaminated = spec.get("contaminated", "keep")
    if metric in ("fisher", "sign_test"):
        a = select(rows, {**spec.get("filter", {}), "arms": [spec["a"]]}, contaminated)
        b = select(rows, {**spec.get("filter", {}), "arms": [spec["b"]]}, contaminated)
        if metric == "fisher":
            pa, na = _passes(a)
            pb, nb = _passes(b)
            return {"p": fisher_exact(pa, na - pa, pb, nb - pb), "a": f"{pa}/{na}", "b": f"{pb}/{nb}"}
        cells: dict[tuple[str, str], dict[str, list[int]]] = defaultdict(lambda: {"a": [0, 0], "b": [0, 0]})
        for side, rs in (("a", a), ("b", b)):
            for r in rs:
                c = cells[(r["agent"], r["scenario"])][side]
                c[0] += 1 if r.get("primary_pass") else 0
                c[1] += 1
        deltas = [v["a"][0] / v["a"][1] - v["b"][0] / v["b"][1] for v in cells.values() if v["a"][1] and v["b"][1]]
        pos, neg = sum(1 for d in deltas if d > 0), sum(1 for d in deltas if d < 0)
        return {"pos": pos, "neg": neg, "p": sign_test(pos, neg), "cells": len(deltas)}
    sel = select(rows, spec.get("filter"), contaminated)
    if metric == "pass_rate":
        p, n = _passes(sel)
        return {"value": p / n if n else None, "passes": p, "n": n}
    if metric == "wilson":
        p, n = _passes(sel)
        lo, hi = wilson(p, n)
        return {"lo": lo, "hi": hi, "passes": p, "n": n}
    if metric == "count":
        return {"value": len(sel)}
    if metric == "distinct":
        return {"value": len({str(r.get(spec["field"])) for r in sel})}
    vals = [_metric(r, spec["field"]) for r in sel]
    if metric == "mean":
        xs = [v for v in vals if v is not None]
        return {"value": sum(xs) / len(xs) if xs else None, "n": len(xs)}
    if metric == "sum":
        return {"value": sum(v for v in vals if v is not None)}
    if metric == "count_true":
        return {"value": sum(1 for r in sel if (r.get("metrics") or {}).get(spec["field"]) is True)}
    raise ValueError(f"unknown metric {metric!r}")


def compare(claim: dict, got: dict) -> list[str]:
    errors = []
    tol = claim["expect"].get("tolerance", 0.0)
    for key, want in claim["expect"].items():
        if key == "tolerance":
            continue
        have = got.get(key)
        if have is None:
            errors.append(f"{key}: no value computed")
        elif isinstance(want, int) and not isinstance(want, bool) and isinstance(have, int):
            if have != want:
                errors.append(f"{key}: expected {want}, computed {have}")
        elif isinstance(want, (int, float)):
            if abs(float(have) - float(want)) > tol + EPS:
                errors.append(f"{key}: expected {want} ± {tol}, computed {have:.6g}")
        elif have != want:
            errors.append(f"{key}: expected {want!r}, computed {have!r}")
    return errors


def check_report(spec: dict, root: Path) -> list[str]:
    """Re-run the archived analyzer on the archived results; compare with the archived report / summary."""
    analyzer = root / spec["analyzer"]
    results = root / spec["results"]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for f in analyzer.parent.glob("analyze*.py"):  # analyze_hooks imports analyze
            shutil.copyfile(f, work / f.name)
        shutil.copyfile(results, work / results.name)
        cmd = [sys.executable, analyzer.name, results.name, *spec.get("args", []), "--out", "report.txt"]
        if spec.get("summary"):
            cmd += ["--json", "summary.json"]
        env = {**os.environ, "PYTHONUTF8": "1"}  # the analyzer writes non-ASCII text with the default encoding
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, encoding="utf-8", env=env)
        if proc.returncode != 0:
            return [f"analyzer failed ({proc.returncode}): {proc.stderr.strip()[-300:]}"]
        errors = []
        new = (work / "report.txt").read_text(encoding="utf-8").splitlines()
        old = (root / spec["report"]).read_text(encoding="utf-8").splitlines()
        allowed = re.compile(spec["allowed_changed_lines"]) if spec.get("allowed_changed_lines") else None
        changed = [ln for ln in difflib.unified_diff(old, new, lineterm="", n=0)
                   if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
        bad = [ln for ln in changed if not (allowed and allowed.search(ln[1:]))]
        if bad:
            errors.append(f"{spec['report']}: {len(bad)} differing lines, first: {bad[0][:160]!r}")
        if spec.get("summary"):
            got = json.loads((work / "summary.json").read_text(encoding="utf-8"))
            want = json.loads((root / spec["summary"]).read_text(encoding="utf-8"))
            for key in spec.get("allowed_extra_keys", []):
                if key not in want:
                    got.pop(key, None)
            if got != want:
                errors.append(f"{spec['summary']}: regenerated summary differs")
        return errors


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("*", "")).strip()


def check_sources(claim: dict, root: Path) -> list[str]:
    errors = []
    for src in claim.get("sources", []):
        path = (root / src["file"]).resolve()
        if not path.is_file():
            errors.append(f"source file missing: {src['file']}")
        elif _normalize(src["text"]) not in _normalize(path.read_text(encoding="utf-8")):
            errors.append(f"source text not found in {src['file']}: {src['text']!r}")
    return errors


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--claims", type=Path, default=CLAIMS)
    ap.add_argument("--root", type=Path, default=HERE, help="archive root that claim file paths are relative to")
    ap.add_argument("--only", action="append", default=[], metavar="ID", help="check only these claim ids")
    ap.add_argument("--show", action="store_true", help="print the computed values")
    ap.add_argument("--check-sources", action="store_true",
                    help="also require each claim's quoted text in its source file (README, findings)")
    ap.add_argument("--reports", action="store_true",
                    help="also regenerate the archived reports with the archived analyzer and compare")
    args = ap.parse_args(argv)
    doc = load_doc(args.claims)
    claims = doc["claims"]
    ids = [c["id"] for c in claims]
    if len(ids) != len(set(ids)):
        print("duplicate claim ids")
        return 1
    if args.only:
        claims = [c for c in claims if c["id"] in args.only]
    failed = 0
    for c in claims:
        try:
            got = compute(c, args.root)
            errors = compare(c, got)
        except (OSError, KeyError, ValueError, ZeroDivisionError) as exc:
            got, errors = {}, [f"error: {exc}"]
        if args.check_sources:
            errors += check_sources(c, args.root)
        status = "FAIL" if errors else "ok"
        failed += bool(errors)
        shown = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in got.items()}
        line = f"{status:4} {c['id']}: {c['claim']}"
        if args.show or errors:
            line += f"  -> {shown}"
        print(line)
        for err in errors:
            print(f"       {err}")
    print(f"claims: {len(claims) - failed}/{len(claims)} reproduced")
    if args.reports and sys.version_info < (3, 12):
        # sum() switched to compensated (Neumaier) summation in Python 3.12; the research ran on 3.12/3.13, so the
        # analyzer's means only reproduce the archived reports digit for digit on 3.12+
        print("reports: skipped, regenerating the archived reports needs Python 3.12+ (float summation changed)")
    elif args.reports:
        rep_failed = 0
        for spec in doc.get("reports", []):
            errors = check_report(spec, args.root)
            rep_failed += bool(errors)
            how = "identical" if not spec.get("allowed_changed_lines") else "identical except analyzer-version lines"
            print(f"{'FAIL' if errors else 'ok':4} report {spec['report']} ({how})")
            for err in errors:
                print(f"       {err}")
        print(f"reports: {len(doc.get('reports', [])) - rep_failed}/{len(doc.get('reports', []))} regenerated")
        failed += rep_failed
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
