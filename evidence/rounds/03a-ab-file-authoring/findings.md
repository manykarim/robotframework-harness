# A/B: current rf-mcp (MCP) vs Agent Skill + local package (no MCP) — 2026-10-01

Harness `harness/harness.py` (ported from `rf-mcp/experiments/bundle-agent-skills-eval`), report `harness/report_rc.txt` + `harness/summary_rc.json`, rows `harness/results_rc.jsonl` (180), pilot `harness/results_rc_pilot.jsonl` (36), gz transcripts `harness/transcripts_rc*/`. Fixtures `fixtures/` (iframe + results_complex recovered byte-identical from old work dirs; apinested + browser_dynamic rebuilt to the same prompts/graders/answers; hidden references verified 5/5, 5/5, 7/7, 6/6; pristine fixtures fail). Treatment prototype `skillpkg/` (`rfmcp` CLI + `robotframework` skill + post-edit hooks; installed editable as `rfmcp-skill` in the worktree venv).

## Design
- Arms: `neither` (venv with robot/Browser/Requests/robotcode only), `mcp` (+ rf-mcp 0.36.0 local stdio, 19 tools), `skillpkg` (+ skill 4.5 KB + AGENTS.md/CLAUDE.md pointer + `rfmcp` helper + hooks: robocop agent profile + robotcode errors; no MCP).
- Agents/models (weak, for headroom): Claude Code `claude-haiku-4-5`, Codex `gpt-5.6-luna@medium`, OpenCode `MiniMax-M2.5`. Copilot CLI `gpt-4.1` NOT run (GitHub rate limit, 429).
- 4 hard scenarios (iframe, apinested, results_complex, browser_dynamic), prompts/graders identical to eval#3/#4, primary = all graders. 5 reps → 180 sessions; 0 timeouts, 0 contaminated, 0 leak-marker hits.
- Fairness edits before the run: fixture-overlapping example names removed from the skill (`*Checkout*`, Alice/Carol, login-inside-iframe example); `id=login-frame >>>` kept because rf-mcp's own guidance contains it.
- Known confound: the skill's generated guides correct three errors in rf-mcp's locator guidance (`Set Selector Prefix` needs `>>>`, `role=` works, `text=` is substring) + a NOT_FOUND frame hint. Did not produce a measurable edge (iframe: mcp 1.00 = skillpkg 1.00).

## Results — correctness
| arm | n | pass | 95% CI |
|---|---:|---:|---|
| neither | 60 | 0.83 | 0.72–0.91 |
| mcp | 60 | **0.97** | 0.89–0.99 |
| skillpkg | 60 | **0.92** | 0.82–0.96 |

| contrast | all Δ (Fisher p) | headroom Δ (p) | cells +/− |
|---|---|---|---|
| mcp−neither | +0.13 (0.029) | +0.27 (0.021) | 5/0 |
| skillpkg−neither | +0.08 (0.269) | +0.20 (0.125) | 5/2 |
| skillpkg−mcp | −0.05 (0.439) | −0.07 (0.671) | 0/2 |

Per cell, skillpkg = mcp in 10/12 cells. The two lower cells:
- claude × apinested: neither 0.60, mcp 0.60, skillpkg 0.20 — every failure in every arm is the same: test imports `Library OrdersServer` by name, agent sees `ModuleNotFoundError` under plain `robot`, then "fixes" it with `robot -P resources` / `PYTHONPATH=…` instead of `${CURDIR}/../resources/OrdersServer.py`; the grader runs plain `robot`. Not a helper false-green; 2/5 vs 3/5 is noise-level. Generic lesson for the skill/helper: "the suite must pass with plain `robot <file>`; import project libraries by path" (+ a `check` warning for name-imports that only resolve via -P).
- opencode × results_complex: skillpkg 0.80 — one rep miscounted pass/fail.

## Results — efficiency (means per session)
| agent | arm | pass | turns | tool calls | cost $ | wall s | notes |
|---|---|---:|---:|---:|---:|---:|---|
| claude | neither | 0.80 | 14.9 | 13.9 | 0.097 | 75 | |
| claude | mcp | 0.90 | 17.4 | 15.2 | 0.115 | 66 | |
| claude | skillpkg | 0.80 | 13.1 | 11.3 | **0.079** | **47** | −31% cost, −29% wall vs mcp |
| codex | neither | 0.95 | — | 7.4 | — | 57 | |
| codex | mcp | 1.00 | — | 7.0 | — | 55 | |
| codex | skillpkg | 1.00 | — | 13.5 | — | 74 | always starts the helper, even for results_complex |
| opencode | neither | 0.75 | 12.8 | 12.3 | — | 42 | |
| opencode | mcp | 1.00 | 18.2 | 17.8 | — | 79 | cache tokens 507k |
| opencode | skillpkg | 0.95 | **9.2** | 8.8 | — | **47** | cache tokens 113k (−78%) |

## Engagement
- MCP arm: Claude called rf-mcp in 11/20 sessions (find_keywords×68, execute_step×48); Codex 0/20 (probe proves it can — it chooses not to); OpenCode 5/20 (mostly iframe).
- skillpkg arm: helper used Claude 14/20, Codex 20/20, OpenCode 5/20 (skill read 13/20); hooks ~2 firings/session.
- **Much of both treatments' gain is passive context, not execution.** OpenCode browser_dynamic neither 0.20 → mcp 1.00 with 0 MCP calls in 4/5 passing sessions; every neither failure there was only the `Library Browser` grader (used another library despite the prompt). Skill text gives the same nudge.

## Verdict
On these hard "write a test and make it pass" tasks with weak models, replacing the MCP server with skill + local package shows **no significant correctness loss** (−0.05, p=0.44; ≥ mcp in 10/12 cells; both lower cells traced to failure modes shared with the other arms) and is **cheaper/faster for Claude Code and OpenCode**, more expensive for Codex. Equivalence is not proven (n=5/cell, 6/12 cells at ceiling in all arms).

## Gaps / next
- Copilot CLI (rate-limited) — run `python3 harness.py run --reps 5 --agents copilot` after reset.
- Scenarios are file-authoring tasks; no exploratory/stepwise task on an unknown live site and no "debug an existing failing suite" task — where live execution (helper vs execute_step) should matter most.
- neither baseline is higher than eval#3/#4 (0.83 vs ~0.25 headroom-restricted then) → less headroom; rebuilt fixtures may be slightly easier.
- Skill/helper improvements suggested by the data: portable-suite rule (plain `robot` must pass; path imports), Codex helper overuse (don't start the helper for output.xml analysis).
