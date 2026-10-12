# Evidence archive

Every number this project publishes comes from the data in this folder. It covers every experiment round of the
rf-mcp research that led to the harness: raw per-session results, graders, reports, the harness versions under
test, the evaluation harness, excluded sessions with their reasons, and incident notes. Anyone can check,
recompute and challenge the claims.

**Source.** rf-mcp branch `research/robotcode-remote-mcp`, commit `7994ae3` (`experiments/robotcode-remote/**`
and `docs/research/static-analysis-quality-gates.md`), plus files from the research worktree that were never
committed: result-file backups, runner logs and one fixture. Details in [PROVENANCE.md](PROVENANCE.md).

## Verify in one minute

```bash
python3 evidence/checksums.py --verify               # archived files match checksums.sha256 (also: sha256sum -c)
python3 evidence/scrub.py --check evidence --exclude _release_assets   # no keys, tokens, e-mails or home paths
python3 evidence/check_claims.py --check-sources     # every published number recomputed from the results
python3 evidence/check_claims.py --reports           # archived analyzer regenerates the archived reports
```

All four use only the Python standard library (3.10+; `--reports` needs 3.12+, because `sum()` switched to
compensated float summation in 3.12 and the research ran on 3.12/3.13). CI runs them on every change to `evidence/` and
`README.md` (`.github/workflows/evidence.yml`).

## Rounds

Rounds are numbered as in the research. The two early A/B rounds ran between rounds 3 and 4 and carry their own
names in the findings ("A/B round 1", "A/B round 2"), so they are `03a` and `03b`. Round 8 is the v1 release gate.

| folder | dates | what was tested | agents / models | sessions | key result |
|---|---|---|---|---|---|
| [01-capability-spikes](rounds/01-capability-spikes/) | 2026-10-01 | robotcode as backend: remote MCP limits, hints, stepwise sessions, static validation, locators | none (scripted) | – | hints portable (32/33), analyze + dryrun catch 32/33 planted errors, 24–81 ms per step |
| [02-local-runtime](rounds/02-local-runtime/) | 2026-10-01 | embedded helper, stock REPL, local keyword docs, agent shell channel | Claude Code, Codex, OpenCode, Copilot CLI | 34 | repl-server not needed; the helper works in all four agents with `setsid` |
| [03-lsp-robocop](rounds/03-lsp-robocop/) | 2026-10-01 | robotcode LSP in agents, LSP as validator, Robocop 9.1 | same | 32 | LSP feedback only after a shim; Robocop agent profile catches 26/33 |
| [03a-ab-file-authoring](rounds/03a-ab-file-authoring/) | 2026-10-01 | A/B 1: rf-mcp vs skill + local package, 4 hard authoring scenarios | Haiku 4.5, gpt-5.6-luna, MiniMax-M2.5 | 180 | mcp 0.97, skillpkg 0.92, neither 0.83 (n.s.) |
| [03b-ab-live-journeys](rounds/03b-ab-live-journeys/) | 2026-10-02 | A/B 2: same arms on 5 live journeys (explore + debug) | same | 135 | skillpkg 0.60, neither 0.53, mcp 0.44 |
| [04-hooks-matrix-and-hooks-ab](rounds/04-hooks-matrix-and-hooks-ab/) | 2026-10-08 | hook capability matrix; hooks (hookpkg) vs CLI (skillpkg) | same | 90 | hooks 0.58 vs CLI 0.56; Claude +0.33, OpenCode −0.33 |
| [05-v2](rounds/05-v2/) | 2026-10-08/09 | REPL/debugger research; hookpkg v1 vs v2 | same | 90 | v2 0.60 vs v1 0.51; fixes OpenCode, costs Claude +48% |
| [06-v3-main](rounds/06-v3-main/) | 2026-10-09 | diagnosis; same-day rf-mcp vs v2 vs v3 | same | 180 | v2 0.70, v3 0.63, rf-mcp 0.52; v2 > rf-mcp in 8/0 cells (p = 0.008) |
| [07-v31-v32](rounds/07-v31-v32/) | 2026-10-10 | v3.1 per-model profiles vs v3 vs rf-mcp, OpenRouter models, Haiku 5.5; v3.1 vs v3.2 | Haiku 5.5, gpt-5.6-luna, MiniMax-M2.5, DeepSeek V4.1 / Qwen 3.8 / GLM 5.3 Flash (+ stopped Gemini) | 206 valid + 40 v3.2 + 10 Gemini | **v3.1 0.83 vs rf-mcp 0.69** (206 sessions); Qwen 0.38 → 0.88 |
| [08-release-gate-v1](rounds/08-release-gate-v1/) | 2026-10-11 | release gate: rf-harness (product 0.9.0, own installer) vs the v3.2 prototype; real-session checks per agent | Haiku 5.5, gpt-5.6-luna, MiniMax-M2.5 (+ Copilot CLI check) | 90 + 5 | **0.82 vs 0.82**, gate PASS; OpenCode 345 s vs 492 s |
| [static-analysis](rounds/static-analysis/) | 2026-10-02 | Robocop + robotcode analyze as quality gates for rf-mcp | none (scripted) | – | agent-profile Robocop + analyze + dryrun catch 32/33 |

