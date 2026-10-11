# Incidents

Everything that went wrong during the research runs and how it was handled. Rows removed from a results file
are not deleted: they are kept in `rounds/<NN>/excluded/excluded_<reason>.jsonl`, each with its `reason`,
`detail` and the backup file it came from, and the backups themselves are in `rounds/<NN>/backups/`. Local times
are CEST (UTC+2).

## Summary

| # | date | round | incident | sessions affected | handling |
|---|---|---|---|---|---|
| 1 | 2026-10-01/02 | A/B 1, A/B 2 | Copilot CLI rate limit (HTTP 429) | all Copilot pilot cells | Copilot excluded from both rounds |
| 2 | 2026-10-02 | A/B 2 | Claude Code OAuth login expired | 25 Claude cells | dropped and re-run (`excluded_auth_expiry.jsonl`) |
| 3 | 2026-10-02 … 10-10 | A/B 2, 4, 5, 6 | external SIGTERMs / kills of the runner | 2 + 3 + 2 + 2 aborted cells | aborted rows dropped on resume and re-run (`excluded_aborted.jsonl`) |
| 4 | 2026-10-10 ~12:00 | 7 | OpenRouter account credits exhausted (HTTP 402) | 76 cells (64 v31or + 12 v32 Qwen) | rows removed, backups kept (`excluded_credits_402.jsonl`) |
| 5 | 2026-10-10 | 7 | Codex backend outage | 1 Codex cell | re-run (`excluded_codex_backend_outage.jsonl`) |
| 6 | 2026-10-10 | 6, 7 | grader artifact `\$916\.99` | 4 v31sub + 1 v3main cells | not corrected; adjusted rates reported |
| 7 | 2026-10-10 | 7 | Gemini 3.8 Flash run stopped | 10 of 20 cells run | stopped to save money; 10 rows kept, 1 aborted row in the file |
| 8 | 2026-10-10 | 7 | contaminated cell | 1 rf-mcp Codex cell | kept in the published reports; sensitivity check in `claims.yaml` |
| 9 | 2026-10-01 … 10-10 | all A/B | disk 91–98% full | none lost | cell dirs pruned after each cell; per-cell workspaces not preserved |
| 10 | 2026-10-08 | 4 | "agent-side error" rows were turn-cap rows | 10 Claude cells | reclassified by the final analyzer; no data change |

## 1. Copilot CLI rate limit

The GitHub Copilot CLI with `gpt-4.1` hit the GitHub rate limit (HTTP 429) within minutes in the A/B round 1
smoke and the A/B round 2 pilot. All Copilot pilot cells were invalid. Copilot was excluded from both rounds:
`results_live_pilot_nocopilot.jsonl` is the pilot without the Copilot rows, and its report is
`report_live_pilot.txt`. In round 4, Copilot CLI 1.0.91 only offered `--model auto`, so it took part in the hook
matrix but not in any A/B.

## 2. Claude Code OAuth expiry (A/B round 2)

The subscription login of Claude Code expired during the 2026-10-02 run. The affected sessions report
"Failed to authenticate". `rerun_auth_failures.sh` (in `eval-snapshots/ab-7994ae3/harness/`) dropped the 25 Claude
cells and re-ran them (log `rounds/03b-ab-live-journeys/logs/rerun_auth_failures.log`). The final data has 0
auth failures.
- Rows: `rounds/03b-ab-live-journeys/excluded/excluded_auth_expiry.jsonl`.
- Backup: `backups/results_live.before_auth_rerun.20261002175305.jsonl`.

From round 6 on, `run_ab_resilient.sh` checks Claude auth before every start and drops "Failed to authenticate"
rows automatically.

## 3. External SIGTERMs

The runner was killed from outside several times. The harness marks running cells `aborted`, and a restart
drops those rows (with a backup) and resumes the missing cells.

| round | when | recorded at the kill | aborted rows | backup |
|---|---|---|---|---|
| A/B 2 | 2026-10-02, two kills | – | 2 | `results_live.before_resume2.20261002215104.jsonl` |
| 4 | 2026-10-08 19:52 | 83/90 | 3 | `results_live_hooks.before_resume.201919.jsonl` |
| 5 | 2026-10-09 01:49 | 64/90 | 2 | `results_live_v2.before_resume.082318.jsonl` |
| 6 | 2026-10-09 ~19:45 | 78/180 | 2 | `results_live_v3main.bak.20261009-194618.jsonl` |
| 7 (v32) | 2026-10-10 13:10 (deliberate restart after the 402 cleanup) | 22/30 Codex | 1 | `results_live_v32.bak.20261010-131143.jsonl` |

The final A/B round 2 run used `systemd-run --user`, and round 6 ran under systemd with `Restart=always`. All
aborted rows are in `excluded_aborted.jsonl` of their round. The `*.pass1.bak.jsonl` backups of rounds 4 and 5
are identical to the final files.

