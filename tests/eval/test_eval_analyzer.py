"""Analyzer port: archived round-6/7 reports regenerate byte-identically; new arm names and invalid rows work."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest
from eval_helpers import EVAL, archived, needs, result_row, write_jsonl

REPORTS = [("v3main", "mcp,hookpkg2,hookpkg3"), ("v31sub", "mcp,hookpkg3,hookpkg31"),
           ("v31or", "mcp,hookpkg3,hookpkg31"), ("v32", "hookpkg31,hookpkg32"), ("v2", "hookpkg,hookpkg2")]


def _regen(tag: str, arms: str, out):
    md, js = out / f"report_live_{tag}.txt", out / f"summary_live_{tag}.json"
    p = subprocess.run([sys.executable, str(EVAL / "analyze_hooks.py"), str(archived(f"results_live_{tag}.jsonl")),
                        "--arms", arms, "--out", str(md), "--json", str(js)], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr
    return md, js


@needs(archived("results_live_v3main.jsonl"), archived("report_live_v3main.txt"))
def test_v3main_report_regenerates_byte_identically(tmp_path):
    md, js = _regen("v3main", "mcp,hookpkg2,hookpkg3", tmp_path)
    assert md.read_bytes() == archived("report_live_v3main.txt").read_bytes()
    assert js.read_bytes() == archived("summary_live_v3main.json").read_bytes()


@pytest.mark.parametrize("tag,arms", REPORTS[1:])
def test_round5_to_7_reports_regenerate_byte_identically(tmp_path, tag, arms):
    if not (archived(f"results_live_{tag}.jsonl").exists() and archived(f"report_live_{tag}.txt").exists()):
        pytest.skip("archived research data not available")
    md, js = _regen(tag, arms, tmp_path)
    assert md.read_bytes() == archived(f"report_live_{tag}.txt").read_bytes()
    assert js.read_bytes() == archived(f"summary_live_{tag}.json").read_bytes()


def _hook_metrics():
    return {"firings": 12, "auto_executed_lines": 9, "denials": 1, "ctx_chars_per_edit": 340.0, "captures": 2,
            "profile": "lean", "profile_src": "transcript", "profile_model": "claude-haiku-5-5",
            "latency_ms_median": {"post-tool": 900}}


def test_product_arms_get_the_hook_tables_and_invalid_rows_are_listed(tmp_path):
    rows = []
    for arm in ("prototype-v32", "rf-harness"):
        for sc in ("tricentis_quote", "demoshop_debug"):
            rows.append(result_row(f"claude|{arm}|{sc}|1", **{arm: _hook_metrics()},
                                   kind="explore" if sc == "tricentis_quote" else "debug"))
    rows.append(result_row("claude|rf-harness|tricentis_quote|2", status="invalid", primary=False,
                           invalid_reason="provider error: 'API Error: 402'"))
    res = write_jsonl(tmp_path / "results_live_x.jsonl", rows)
    out = tmp_path / "r.md"
    p = subprocess.run([sys.executable, str(EVAL / "analyze_hooks.py"), str(res), "--arms", "prototype-v32,rf-harness",
                        "--out", str(out)], capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    md = out.read_text()
    assert md.startswith("# rf-harness vs prototype-v32 — A/B")
    assert "status: ok=4, invalid=1" in md and "scored (ok, de-duplicated): **4**" in md
    assert "invalid: provider error: 'API Error: 402'" in md
    for arm in ("prototype-v32", "rf-harness"):
        assert f"{arm} engagement (hooks instead of a CLI)" in md
        assert f"{arm}: v2 hooks per session" in md and f"{arm}: v3 metrics per session" in md
        assert f"{arm}: output profile per agent" in md
    assert "hook-arm cross-contamination rows: 0" in md


def test_analyze_summary_json_has_contrasts(tmp_path):
    rows = [result_row(f"codex|{arm}|tricentis_quote|{r}", primary=(arm == "rf-harness" or r == 1))
            for arm in ("mcp", "rf-harness") for r in (1, 2)]
    res = write_jsonl(tmp_path / "r.jsonl", rows)
    js = tmp_path / "s.json"
    subprocess.run([sys.executable, str(EVAL / "analyze_hooks.py"), str(res), "--arms", "mcp,rf-harness",
                    "--out", str(tmp_path / "r.md"), "--json", str(js)], check=True, capture_output=True, timeout=60)
    c = json.loads(js.read_text())["contrasts"][0]
    assert (c["a"], c["b"]) == ("rf-harness", "mcp") and c["all"]["delta_pooled"] == 0.5


@pytest.mark.skipif(sys.version_info < (3, 12), reason="the reference is CPython 3.12+ builtins.sum()")
def test_compat_sum_replicates_the_312_float_summation():
    """analyze.compat_sum keeps reports byte-identical on Python 3.10/3.11 (3.12 changed float sum())."""
    import random

    import analyze as A

    rng = random.Random(7)
    for _ in range(5000):
        xs = [rng.choice([rng.random() * 10 ** rng.randint(-8, 8), rng.randint(-5, 5), 1e16, -1e16, 0.1, True])
              for _ in range(rng.randint(0, 12))]
        got, want = A.compat_sum(xs), sum(xs)
        assert got == want and type(got) is type(want), xs
    assert A.compat_sum([0.1] * 10) == 1.0 and A.compat_sum([1, 2, 3]) == 6