Every A/B round folder has the same layout:

| path | content |
|---|---|
| `README.md` | what was tested, design, result, exclusions, files |
| `findings*.md` | the original findings report (its `harness/<file>` paths now point to `results/` and `reports/`) |
| `results/` | raw per-session result rows (`results_*.jsonl`, one JSON object per session) |
| `reports/` | analyzer output (`report_*.txt`, `summary_*.json`) |
| `scenarios.json` | scenario prompts, grader definitions, fixture and reference-solution hashes |
| `config.json` | agents, models, arms, scenarios, reps, harness version, dates, recorded agent versions, excluded counts |
| `excluded/` | `excluded_<reason>.jsonl`: each row with `reason`, `detail`, the backup it came from and whether it is still in the results file |
| `backups/` | the original result files the excluded rows were removed from |
| `logs/` | runner logs |
| `build-verification/` | build checks of the harness version introduced in the round |
| `checksums.sha256` | sha256 of every file in the folder (`sha256sum -c checksums.sha256`) |

Other folders:
- [`harness-versions/`](harness-versions/): source snapshots of the research prototypes (`skillpkg`, `hookpkg`
  v1, `hookpkg2`, `hookpkg3`, `hookpkg31`, `hookpkg32`), code only.
- [`eval-snapshots/ab-7994ae3/`](eval-snapshots/ab-7994ae3/): the evaluation harness, analyzers, runners and
  scenario fixtures (with hidden references and negative controls) as committed at the end of the research.
- [`upstream/`](upstream/): summary of the earlier robotcode CLI study (findings only, by owner decision).
- [`incidents.md`](incidents.md): expired logins, SIGTERMs, credit exhaustion, the Codex outage, grader
  artifacts, stopped runs, disk pressure.
- [`claims.yaml`](claims.yaml): index of published claims.
- [`transcripts/`](transcripts/): manifests of the transcript release assets.
- `.gitignore` re-includes `results/`, `output.xml`, `log.html`, `report.html` and `site/`, which the root
  `.gitignore` hides elsewhere. `.gitattributes` turns off end-of-line conversion, so checksums hold on every
  platform.

## Reading a result row

One line per session. The fields you need most:
- identity: `key` = `agent|arm|scenario|rep`, plus `agent`, `arm`, `scenario`, `rep`, `model`;
- validity: `status` (`ok` or `aborted`) and `contaminated`;
- outcome: `primary_pass` (all graders passed), `verdicts` (each grader with `passed` and `detail`),
  `n_checks` / `n_pass`;
- `metrics`: `wall_s`, `turns`, `tool_calls`, tokens, `cost_usd`, `timed_out`;
- `stepwise`: live-step counts;
- per-arm engagement, e.g. `hookpkg31`: hook firings, verdict classes, context characters per edit, profile;
- `transcript`: path of the session transcript inside the release asset.

The analyzers score rows with `status == "ok"` and keep the last ok row per `key`. Pass rate = mean of
`primary_pass`. Contaminated rows are kept unless `--drop-contaminated` is given; the published reports keep them
(see `claims.yaml`, `r7-rfmcp-drop-contaminated`).

## Claims

[`claims.yaml`](claims.yaml) lists every number in the README (and the main findings numbers the docs use). For
each claim it records the round, the result files, how to recompute it (metric, filter, contamination policy),
the expected values and tolerances, and the quoted source text. It is written in the JSON-compatible subset of YAML
(full-line `#` comments, the rest is JSON), so `check_claims.py` needs no YAML library.

```bash
python3 evidence/check_claims.py --only readme-pooled-harness --show
# ok   readme-pooled-harness: harness (v3.1) pooled pass rate 0.83 (83%) on live journeys  -> {'value': 0.8286, 'passes': 58, 'n': 70}
```

