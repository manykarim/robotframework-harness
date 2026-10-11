#!/usr/bin/env python3
"""Aggregate results_rc*.jsonl (harness.py) into the neither / mcp / skillpkg comparison.

Usage:
    python3 analyze.py [results_rc.jsonl] [--out report.md] [--json summary.json]
                       [--drop-contaminated] [--label "..."]

Prints markdown to stdout unless --out is given. Sections:
  1. data quality (status, timeouts, contamination, leak markers, model actually used)
  2. per agent x scenario x arm: n, pass rate, check rate, turns, tool calls, MCP calls,
     tokens (in/out/cache), cost, wall time
  3. effects on primary pass rate: mcp-neither, skillpkg-neither, skillpkg-mcp
       - per agent x scenario cell (rate difference)
       - pooled: equal-weight mean of cell deltas, pooled counts with Fisher exact p (two-sided),
         exact sign test over cells; ALL cells and HEADROOM cells (neither < 1.00)
       - per agent pooled
  4. efficiency per agent x arm (turns / tool calls / tokens / wall; not pooled across agents,
     because token accounting differs per CLI)
  5. engagement: MCP arm (calls, tools, server connected) and skillpkg arm (helper CLI used,
     SKILL.md read, hook firings, pass rate with/without helper use)
  6. (round 2, live rows only) results split by scenario KIND (explore vs debug): pass rate,
     first-attempt pass, flaky passes, effect contrasts per kind; and "does the helper replace
     execute_step?": per-session stepwise counts (rf-mcp execute_step/execute_batch/intent_action/
     get_session_state/run_test_suite/find_keywords vs `rfmcp step|run|state|search|doc|check` vs plain
     `robot` runs) related to success (pass with vs without stepwise use, Fisher p; pass by tercile).
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARMS = ["neither", "mcp", "skillpkg"]
CONTRASTS = [("mcp", "neither"), ("skillpkg", "neither"), ("skillpkg", "mcp")]


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def load(path: Path) -> tuple[list[dict], list[dict]]:
    """Returns (ok rows de-duplicated by key keeping the last, all rows)."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            pass
    latest: dict[str, dict] = {}
    for r in rows:
        if r.get("status") == "ok":
            latest[r["key"]] = r
    return list(latest.values()), rows


def _m(r: dict, k: str):
    return (r.get("metrics") or {}).get(k)


def _mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float)) and not isinstance(x, bool)]
    return sum(xs) / len(xs) if xs else None


def _f(x, nd=2):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{nd}f}"
    return str(x)


def _k(x):
    return "—" if x is None else (f"{x / 1000:.1f}k" if x >= 1000 else f"{x:.0f}")


def _sgn(x):
    return "—" if x is None else (f"+{x:.2f}" if x >= 0 else f"{x:.2f}")


def _p(p):
    if p is None:
        return "—"
    return "<0.001" if p < 0.001 else f"{p:.3f}"


