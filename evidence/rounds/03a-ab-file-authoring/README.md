# A/B round 1: file authoring, rf-mcp vs Agent Skill + local package (2026-10-01)

**Question.** On hard "write a test and make it pass" tasks, does replacing the rf-mcp MCP server with an Agent
Skill plus a local robotcode-based helper (`skillpkg`: `rfmcp` CLI, skill, post-edit hooks) cost correctness?

**Design.**

| | |
|---|---|
| arms | `neither` (robot, Browser, Requests, robotcode only) · `mcp` (rf-mcp 0.36.0, local stdio) · `skillpkg` (no MCP) |
| agents / models | Claude Code 2.1.286 + claude-haiku-4-5 · Codex + gpt-5.6-luna@medium · OpenCode + MiniMax-M2.5 (weak models, for headroom). Copilot CLI was not run (GitHub rate limit, HTTP 429). |
| scenarios | 4 hard file-authoring scenarios: `iframe`, `apinested`, `results_complex`, `browser_dynamic`. Prompts and graders are verbatim from the earlier rf-mcp eval#3/#4. |
| reps | 5 per agent × arm × scenario (180 sessions) + pilot (36) + smoke (9) |
| harness | `rc-1` (rows' `harness_version`); code snapshot `../../eval-snapshots/ab-7994ae3/harness/` |
| grading | primary pass = all graders (file exists, required library, expected values, `robot` passes, no deprecated keywords) |
| window | 2026-10-01, 19:26–21:35 UTC |

**Result.** neither 0.83, rf-mcp **0.97**, skillpkg **0.92** (n = 60 each). skillpkg vs mcp: −0.05 (Fisher
p = 0.44), equal in 10 of 12 cells. skillpkg was cheaper and faster for Claude Code and OpenCode, and slower for
Codex. Equivalence is not proven: 5 reps per cell, 6 of 12 cells at the ceiling in every arm.

**Excluded rows.** None. One smoke-test transcript has no result row (a re-run smoke cell); it is listed as
`unreferenced` in the transcript manifest.

**Files.**

| path | content |
|---|---|
| `findings.md` | findings report |
| `results/results_rc.jsonl` | 180 scored sessions (main run) |
| `results/results_rc_pilot.jsonl`, `results/results_rc_smoke.jsonl` | pilot and smoke runs |
| `reports/report_rc.txt`, `reports/summary_rc.json` | analyzer output (`analyze.py`) |
| `scenarios.json` | scenario prompts, graders, fixture and reference hashes |
| `build-verification/skillpkg/` | the skillpkg build checks (agent runs summary, hook verification) |
| `logs/` | runner logs (`run_rc.log`, `pilot_rc.log`) |
| `config.json`, `checksums.sha256` | run configuration, checksums |

The findings refer to `harness/<file>`: results are now in `results/`, reports in `reports/`. Transcripts:
release asset `evidence-transcripts-03a-ab-file-authoring.tar.zst` (see `../../README.md`).

**Reproduce.** `../../REPRODUCE.md#03a-ab-round-1`.