When a number in `README.md` or `docs/` changes, change or add its claim in the same commit.
`check_claims.py --check-sources` fails when a quoted claim text is no longer in its source file.

## Transcripts (release assets)

The session transcripts (about 130 MB gzip in the research tree) are too large for git. They are published as
GitHub release assets, one per A/B round. Each was scrubbed with the same `scrub.py`, packed decompressed, and
compressed with zstd:

| asset | transcripts | size |
|---|---|---|
| `evidence-transcripts-03a-ab-file-authoring.tar.zst` | 226 | 2.0 MB |
| `evidence-transcripts-03b-ab-live-journeys.tar.zst` | 214 | 24.7 MB |
| `evidence-transcripts-04-hooks-matrix-and-hooks-ab.tar.zst` | 93 | 11.7 MB |
| `evidence-transcripts-05-v2.tar.zst` | 92 | 8.2 MB |
| `evidence-transcripts-06-v3-main.tar.zst` | 197 | 12.7 MB |
| `evidence-transcripts-07-v31-v32.tar.zst` | 335 | 25.8 MB |

The committed manifest `transcripts/<round>.manifest.json` lists, for every transcript:
- its path in the asset, sha256 and size;
- the transcript path the result row refers to;
- the results file and row `key`;
- the row status: `scored`, `not_scored_in_results_file`, `excluded:<reason>`, or `unreferenced` (one
  re-run smoke cell in 03a);
- the scrub substitutions.

`transcripts/assets.json` holds each asset's sha256.

```bash
mkdir -p evidence/_release_assets
gh release download <tag> --repo manykarim/robotframework-harness --pattern 'evidence-transcripts-*' \
    --dir evidence/_release_assets            # once the assets are published (task 8.2)
python3 evidence/verify_assets.py --require    # asset sha256, every member's sha256, every transcript -> one row
```

`verify_assets.py` needs the `zstd` CLI (or Python 3.14+) for `.tar.zst`. To rebuild the assets from the research
tree, run `python3 evidence/pack_transcripts.py --transcripts <research ab/harness dir>`. They are written to
`evidence/_release_assets/` (git-ignored); nothing is uploaded.

## Limits: read before quoting a number

- **Small samples.** 3–5 reps per agent × arm × scenario cell. Most single contrasts are not significant at
  p < 0.05. The strongest are round 6 (v2 > rf-mcp in 8 of 8 non-tied cells, sign test p = 0.008) and round 7
  pooled (Fisher p = 0.073). Same-arm run-to-run noise between rounds is about ±0.07–0.13.
- **Live sites.** The journeys run against public websites that change. Only same-window comparisons are valid,
  and every round's arms were interleaved in one window ([REPRODUCE.md](REPRODUCE.md)).
- **Grader artifacts.** The `\$916\.99` regex case hits 4 round-7 cells and 1 round-6 cell, in all arms. It is
  not corrected; adjusted rates are in `incidents.md`.
- **Exclusions.** 76 round-7 sessions were removed after the OpenRouter credit exhaustion. The OpenRouter half of
  round 7 is therefore partial: rep 1 complete, rep 2 partial.
- **Content confounds.** The prototypes' skills contained better guidance than rf-mcp's in some rounds (noted in
  the findings). The comparison is "harness as built" vs "rf-mcp 0.36.0", not delivery mechanism alone.
- **Weak and cheap models by design.** The models were chosen to leave headroom (Haiku, MiniMax, Flash models).
  Strong models were near the ceiling with either delivery in round 7.
- **Only the final harness code survives.** Earlier rounds ran earlier harness revisions. The archived reports of
  the early rounds regenerate identically except for one data-quality line that the later analyzer splits
  (turn caps vs agent errors).
- **Uncommitted raw outputs.** About 46 MB of spike outputs, plus about 300 MB of agent run directories from rounds
  1–5, were never committed upstream and are not in this archive (PROVENANCE.md).

## Scrub

`scrub.py` removes or redacts:
- provider keys and tokens (OpenRouter, Anthropic, OpenAI, GitHub, Slack, AWS, Google, bearer tokens, JWTs);
- OAuth fields and private keys;
- the literal values of secret environment variables;
- e-mail addresses outside the allowlist (the author's public addresses and fixture or demo-site domains);
- agent home directories and authentication files.

It also normalizes absolute home paths to `~`. It ran on every file during import and on every transcript during
packing, and it re-checks the scrubbed transcript content before an asset is built. Import substitutions:
`scrub_report.json` (counts only). Transcript substitutions: in each manifest.
