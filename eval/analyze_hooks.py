"""Hook-arm A/B analysis (ported from the round-7 research analyzer; archived reports regenerate byte-identically).

Arms understood: neither, mcp, skillpkg (historical), the historical hook arms hookpkg, hookpkg2, hookpkg3, hookpkg31,
hookpkg32, and the product arms rf-harness and prototype-v32 (both get the v2 + v3 + output-profile tables, like
hookpkg32).

Original round-4 description: hookpkg (Agent Skill + hooks, no CLI) vs skillpkg (rfmcp CLI) on the live scenarios.

Reuses analyze.py's tables with ARMS/CONTRASTS overridden, replaces its 3-arm per-cell table with a generic one,
and adds a hookpkg engagement section (hook firings, auto-executed lines, gate denials/rewrites, Stop blocks).

Usage: python3 analyze_hooks.py results_live_hooks.jsonl --out report_live_hooks.txt --json summary_live_hooks.json
       python3 analyze_hooks.py results_live_v2.jsonl --arms hookpkg,hookpkg2 --out report_live_v2.txt
       python3 analyze_hooks.py results_live_v3.jsonl --arms mcp,hookpkg2,hookpkg3 --out report_live_v3.txt
       python3 analyze_hooks.py results_live_v31or.jsonl --arms mcp,hookpkg3,hookpkg31 --out report_live_v31or.txt
--arms: any arms (comma-separated); the FIRST is the baseline, every other arm is contrasted against it
(default skillpkg,hookpkg == the round-4 report). Every hook arm (row[<arm>] metrics) gets an engagement table;
hookpkg2/hookpkg3 also the v2 table (docs files, captures, rechecks, REPL format rewrites/denials, loop hints, guard
denials) and hookpkg3 the v3 table (context chars per edit, skipped captures/re-checks, adaptive timeout changes,
warnings vs denials, race reproductions). Arms without hook metrics (neither, mcp, skillpkg) only appear in the
pass/efficiency tables.
v3.1: hookpkg31 gets the v2 + v3 tables and an output-profile table (lean/rich per agent, where the profile came from).
Agents: any agent id (claude, codex, opencode, copilot first, then e.g. cc-or:<short> / oc-or:<short> OpenRouter
routes) appears in every table; OpenRouter agents get a cost table (estimate from OpenRouter prices + /key usage delta;
metrics.cost_usd of those rows already holds the estimate).
"""
import argparse
import json
import sys
from pathlib import Path

import analyze as A

if sys.version_info < (3, 12):
    sum = A.compat_sum  # noqa: A001  (CPython 3.12 float summation: identical reports on every Python)

ARMS = ["skillpkg", "hookpkg"]
CONTRASTS = [("hookpkg", "skillpkg")]


def per_cell_table(contrasts, agents, scenarios):
    L = ["### 3c. Per cell rates\n",
         "| agent | scenario | " + " | ".join(ARMS) + " | " + " | ".join(f"{a}−{b}" for a, b in CONTRASTS) + " |",
         "|---|---|" + "---:|" * (len(ARMS) + len(CONTRASTS))]
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
            L.append(f"| {ag} | {sc} | " + " | ".join(A._f(rates.get(a)) for a in ARMS) + " | "
                     + " | ".join(A._sgn(d) for d in ds) + " |")
    L.append("")
    return L


