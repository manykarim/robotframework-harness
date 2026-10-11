# Evidence

The harness came out of seven experiment rounds (2026-10-01 to 2026-10-10); round 8 (2026-10-11) is the v1 release gate. All data, graders, reports and harness
versions are in the repository's [`evidence/`](https://github.com/manykarim/robotframework-ai-engineering/tree/main/evidence)
folder. `evidence/check_claims.py` recomputes every number on this page from the archived results.

## Headline results

| round | comparison (same window) | sessions | result |
|---|---|---|---|
| 8 | release gate: **rf-harness** (product 0.9.0) vs v3.2 prototype; Haiku 5.5, Codex, OpenCode/MiniMax | 90 | **0.82 vs 0.82** (Claude 15/15 each; gate PASS; OpenCode 345 s vs 492 s) |
| 7 | rf-mcp vs v3 vs **v3.1** (per-model output profiles); Haiku 5.5, Codex, OpenCode/MiniMax, DeepSeek/Qwen/GLM via OpenRouter | 206 valid | **0.69 / 0.75 / 0.83** (v3.1 vs rf-mcp p = 0.073; 7 cells better, 2 worse) |
| 7 | v3.1 vs **v3.2** (covered-input targets, read-streak nudge), Codex | 30 | 14/15 vs **15/15** (n.s.) |
| 6 | rf-mcp vs v2 vs v3, Claude (Haiku 4.5) / Codex / OpenCode | 180 | 0.52 / **0.70** / 0.63 (v2 > rf-mcp in 8 of 8 differing cells, sign p = 0.008) |
| 5 | hooks v1 vs v2 | 90 | 0.51 vs 0.60 |
| 4 | hooks (v1) vs helper CLI | 90 | 0.58 vs 0.56; Claude 0.53 vs 0.20 |
| A/B 2 | no tools vs rf-mcp vs skill + helper CLI, live journeys | 135 | 0.53 / 0.44 / 0.60 |
| A/B 1 | same arms, file-authoring tasks | 180 | 0.83 / 0.97 / 0.92 |

### Round 7 per model

| agent / model | rf-mcp | v3 | v3.1 |
|---|---|---|---|
| Claude Code + Haiku 5.5 | 0.93 | 0.80 | 0.93 |
| Codex (gpt-5.6-luna) | 0.87 | 0.87 | 0.87 |
| OpenCode + MiniMax-M2.5 | 0.27 | 0.47 | 0.53 |
| DeepSeek V4.1 Flash | 1.00 | 1.00 | 1.00 |
| GLM 5.3 Flash | 0.71 | 0.75 | 0.88 |
| Qwen 3.8 Flash | 0.38 | 0.75 | 0.88 |

### Efficiency (round 7)

- Codex wall time: 405 s with rf-mcp, 199 s with v3.1.
- OpenCode: 1,237 s → 436 s, and 7 → 0 timeouts.
- DeepSeek estimated cost per session: $0.21 → $0.05.

## What the evidence does and does not show

- **Strong models tie.** Claude Haiku 5.5 and Codex are near the ceiling with either rf-mcp or the harness. For them
  the harness's value is speed, cost and local execution.
- **Weaker and cheaper models gain the most:** Qwen +0.50, OpenCode/MiniMax +0.27, GLM +0.17.
- **Sample sizes are small:** 3 reps per cell. Several differences are not statistically significant; the tables give
  the tests.
- **Live sites drift.** Only comparisons from the same time window are valid.
- **Known grader artifacts are documented.** A regex-escaped total (`916\.99`) failed a literal-text check in four
  sessions across all arms. Adjusted rates are in the round-7 folder, and the conclusions do not change.
- **Excluded sessions are kept, with reasons**: expired logins, exhausted provider credits, backend outages, aborted
  cells. See `evidence/incidents.md`.

## Verify

```bash
python3 evidence/checksums.py --verify
python3 evidence/check_claims.py --check-sources
python3 evidence/check_claims.py --reports        # Python 3.12+
```

Transcripts (85 MB, scrubbed) are release assets; `evidence/verify_assets.py` checks them against their manifests.
Reproduction steps are in `evidence/REPRODUCE.md`.
