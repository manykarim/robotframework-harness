# A/B round 2: live journeys, rf-mcp vs Agent Skill + local package vs plain agent (2026-10-02)

**Question.** On exploratory end-to-end journeys against live websites, and on debugging an existing failing
suite, where live execution should matter most, does the skill + local helper hold up against rf-mcp?

**Design.**

| | |
|---|---|
| arms | `neither` · `mcp` (rf-mcp 0.36.0) · `skillpkg` (skill improved blind before this round: debug and explore guides, `state controls`, NOT_VISIBLE/COVERED probes, portable-suite check) |
| agents / models | Claude Code 2.1.286/2.1.287 + claude-haiku-4-5 · Codex + gpt-5.6-luna@medium · OpenCode + MiniMax-M2.5. Copilot CLI + gpt-4.1 was excluded: GitHub rate limit within minutes, all pilot cells invalid (`results_live_pilot_nocopilot.jsonl` is the pilot without them). |
| scenarios | EXPLORE `tricentis_quote`, `carconfig_order`, `demoshop_order`; DEBUG `demoshop_debug`, `tricentis_debug` (live sites, business goals only, no locators) |
| reps | 3 per agent × arm × scenario (135 sessions), 80-turn cap, 30-minute timeout, at most 3 concurrent browsers |
| harness | `rc-3-journey` (pilot `rc-2`); journey-evidence graders read the grading run's TRACE `output.xml` |
| window | main run 2026-10-02, 09:51–22:00 UTC (pilot and smoke from 2026-10-01 23:41 UTC) |

**Result.** neither 0.53, rf-mcp **0.44**, skillpkg **0.60** (n = 45 each). skillpkg − mcp: +0.16 (Fisher
p = 0.21), better in 9 cells and worse in 3 (sign p = 0.15). The clearest signal was debugging existing suites:
skillpkg 0.61 vs rf-mcp 0.33, where the rf-mcp tools were barely used. On exploratory journeys all arms were
equal (0.52–0.59). No contrast reaches p < 0.05 at 3 reps per cell.

**Excluded rows (27, kept in `excluded/`).**
- `excluded_auth_expiry.jsonl` (25): the Claude Code OAuth login expired during the run. 25 Claude cells were
  dropped by `rerun_auth_failures.sh` and re-run. Backup: `backups/results_live.before_auth_rerun.*.jsonl`.
- `excluded_aborted.jsonl` (2): cells interrupted by an external SIGTERM, dropped on resume and re-run. Backup:
  `backups/results_live.before_resume2.*.jsonl`.

The final file has 135 unique rows, all `ok`, 0 contaminated, 0 leak hits. See `../../incidents.md`.

**Note on the archived report.** Re-running the final analyzer on `results_live.jsonl` reproduces
`reports/report_live.txt` except one data-quality line. The later analyzer splits Claude's turn-cap rows out of
"rows whose transcript reports an agent-side error" (`check_claims.py --reports`).

**Files.** `findings_live.md`; `results/` (main, pilot, pilot without Copilot, smoke); `reports/` (reports,
summaries, `verify_live*.json` = reference-solution verification incl. negative controls); `excluded/`,
`backups/`, `logs/`; `scenarios.json`; `config.json`; `checksums.sha256`. Transcripts: release asset
`evidence-transcripts-03b-ab-live-journeys.tar.zst`.

**Reproduce.** `../../REPRODUCE.md#03b-ab-round-2`.
