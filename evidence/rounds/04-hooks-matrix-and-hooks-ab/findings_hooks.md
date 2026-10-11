# Round 4 A/B: hookpkg (Agent Skill + hooks, no CLI) vs skillpkg (rfmcp CLI) — live scenarios (2026-10-08)

Data `harness/results_live_hooks.jsonl` (90 cells), report `harness/report_live_hooks.txt` (+ `summary_live_hooks.json`), analysis script `harness/analyze_hooks.py`, runner `harness/run_hooks_ab.sh`. Same 5 live scenarios, journey-evidence graders and models as round 2 (claude-haiku-4-5, codex gpt-5.6-luna@medium, opencode MiniMax-M2.5), 3 reps, 80-turn cap. References re-verified 2026-10-08 (tricentis_debug passed on retry once). Ops: an external SIGTERM stopped the systemd unit at 19:52 (83/90 recorded; 3 aborted rows dropped; remaining 7 resumed). Final: 90 unique, all ok, 0 auth failures, 0 contaminated, 0 leaks, 1 timeout; 10 Claude rows report an agent-side error (to investigate).

## Results
| | skillpkg (CLI) | hookpkg (hooks) |
|---|---|---|
| **pass, all (n=45)** | 0.56 (0.41–0.69) | **0.58** (0.43–0.71) |
| explore / debug | 0.56 / 0.56 | 0.56 / **0.61** |
| Claude / Codex / OpenCode | 0.20 / 0.80 / **0.67** | **0.53** / **0.87** / 0.33 |
| robot passes on first grader attempt (explore / debug) | 16/27, 12/18 | **23/27, 17/18** |
| turns — Claude / OpenCode | 72 / 85 | **45 / 55** |
| debug turns (all agents) | 73 | **31** |
| Claude cost / wall | $0.544 / 434 s | **$0.427 / 351 s** |
| wall — Codex / OpenCode | 276 / 539 s | **267 / 453 s** |

hookpkg−skillpkg: +0.02 overall (Fisher p=1.0; cells 6/4). Per agent: Claude **+0.33** (p=0.13), Codex +0.07, OpenCode **−0.33** (p=0.14; explore 0.22 vs 0.78).

## Hook engagement (means per hookpkg session)
| agent | pass | firings | auto-executed lines | non-pass auto lines | gate denials | Stop blocks | robot reproductions | .rf/state reads | .rf/docs reads |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| claude | 0.53 | 47.7 | 109.7 | 12.2 | 1.1 | 0 | 1.0 | 14.9 | 0.7 |
| codex | 0.87 | 47.5 | 64.1 | 7.9 | 0.0 | 0 | 1.6 | 8.8 | 3.1 |
| opencode | 0.33 | 55.9 | 137.3 | 15.9 | 1.6 | 0 | 1.8 | 18.1 | 2.1 |
- 0 `rfmcp` CLI calls in the hook arm; Stop gate never needed (agents ran `robot` themselves).
- Sessions with ≥1 gate denial passed 0.39 (n=18) vs 0.70 (n=27) without (confounded).
- Sessions with a robot-run reproduction passed 0.64 vs 0.50.
- Agents rarely grep `.rf/docs` (0.7–3.1 reads/session) but read `.rf/state` often (9–18).

## Verdict
Hooks can replace the CLI with equal overall correctness and fewer turns, lower cost and more first-attempt-green suites; the effect is agent-dependent: strongly positive for Claude Code (the main target), neutral-positive for Codex, negative for OpenCode/MiniMax (to investigate: plugin output mutation, deny-by-throw, appended context handling). n=3 per cell — not significant.
