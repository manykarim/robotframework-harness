# A/B round 2 (live sites): rf-mcp (MCP) vs Agent Skill + local package — 2026-10-03

Data `harness/results_live.jsonl` (135 cells, HARNESS_VERSION rc-3-journey), report `harness/report_live.txt` + `harness/summary_live.json`, pilot `harness/results_live_pilot.jsonl` / `report_live_pilot.txt`, references `harness/verify_live_journey.{log,json}`.

## Design
- Arms: `neither` (venv: robot, Browser, Requests, robotcode), `mcp` (+ rf-mcp 0.36.0 local stdio), `skillpkg` (+ skill + `rfmcp` helper + post-edit hooks [robocop agent profile + robotcode errors], no MCP). Skill improved blind before this round (debug + explore guides, `state controls`, NOT_VISIBLE/COVERED probes, portable-suite check) — features rf-mcp lacks (content confound).
- Agents/models: Claude Code claude-haiku-4-5, Codex gpt-5.6-luna@medium, OpenCode MiniMax-M2.5. Copilot gpt-4.1 excluded (GitHub rate limit within minutes; all pilot cells invalid).
- Scenarios (live): EXPLORE `tricentis_quote` (Automobile quote → Platinum 509.00 → "Sending e-mail success!"), `carconfig_order` (German configurator, Luxury X5 + 6 options → 82.400,00 € → bank-transfer checkout → "Bestellung erfolgreich!" + #CO- order no.), `demoshop_order` (demo login → 2× Horizon Portable Display + 1× Cascade Water Bottle → $857.00 → checkout with given data → tax $59.99, total $916.99 → `Order ORD-… confirmed!`); DEBUG `demoshop_debug` (5 tests, 4 planted test bugs), `tricentis_debug` (3 truck tests, 4 planted bugs incl. past start date).
- Graders: robot_pass live (1 retry), expected values, anti-cheat (debug: test set unchanged, assertions kept, no TRY/Ignore Error/Skip…), **journey evidence from the grading run's TRACE output.xml**: confirmation + data-dependent value read from the page by a passing Browser keyword, minimum distinct input fields driven + all given data entered, no deep links / JS navigation / hard-coded assertion targets. References 3/3; negative controls (6) caught.
- 3 reps × 3 arms × 5 scenarios × 3 agents = 135 sessions, 80-turn cap, ≤ 3 concurrent browsers. Ops: Claude OAuth expiry invalidated 25 Claude cells → dropped and re-run (0 auth failures in final data); two external SIGTERMs (runs resumed; final run under `systemd-run --user`); final data 135 unique, all status ok, 0 contaminated, 0 leak hits.

## Results — correctness
| arm | n | pass | 95% CI |
|---|---:|---:|---|
| neither | 45 | 0.53 | 0.39–0.67 |
| mcp | 45 | **0.44** | 0.31–0.59 |
| skillpkg | 45 | **0.60** | 0.45–0.73 |

| contrast | all Δ (Fisher p) | headroom Δ (p) | cells +/− (sign p) |
|---|---|---|---|
| mcp−neither | −0.09 (0.53) | +0.03 (1.00) | 3/6 |
| skillpkg−neither | +0.07 (0.67) | +0.21 (0.14) | 7/4 all; 7/1 headroom (0.07) |
| skillpkg−mcp | **+0.16 (0.21)** | +0.18 (0.22) | **9/3 (0.15)** |

By kind:
| kind | neither | mcp | skillpkg | skillpkg−mcp |
|---|---|---|---|---|
| explore (3 journeys, n=27/arm) | 0.59 | 0.52 | 0.59 | +0.07 (p=0.79) |
| debug (2 suites, n=18/arm) | 0.44 | 0.33 | **0.61** | **+0.28 (p=0.18, 4/0 cells)** |

By agent: Claude 0.33 / 0.20 / **0.47**; Codex 0.87 / 0.80 / 0.80 (near ceiling); OpenCode 0.40 / 0.33 / **0.53** (neither / mcp / skillpkg).

## Results — efficiency (means per session)
| agent | neither | mcp | skillpkg |
|---|---|---|---|
| Claude wall / cost | 749 s / $0.660 | 640 s / $0.674 | **415 s / $0.557** |
| Codex wall / tool calls | 433 s / 35 | 424 s / 39 | **366 s** / 47 |
| OpenCode wall | 1317 s | 826 s | **725 s** |

## Engagement — does the helper replace execute_step?
- rf-mcp tools used in 23/45 MCP-arm sessions (Claude 9/15, Codex 3/15, OpenCode 11/15; execute_step×803, get_session_state×130, visual_check×44); in **debug only 1/18** sessions used rf-mcp (agents re-ran `robot`).
- Helper used in 44/45 skillpkg sessions (step×1128, state×554, run×136); debug 16/18. Hooks fired 5–17× per session.
- Explore stepwise: mcp 30.9 steps + 4.8 inspections/session; skillpkg 29.5 steps + **15.3 inspections**; pass with rf-mcp stepping 0.45 (n=20) vs without 0.71 (n=7) — stepping did not convert into success (confounded).
- Debug: skillpkg sessions using the helper passed 0.69 (n=16) vs 0.00 (n=2) — the repair workflow (results → reproduce with `rfmcp run --lines` → `state` → fix) is where the helper adds value.
- Journey completeness (robot green but journey incomplete): carconfig mcp 4 of 7 green suites (e.g. order number never read; suites rendered by build_test_suite), skillpkg 3 of 8, neither 0 of 7; demoshop_order skillpkg 3 of 9 green suites missed fields, neither 2 + 2 shortcuts.
- Frequent failure everywhere: `tricentis_debug` start date replaced by a new hard-coded date (neither 7, mcp 7, skillpkg 5 sessions).

## Verdict
Across 135 live sessions with strict full-journey grading, the skill + local package arm had the **highest pass rate (0.60 vs 0.44 rf-mcp vs 0.53 baseline)** and was **fastest/cheapest**, but no contrast reaches p<0.05 at n=3 per cell. The clearest signal is **debugging existing suites** (0.61 vs 0.33), where rf-mcp's tools were essentially unused and the helper's repair workflow was used in 16/18 sessions. For **exploratory full journeys all arms are equal** (0.52–0.59): neither execute_step nor the helper improved completion over a plain agent + `robot`; the helper is a functional replacement for execute_step (similar stepping volume, 3× more page inspection) but stepwise execution alone did not drive success. Combined with round 1 (file-authoring tasks: mcp 0.97, skillpkg 0.92, neither 0.83), there is no evidence that dropping the MCP server costs quality; the new design is cheaper and at least as good. Caveats: content confound (skill has better guidance + probes), weak models only, Copilot missing, live-site variability, small n.
