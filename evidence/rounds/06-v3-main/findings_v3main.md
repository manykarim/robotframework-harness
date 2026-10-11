# Round 6 main experiment: rf-mcp vs hookpkg2 (v2) vs hookpkg3 (v3) — same day, live scenarios (2026-10-10)

Data `harness/results_live_v3main.jsonl` (180 cells: 3 arms × 3 agents × 5 scenarios × 4 reps, interleaved), report `harness/report_live_v3main.txt` (+ `summary_live_v3main.json`), runner `run_ab_resilient.sh v3main mcp,hookpkg2,hookpkg3 4` under systemd (`Restart=always`, `RestartPreventExitStatus=0 2`). Pilot (v3 only, 15 cells): `results_live_v3pilot.jsonl` 8/15. Ops: one external kill ≈ 19:45 → automatic restart, 2 aborted rows dropped, run completed 00:31 without intervention. Final: 180 unique, all ok, 0 auth failures, 0 contaminated, 0 leaks, 5 timeouts, turn-cap rows: claude/mcp 9, claude/hookpkg2 1.

## Correctness
| arm | n | pass | 95% CI |
|---|---:|---:|---|
| mcp (rf-mcp 0.36.0) | 60 | 0.52 | 0.39–0.64 |
| hookpkg2 (v2) | 60 | **0.70** | 0.57–0.80 |
| hookpkg3 (v3) | 60 | 0.63 | 0.51–0.74 |

| contrast | Δ (Fisher p) | cells +/− (sign p) |
|---|---|---|
| v2 − mcp | **+0.18** (0.061) | **8/0 (0.008)** |
| v3 − mcp | +0.12 (0.268) | 9/2 (0.065) |
| v3 − v2 | −0.07 (0.562) | – |

| agent | mcp | v2 | v3 |
|---|---|---|---|
| Claude (main target) | 0.30 | 0.60 | **0.65** |
| Codex | 0.80 | **0.95** | 0.85 |
| OpenCode | 0.45 | **0.55** | 0.40 |

| kind | mcp | v2 | v3 |
|---|---|---|---|
| explore (n=36/arm) | 0.53 | 0.69 | 0.61 |
| debug (n=24/arm) | 0.50 | 0.71 | 0.67 |

Per scenario (Δ vs mcp, v2 / v3): tricentis_quote +0.25 / +0.08; carconfig_order +0.25 / +0.33; demoshop_order 0.00 / −0.17; demoshop_debug +0.33 / +0.17; tricentis_debug +0.08 / +0.17.

## Efficiency (means per session)
| agent | mcp | v2 | v3 |
|---|---|---|---|
| Claude cost / wall / turns | $0.626 / 556 s / 68 | $0.396 / 364 s / 42 | **$0.336 / 314 s / 41** |
| Codex wall / tool calls | 362 s / 39 | 197 s / 25 | **195 s** / 27 |
| OpenCode wall / turns | 895 s / 97 | 606 s / 59 | **352 s / 46** |
| explore wall (all agents) | 501 s | 364 s | **227 s** |
| debug wall (all agents) | 760 s | 427 s | **377 s** |
v3 vs mcp: Claude cost −46%, wall −44%; OpenCode wall −61%. v3 vs v2: Claude cost −15%, OpenCode wall −42%.

## Engagement
- mcp arm: heavy stepping (Claude explore execute_step×441, OpenCode explore×496); Claude hit the 80-turn cap 9× in the mcp arm.
- v3 context ≈ 360 chars/edit (Claude 360, Codex 370, OpenCode 356) and 4.6–8.2k chars/session; **0 SLOW verdicts** (MISSING 59/30/57), failure classes dominated by absent / covered / value / ambiguous — the round-6 misclassification is gone. `.rf/state/latest` read 8–16×/session; kw-doc files rarely read.
- v2 still produced SLOW verdicts (Claude 61, OpenCode 67, Codex 23) alongside MISSING.

## Verdict
1. **Both hook harnesses beat current rf-mcp in the same time window**: v2 +0.18 (sign test 8/0 cells, p=0.008), v3 +0.12 (9/2, p=0.065) — and at roughly half the cost/time.
2. **v3 ≈ v2 on correctness** (−0.07, n.s.) and is the most efficient design; for **Claude Code (main target) v3 is best on both pass rate (0.65) and cost ($0.34)**.
3. **OpenCode/MiniMax prefers v2's richer output** (0.55 vs 0.40); Codex near ceiling either way.
4. Recommended next step: v3.1 = v3 + per-agent output profile (richer, v2-like context for OpenCode/MiniMax; v3 lean budgets for Claude/Codex), then confirm with more reps.
