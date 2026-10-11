"""Release gate (task 5.3): non-inferiority for the main agent, significant per-agent regressions, same window."""

from __future__ import annotations

import gate as G
import pytest
from eval_helpers import archived, needs, result_row, write_jsonl

SCEN = ["tricentis_quote", "carconfig_order", "demoshop_order", "demoshop_debug", "tricentis_debug"]


def synth(tmp_path, rates: dict[tuple[str, str], int], reps: int = 4, name: str = "r.jsonl", windows=None):
    """rates[(agent, arm)] = passes per scenario out of `reps` (same for every scenario)."""
    rows = []
    for (agent, arm), passes in rates.items():
        for sc in SCEN:
            for rep in range(1, reps + 1):
                r = result_row(f"{agent}|{arm}|{sc}|{rep}", primary=rep <= passes)
                if windows and arm in windows:
                    r["started_at"], r["finished_at"] = windows[arm]
                rows.append(r)
    return write_jsonl(tmp_path / name, rows)


def test_equal_arms_pass(tmp_path):
    p = synth(tmp_path, {("claude", "cand"): 3, ("claude", "base"): 3, ("codex", "cand"): 4, ("codex", "base"): 4})
    g = G.evaluate([p], "cand", "base")
    assert g["verdict"] == "PASS" and not g["reasons"]
    assert g["non_inferiority"]["result"] == "PASS"


def test_main_agent_drop_of_010_fails(tmp_path):
    """Spec scenario: a harness change lowers Claude Code's pass rate by 0.10 -> the gate fails."""
    rows = []
    for arm, passes in (("cand", 16), ("base", 18)):          # 0.80 vs 0.90 over 20 sessions
        for i in range(20):
            rows.append(result_row(f"claude|{arm}|{SCEN[i % 5]}|{i // 5 + 1}", primary=i < passes))
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    g = G.evaluate([p], "cand", "base")
    assert g["verdict"] == "FAIL"
    assert g["non_inferiority"]["delta"] == pytest.approx(-0.10)
    assert any(r.startswith("non-inferiority") for r in g["reasons"])
    assert G.main([str(p), "--candidate", "cand", "--baseline", "base", "--out", str(tmp_path / "g.md")]) == 1
    assert "**FAIL**" in (tmp_path / "g.md").read_text()


def test_drop_within_margin_passes(tmp_path):
    rows = []
    for arm, passes in (("cand", 19), ("base", 20)):          # 0.475 vs 0.50 over 40: within 0.05
        for i in range(40):
            rows.append(result_row(f"claude|{arm}|{SCEN[i % 5]}|{i // 5 + 1}", primary=i < passes))
    g = G.evaluate([write_jsonl(tmp_path / "r.jsonl", rows)], "cand", "base")
    assert g["verdict"] == "PASS", g["reasons"]


def test_significant_regression_of_another_agent_fails(tmp_path):
    p = synth(tmp_path, {("claude", "cand"): 4, ("claude", "base"): 4, ("opencode", "cand"): 0,
                         ("opencode", "base"): 4})
    g = G.evaluate([p], "cand", "base")
    assert g["verdict"] == "FAIL"
    oc = next(a for a in g["per_agent"] if a["agent"] == "opencode")
    assert oc["regression"] and oc["fisher_p"] < 0.05
    assert any("significant regression: opencode" in r for r in g["reasons"])


def test_missing_main_agent_fails(tmp_path):
    p = synth(tmp_path, {("codex", "cand"): 4, ("codex", "base"): 4})
    g = G.evaluate([p], "cand", "base")
    assert g["verdict"] == "FAIL" and g["non_inferiority"]["result"] == "NO DATA"
    assert G.evaluate([p], "cand", "base", main_agent="codex")["verdict"] == "PASS"


def test_different_time_windows_fail(tmp_path):
    p = synth(tmp_path, {("claude", "cand"): 3, ("claude", "base"): 3},
              windows={"cand": ("2026-10-11T08:00:00+00:00", "2026-10-11T09:00:00+00:00"),
                       "base": ("2026-10-01T08:00:00+00:00", "2026-10-01T09:00:00+00:00")})
    g = G.evaluate([p], "cand", "base")
    assert g["verdict"] == "FAIL" and g["same_window"] is False
    assert G.evaluate([p], "cand", "base", allow_different_windows=True)["verdict"] == "PASS"


