#!/usr/bin/env python3
"""Release gate: candidate arm vs baseline arm from one same-window A/B run (design D10, task 5.3; stdlib only).

    python3 gate.py RESULTS.jsonl [RESULTS2.jsonl ...] --candidate rf-harness --baseline prototype-v32 \
        [--main-agent claude] [--margin 0.05] [--alpha 0.05] [--agents a,b] [--keep-contaminated] \
        [--adjust KEY=pass|fail ...] [--adjust-file adjust.json] [--out gate.md] [--json gate.json]

Several results files are pooled (rows de-duplicated by cell key, the later file wins), e.g. round 7's subscription
and OpenRouter runs. Only `status == "ok"` rows are scored; invalid / aborted / error rows and (unless
--keep-contaminated) contaminated rows are excluded and counted in the report.

Verdict FAIL when any of:
  1. non-inferiority (main agent, default claude): candidate pass rate < baseline pass rate - margin (default 0.05),
     or the main agent has no paired candidate/baseline sessions;
  2. significant per-agent regression: Fisher two-sided p < alpha (default 0.05) with the candidate worse;
  3. the two arms did not run in the same time window (their [first start, last finish] intervals do not overlap;
     --allow-different-windows skips this check).
Otherwise PASS. Exit code 0 = PASS, 1 = FAIL, 2 = usage error.

Rates compare only (agent, scenario) cells that both arms have (analyze.contrast). The report also gives pooled,
per-kind and per-scenario contrasts with Wilson 95% CIs, Fisher and per-cell sign tests, cost / wall time / turns, and
the sensitivity of the pass rates to value-grader artifacts (rows that failed only a value grader; --adjust records
manually confirmed artifacts and changes the data the verdict uses).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import analyze as A  # noqa: E402
from value_graders import is_value_regex  # noqa: E402

MAIN_AGENT = "claude"
MARGIN = 0.05
ALPHA = 0.05
BASE_AGENTS = ("claude", "codex", "opencode", "copilot")
SCENARIO_ORDER = ["tricentis_quote", "carconfig_order", "demoshop_order", "demoshop_debug", "tricentis_debug",
                  "iframe", "apinested", "results_complex", "browser_dynamic"]
EPS = 1e-12


# --------------------------------------------------------------------------- #
# data
# --------------------------------------------------------------------------- #
def load_rows(paths: list[Path]) -> tuple[list[dict], list[dict]]:
    """(ok rows de-duplicated by key across files - later file wins, all rows)."""
    ok: dict[str, dict] = {}
    every: list[dict] = []
    for p in paths:
        o, a = A.load(Path(p))
        every += a
        for r in o:
            ok[r["key"]] = r
    return list(ok.values()), every


def parse_adjustments(items: list[str], file: str | None) -> dict[str, bool]:
    adj: dict[str, bool] = {}
    if file:
        for k, v in json.loads(Path(file).read_text(encoding="utf-8")).items():
            adj[k] = bool(v) if not isinstance(v, str) else v.lower() in ("pass", "true", "1")
    for it in items or []:
        k, _, v = it.rpartition("=")
        if not k or v.lower() not in ("pass", "fail", "true", "false", "1", "0"):
            raise SystemExit(f"--adjust expects KEY=pass|fail, got {it!r}")
        adj[k] = v.lower() in ("pass", "true", "1")
    return adj


def _scenario_graders() -> dict[str, list[dict]]:
    """scenario id -> grader specs (verdicts are written in grader order), from harness.py."""
    try:
        import harness as H  # noqa: PLC0415  (stdlib only; import has no side effects)
        return {sid: list(sc.graders) for sid, sc in H.SCEN_BY_ID.items()}
    except Exception:
        return {}


def value_only_failure(row: dict, graders: dict[str, list[dict]]) -> list[str] | None:
    """The value-grader regexes of a failed row whose ONLY failing checks are value graders (file_contains /
    files_contain with a numeric literal regex), else None. Such a row may be a grader artifact (e.g. `\\$916\\.99`)."""
    if row.get("primary_pass"):
        return None
    vs = row.get("verdicts") or []
    gs = graders.get(row.get("scenario") or "") or []
    failed = [(i, v) for i, v in enumerate(vs) if not v.get("passed")]
    if not failed or len(gs) != len(vs):
        return None
    out = []
    for i, _verdict in failed:
        g = gs[i]
        if g.get("type") not in ("file_contains", "files_contain") or not is_value_regex(g.get("regex") or ""):
            return None
        out.append(g["regex"])
    return out


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #
def newcombe(pa: int, na: int, pb: int, nb: int) -> tuple[float, float] | None:
    """Newcombe hybrid-score 95% CI for rate_a - rate_b (Wilson intervals of both rates)."""
    wa, wb = A.wilson(pa, na), A.wilson(pb, nb)
    if not wa or not wb:
        return None
    a, b = pa / na, pb / nb
    d = a - b
    return (d - math.sqrt((a - wa[0]) ** 2 + (wb[1] - b) ** 2), d + math.sqrt((wa[1] - a) ** 2 + (b - wb[0]) ** 2))


def _window(rows: list[dict]) -> tuple[str, str] | None:
    st = [r.get("started_at") for r in rows if r.get("started_at")]
    fi = [r.get("finished_at") or r.get("started_at") for r in rows if r.get("started_at")]
    return (min(st), max(fi)) if st else None


def _iso(s: str) -> datetime:
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))


# --------------------------------------------------------------------------- #
# gate
# --------------------------------------------------------------------------- #
def evaluate(paths: list[Path], candidate: str, baseline: str, main_agent: str = MAIN_AGENT, margin: float = MARGIN,
             alpha: float = ALPHA, agents_filter: list[str] | None = None, keep_contaminated: bool = False,
             adjust: dict[str, bool] | None = None, allow_different_windows: bool = False) -> dict:
    ok_rows, all_rows = load_rows(paths)
    arms = (candidate, baseline)
    excluded = Counter(str(r.get("status")) for r in all_rows if r.get("arm") in arms and r.get("status") != "ok")
    rows = [r for r in ok_rows if r.get("arm") in arms]
    if agents_filter:
        rows = [r for r in rows if r.get("agent") in agents_filter]
    cont = [r["key"] for r in rows if r.get("contaminated")]
    if not keep_contaminated:
        rows = [r for r in rows if not r.get("contaminated")]
    graders = _scenario_graders()
    artifacts = {r["key"]: value_only_failure(r, graders) for r in rows}
    artifacts = {k: v for k, v in artifacts.items() if v}
    adjust = dict(adjust or {})
    applied = [r["key"] for r in rows if r["key"] in adjust and bool(r.get("primary_pass")) != adjust[r["key"]]]
    if applied:          # copies: never mutate the loaded rows
        rows = [dict(r, primary_pass=adjust[r["key"]], adjusted=True) if r["key"] in applied else r for r in rows]

    agents = [a for a in BASE_AGENTS if any(r["agent"] == a for r in rows)]
    agents += sorted({r["agent"] for r in rows} - set(agents))
    scenarios = [s for s in SCENARIO_ORDER if any(r["scenario"] == s for r in rows)]
    scenarios += sorted({r["scenario"] for r in rows} - set(scenarios))
    cells = A.cells_of(rows)
    c = A.contrast(cells, agents, scenarios, candidate, baseline)
    kinds = {}
    for kd in ("explore", "debug", "authoring"):
        sc = sorted({r["scenario"] for r in rows if r.get("kind") == kd})
        if sc:
            kinds[kd] = A.contrast(cells, agents, sc, candidate, baseline)["all"]

    reasons: list[str] = []
    main = c["by_agent"].get(main_agent, {}).get("all", {}) if main_agent in agents else {}
    ni: dict = {"agent": main_agent, "margin": margin}
    if not main.get("cells"):
        reasons.append(f"non-inferiority: no paired {candidate}/{baseline} sessions for the main agent {main_agent}")
        ni["result"] = "NO DATA"
    else:
        ni.update(rate_candidate=main["rate_a"], rate_baseline=main["rate_b"], pass_candidate=main["pass_a"],
                  n_candidate=main["n_a"], pass_baseline=main["pass_b"], n_baseline=main["n_b"],
                  delta=main["delta_pooled"], threshold=main["rate_b"] - margin,
                  ci_delta=newcombe(main["pass_a"], main["n_a"], main["pass_b"], main["n_b"]),
                  ci_candidate=A.wilson(main["pass_a"], main["n_a"]), ci_baseline=A.wilson(main["pass_b"], main["n_b"]))
        if main["rate_a"] < main["rate_b"] - margin - EPS:
            ni["result"] = "FAIL"
            reasons.append(f"non-inferiority: {main_agent} {candidate} {main['rate_a']:.2f} "
                           f"({main['pass_a']}/{main['n_a']}) < {baseline} {main['rate_b']:.2f} "
                           f"({main['pass_b']}/{main['n_b']}) - {margin:.2f}")
        else:
            ni["result"] = "PASS"
    per_agent = []
    for ag in agents:
        pa = c["by_agent"][ag]["all"]
        if not pa.get("cells"):
            continue
        regress = pa["fisher_p"] < alpha and pa["rate_a"] < pa["rate_b"]
        per_agent.append({"agent": ag, "cells": pa["cells"], "rate_candidate": pa["rate_a"],
                          "rate_baseline": pa["rate_b"], "pass_candidate": pa["pass_a"], "n_candidate": pa["n_a"],
                          "pass_baseline": pa["pass_b"], "n_baseline": pa["n_b"], "delta": pa["delta_pooled"],
                          "fisher_p": pa["fisher_p"], "cells_pos": pa["cells_pos"], "cells_neg": pa["cells_neg"],
                          "sign_p": pa["sign_p"], "regression": regress})
        if regress:
            reasons.append(f"significant regression: {ag} {candidate} {pa['rate_a']:.2f} vs {baseline} "
                           f"{pa['rate_b']:.2f} (Fisher p = {pa['fisher_p']:.3f} < {alpha})")
    win = {arm: _window([r for r in rows if r["arm"] == arm]) for arm in arms}
    same_window = None
    if win[candidate] and win[baseline]:
        same_window = max(_iso(win[candidate][0]), _iso(win[baseline][0])) <= \
            min(_iso(win[candidate][1]), _iso(win[baseline][1]))
        if not same_window and not allow_different_windows:
            reasons.append(f"same-window rule: {candidate} ran {win[candidate][0]}..{win[candidate][1]}, "
                           f"{baseline} ran {win[baseline][0]}..{win[baseline][1]} (no overlap)")
    eff = {}
    for ag in agents:
        for arm in arms:
            rs = [r for r in rows if r["agent"] == ag and r["arm"] == arm]
            if rs:
                s = A.cell_stats(rs)
                eff[f"{ag}|{arm}"] = {k: s[k] for k in ("n", "rate", "cost_usd", "wall_s", "turns", "tool_calls")}

    def _sens(arm):
        rs = [r for r in rows if r["arm"] == arm]
        return {"n": len(rs), "passes": sum(1 for r in rs if r.get("primary_pass")),
                "passes_upper": sum(1 for r in rs if r.get("primary_pass") or r["key"] in artifacts)}
    return {
        "verdict": "FAIL" if reasons else "PASS", "reasons": reasons,
        "candidate": candidate, "baseline": baseline, "main_agent": main_agent, "margin": margin, "alpha": alpha,
        "sources": [str(p) for p in paths], "rows": len(rows),
        "n_candidate": sum(1 for r in rows if r["arm"] == candidate),
        "n_baseline": sum(1 for r in rows if r["arm"] == baseline),
        "excluded": dict(excluded), "contaminated": cont, "contaminated_kept": keep_contaminated,
        "adjusted": applied, "non_inferiority": ni, "per_agent": per_agent,
        "overall": {k: v for k, v in c["all"].items()}, "by_kind": kinds,
        "by_scenario": c["by_scenario"], "per_cell": {f"{a}|{s}": {"delta": v["delta"], "rate_a": v["a"]["rate"],
                                                                    "rate_b": v["b"]["rate"], "n_a": v["a"]["n"],
                                                                    "n_b": v["b"]["n"]}
                                                      for (a, s), v in c["per_cell"].items()},
        "windows": win, "same_window": same_window, "efficiency": eff,
        "value_artifacts": artifacts,
        "value_artifact_sensitivity": {arm: _sens(arm) for arm in arms},
        "arm_totals": {arm: {"passes": _sens(arm)["passes"], "n": _sens(arm)["n"]} for arm in arms},
        "agents": agents, "scenarios": scenarios,
    }


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #
def _ci(ci) -> str:
    return "—" if not ci else f"{ci[0]:.2f}–{ci[1]:.2f}"


def _rate(p: int, n: int) -> str:
    return "—" if not n else f"{p / n:.2f} ({p}/{n})"


def markdown(g: dict) -> str:
    cand, base = g["candidate"], g["baseline"]
    L = [f"# Release gate: {cand} vs {base} — **{g['verdict']}**\n",
         f"Sources: {', '.join('`' + Path(s).name + '`' for s in g['sources'])} · rows used: {g['rows']} "
         f"({cand} {g['n_candidate']}, {base} {g['n_baseline']}) · excluded non-ok rows: "
         + (", ".join(f"{k}={v}" for k, v in sorted(g["excluded"].items())) or "none")
         + f" · contaminated: {len(g['contaminated'])} ({'kept' if g['contaminated_kept'] else 'excluded'})"
         + (f" · manually adjusted rows: {len(g['adjusted'])}" if g["adjusted"] else "")
         + f" · main agent: {g['main_agent']} · margin {g['margin']:.2f} · alpha {g['alpha']:.2f}\n",
         "## Verdict\n"]
    if g["reasons"]:
        L += [f"- FAIL: {r}" for r in g["reasons"]]
    else:
        L.append(f"- PASS: {g['main_agent']} non-inferior within {g['margin']:.2f}, no agent with a significant "
                 "regression, same time window.")
    L.append("")
    ni = g["non_inferiority"]
    L.append(f"## 1. Non-inferiority: {ni['agent']} (rule: {cand} ≥ {base} − {ni['margin']:.2f})\n")
    if ni.get("result") == "NO DATA":
        L.append("No paired sessions for the main agent.\n")
    else:
        L += ["| arm | n | passes | rate | 95% CI |", "|---|---:|---:|---:|---|",
              f"| {cand} | {ni['n_candidate']} | {ni['pass_candidate']} | {ni['rate_candidate']:.2f} | "
              f"{_ci(ni['ci_candidate'])} |",
              f"| {base} | {ni['n_baseline']} | {ni['pass_baseline']} | {ni['rate_baseline']:.2f} | "
              f"{_ci(ni['ci_baseline'])} |", "",
              f"Δ = {A._sgn(ni['delta'])} (Newcombe 95% CI {_ci(ni['ci_delta'])}); threshold {ni['threshold']:.2f} "
              f"→ **{ni['result']}**\n"]
    L += ["## 2. Per agent (pooled over paired scenario cells)\n",
          f"| agent | cells | {cand} | {base} | Δ | Fisher p | cells +/− | sign p | significant regression |",
          "|---|---:|---:|---:|---:|---:|---|---:|---|"]
    for a in g["per_agent"]:
        L.append(f"| {a['agent']} | {a['cells']} | {_rate(a['pass_candidate'], a['n_candidate'])} | "
                 f"{_rate(a['pass_baseline'], a['n_baseline'])} | {A._sgn(a['delta'])} | {A._p(a['fisher_p'])} | "
                 f"{a['cells_pos']}/{a['cells_neg']} | {A._p(a['sign_p'])} | {'**yes**' if a['regression'] else 'no'} |")
    L.append("")
    L += ["## 3. Overall, per scenario kind and per scenario\n",
          f"| subset | cells | {cand} (95% CI) | {base} (95% CI) | Δpool | Δcell | Fisher p | cells +/− | sign p |",
          "|---|---:|---|---|---:|---:|---:|---|---:|"]

    def row(label, p):
        if not p.get("cells"):
            return f"| {label} | 0 | | | | | | | |"
        return (f"| {label} | {p['cells']} | {_rate(p['pass_a'], p['n_a'])} [{_ci(A.wilson(p['pass_a'], p['n_a']))}] | "
                f"{_rate(p['pass_b'], p['n_b'])} [{_ci(A.wilson(p['pass_b'], p['n_b']))}] | "
                f"{A._sgn(p['delta_pooled'])} | {A._sgn(p['delta_cellmean'])} | {A._p(p['fisher_p'])} | "
                f"{p['cells_pos']}/{p['cells_neg']} | {A._p(p['sign_p'])} |")
    L.append(row("**all** (paired cells)", g["overall"]))
    for kd, p in g["by_kind"].items():
        L.append(row(f"kind {kd}", p))
    for sc in g["scenarios"]:
        L.append(row(sc, g["by_scenario"].get(sc, {})))
    L.append("")
    L.append("Arm totals over all scored rows (incl. cells only one arm has): "
             + "; ".join(f"{arm} {_rate(t['passes'], t['n'])} [{_ci(A.wilson(t['passes'], t['n']))}]"
                         for arm, t in g["arm_totals"].items()) + "\n")
    L += ["## 4. Cost, wall time and turns (means per session)\n",
          "| agent | arm | n | pass | cost $ | wall s | turns | tool calls |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for k, e in g["efficiency"].items():
        ag, arm = k.split("|", 1)
        L.append(f"| {ag} | {arm} | {e['n']} | {A._f(e['rate'])} | {A._f(e['cost_usd'], 3)} | {A._f(e['wall_s'], 0)} | "
                 f"{A._f(e['turns'], 1)} | {A._f(e['tool_calls'], 1)} |")
    L.append("")
    L.append("## 5. Same time window\n")
    for arm, w in g["windows"].items():
        L.append(f"- {arm}: {w[0] + ' .. ' + w[1] if w else 'no rows'}")
    L.append(f"- overlap: {'yes' if g['same_window'] else ('no' if g['same_window'] is False else 'n/a')}\n")
    L.append("## 6. Sensitivity to value-grader artifacts\n")
    va = g["value_artifacts"]
    L.append(f"Rows that failed ONLY value graders (a regex-escaped assertion such as `\\$916\\.99` may be the cause; "
             f"graders of new runs accept that form): {len(va)}"
             + (": " + "; ".join(f"{k} {v}" for k, v in sorted(va.items())[:12]) if va else "") + "\n")
    sens = g["value_artifact_sensitivity"]
    L.append("| arm | pass rate (as graded) | upper bound if every such row were an artifact |")
    L.append("|---|---:|---:|")
    for arm in (cand, base):
        x = sens[arm]
        L.append(f"| {arm} | {_rate(x['passes'], x['n'])} | {_rate(x['passes_upper'], x['n'])} |")
    if g["adjusted"]:
        L.append(f"\nManually adjusted rows (--adjust, used for the verdict): {', '.join(sorted(g['adjusted']))}")
    L.append("")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="release gate: candidate vs baseline arm (same-window A/B)")
    ap.add_argument("results", nargs="+")
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--main-agent", default=MAIN_AGENT)
    ap.add_argument("--margin", type=float, default=MARGIN)
    ap.add_argument("--alpha", type=float, default=ALPHA)
    ap.add_argument("--agents", default=None, help="restrict to these agents (comma-separated)")
    ap.add_argument("--keep-contaminated", action="store_true",
                    help="score contaminated rows too (the archived research reports did)")
    ap.add_argument("--adjust", action="append", default=[], help="KEY=pass|fail: a manually confirmed grader artifact")
    ap.add_argument("--adjust-file", default=None, help="JSON {cell key: true|false}")
    ap.add_argument("--allow-different-windows", action="store_true")
    ap.add_argument("--out", default=None, help="markdown report (default: stdout)")
    ap.add_argument("--json", default=None)
    args = ap.parse_args(argv)
    paths = [Path(p) for p in args.results]
    missing = [str(p) for p in paths if not p.is_file()]
    if missing:
        print(f"missing results file(s): {', '.join(missing)}", file=sys.stderr)
        return 2
    g = evaluate(paths, args.candidate, args.baseline, args.main_agent, args.margin, args.alpha,
                 [a for a in (args.agents or "").split(",") if a] or None, args.keep_contaminated,
                 parse_adjustments(args.adjust, args.adjust_file), args.allow_different_windows)
    md = markdown(g)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"{g['verdict']}: {args.candidate} vs {args.baseline} -> {args.out}")
    else:
        print(md)
    if args.json:
        Path(args.json).write_text(json.dumps(g, indent=2, default=str), encoding="utf-8")
    return 0 if g["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
