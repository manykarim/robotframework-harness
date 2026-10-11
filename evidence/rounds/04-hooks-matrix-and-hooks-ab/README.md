# Round 4: hook capability matrix + A/B hooks vs CLI (2026-10-08)

**Questions.**
1. Which agent hooks does each CLI support headless: session-start context, prompt context, pre-tool
   deny/rewrite, post-tool context, a blocking stop gate, session end, timeouts, crashed hooks?
2. Can hooks replace the agent-facing CLI? This round compares `hookpkg` (Agent Skill + hooks only, live
   execution of edited test lines in a post-tool hook) with `skillpkg` (the `rfmcp` CLI from the earlier rounds).

**Hook matrix** (`hooks_matrix/findings.md`). Claude Code 2.1.289, Codex 0.161.0, Copilot CLI 1.0.91 (only
`--model auto` was available), OpenCode 1.15.12. The skills + hooks design works in all four. Claude Code and Codex
support every part natively. Copilot CLI supports everything except a usable SessionEnd. OpenCode has no blocking
Stop hook (a plugin workaround passed headless). VS Code was assessed from its docs only.

**A/B design.**

| | |
|---|---|
| arms | `skillpkg` (CLI) · `hookpkg` (hooks, no CLI); package `../../harness-versions/hookpkg/`, build report `hookpkg_build_findings.md` |
| agents / models | Claude Code 2.1.289 + claude-haiku-4-5 · Codex + gpt-5.6-luna@medium · OpenCode + MiniMax-M2.5 |
| scenarios | the 5 live scenarios of A/B round 2 (references re-verified 2026-10-08) |
| reps | 3 (90 sessions), 80-turn cap |
| harness | `rc-3-journey`, runner `run_hooks_ab.sh` |
| window | 2026-10-08, 14:38–18:42 UTC |

**Result.** skillpkg 0.56, hookpkg **0.58** (n = 45 each; +0.02, Fisher p = 1.0). The effect depends on the agent:
Claude Code +0.33, Codex +0.07, OpenCode −0.33. With hooks, sessions needed fewer turns, cost less and produced
more suites that were green on the first grader attempt (explore 23/27 vs 16/27). Not significant at 3 reps.

**Excluded rows.** `excluded/excluded_aborted.jsonl` (3): an external SIGTERM stopped the run at 19:52 local
with 83/90 recorded. The 3 aborted rows were dropped and the remaining 7 cells resumed. Backups in `backups/`.

**Correction found by this archive.** The findings say "10 Claude rows report an agent-side error (to
investigate)". The final analyzer separates turn-cap rows from agent errors: the same rows are 9 skillpkg and
1 hookpkg sessions that hit the 80-turn cap (`check_claims.py --reports`).

**Files.** `findings_hooks.md`, `hookpkg_build_findings.md`, `hooks_matrix/` (probes, configs incl.
`codex_pretrust_hooks.py`, `results_summary.json`, the agents' hook docs as fetched, trust probes),
`results/results_live_hooks.jsonl`, `reports/`, `excluded/`, `backups/`, `logs/`, `build-verification/hookpkg/`,
`scenarios.json`, `config.json`, `checksums.sha256`. The hook matrix run directories (`hooks_matrix/runs/`,
about 39 MB) were not committed upstream. Transcripts: release asset
`evidence-transcripts-04-hooks-matrix-and-hooks-ab.tar.zst`.

**Reproduce.** `../../REPRODUCE.md#04-round-4`.