def md_hooks(rows, agents, arm="hookpkg", sec="7"):
    L = [f"## {sec}. {arm} engagement (hooks instead of a CLI)\n",
         "| agent | n | pass | firings | auto-executed lines | non-pass auto lines | gate denials | rewrites | "
         "Stop blocks | robot reproductions | still-running | .rf/state reads | .rf/docs reads | rfmcp CLI calls |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for ag in agents:
        rs = [r for r in rows if r["agent"] == ag and r["arm"] == arm]
        if not rs:
            continue
        h = [r.get(arm) or {} for r in rs]
        m = lambda k: A._mean([x.get(k) for x in h if x.get(k) is not None])
        cli = sum(int((r.get("helper_cli_calls") or 0) if isinstance(r.get("helper_cli_calls"), int) else 0) for r in rs)
        L.append(f"| {ag} | {len(rs)} | {A._f(A._mean([A._pass(r) for r in rs]))} | {A._f(m('firings'), 1)} | "
                 f"{A._f(m('auto_executed_lines'), 1)} | {A._f(m('auto_non_pass_lines'), 1)} | {A._f(m('denials'), 1)} | "
                 f"{A._f(m('rewrites'), 1)} | {A._f(m('stop_blocks'), 1)} | {A._f(m('reproductions'), 1)} | "
                 f"{A._f(m('still_running'), 1)} | {A._f(m('state_reads'), 1)} | {A._f(m('docs_reads'), 1)} | {cli} |")
    L.append("")
    # pass rate vs hook activity
    hr = [r for r in rows if r["arm"] == arm]
    def split(key, thr):
        hi = [r for r in hr if ((r.get(arm) or {}).get(key) or 0) >= thr]
        lo = [r for r in hr if ((r.get(arm) or {}).get(key) or 0) < thr]
        return (A._mean([A._pass(r) for r in hi]), len(hi), A._mean([A._pass(r) for r in lo]), len(lo))
    L.append(f"Pass rate by hook activity ({arm} sessions; confounded — struggling sessions trigger more hooks):\n")
    L.append("| split | pass (n) high | pass (n) low |")
    L.append("|---|---|---|")
    for key, thr, label in [("denials", 1, "≥1 gate denial vs none"), ("stop_blocks", 1, "≥1 Stop block vs none"),
                            ("reproductions", 1, "≥1 robot-run reproduction vs none")]:
        a, na, b, nb = split(key, thr)
        L.append(f"| {label} | {A._f(a)} ({na}) | {A._f(b)} ({nb}) |")
    L.append("")
    # latency
    lat = {}
    for r in hr:
        for ev, v in ((r.get(arm) or {}).get("latency_ms_median") or {}).items():
            lat.setdefault(ev, []).append(v)
    if lat:
        L.append("Median hook latency per session, averaged (ms): " +
                 ", ".join(f"{ev} {A._f(A._mean(v), 0)}" for ev, v in sorted(lat.items())) + "\n")
    return L


HOOK_ARM_NAMES = ("hookpkg", "hookpkg2", "hookpkg3", "hookpkg31", "hookpkg32", "rf-harness", "prototype-v32")
PRODUCT_HOOK_ARMS = ("rf-harness", "prototype-v32")      # v3.2-level metrics (v2 + v3 + profile tables)
V2_ARMS = ("hookpkg2", "hookpkg3", "hookpkg31", "hookpkg32") + PRODUCT_HOOK_ARMS
V3_ARMS = ("hookpkg3", "hookpkg31", "hookpkg32") + PRODUCT_HOOK_ARMS
PROFILE_ARMS = ("hookpkg31", "hookpkg32") + PRODUCT_HOOK_ARMS


def _cross_label():
    if any(a in ARMS for a in PRODUCT_HOOK_ARMS):
        return "hook-arm"
    return ('v1/v2/v3/v3.1/v3.2' if 'hookpkg32' in ARMS else 'v1/v2/v3/v3.1' if 'hookpkg31' in ARMS
            else ('v1/v2/v3' if 'hookpkg3' in ARMS else 'v1/v2'))
V3_KEYS = [("ctx_chars_per_edit", "ctx chars/edit"), ("ctx_chars_edit_ok", "ok edit"), ("ctx_chars_edit_fail", "fail edit"),
           ("ctx_chars_robot", "robot run"), ("ctx_chars_total", "ctx total"), ("captures", "captures"),
           ("capture_skipped", "capture skipped"), ("timeout_rechecks", "rechecks"), ("rechecks_skipped", "instant MISSING"),
           ("recheck_s_total", "recheck s"), ("tmo_changes", "tmo changes"), ("denials", "denials"),
           ("warnings", "warnings"), ("repro_race", "race repro"), ("docs_on_demand", "kw docs on demand")]


def md_profiles(rows, agents, arm="hookpkg31", sec="10"):
    L = [f"## {sec}. {arm}: output profile per agent (lean = v3 output, rich = v2-like guidance)\n",
         "| agent | n | pass | profile (sessions) | decided from | model (hook) | ctx chars/edit | ok edit | fail edit |",
         "|---|---:|---:|---|---|---|---:|---:|---:|"]
    for ag in agents:
        rs = [r for r in rows if r["agent"] == ag and r["arm"] == arm]
        if not rs:
            continue
        h = [r.get(arm) or {} for r in rs]
        prof: dict = {}
        src: dict = {}
        mod: dict = {}
        for x in h:
            prof[x.get("profile") or "?"] = prof.get(x.get("profile") or "?", 0) + 1
            src[x.get("profile_src") or "?"] = src.get(x.get("profile_src") or "?", 0) + 1
            if x.get("profile_model"):
                mod[x["profile_model"]] = mod.get(x["profile_model"], 0) + 1
        m = lambda k: A._mean([x.get(k) for x in h if isinstance(x.get(k), (int, float))])
        fmt = lambda d: ", ".join(f"{k} {v}" for k, v in sorted(d.items(), key=lambda kv: -kv[1])) or "-"
        L.append(f"| {ag} | {len(rs)} | {A._f(A._mean([A._pass(r) for r in rs]))} | {fmt(prof)} | {fmt(src)} | "
                 f"{fmt(mod)} | {A._f(m('ctx_chars_per_edit'), 0)} | {A._f(m('ctx_chars_edit_ok'), 0)} | "
                 f"{A._f(m('ctx_chars_edit_fail'), 0)} |")
    L.append("")
    return L


def md_openrouter(rows, agents, sec="11"):
    orr = [r for r in rows if isinstance(r.get("openrouter"), dict)]
    if not orr:
        return []
    L = [f"## {sec}. OpenRouter agents: cost per session\n",
         "`est $` = tokens × the model's OpenRouter prices (or_prices.json); `usage Δ $` = account usage delta "
         "(/api/v1/key) before/after the cell — shared with concurrent OpenRouter cells (see `conc`) and booked with a "
         "short delay, so per-cell deltas are a cross-check, totals are reliable.\n",
         "| agent | arm | n | pass | model | est $/session | usage Δ $/session | est $ total | in (uncached) | out | "
         "cache read | cache write | conc (max) | via OpenRouter |",
         "|---|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for ag in agents:
        for arm in sorted({r["arm"] for r in orr if r["agent"] == ag}):
            rs = [r for r in orr if r["agent"] == ag and r["arm"] == arm]
            o = [r["openrouter"] for r in rs]
            est = [x.get("est_cost_usd") for x in o if isinstance(x.get("est_cost_usd"), (int, float))]
            dl = [x.get("usage_delta_usd") for x in o if isinstance(x.get("usage_delta_usd"), (int, float))]
            tk = lambda k: A._mean([(x.get("tokens") or {}).get(k) for x in o if (x.get("tokens") or {}).get(k) is not None])
            conc = max([int(r.get("or_concurrent_at_start") or 0) for r in rs] + [0])
            via = sum(1 for x in o if x.get("via_openrouter"))
            L.append(f"| {ag} | {arm} | {len(rs)} | {A._f(A._mean([A._pass(r) for r in rs]))} | "
                     f"{o[0].get('model_id')} | {A._f(A._mean(est), 4)} | {A._f(A._mean(dl), 4)} | "
                     f"{A._f(sum(est), 3) if est else '-'} | {A._k(tk('in_uncached'))} | {A._k(tk('out'))} | "
                     f"{A._k(tk('cache_read'))} | {A._k(tk('cache_write'))} | {conc} | {via}/{len(rs)} |")
    tot = sum(r["openrouter"].get("est_cost_usd") or 0 for r in orr)
    L.append(f"\nTotal OpenRouter estimate: ${tot:.3f} over {len(orr)} sessions.\n")
    return L


def md_hooks_v3(rows, agents, arm="hookpkg3", sec="9"):
    L = [f"## {sec}. {arm}: v3 metrics per session (means)\n",
         "| agent | n | " + " | ".join(lbl for _, lbl in V3_KEYS) + " | verdicts slow/missing | fail classes |",
         "|---|---:|" + "---:|" * (len(V3_KEYS) + 2)]
    for ag in agents:
        rs = [r for r in rows if r["agent"] == ag and r["arm"] == arm]
        if not rs:
            continue
        h = [r.get(arm) or {} for r in rs]
        m = lambda k: A._mean([x.get(k) for x in h if isinstance(x.get(k), (int, float))])
        slow = sum((x.get("recheck_verdicts") or {}).get("slow", 0) for x in h)
        miss = sum((x.get("recheck_verdicts") or {}).get("missing", 0) for x in h)
        cls: dict = {}
        for x in h:
            for k, v in (x.get("fail_classes") or {}).items():
                cls[k] = cls.get(k, 0) + v
        cl = ", ".join(f"{k} {v}" for k, v in sorted(cls.items(), key=lambda kv: -kv[1])[:5]) or "-"
        L.append(f"| {ag} | {len(rs)} | " + " | ".join(A._f(m(k), 1) for k, _ in V3_KEYS) + f" | {slow}/{miss} | {cl} |")
    L.append("")
    return L


V2_KEYS = [("docs_files", "docs files"), ("docs_kw_files", "kw docs"), ("captures", "captures"),
           ("timeout_rechecks", "rechecks"), ("format_rewrites", "REPL rewrites"), ("format_denials", "REPL denials"),
           ("repl_commands", "REPL cmds"), ("loop_hints", "loop hints"), ("guard_denials", "guard denials"),
           ("guard_denials_suite", "suite"), ("guard_denials_install", "install"),
           ("guard_denials_pythonpath", "-P"), ("guard_denials_bigread", "big read"), ("valve_allows", "valve"),
           ("kwdoc_reads", ".rf/docs/kw reads"), ("latest_reads", ".rf/state/latest reads")]


def md_hooks_v2(rows, agents, arm="hookpkg2", sec="8"):
    L = [f"## {sec}. {arm}: v2 hooks per session (means)\n",
         "| agent | n | " + " | ".join(lbl for _, lbl in V2_KEYS) + " | slow/missing | capture ms (median) |",
         "|---|---:|" + "---:|" * (len(V2_KEYS) + 2)]
    for ag in agents:
        rs = [r for r in rows if r["agent"] == ag and r["arm"] == arm]
        if not rs:
            continue
        h = [r.get(arm) or {} for r in rs]
        m = lambda k: A._mean([x.get(k) for x in h if x.get(k) is not None])
        slow = sum((x.get("recheck_verdicts") or {}).get("slow", 0) for x in h)
        miss = sum((x.get("recheck_verdicts") or {}).get("missing", 0) for x in h)
        cms = [x.get("capture_ms_median") for x in h if x.get("capture_ms_median") is not None]
        L.append(f"| {ag} | {len(rs)} | " + " | ".join(A._f(m(k), 1) for k, _ in V2_KEYS)
                 + f" | {slow}/{miss} | {A._f(sorted(cms)[len(cms) // 2] if cms else None, 0)} |")
    L.append("")
    cross = [r for r in rows if r["arm"] in HOOK_ARM_NAMES and r.get("hook_cross_hits")]
    L.append(f"{_cross_label()} cross-contamination rows: {len(cross)}\n")
    return L


def main():
    global ARMS, CONTRASTS
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--out")
    ap.add_argument("--json")
    ap.add_argument("--arms", default=",".join(ARMS),
                    help="comma-separated arms; the first is the baseline the others are contrasted with")
    args = ap.parse_args()
    ARMS = [a for a in args.arms.split(",") if a]
    CONTRASTS = [(a, ARMS[0]) for a in ARMS[1:]]
    A.ARMS = ARMS
    A.CONTRASTS = CONTRASTS
    ok_rows, all_rows = A.load(Path(args.results))
    base = ("claude", "codex", "opencode", "copilot")
    agents = [a for a in base if any(r["agent"] == a for r in ok_rows)]
    agents += sorted({r["agent"] for r in ok_rows} - set(base))       # cc-or:<short>, oc-or:<short>, ...
    order = ["tricentis_quote", "carconfig_order", "demoshop_order", "demoshop_debug", "tricentis_debug"]
    scenarios = [s for s in order if any(r["scenario"] == s for r in ok_rows)]
    scenarios += sorted({r["scenario"] for r in ok_rows} - set(scenarios))
    cells = A.cells_of(ok_rows)
    contrasts = [A.contrast(cells, agents, scenarios, a, b) for a, b in CONTRASTS]
    title = " vs ".join(ARMS[1:][::-1] + ARMS[:1]) if len(ARMS) > 1 else ARMS[0]
    L = [("# hookpkg (skills + hooks, no CLI) vs skillpkg (rfmcp CLI) — live A/B\n" if ARMS == ["skillpkg", "hookpkg"]
          else f"# {title} — A/B\n"),
         f"Source: `{Path(args.results).name}` · agents: {', '.join(agents)} · scenarios: {', '.join(scenarios)} · "
         f"rows: {len(ok_rows)}\n"]
    L += A.md_quality(ok_rows, all_rows)
    L += A.md_cells(cells, agents, scenarios)
    eff = A.md_effects(contrasts, agents, scenarios)
    cut = next((i for i, x in enumerate(eff) if x.startswith("### 3c")), len(eff))
    L += eff[:cut] + per_cell_table(contrasts, agents, scenarios)
    L += A.md_efficiency(ok_rows, agents)
    L += A.md_live(ok_rows, agents, cells)
    sec = 7
    for arm in ARMS:
        if arm in HOOK_ARM_NAMES and any(r["arm"] == arm and isinstance(r.get(arm), dict) for r in ok_rows):
            L += md_hooks(ok_rows, agents, arm, str(sec))
            sec += 1
            if arm in V2_ARMS:
                L += md_hooks_v2(ok_rows, agents, arm, str(sec))
                sec += 1
            if arm in V3_ARMS:
                L += md_hooks_v3(ok_rows, agents, arm, str(sec))
                sec += 1
            if arm in PROFILE_ARMS:
                L += md_profiles(ok_rows, agents, arm, str(sec))
                sec += 1
    L += md_openrouter(ok_rows, agents, str(sec))
    md = "\n".join(L)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
        print(f"rows={len(ok_rows)} -> {args.out}")
    else:
        print(md)
    if args.json:
        Path(args.json).write_text(json.dumps({"rows": len(ok_rows), "contrasts": A.to_json(contrasts),
                                               "live": A.live_json(ok_rows)}, indent=2, default=str),
                                   encoding="utf-8")


if __name__ == "__main__":
    main()