def test_invalid_and_contaminated_rows_are_excluded(tmp_path):
    rows = [result_row(f"claude|cand|{sc}|1") for sc in SCEN] + [result_row(f"claude|base|{sc}|1") for sc in SCEN]
    rows.append(result_row("claude|cand|tricentis_quote|2", status="invalid", primary=False,
                           invalid_reason="provider error: 'API Error: 402'"))
    rows.append(result_row("claude|base|tricentis_quote|2", primary=False, contaminated=True))
    g = G.evaluate([write_jsonl(tmp_path / "r.jsonl", rows)], "cand", "base")
    assert g["excluded"] == {"invalid": 1}
    assert g["contaminated"] == ["claude|base|tricentis_quote|2"]
    assert g["n_candidate"] == 5 and g["n_baseline"] == 5


def test_adjustments_change_the_data_and_are_reported(tmp_path):
    rows = [result_row(f"claude|cand|{sc}|1", primary=sc != "demoshop_order") for sc in SCEN]
    rows += [result_row(f"claude|base|{sc}|1") for sc in SCEN]
    p = write_jsonl(tmp_path / "r.jsonl", rows)
    assert G.evaluate([p], "cand", "base")["verdict"] == "FAIL"           # 0.80 vs 1.00
    g = G.evaluate([p], "cand", "base", adjust={"claude|cand|demoshop_order|1": True})
    assert g["verdict"] == "PASS" and g["adjusted"] == ["claude|cand|demoshop_order|1"]
    assert "Manually adjusted rows" in G.markdown(g)


# --------------------------------------------------------------------------- archived round-6 / round-7 data
V3MAIN = archived("results_live_v3main.jsonl")
V31SUB, V31OR = archived("results_live_v31sub.jsonl"), archived("results_live_v31or.jsonl")
V32 = archived("results_live_v32.jsonl")


@needs(V3MAIN)
def test_round6_numbers_match_findings_v3main():
    """findings_v3main.md: mcp 0.52 / v2 0.70 / v3 0.63; v2-mcp +0.18 (p 0.061, cells 8/0, sign 0.008);
    v3-mcp +0.12 (p 0.268, 9/2, 0.065); v3-v2 -0.07 (p 0.562); Claude 0.30 / 0.60 / 0.65."""
    v2 = G.evaluate([V3MAIN], "hookpkg2", "mcp")
    v3 = G.evaluate([V3MAIN], "hookpkg3", "mcp")
    v3v2 = G.evaluate([V3MAIN], "hookpkg3", "hookpkg2")
    assert (v2["overall"]["pass_a"], v2["overall"]["n_a"], v2["overall"]["pass_b"]) == (42, 60, 31)
    assert round(v2["overall"]["rate_b"], 2) == 0.52 and round(v2["overall"]["rate_a"], 2) == 0.70
    assert round(v3["overall"]["rate_a"], 2) == 0.63
    assert round(v2["overall"]["delta_pooled"], 2) == 0.18 and round(v2["overall"]["fisher_p"], 3) == 0.061
    assert (v2["overall"]["cells_pos"], v2["overall"]["cells_neg"]) == (8, 0)
    assert round(v2["overall"]["sign_p"], 3) == 0.008
    assert round(v3["overall"]["delta_pooled"], 2) == 0.12 and round(v3["overall"]["fisher_p"], 3) == 0.268
    assert (v3["overall"]["cells_pos"], v3["overall"]["cells_neg"]) == (9, 2) and round(v3["overall"]["sign_p"], 3) == 0.065
    assert round(v3v2["overall"]["delta_pooled"], 2) == -0.07 and round(v3v2["overall"]["fisher_p"], 3) == 0.562
    ni = v3["non_inferiority"]
    assert (round(ni["rate_candidate"], 2), round(ni["rate_baseline"], 2)) == (0.65, 0.30)
    # verdicts: both hook harnesses pass against rf-mcp; v3 is non-inferior to v2 for Claude (0.65 vs 0.60)
    assert (v2["verdict"], v3["verdict"], v3v2["verdict"]) == ("PASS", "PASS", "PASS")
    # and the reverse direction (rf-mcp as a "candidate" vs v3) fails non-inferiority for Claude (0.30 vs 0.65)
    rev = G.evaluate([V3MAIN], "mcp", "hookpkg3")
    assert rev["verdict"] == "FAIL" and rev["non_inferiority"]["result"] == "FAIL"


