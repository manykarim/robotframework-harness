# Round 5 A/B: hookpkg (v1) vs hookpkg2 (v2) — live scenarios (2026-10-09)

Data `harness/results_live_v2.jsonl` (90 cells), report `harness/report_live_v2.txt` (+ `summary_live_v2.json`), runner `harness/run_v2_ab.sh`, analysis `analyze_hooks.py results_live_v2.jsonl --arms hookpkg,hookpkg2`. Same 5 live scenarios, journey-evidence graders, models (claude-haiku-4-5, codex gpt-5.6-luna@medium, opencode MiniMax-M2.5), 3 reps, 80-turn cap. Ops: external SIGTERM at 01:49 (64/90; 2 aborted rows dropped; 28 resumed 08:23–10:01). Final: 90 unique, all ok, 0 auth failures, 0 contaminated (incl. v1/v2 cross-markers), 0 leaks, 3 timeouts, 1 turn-cap row (claude/hookpkg2).

## Results
| | hookpkg (v1) | hookpkg2 (v2) |
|---|---|---|
| **pass, all (n=45)** | 0.51 (0.37–0.65) | **0.60** (0.45–0.73) |
| explore / debug | 0.48 / 0.56 | **0.63** / 0.56 |
| Claude / Codex / OpenCode | 0.40 / **0.93** / 0.20 | 0.40 / 0.87 / **0.53** |
| OpenCode explore / debug | 0.22 / 0.17 | **0.56 / 0.50** |
| Claude cost / wall / turns | **$0.367 / 353 s / 39** | $0.542 / 526 s / 52 |
| OpenCode wall / turns / in_tok | 642 s / 64 / 141k | **620 s / 60 / 93k** |
| Codex wall | **207 s** | 268 s |
| debug wall (all agents) | **325 s** | 472 s |

hookpkg2−hookpkg: +0.09 overall (Fisher p=0.53; cells 5/4); OpenCode **+0.33** (p=0.13); Claude ±0; Codex −0.07. Per scenario: tricentis_quote +0.22, carconfig +0.11, demoshop_order +0.11, demoshop_debug +0.22, tricentis_debug −0.22. Run-to-run variance of the same v1 arm vs round 4: 0.51 now vs 0.58 then (Claude 0.40 vs 0.53, OpenCode 0.20 vs 0.33) → noise ≈ ±0.07–0.13.

## v2 hooks in real runs (means per hookpkg2 session)
| agent | kw docs files | captures | rechecks (SLOW/MISSING total) | loop hints | guard denials | REPL rewrites | `.rf/docs/kw` reads | `.rf/state/latest` reads | capture ms |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| claude | 18.7 | 48.5 | 6.8 (49/53) | 1.7 | 0.4 | 0.1 | 0.1 | 18.6 | 152 |
| codex | 7.0 | 29.1 | 2.6 (16/23) | 0.4 | 0.0 | 0.5 | 0.3 | 8.8 | 152 |
| opencode | 26.3 | 42.9 | 9.4 (62/79) | 4.1 | 0.6 | 0.0 | 0.3 | 16.1 | 161 |
- **Short timeout + re-check fired constantly**: ~45% of re-checks were SLOW (element appeared after > 2.5 s) → extra waits, likely a main driver of v2's longer wall time for Claude/Codex.
- **Keyword-doc files are written but almost never read** (0.1–0.3 reads/session); the inline signature/first sentence is what reaches the agent.
- **Page-capture files are read heavily** (9–19 reads of `.rf/state/latest/` per session) → high value.
- Guards (suite, install, `-P`, big read) and REPL rewrites rarely fire (agents seldom use the REPL; no tampering attempts).
- Sessions with ≥ 1 gate denial passed 0.47 vs 0.69 (confounded); Stop gate never blocked.

## Verdict
v2 is a net improvement mainly because it **fixes OpenCode** (0.20 → 0.53; explore 0.22 → 0.56 — deep-link/context/output fixes), with exploration overall +0.15. For **Claude** (main target) v2 brings no pass-rate gain but costs **+48%** ($0.54 vs $0.37) and +49% wall time — the extra per-edit context and frequent SLOW re-checks are overhead there. Not significant at n=3 per cell; same-arm run-to-run variance is of similar size.

## Suggested v3 tuning
1. Timeout policy: 2.5 s is too aggressive for real sites (≈45% SLOW) → start at ~5 s, adapt per page (after one SLOW on a page, skip the short timeout there), keep re-check.
2. Keep v2's OpenCode fixes (compact output with `NEXT:`, hidden same-origin hrefs, fresh browser context per restart, async plugin).
3. Trim per-edit context for Claude (it reads `.rf/state` files itself): inline only failures + 1-line page summary.
4. Keep page capture (heavily used); keep kw-doc files but rely on the inline signature (files rarely pulled).
5. Re-run with more reps (or a second model tier) before concluding — noise is comparable to the effects.
