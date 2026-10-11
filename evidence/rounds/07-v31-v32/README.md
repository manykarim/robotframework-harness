# Round 7: v3.1 per-model output profiles, cheap OpenRouter models, Haiku 5.5, and v3.2 (2026-10-10)

The README headline ("83% vs 69% across six agent/model combinations, 206 sessions") comes from this round.

**Question.** Does v3.1 (v3 plus a per-agent/model output profile: `lean` for Claude and GPT models, `rich` for
open-weight models) beat rf-mcp across strong and cheap models in one time window? Does v3.2 fix the v3.1
failures?

**Runs** (all in the same window, 2026-10-10 04:37–13:33 UTC, same live scenarios and journey graders as round 6):

| results file | agents / models | arms | reps | valid rows |
|---|---|---|---|---|
| `results/results_live_v31sub.jsonl` | Claude Code 2.1.296 + claude-haiku-5-5 · Codex + gpt-5.6-luna@medium · OpenCode + MiniMax-M2.5 | mcp, hookpkg3, hookpkg31 | 3 | 135/135 |
| `results/results_live_v31or.jsonl` | Claude Code via OpenRouter + DeepSeek V4.1 Flash, Qwen 3.8 Flash, GLM 5.3 Flash | mcp, hookpkg3, hookpkg31 | rep 1 complete, rep 2 partial | 71/135 (64 removed after the credit exhaustion) |
| `results/results_live_v31gem.jsonl` | Claude Code via OpenRouter + Gemini 3.8 Flash | mcp, hookpkg31 | stopped after 10 of 20 cells | 10 (+1 aborted row in the file) |
| `results/results_live_v32.jsonl` | Codex (complete), Qwen 3.8 Flash (partial) | hookpkg31, hookpkg32 | 3 | 39 |
| `results/results_live_v32smoke.jsonl` | Qwen 3.8 Flash, tricentis_quote | hookpkg32 | 1 | 1 (PASS 12/12) |

Harness `rc-3-journey`, 80-turn cap, 30-minute timeout; runner `run_ab_resilient.sh` (commands in
`logs/run_ab_*.log` and `../../REPRODUCE.md`). Packages: `../../harness-versions/hookpkg31/`, `hookpkg32/`;
build reports `hookpkg31_build_findings.md`, `hookpkg32_build_findings.md`.

**Result (pooled over v31sub + v31or, 206 valid sessions).**

| arm | pass | 95% CI |
|---|---|---|
| rf-mcp 0.36.0 | 47/68 = 0.69 | 0.57–0.79 |
| v3 | 51/68 = 0.75 | 0.64–0.84 |
| v3.1 | 58/70 = **0.83** | 0.72–0.90 |

- v3.1 vs rf-mcp: +0.14, Fisher p = 0.073; better in 7 agent × scenario cells, worse in 2 (sign test p = 0.18).
- Strong models are near the ceiling with either delivery: Claude + Haiku 5.5 0.93 = 0.93, Codex 0.87 = 0.87.
- The gains are with cheaper models: OpenCode/MiniMax 0.27 → 0.53, Qwen 3.8 Flash 0.38 → 0.88, GLM 0.71 → 0.88.
- The harness also cut wall time: Codex 405 s → 199 s; OpenCode 1,237 s → 436 s, with 7 → 0 timeouts.
- v3.1 vs v3.2, same window: Codex 14/15 vs **15/15**; Qwen (partial) 4/4 vs 4/5.

`../../claims.yaml` recomputes all of these from the files here (`python3 evidence/check_claims.py`).

**Excluded and not-scored rows** (`excluded/`, each with `reason`, `detail` and the backup it came from):

| file | rows | why |
|---|---|---|
| `excluded_credits_402.jsonl` | 76 (64 v31or + 12 v32 Qwen) | The OpenRouter **account** balance ran out around 12:00 local ($455.17 of $455). Claude Code records the HTTP 402 as a normal turn, so these rows were first written as `ok`. They were detected by the transcript scan for `API Error: 402` / `requires more credits` and removed. Backups: `backups/*.credits402.jsonl`. |
| `excluded_codex_backend_outage.jsonl` | 1 | Codex backend request failed (transport channel to the backend closed after 3 tool calls). The cell was re-run. Backup: `backups/*.codexinfra.jsonl`. |
| `excluded_aborted.jsonl` | 1 | v32 Codex cell aborted when the runner was restarted at 13:10; re-run |
| `excluded_contaminated.jsonl` | 1 (in file) | `codex|mcp|tricentis_debug|1`: helper-CLI marker in the mcp arm. **The published reports and pooled numbers keep it** (n = 68 for rf-mcp). Dropping it gives 46/67 = 0.687, which still rounds to 0.69 (claim `r7-rfmcp-drop-contaminated`). |
| `excluded_not_ok_in_file.jsonl` | 1 (in file) | the aborted Gemini row in `results_live_v31gem.jsonl` (run stopped) |

**Known grader artifact.** Four v31sub cells (mcp 1, v3 2, v3.1 1) and one rf-mcp cell in round 6 fail only
because the suite asserts the order total as a regex (`\$916\.99`), while the file-content grader looks for the
literal `916.99`. The data is not corrected. Adjusted v31sub rates would be rf-mcp 0.71, v3 0.76, v3.1 0.80. The
artifact hits all arms about equally and changes no conclusion.

**Files.**

| path | content |
|---|---|
| `findings_v31.md` | findings report (its `harness/<file>` references are now `results/` and `reports/`) |
| `results/` | the five results files, OpenRouter budget baselines (`*.or_budget.json`), price cache `or_prices.json` |
| `reports/` | `report_live_v31sub.txt`, `report_live_v31or.txt`, `report_live_v32.txt` + summaries, reproduced byte-identically by the archived analyzer. There is no report for the stopped Gemini run or the single smoke cell. |
| `scenarios.json` | prompts, graders, fixture and reference hashes of the 5 live scenarios |
| `excluded/`, `backups/` | excluded rows and the original result files they were removed from |
| `logs/` | runner logs (`run_ab_*.log`: start/stop/resume/drops; `run_live_*.log`: per-cell lines) |
| `build-verification/hookpkg31/`, `hookpkg32/` | simulation suites and their recorded results (v3.2: 221/224) |
| `config.json`, `checksums.sha256` | run configuration (agents, models, reps, dates), checksums |

Transcripts: release asset `evidence-transcripts-07-v31-v32.tar.zst`, 335 transcripts, each mapped to a row
(255 scored, 78 excluded, 2 not scored).

**Limits.** 3 reps per cell (2 or fewer for the OpenRouter models); live sites can change between runs; one
grader artifact. Only same-window comparisons are valid (see `../../REPRODUCE.md`).

**Reproduce.** `../../REPRODUCE.md#07-round-7`.

## Errata

- `findings_v31.md` (Data section) says the contaminated cell `codex|mcp|tricentis_debug|1` "is excluded by the
  analyzer". That is wrong: the analyzer reports it as contaminated but keeps it in the pass rates, so the published
  numbers (206 sessions, rf-mcp 47/68, Codex rf-mcp wall 405 s) include it. Dropping it changes no conclusion
  (rf-mcp 46/67 = 0.687, Codex rf-mcp wall 402 s); see claim `r7-rfmcp-drop-contaminated`. The findings file is kept
  byte-identical to the research original; this note is the correction.