@needs(V31SUB, V31OR)
def test_round7_pooled_numbers_match_findings_v31():
    """findings_v31.md section 1: pooled rf-mcp 47/68, v3 51/68, v3.1 58/70; v3.1 vs rf-mcp +0.14 (p 0.073),
    cells 7/2 (sign 0.18); v3 vs rf-mcp +0.06 (p 0.57); Claude rf-mcp 0.93 / v3 0.80 / v3.1 0.93."""
    kw = {"keep_contaminated": True}           # the archived report scored the one contaminated row
    v31 = G.evaluate([V31SUB, V31OR], "hookpkg31", "mcp", **kw)
    v3 = G.evaluate([V31SUB, V31OR], "hookpkg3", "mcp", **kw)
    o = v31["overall"]
    assert (o["pass_a"], o["n_a"], o["pass_b"], o["n_b"]) == (58, 70, 47, 68)
    assert round(o["delta_pooled"], 2) == 0.14 and round(o["fisher_p"], 3) == 0.073
    assert (o["cells_pos"], o["cells_neg"]) == (7, 2) and round(o["sign_p"], 2) == 0.18
    assert (v3["overall"]["pass_a"], v3["overall"]["n_a"]) == (51, 68)
    assert round(v3["overall"]["delta_pooled"], 2) == 0.06 and round(v3["overall"]["fisher_p"], 2) == 0.57
    assert round(v31["non_inferiority"]["rate_candidate"], 2) == 0.93 == round(v31["non_inferiority"]["rate_baseline"], 2)
    assert round(v3["non_inferiority"]["rate_candidate"], 2) == 0.80
    per = {a["agent"]: a for a in v31["per_agent"]}
    assert round(per["opencode"]["rate_candidate"], 2) == 0.53 and round(per["opencode"]["rate_baseline"], 2) == 0.27
    assert round(per["cc-or:qwen3.8-flash"]["rate_candidate"], 2) == 0.88
    assert v31["verdict"] == "PASS"
    assert v3["verdict"] == "FAIL"                    # Claude 0.80 < 0.93 - 0.05
    assert G.evaluate([V31SUB, V31OR], "hookpkg31", "hookpkg3", **kw)["verdict"] == "PASS"
    # default policy (contaminated rows excluded) drops codex|mcp|tricentis_debug|1 and keeps the verdict
    d = G.evaluate([V31SUB, V31OR], "hookpkg31", "mcp")
    assert d["contaminated"] == ["codex|mcp|tricentis_debug|1"]
    assert (d["overall"]["pass_b"], d["overall"]["n_b"]) == (46, 67) and d["verdict"] == "PASS"


@needs(V31SUB)
def test_round7_grader_artifact_sensitivity_matches_findings():
    """findings_v31.md: four v31sub cells fail only on the `\\$?916\\.99` grader (mcp 1, v3 2, v3.1 1); adjusted
    v31sub rf-mcp 0.71, v3 0.76, v3.1 0.80."""
    raw = G.evaluate([V31SUB], "hookpkg31", "mcp", keep_contaminated=True)
    raw3 = G.evaluate([V31SUB], "hookpkg3", "mcp", keep_contaminated=True)
    arts = {k: v for k, v in {**raw["value_artifacts"], **raw3["value_artifacts"]}.items() if v == [r"\$?916\.99"]}
    assert sorted(arts) == ["claude|hookpkg31|demoshop_order|2", "claude|hookpkg3|demoshop_order|2",
                            "claude|hookpkg3|demoshop_order|3", "claude|mcp|demoshop_order|2"]
    adj = {k: True for k in arts}
    a31 = G.evaluate([V31SUB], "hookpkg31", "mcp", keep_contaminated=True, adjust=adj)
    a3 = G.evaluate([V31SUB], "hookpkg3", "mcp", keep_contaminated=True, adjust=adj)
    assert round(a31["arm_totals"]["mcp"]["passes"] / 45, 2) == 0.71
    assert round(a3["arm_totals"]["hookpkg3"]["passes"] / 45, 2) == 0.76
    assert round(a31["arm_totals"]["hookpkg31"]["passes"] / 45, 2) == 0.80


@needs(V32)
def test_round7_v32_numbers_match_findings():
    """findings_v31.md: Codex v3.1 14/15 vs v3.2 15/15; overall 18/19 vs 19/20 (n.s.)."""
    g = G.evaluate([V32], "hookpkg32", "hookpkg31", main_agent="codex")
    assert g["verdict"] == "PASS"
    ni = g["non_inferiority"]
    assert (ni["pass_candidate"], ni["n_candidate"], ni["pass_baseline"], ni["n_baseline"]) == (15, 15, 14, 15)
    assert g["arm_totals"] == {"hookpkg32": {"passes": 19, "n": 20}, "hookpkg31": {"passes": 18, "n": 19}}
    assert G.evaluate([V32], "hookpkg32", "hookpkg31")["verdict"] == "FAIL"     # no Claude sessions in this run