# --------------------------------------------------------------------------- #
# statistics (pure python)
# --------------------------------------------------------------------------- #
def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]] (rows = arms, cols = pass/fail)."""
    n1, n2, k = a + b, c + d, a + c
    N = n1 + n2
    if N == 0 or n1 == 0 or n2 == 0:
        return 1.0
    denom = math.comb(N, k)

    def pr(x):
        return math.comb(n1, x) * math.comb(n2, k - x) / denom
    lo, hi = max(0, k - n2), min(k, n1)
    p_obs = pr(a)
    return min(1.0, sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p_obs * (1 + 1e-9)))


def sign_test(pos: int, neg: int) -> float:
    """Exact two-sided binomial sign test (ties dropped)."""
    n = pos + neg
    if n == 0:
        return 1.0
    k = min(pos, neg)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def wilson(passes: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    if n == 0:
        return None
    ph = passes / n
    den = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / den
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


# --------------------------------------------------------------------------- #
# summaries
# --------------------------------------------------------------------------- #
def cells_of(rows):
    cells = defaultdict(list)
    for r in rows:
        cells[(r["agent"], r["scenario"], r["arm"])].append(r)
    return cells


def cell_stats(rs: list[dict]) -> dict:
    n = len(rs)
    passes = sum(1 for r in rs if r.get("primary_pass"))
    return {
        "n": n, "passes": passes, "rate": passes / n if n else None,
        "checkrate": _mean([(r.get("n_pass") or 0) / (r.get("n_checks") or 1) for r in rs]),
        "turns": _mean([_m(r, "turns") for r in rs]),
        "tool_calls": _mean([_m(r, "tool_calls") for r in rs]),
        "mcp_calls": _mean([(r.get("mcp") or {}).get("calls") for r in rs]),
        "in_tok": _mean([_m(r, "in_tok") for r in rs]),
        "out_tok": _mean([_m(r, "out_tok") for r in rs]),
        "cache_read_tok": _mean([_m(r, "cache_read_tok") for r in rs]),
        "cost_usd": _mean([_m(r, "cost_usd") for r in rs]),
        "wall_s": _mean([_m(r, "wall_s") for r in rs]),
        "timeouts": sum(1 for r in rs if _m(r, "timed_out")),
    }


def contrast(cells: dict, agents, scenarios, a: str, b: str) -> dict:
    """Effect a - b on primary pass rate: per cell, pooled (all + headroom), per agent."""
    per_cell = {}
    for ag in agents:
        for sc in scenarios:
            ra, rb = cells.get((ag, sc, a)), cells.get((ag, sc, b))
            if not ra or not rb:
                continue
            sa, sb = cell_stats(ra), cell_stats(rb)
            rn = cells.get((ag, sc, "neither"))
            neither_rate = cell_stats(rn)["rate"] if rn else None
            per_cell[(ag, sc)] = {"a": sa, "b": sb, "delta": sa["rate"] - sb["rate"],
                                  "headroom": neither_rate is not None and neither_rate < 1.0}

    def pool(keys) -> dict:
        keys = list(keys)
        if not keys:
            return {"cells": 0}
        pa = sum(per_cell[k]["a"]["passes"] for k in keys)
        na = sum(per_cell[k]["a"]["n"] for k in keys)
        pb = sum(per_cell[k]["b"]["passes"] for k in keys)
        nb = sum(per_cell[k]["b"]["n"] for k in keys)
        deltas = [per_cell[k]["delta"] for k in keys]
        pos = sum(1 for d in deltas if d > 0)
        neg = sum(1 for d in deltas if d < 0)
        return {"cells": len(keys), "rate_a": pa / na if na else None, "rate_b": pb / nb if nb else None,
                "n_a": na, "n_b": nb, "pass_a": pa, "pass_b": pb,
                "delta_pooled": (pa / na - pb / nb) if na and nb else None,
                "delta_cellmean": sum(deltas) / len(deltas),
                "fisher_p": fisher_exact(pa, na - pa, pb, nb - pb),
                "cells_pos": pos, "cells_neg": neg, "sign_p": sign_test(pos, neg)}

    allk = list(per_cell)
    head = [k for k in allk if per_cell[k]["headroom"]]
    by_agent = {ag: {"all": pool(k for k in allk if k[0] == ag),
                     "headroom": pool(k for k in head if k[0] == ag)} for ag in agents}
    by_scen = {sc: pool(k for k in allk if k[1] == sc) for sc in scenarios}
    return {"a": a, "b": b, "per_cell": per_cell, "all": pool(allk), "headroom": pool(head),
            "by_agent": by_agent, "by_scenario": by_scen}


# --------------------------------------------------------------------------- #
# markdown
# --------------------------------------------------------------------------- #
def md_quality(ok_rows, all_rows) -> list[str]:
    L = ["## 1. Data quality\n"]
    st = Counter(r.get("status") for r in all_rows)
    L.append(f"- rows in file: {len(all_rows)} · status: " + ", ".join(f"{k}={v}" for k, v in st.items())
             + f" · scored (ok, de-duplicated): **{len(ok_rows)}**")
    to = sum(1 for r in ok_rows if _m(r, "timed_out"))
    cont = [r["key"] for r in ok_rows if r.get("contaminated")]
    leak = [(r["key"], r.get("leak_markers")) for r in ok_rows if r.get("leak_markers")]
    L.append(f"- timeouts: {to} · contaminated (MCP call outside mcp arm, or helper CLI outside skillpkg arm): "
             f"{len(cont)}" + (f" {cont[:8]}" if cont else ""))
    L.append(f"- leak-marker hits (agent touched reference/old-eval paths): {len(leak)}"
             + (f" {leak[:5]}" if leak else ""))
    models = Counter((r["agent"], r.get("model"), (r.get("agent_info") or {}).get("model_seen")) for r in ok_rows)
    L.append("- models (agent, requested, seen-in-transcript): "
             + "; ".join(f"{a}={m} (seen {s or 'n/a'}) x{n}" for (a, m, s), n in sorted(models.items(), key=str)))
    errs = [r for r in all_rows if r.get("status") != "ok"]
    if errs:
        L.append("- non-ok rows: " + "; ".join(f"{r.get('key')}: {str(r.get('error'))[:80]}" for r in errs[:6]))
    def _turn_cap(r):  # Claude result subtype error_max_turns = the --max-turns budget ran out (not a crash)
        es = (r.get("agent_info") or {}).get("errors") or []
        return bool(es) and all(str(e) == "result:error_max_turns" for e in es)
    agent_errs = Counter(r["agent"] for r in ok_rows if (r.get("agent_info") or {}).get("errors") and not _turn_cap(r))
    if agent_errs:
        L.append(f"- rows whose transcript reports an agent-side error: {dict(agent_errs)}")
    caps = Counter(f"{r['agent']}/{r['arm']}" for r in ok_rows if _turn_cap(r))
    if caps:
        L.append(f"- rows that hit the turn cap (--max-turns; Claude result error_max_turns, not an agent error): "
                 f"{dict(caps)}")
    L.append("")
    return L


def md_cells(cells, agents, scenarios) -> list[str]:
    L = ["## 2. Per agent × scenario × arm\n",
         "`pass` = primary (all graders) pass rate · `chk` = mean fraction of graders passed · tokens are "
         "per-CLI accounting (in = uncached input + cache writes; cache = cache reads) — compare within an agent.\n",
         "| agent | scenario | arm | n | pass | chk | turns | tools | mcp | in_tok | out_tok | cache | cost $ | wall s | TO |",
         "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for ag in agents:
        for sc in scenarios:
            for arm in ARMS:
                rs = cells.get((ag, sc, arm))
                if not rs:
                    continue
                s = cell_stats(rs)
                L.append(f"| {ag} | {sc} | {arm} | {s['n']} | {_f(s['rate'])} | {_f(s['checkrate'])} | "
                         f"{_f(s['turns'], 1)} | {_f(s['tool_calls'], 1)} | {_f(s['mcp_calls'], 1)} | "
                         f"{_k(s['in_tok'])} | {_k(s['out_tok'])} | {_k(s['cache_read_tok'])} | "
                         f"{_f(s['cost_usd'], 3)} | {_f(s['wall_s'], 0)} | {s['timeouts']} |")
    L.append("")
    # arm totals with Wilson CI
    L.append("Pooled pass rate per arm (all agents × scenarios), 95% Wilson CI:\n")
    L.append("| arm | n | passes | rate | 95% CI |")
    L.append("|---|---:|---:|---:|---|")
    for arm in ARMS:
        rs = [r for (a, s, ar), v in cells.items() if ar == arm for r in v]
        if not rs:
            continue
        p = sum(1 for r in rs if r.get("primary_pass"))
        ci = wilson(p, len(rs))
        L.append(f"| {arm} | {len(rs)} | {p} | {p / len(rs):.2f} | "
                 f"{'—' if not ci else f'{ci[0]:.2f}–{ci[1]:.2f}'} |")
    L.append("")
    return L


def md_effects(contrasts: list[dict], agents, scenarios) -> list[str]:
    L = ["## 3. Effects on primary pass rate\n",
         "`Δcell` = equal-weight mean of per-(agent×scenario) rate differences; `Δpool` = difference of pooled "
         "rates; Fisher = two-sided exact test on pooled pass/fail counts (ignores strata); sign = exact sign "
         "test over cells (+/− cells, ties dropped). **Headroom** = cells where `neither` < 1.00.\n",
         "| contrast | subset | cells | rate A | rate B | Δcell | Δpool | Fisher p | cells +/− | sign p |",
         "|---|---|---:|---:|---:|---:|---:|---:|---|---:|"]
    for c in contrasts:
        for subset in ("all", "headroom"):
            p = c[subset]
            if not p.get("cells"):
                L.append(f"| {c['a']}−{c['b']} | {subset} | 0 | | | | | | | |")
                continue
            L.append(f"| **{c['a']}−{c['b']}** | {subset} | {p['cells']} | {_f(p['rate_a'])} ({p['pass_a']}/{p['n_a']}) | "
                     f"{_f(p['rate_b'])} ({p['pass_b']}/{p['n_b']}) | {_sgn(p['delta_cellmean'])} | "
                     f"{_sgn(p['delta_pooled'])} | {_p(p['fisher_p'])} | {p['cells_pos']}/{p['cells_neg']} | "
                     f"{_p(p['sign_p'])} |")
    L.append("")
    L.append("### 3a. Per agent (pooled over scenarios)\n")
    L.append("| agent | contrast | rate A | rate B | Δpool (all) | Fisher p | Δpool (headroom) | Fisher p (headroom) |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for ag in agents:
        for c in contrasts:
            pa, ph = c["by_agent"][ag]["all"], c["by_agent"][ag]["headroom"]
            if not pa.get("cells"):
                continue
            L.append(f"| {ag} | {c['a']}−{c['b']} | {_f(pa['rate_a'])} | {_f(pa['rate_b'])} | "
                     f"{_sgn(pa['delta_pooled'])} | {_p(pa['fisher_p'])} | "
                     f"{_sgn(ph.get('delta_pooled')) if ph.get('cells') else '—'} | "
                     f"{_p(ph.get('fisher_p')) if ph.get('cells') else '—'} |")
    L.append("")
    L.append("### 3b. Per scenario (pooled over agents)\n")
    L.append("| scenario | " + " | ".join(f"{c['a']}−{c['b']} Δpool (p)" for c in contrasts) + " |")
    L.append("|---|" + "---:|" * len(contrasts))
    for sc in scenarios:
        parts = []
        for c in contrasts:
            p = c["by_scenario"][sc]
            parts.append("—" if not p.get("cells") else f"{_sgn(p['delta_pooled'])} ({_p(p['fisher_p'])})")
        L.append(f"| {sc} | " + " | ".join(parts) + " |")
    L.append("")
    L.append("### 3c. Per cell rates\n")
    L.append("| agent | scenario | neither | mcp | skillpkg | mcp−neither | skillpkg−neither | skillpkg−mcp |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for ag in agents:
        for sc in scenarios:
            rates = {}
            for c in contrasts:
                pc = c["per_cell"].get((ag, sc))
                if pc:
                    rates[c["a"]] = pc["a"]["rate"]
                    rates[c["b"]] = pc["b"]["rate"]
            if not rates:
                continue
            ds = [c["per_cell"].get((ag, sc), {}).get("delta") for c in contrasts]
            L.append(f"| {ag} | {sc} | {_f(rates.get('neither'))} | {_f(rates.get('mcp'))} | "
                     f"{_f(rates.get('skillpkg'))} | " + " | ".join(_sgn(d) for d in ds) + " |")
    L.append("")
    return L


def md_efficiency(rows, agents) -> list[str]:
    L = ["## 4. Efficiency per agent × arm (all scenarios; means per session)\n",
         "| agent | arm | n | pass | turns | tool calls | in_tok | out_tok | cache | cost $ | wall s |",
         "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for ag in agents:
        for arm in ARMS:
            rs = [r for r in rows if r["agent"] == ag and r["arm"] == arm]
            if not rs:
                continue
            s = cell_stats(rs)
            L.append(f"| {ag} | {arm} | {s['n']} | {_f(s['rate'])} | {_f(s['turns'], 1)} | {_f(s['tool_calls'], 1)} | "
                     f"{_k(s['in_tok'])} | {_k(s['out_tok'])} | {_k(s['cache_read_tok'])} | {_f(s['cost_usd'], 3)} | "
                     f"{_f(s['wall_s'], 0)} |")
    L.append("")
    return L


def md_engagement(rows, agents) -> list[str]:
    L = ["## 5. Engagement\n", "### MCP arm\n",
         "| agent | n | ≥1 MCP call | mean MCP calls | server connected | top tools |",
         "|---|---:|---:|---:|---:|---|"]
    for ag in agents:
        rs = [r for r in rows if r["agent"] == ag and r["arm"] == "mcp"]
        if not rs:
            continue
        used = sum(1 for r in rs if (r.get("mcp") or {}).get("calls"))
        conn = 0
        known = 0
        tools: Counter = Counter()
        for r in rs:
            srv = (r.get("mcp") or {}).get("servers")
            if isinstance(srv, list):
                known += 1
                if any(isinstance(s, dict) and "robotmcp" in str(s.get("name", "")).lower()
                       and s.get("status") == "connected" for s in srv):
                    conn += 1
            tools.update((r.get("mcp") or {}).get("tools") or {})
        L.append(f"| {ag} | {len(rs)} | {used}/{len(rs)} | {_f(_mean([(r.get('mcp') or {}).get('calls') for r in rs]), 1)} | "
                 f"{f'{conn}/{known}' if known else 'n/a'} | "
                 + ", ".join(f"{t}×{n}" for t, n in tools.most_common(5)) + " |")
    L.append("")
    L.append("### skillpkg arm\n")
    L.append("| agent | n | helper used | skill read | mean helper calls | top rfmcp subcmds | "
             "hook firings: log / on .robot / transcript | pass if helper used | pass if not |")
    L.append("|---|---:|---:|---:|---:|---|---|---:|---:|")
    for ag in agents:
        rs = [r for r in rows if r["agent"] == ag and r["arm"] == "skillpkg"]
        if not rs:
            continue
        sp = [r.get("skillpkg") or {} for r in rs]
        used = [r for r in rs if (r.get("skillpkg") or {}).get("helper_used")]
        notused = [r for r in rs if not (r.get("skillpkg") or {}).get("helper_used")]
        pu = _mean([1 if r.get("primary_pass") else 0 for r in used])
        pn = _mean([1 if r.get("primary_pass") else 0 for r in notused])
        subs: Counter = Counter()
        for s_ in sp:
            subs.update(s_.get("helper_subcmds") or {})
        L.append(f"| {ag} | {len(rs)} | {len(used)}/{len(rs)} | "
                 f"{sum(1 for s in sp if s.get('skill_read'))}/{len(rs)} | "
                 f"{_f(_mean([s.get('helper_calls') for s in sp]), 1)} | "
                 + ", ".join(f"{k}×{v}" for k, v in subs.most_common(4)) + " | "
                 f"{_f(_mean([s.get('hook_firings_log') for s in sp]), 1)} / "
                 f"{_f(_mean([s.get('hook_firings_with_files') for s in sp]), 1)} / "
                 f"{_f(_mean([s.get('hook_events_transcript') for s in sp]), 1)} | {_f(pu)} | {_f(pn)} |")
    L.append("")
    return L


# --------------------------------------------------------------------------- #
# Round 2: live scenarios - kind split + stepwise usage vs success
# --------------------------------------------------------------------------- #
STEP_FIELDS = [("live_steps", "steps"), ("live_inspect", "inspect"), ("tool_runs", "tool runs"),
               ("kw_lookup", "kw lookup"), ("robot_runs", "robot CLI"), ("adhoc_browser", "ad-hoc browser")]


def _sw(r: dict, k: str):
    return (r.get("stepwise") or {}).get(k)


def _pass(r: dict) -> int:
    return 1 if r.get("primary_pass") else 0


def md_live(rows: list[dict], agents: list[str], cells: dict) -> list[str]:
    live = [r for r in rows if r.get("live") or r.get("kind") in ("explore", "debug")]
    if not live:
        return []
    kinds = [k for k in ("explore", "debug") if any(r.get("kind") == k for r in live)]
    L = ["## 6. Live round: explore vs debug, and does the helper replace execute_step?\n",
         "`first` = robot passed on the grader's first attempt (no retry); `flaky` = passed only on the "
         "automatic retry. Stepwise columns are means per session: **steps** = rf-mcp execute_step + "
         "execute_batch + intent_action | `rfmcp step`; **inspect** = get_session_state | `rfmcp state`; "
         "**tool runs** = run_test_suite | `rfmcp run`; **kw lookup** = find_keywords + get_keyword_info | "
         "`rfmcp search` + `rfmcp doc`; **robot CLI** = plain `robot` shell runs (all arms); "
         "**ad-hoc browser** = shell calls driving playwright/chromium/robotcode repl directly.\n",
         "### 6a. Pass rate and stepwise usage per kind × arm (all agents)\n",
         "| kind | arm | n | pass | 95% CI | first | flaky | " + " | ".join(h for _, h in STEP_FIELDS)
         + " | ≥1 step/inspect | turns | tools | wall s |",
         "|---|---|---:|---:|---|---:|---:|" + "---:|" * len(STEP_FIELDS) + "---:|---:|---:|---:|"]
    for kd in kinds:
        for arm in ARMS:
            rs = [r for r in live if r.get("kind") == kd and r["arm"] == arm]
            if not rs:
                continue
            p = sum(_pass(r) for r in rs)
            ci = wilson(p, len(rs))
            first = sum(1 for r in rs if r.get("robot_first_pass"))
            flaky = sum(1 for r in rs if r.get("flaky") and r.get("primary_pass"))
            anyst = sum(1 for r in rs if _sw(r, "stepwise_any"))
            L.append(f"| {kd} | {arm} | {len(rs)} | {p / len(rs):.2f} | "
                     f"{'—' if not ci else f'{ci[0]:.2f}–{ci[1]:.2f}'} | {first}/{len(rs)} | {flaky} | "
                     + " | ".join(_f(_mean([_sw(r, k) for r in rs]), 1) for k, _ in STEP_FIELDS)
                     + f" | {anyst}/{len(rs)} | {_f(_mean([_m(r, 'turns') for r in rs]), 1)} | "
                     f"{_f(_mean([_m(r, 'tool_calls') for r in rs]), 1)} | {_f(_mean([_m(r, 'wall_s') for r in rs]), 0)} |")
    L.append("")
    # contrasts pooled per kind
    L.append("### 6b. Arm contrasts per kind (pooled over agents × scenarios of that kind)\n")
    L.append("| kind | contrast | rate A | rate B | Δpool | Fisher p | cells +/− |")
    L.append("|---|---|---:|---:|---:|---:|---|")
    for kd in kinds:
        scen = sorted({r["scenario"] for r in live if r.get("kind") == kd})
        for a, b in CONTRASTS:
            c = contrast(cells, agents, scen, a, b)["all"]
            if not c.get("cells"):
                continue
            L.append(f"| {kd} | {a}−{b} | {_f(c['rate_a'])} ({c['pass_a']}/{c['n_a']}) | "
                     f"{_f(c['rate_b'])} ({c['pass_b']}/{c['n_b']}) | {_sgn(c['delta_pooled'])} | "
                     f"{_p(c['fisher_p'])} | {c['cells_pos']}/{c['cells_neg']} |")
    L.append("")
    # stepwise use vs success
    L.append("### 6c. Stepwise use vs success (per kind × arm)\n")
    L.append("Sessions split by whether they used live stepwise execution/inspection at all (steps + inspect "
             "> 0), and by tercile of `steps`. A treatment whose gain comes from stepwise execution should show "
             "higher pass with use than without (confounded: struggling sessions also step more).\n")
    L.append("| kind | arm | pass with step/inspect (n) | pass without (n) | Fisher p | pass by steps tercile "
             "(low/mid/high) | mean steps: passed vs failed |")
    L.append("|---|---|---|---|---:|---|---|")
    for kd in kinds:
        for arm in ARMS:
            rs = [r for r in live if r.get("kind") == kd and r["arm"] == arm]
            if not rs:
                continue
            u = [r for r in rs if _sw(r, "stepwise_any")]
            n = [r for r in rs if not _sw(r, "stepwise_any")]
            pu, pn = sum(_pass(r) for r in u), sum(_pass(r) for r in n)
            fp = fisher_exact(pu, len(u) - pu, pn, len(n) - pn) if u and n else None
            srt = sorted(rs, key=lambda r: _sw(r, "live_steps") or 0)
            k = len(srt)
            ters = [srt[: k // 3], srt[k // 3: 2 * k // 3], srt[2 * k // 3:]] if k >= 3 else [srt]
            ter_s = " / ".join(f"{_f(_mean([_pass(r) for r in t]))}" for t in ters if t)
            sp = _mean([_sw(r, "live_steps") for r in rs if r.get("primary_pass")])
            sf = _mean([_sw(r, "live_steps") for r in rs if not r.get("primary_pass")])
            L.append(f"| {kd} | {arm} | {_f(pu / len(u) if u else None)} ({len(u)}) | "
                     f"{_f(pn / len(n) if n else None)} ({len(n)}) | {_p(fp)} | {ter_s} | {_f(sp, 1)} vs {_f(sf, 1)} |")
    L.append("")
    # per agent detail
    L.append("### 6d. Per agent × kind × arm: pass and stepwise usage\n")
    L.append("| agent | kind | arm | n | pass | flaky | steps | inspect | tool runs | robot CLI | mcp tools / rfmcp subcmds |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for ag in agents:
        for kd in kinds:
            for arm in ARMS:
                rs = [r for r in live if r["agent"] == ag and r.get("kind") == kd and r["arm"] == arm]
                if not rs:
                    continue
                tools: Counter = Counter()
                for r in rs:
                    sw = r.get("stepwise") or {}
                    tools.update({k: v for k, v in (sw.get("mcp") or {}).items() if v})
                    tools.update({f"rfmcp {k}": v for k, v in (sw.get("helper") or {}).items() if v})
                L.append(f"| {ag} | {kd} | {arm} | {len(rs)} | {_f(_mean([_pass(r) for r in rs]))} | "
                         f"{sum(1 for r in rs if r.get('flaky') and r.get('primary_pass'))} | "
                         f"{_f(_mean([_sw(r, 'live_steps') for r in rs]), 1)} | "
                         f"{_f(_mean([_sw(r, 'live_inspect') for r in rs]), 1)} | "
                         f"{_f(_mean([_sw(r, 'tool_runs') for r in rs]), 1)} | "
                         f"{_f(_mean([_sw(r, 'robot_runs') for r in rs]), 1)} | "
                         + ", ".join(f"{t}×{v}" for t, v in tools.most_common(6)) + " |")
    L.append("")
    # failing graders (what breaks) per kind x arm
    L.append("### 6e. Failed graders per kind × arm (count of sessions)\n")
    L.append("| kind | arm | failed graders |")
    L.append("|---|---|---|")
    for kd in kinds:
        for arm in ARMS:
            rs = [r for r in live if r.get("kind") == kd and r["arm"] == arm]
            if not rs:
                continue
            fc: Counter = Counter()
            for r in rs:
                for v in r.get("verdicts") or []:
                    if not v.get("passed"):
                        fc[v.get("label") or v["type"]] += 1
            L.append(f"| {kd} | {arm} | " + (", ".join(f"{k}×{v}" for k, v in fc.most_common(10)) or "—") + " |")
    L.append("")
    # journey evidence (rc-3): robot green but the run did not really drive the journey
    jrows = [r for r in live if any(v.get("type") == "journey" for v in r.get("verdicts") or [])]
    if jrows:
        parts = [("confirm", "confirm read"), ("values", "value read"), ("inputs", "fields driven"),
                 ("nav", "no shortcut")]
        L.append("### 6f. Journey evidence per scenario × arm (journey-evidence graders on the graded run's "
                 "output.xml)\n")
        L.append("`robot green` = robot_pass passed; the part columns count robot-green sessions that FAILED that "
                 "journey part (green suite, incomplete journey / shortcut); `journey ok` = robot green and all four "
                 "parts passed.\n")
        L.append("| scenario | arm | n | robot green | " + " | ".join(h for _, h in parts) + " | journey ok |")
        L.append("|---|---|---:|---:|" + "---:|" * len(parts) + "---:|")

        def _jfail(r, part):
            return any(v.get("type") == "journey" and v.get("part") == part and not v.get("passed")
                       for v in r.get("verdicts") or [])
        for sc in sorted({r["scenario"] for r in jrows}):
            for arm in ARMS:
                rs = [r for r in jrows if r["scenario"] == sc and r["arm"] == arm]
                if not rs:
                    continue
                green = [r for r in rs if any(v.get("type") == "robot_pass" and v.get("passed")
                                              for v in r.get("verdicts") or [])]
                jok = sum(1 for r in green if not any(_jfail(r, p) for p, _ in parts))
                L.append(f"| {sc} | {arm} | {len(rs)} | {len(green)} | "
                         + " | ".join(str(sum(1 for r in green if _jfail(r, p))) for p, _ in parts)
                         + f" | {jok} |")
        L.append("")
    return L


def live_json(rows: list[dict]) -> dict:
    out: dict = {}
    for r in rows:
        if not (r.get("live") or r.get("kind") in ("explore", "debug")):
            continue
        d = out.setdefault(r.get("kind"), {}).setdefault(r["arm"], {"n": 0, "pass": 0, "flaky": 0,
                                                                     "stepwise_any": 0, "steps": 0, "inspect": 0})
        d["n"] += 1
        d["pass"] += _pass(r)
        d["flaky"] += 1 if (r.get("flaky") and r.get("primary_pass")) else 0
        d["stepwise_any"] += 1 if _sw(r, "stepwise_any") else 0
        d["steps"] += _sw(r, "live_steps") or 0
        d["inspect"] += _sw(r, "live_inspect") or 0
    return out


def to_json(contrasts):
    out = []
    for c in contrasts:
        cc = {k: v for k, v in c.items() if k != "per_cell"}
        cc["per_cell"] = {f"{a}|{s}": {"delta": v["delta"], "headroom": v["headroom"],
                                       "rate_a": v["a"]["rate"], "rate_b": v["b"]["rate"],
                                       "n_a": v["a"]["n"], "n_b": v["b"]["n"]}
                          for (a, s), v in c["per_cell"].items()}
        out.append(cc)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="?", default=str(HERE / "results_rc.jsonl"))
    ap.add_argument("--out", default=None, help="write markdown here (default: stdout)")
    ap.add_argument("--json", default=None, help="write machine-readable summary here")
    ap.add_argument("--label", default="")
    ap.add_argument("--drop-contaminated", action="store_true")
    args = ap.parse_args()

    ok_rows, all_rows = load(Path(args.results))
    if args.drop_contaminated:
        ok_rows = [r for r in ok_rows if not r.get("contaminated")]
    if not ok_rows:
        raise SystemExit("no ok rows")
    agents = [a for a in ("claude", "codex", "opencode", "copilot") if any(r["agent"] == a for r in ok_rows)]
    known = ("iframe", "apinested", "results_complex", "browser_dynamic",
             "tricentis_quote", "carconfig_order", "demoshop_debug", "tricentis_debug")
    scenarios = [s for s in known if any(r["scenario"] == s for r in ok_rows)]
    scenarios += sorted({r["scenario"] for r in ok_rows} - set(scenarios))
    cells = cells_of(ok_rows)
    contrasts = [contrast(cells, agents, scenarios, a, b) for a, b in CONTRASTS]

    reps = max((r.get("rep", 1) for r in ok_rows), default=1)
    L = [f"# neither vs rf-mcp vs skillpkg — cross-agent A/B{(' — ' + args.label) if args.label else ''}\n",
         f"Source: `{Path(args.results).name}` · agents: {', '.join(agents)} · scenarios: {', '.join(scenarios)} · "
         f"arms: {', '.join(a for a in ARMS if any(r['arm'] == a for r in ok_rows))} · max rep: {reps}\n"]
    L += md_quality(ok_rows, all_rows)
    L += md_cells(cells, agents, scenarios)
    L += md_effects(contrasts, agents, scenarios)
    L += md_efficiency(ok_rows, agents)
    L += md_engagement(ok_rows, agents)
    L += md_live(ok_rows, agents, cells)
    md = "\n".join(L)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"rows={len(ok_rows)} -> {args.out}")
    else:
        print(md)
    if args.json:
        Path(args.json).write_text(json.dumps({"rows": len(ok_rows), "contrasts": to_json(contrasts),
                                               "live": live_json(ok_rows)},
                                              indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
