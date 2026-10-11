# Round 8: v1 release gate (2026-10-11)

**Question.** Does the product (`rf-harness`, release candidate 0.9.0, installed through its own installer) perform at
least as well as the measured research prototype v3.2 (`hookpkg32`) in the same time window?

**Design.**
- Arms: `prototype-v32` (baseline) vs `rf-harness` (candidate).
- Agents: Claude Code + Haiku 5.5, Codex (gpt-5.6-luna), OpenCode + MiniMax-M2.5.
- Scenarios: the five live journeys of round 7 (graders identical; `eval/harness.py check-scenarios` reports
  IDENTICAL).
- 3 reps, 90 cells, all run between 07:18 and 11:20 UTC.
- Runner: self-healing; 0 restarts, 0 invalid, 0 contaminated cells.
- Qwen 3.8 Flash (OpenRouter) was planned but not run: the OpenRouter account balance was exhausted (see round 7
  incidents).

## Result: gate PASS

| agent | rf-harness | prototype-v32 | wall s (rf-harness / prototype) |
|---|---|---|---|
| Claude Code (main agent) | 15/15 | 15/15 | 282 / 268 |
| Codex | 14/15 | 14/15 | 204 / 218 |
| OpenCode | 8/15 | 8/15 | 345 / 492 |
| **all** | **37/45 = 0.82** | **37/45 = 0.82** | |

- **Non-inferiority (Claude, margin 0.05):** Δ = +0.00 → PASS.
- **Per agent:** no significant regression. Every Fisher p = 1.0.
- **Efficiency:** OpenCode is 30% faster with the product (345 s vs 492 s) and makes fewer tool calls (43.8 vs 50.1).
  Codex is slightly faster. Claude's cost is $0.027 vs $0.030.
- **Failures are task-semantics misses in both arms**, not harness defects:
  - OpenCode deep-link shortcuts on demoshop_order;
  - a start date not computed at run time on tricentis_debug;
  - one Codex debug repair that stayed red.

  `reports/gate1_gate.md` has the per-scenario table, `reports/report_live_gate1.txt` the full analyzer output.

## Real-session checks per agent (qs1, qs2)

| agent | version | result |
|---|---|---|
| Claude Code | 2.1.296 | 12/12 on tricentis_quote, 258 s |
| Codex | 0.162.1 | 12/12, 110 s |
| OpenCode | 1.15.12 | 12/12, 119 s |
| Copilot CLI | 1.0.91 | qs1: 12/12, but 0 hook events (the folder was not trusted); qs2 with the folder trusted: 12/12, 83 hook events |

The qs1 Copilot cell led to the `trusted_folders` doctor check and the eval-side trust simulation. qs1 also showed false
contamination flags: the product's `.rf/hook` folder has the same name as the legacy v1 prototype's state folder. The
evaluation harness now treats it as the arm's own path. Neither issue affected the gate run.

## Files

| path | content |
|---|---|
| `results/results_live_gate1.jsonl` | 90 gate sessions |
| `results/results_live_qs1.jsonl`, `results_live_qs2.jsonl` | real-session checks |
| `reports/gate1_gate.md`, `gate1_gate.json` | release-gate verdict (`eval/gate.py`) |
| `reports/report_live_gate1.txt`, `summary_live_gate1.json` | analyzer report (`eval/analyze_hooks.py`) |
| `logs/` | runner and harness logs |
| `config.json` | agents, models, versions, dates |

Reproduce: `eval/run_ab_resilient.sh gate1 prototype-v32,rf-harness 3 claude,codex,opencode live --claude-model
claude-haiku-5-5 --browser-concurrency 2` (with `AB_VENV_BIN` pointing at a dedicated grading venv), then
`python3 eval/gate.py <results> --candidate rf-harness --baseline prototype-v32 --main-agent claude`.