## 4. OpenRouter credit exhaustion (round 7)

From about 12:00 local on 2026-10-10, every OpenRouter request returned HTTP 402 ("requires more credits … can
only afford 27,823 tokens").
- **Cause.** The **account** balance was used up ($455.17 spent of $455). The key had used only $32.28 of its $250
  limit, so the key limit is not the only limit.
- **Why the runner missed it.** Claude Code records the 402 as a normal `result:success` turn. The runner checked
  only stderr and agent_info, so 64 v31or cells and 12 v32 Qwen cells were written as `ok`. Some were cut off
  mid-session after 48–60 tool calls.
- **Detection rule.** `run_ab_resilient.sh` (`clean()`) scans the transcript of every OpenRouter row for
  `API Error: 402`, `requires more credits`, `API Error: 401` or `Insufficient credits`, and drops those rows.
- **Prevention.** `or_ok` checks the account balance (`/credits` endpoint) and refuses to start below $0.50
  (`AB_MIN_OR_BALANCE`).
- **Rows.** `rounds/07-v31-v32/excluded/excluded_credits_402.jsonl` (76).
- **Backups.** `rounds/07-v31-v32/backups/results_live_v31or.bak.20261010-131135.credits402.jsonl` and
  `results_live_v32.bak.20261010-131136.credits402.jsonl`.

Also, the budget guard compares account-wide usage against a per-run baseline, so parallel OpenRouter runs
consumed each other's budgets. The new evaluation harness requires per-run budgets (design D10, task 5.2).

## 5. Codex backend outage (round 7)

`codex|hookpkg31|tricentis_debug|2` failed after 3 tool calls: the Codex transport channel to its backend closed.
This is an infrastructure failure, not an agent failure. The cell was re-run, and the re-run passed. The
original row is in `rounds/07-v31-v32/excluded/excluded_codex_backend_outage.jsonl`; backup
`results_live_v32.bak.20261010-132914.codexinfra.jsonl`.

## 6. Grader artifact `\$916\.99`

In `demoshop_order` the order total is $916.99. Some agents asserted it as a regular expression
(`Should Match Regexp … \$916\.99`). The file-content grader looks for the literal `916.99`, so these suites fail
a grader although the journey was correct.
- **Affected cells.** 4 in v31sub (mcp 1, v3 2, v3.1 1) and 1 rf-mcp cell in round 6.
- **Data.** Not corrected. The archive keeps the original verdicts.
- **Adjusted rates** (findings_v31.md): v31sub rf-mcp 0.71, v3 0.76, v3.1 0.80; Claude 1.00 / 0.93 / 1.00.
- **Impact.** The artifact hits all arms about equally and changes no conclusion. The evaluation harness port
  adds regex-tolerant value graders (task 5.2).

## 7. Gemini 3.8 Flash run stopped (round 7)

10 cells, **0/10** in both arms; 9 of 10 hit the 80-turn cap. About $2.40 of real spend per cell, against an
estimate of $1.0–3.8 (hidden reasoning tokens are not in the estimate). The run was stopped after 10 of 20 cells to
save about $25. `results_live_v31gem.jsonl` keeps the 10 rows plus the 1 aborted row of the stopped cell
(`excluded_not_ok_in_file.jsonl`). There is no report for this run.

## 8. Contaminated cell (round 7)

`codex|mcp|tricentis_debug|1` carries a helper-CLI marker in the rf-mcp arm. findings_v31.md says the analyzer
excludes it, but `analyze_hooks.py` drops contaminated rows only with `--drop-contaminated`. The published report
and the pooled numbers keep it (n = 68 for rf-mcp). Dropping it gives 46/67 = 0.687, still 0.69, and Codex rf-mcp
wall time becomes 402 s instead of 405 s. Both variants are checked in `claims.yaml`.

## 9. Disk pressure

The disk was 91–98% full during the A/B runs (the `disk before` lines in the `run_live_*.log` files show 7.6–16 GB
free of 234 GB). The harness refuses to start cells below 1.2 GB free and deletes every cell directory after
recording its row and gzipping the agent transcript (`PRUNE=True`). The logs show no cell lost to a full disk. As a
consequence, the per-cell workspaces, agent homes and hook logs were never kept: the evidence of a session is its
result row and its transcript.

## 10. Round-4 "agent-side errors" were turn caps

findings_hooks.md reports "10 Claude rows report an agent-side error (to investigate)". The final analyzer splits
turn-cap rows (`error_max_turns`) from agent errors. Re-running it on the archived round-4 data shows the 10 rows
are 9 skillpkg and 1 hookpkg sessions that hit the 80-turn cap (`check_claims.py --reports`). The same
reclassification applies to the A/B round 1 and 2 reports. No numbers change.
