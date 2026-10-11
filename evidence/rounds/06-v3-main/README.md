# Round 6: diagnosis + same-day A/B rf-mcp vs v2 vs v3 (2026-10-09)

**Diagnosis** (`diag/findings.md`). Why did v2 cost Claude more? Not wait time: misleading verdicts, and a live
run that no longer matched the plain run. 110 of 111 SLOW verdicts were misclassified: the element was present,
and the click was intercepted by a styled `<span>`. The scripts (`parse_claude.py`, `episodes.py`, `reactions.py`,
`rechecks_all.py`, `composition.py`, `opencode_sessions.py`) and their outputs are in `diag/`.

**A/B design.**

| | |
|---|---|
| arms | `mcp` (rf-mcp 0.36.0) · `hookpkg2` (v2) · `hookpkg3` (v3: Playwright-log failure classes before any re-check, adaptive timeouts, captures only on failure, lean context budgets, warnings instead of denials); build report `hookpkg3_build_findings.md` |
| agents / models | Claude Code 2.1.295/2.1.296 + claude-haiku-4-5 · Codex + gpt-5.6-luna@medium · OpenCode + MiniMax-M2.5 |
| scenarios | the 5 live scenarios |
| reps | 4 (180 sessions, interleaved), 80-turn cap; pilot: v3 only, 15 sessions (`results_live_v3pilot.jsonl`, 8/15) |
| harness | `rc-3-journey`; runner `run_ab_resilient.sh v3main mcp,hookpkg2,hookpkg3 4` under systemd (`Restart=always`) |
| window | 2026-10-09, 13:37–22:31 UTC: one window, all arms |

**Result.**

| arm | pass (n = 60) |
|---|---|
| rf-mcp | 0.52 |
| v2 | **0.70** |
| v3 | 0.63 |

- v2 − rf-mcp: +0.18 (Fisher p = 0.061); better in 8 cells, worse in 0 (sign test p = 0.008).
- v3 − rf-mcp: +0.12; 9/2 cells (p = 0.065).
- For Claude Code (the main target), v3 was best: 0.65 vs 0.30 with rf-mcp, at $0.34 vs $0.63 per session.

**Excluded rows.** `excluded/excluded_aborted.jsonl` (2): an external kill around 19:45 local. systemd restarted
the runner, the 2 aborted rows were dropped, and the run completed at 00:31 without intervention. Backup in
`backups/`. Final: 180 unique rows, all ok, 0 auth failures, 0 contaminated, 0 leaks, 5 timeouts.

**Files.** `findings_v3main.md`, `hookpkg3_build_findings.md`, `diag/`, `results/`, `reports/` (reproduced
byte-identically by the archived analyzer), `excluded/`, `backups/`, `logs/`, `build-verification/hookpkg3/`,
`scenarios.json`, `config.json`, `checksums.sha256`. Transcripts: release asset
`evidence-transcripts-06-v3-main.tar.zst`.

**Reproduce.** `../../REPRODUCE.md#06-round-6`.
