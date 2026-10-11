# Round 5: REPL/debugger hook research + A/B hookpkg v1 vs v2 (2026-10-08 – 2026-10-09)

**Research** (`research/findings.md`, 2026-10-08). The REPL and `robot-debug` input format: about 95 REPL cases
were verified live on RF 7.5 and robotcode 2.7, giving 40 format rules (`research/repl_format_rules.json`), a
linter (34/34) and 15 rewritten commands. Also covered: live-timeout behaviour (`research/timeouts/`), page
capture (`research/capture/`), keyword-doc generation (`research/docs/`, 15 failure-rule regexes), and a survey of
hook ideas (`research/hooks_survey/`).

**A/B design.**

| | |
|---|---|
| arms | `hookpkg` (v1) · `hookpkg2` (v2: failing-keyword docs, per-step page capture, short live timeouts with a slow-vs-missing re-check, REPL format enforcement, guards, loop hints); build report `hookpkg2_build_findings.md` |
| agents / models | Claude Code 2.1.295 + claude-haiku-4-5 · Codex + gpt-5.6-luna@medium · OpenCode + MiniMax-M2.5 |
| scenarios | the 5 live scenarios |
| reps | 3 (90 sessions), 80-turn cap |
| harness | `rc-3-journey`, runner `run_v2_ab.sh`, analysis `analyze_hooks.py --arms hookpkg,hookpkg2` |
| window | 2026-10-08 21:07 UTC – 2026-10-09 08:01 UTC (interrupted overnight, see below) |

**Result.** v1 0.51, v2 **0.60** (n = 45 each; +0.09, Fisher p = 0.53). v2 fixed OpenCode (0.20 → 0.53), but for
Claude Code it cost +48% ($0.54 vs $0.37) and +49% wall time with no pass-rate gain. About 45% of the short-timeout
re-checks were SLOW verdicts. Same-arm run-to-run variance (v1 here 0.51 vs 0.58 in round 4) is as large as the
effects.

**Excluded rows.** `excluded/excluded_aborted.jsonl` (2): an external SIGTERM at 01:49 local (64/90 recorded).
The 2 aborted rows were dropped and 28 cells resumed 08:23–10:01. Backups in `backups/`.

**Files.** `findings_v2.md`, `hookpkg2_build_findings.md`, `research/`, `results/results_live_v2.jsonl`,
`reports/` (reproduced byte-identically by the archived analyzer), `excluded/`, `backups/`, `logs/`,
`build-verification/hookpkg2/`, `scenarios.json`, `config.json`, `checksums.sha256`. Uncommitted research
outputs (about 15 MB of timeout runs, captures and repl-format runs) are not archived. Transcripts: release asset
`evidence-transcripts-05-v2.tar.zst`.

**Reproduce.** `../../REPRODUCE.md#05-round-5`.
