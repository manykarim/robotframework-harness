# hookpkg2 — improved skills+hooks RF harness (build report, 2026-10-08)

Source: hookpkg2 builder subagent report (saved by the coordinating session). Package `ab/hookpkg2/` (`rfharness2`, installed side by side with v1 `rfharness`; v1 untouched). Research inputs: `round5/research/findings.md`. Blind protocol kept (no fixtures/target sites).

## Changes vs v1 (owner items)
1. **Failed keyword → docs file**: live failures (incl. deepest failing keyword inside a user keyword), `robot` runs and REPL/debug output write `.rf/docs/kw/<Owner>.<Keyword>.md`; hook output = path + one-line signature + first doc sentence. Cut from a cached robotcode-libdoc spec in 3–4 ms; cache miss → detached `robotcode libdoc <target> show "<Kw>"` (~1.2 s), hook waits ≤ 1.2 s.
2. **Page capture**: after page-changing Browser/Selenium keywords (also nested) and locator failures → `.rf/state/latest/{page.txt, controls.txt, aria.yaml, source.html, screenshot.jpg}`; history `step-NNN-<kw>/` (hard links, last 15) + `history.tsv`; hash dedup with short settle after clicks; ARIA `mode=ai` on Browser ≥ 20.5 else per-iframe sections; output = file list with sizes + 1–3 line summary.
3. **Short timeouts**: live session element keywords 2.5 s; navigation/`Wait*` (and nested) keep normal timeout; timeout → one re-check against the normal timeout from the last page change → SLOW (line re-run + explicit-wait advice) or MISSING (iframe probe + similar controls). Agent-run REPLs get the same via a listener in `ROBOT_OPTIONS` (nothing typed → `.save` can't leak it).
4. **Import → docs**: Library/Resource imports in edits and REPL bodies → `.rf/docs/<Name>.md` + `.full.md`, mentioned once per name.
5. **REPL/debugger format**: 40 research rules (vendored linter); auto-add `--plain --no-history -d .rf/out 2>&1`, quote heredoc when safe, fold `...` lines, strip quotes from dot-commands, append `.exit` (REPL only); deny interactive REPL for Claude/OpenCode, unclosed blocks, `*** Keywords ***` in REPL input, `repl-server`; ≤ 1 KB format card once; PostToolUse parses `[ FAIL ]` and `* exception`. Deviation: unquoted heredoc auto-quoted when every `$` is an RF `${` (denied when shell `$VARS` present).
6. **Guards**: loop hint after the same step fails 3×; suite guard vs session-start baseline (deny removed tests / fewer assertions / new failure-hiding keywords; warn on weakened operators or changed expected values); new `Sleep` refused once; pip/playwright installs denied (third attempt replaced by `echo`); `robot -P`/PYTHONPATH and reading large output.xml/source denied; UserPromptSubmit short project context; root-cause denials (missing `*** Keywords ***` header); restarted test gets a fresh browser context; probe-only edits don't restart.
7. **OpenCode**: async plugin (spawn, not spawnSync), guidance prepended, compact output ≤ ~1.2 KB ending with `NEXT:`, allow-with-warning after 2 denials, no screenshot reads, session note delivered on first prompt.
8. **SKILL.md** rewritten (5,127 B).

## Files
New `rfharness2/`: `replfmt` (557), `guards` (286), `kwdoc` (243), `docsgen` (184), `livetmo` (199), `rfh2_repl_listener` (201), `data/` (research rules, keyword-name cache). Grown: `hook.py` 663→1358, `execd.py` 598→961, `pagestate.py` 240→440, `install.py` 276→311. `verify/`: `verify_hooks.py` (725), `agents_run.py` (374), `simlib.py` (223), `harness_smoke.py`, `summarize_runs.py`, `runs/*.json`, `results_hooks.json`. Harness: `harness.py` +127 diff lines (arm `hookpkg2` in ARM_SPEC/HOOK_ARMS, not in default arms; `row["hookpkg2"]` metrics; v1/v2 cross-contamination markers), `analyze_hooks.py` +69 (`--arms`, default output byte-identical), "turn cap" label for Claude `error_max_turns` rows.

## Latencies
PreToolUse warm median 104–136 ms wall (≤ 13 ms in-hook); first call ≤ 1.65 s (lint daemon cold); page capture median 158–162 ms (max 315 ms); kw docs 3–4 ms cached; SessionEnd 0.3–0.4 s.

## Verification
Simulation 159/159. Real headless sessions (8; all plain robot green, 0 rfmcp calls, 0 orphans, credentials deleted):
| Agent | Task | Time | What reached the model |
|---|---|---|---|
| Claude haiku-4-5 | journey + repair | 109 s | live results; 13 captures |
| Claude | journey | 88 s | MISSING recheck ×2, kw docs |
| Claude | REPL | – | interactive REPL denied + card, then canonical heredocs; rewrites |
| Codex luna@low | web | 107 s | 31 live lines, 1 MISSING recheck |
| Codex | REPL | – | interactive REPL allowed (types into stdin) + rewritten |
| OpenCode M2.5 | web ×2 | 177–188 s | after compact fix: recheck/docs/`NEXT:` visible |
| OpenCode M2.5 | REPL | – | deny + card, `[rfh2]` ×18 |
| OpenCode M2.7 | web | 188 s | 8 kw docs |
| Copilot `--model auto` | web | 137 s | 2 MISSING rechecks visible |

## Known gaps
SLOW verdicts, loop hints, guard denials fired only in simulation (real agents added waits themselves); Codex/Copilot transcripts don't show hook text (delivery inferred); Codex typed-into interactive REPL fires no PostToolUse; untested live: Selenium paths, Browser 20.5 `mode=ai` (A/B venv has Browser 19.12.7), docs for keywords defined inside a `.robot` file; screenshots JPEG (research found PNG smaller on text pages); a recheck right after a page change can still cost up to the normal 10 s; live runs capture ≤ 6 pages each; click steps add ~0.4 s settle. Left: docs cache `~/.cache/rfharness2` (~1 MB).

## A/B commands
```
cd ab/harness
python3 harness.py check-scenarios
python3 harness.py run --scenarios live --reps 3 --arms hookpkg,hookpkg2 --agents claude,codex,opencode --max-turns 80 --browser-concurrency 3 --tag v2
python3 analyze_hooks.py results_live_v2.jsonl --arms hookpkg,hookpkg2 --out report_live_v2.txt --json summary_live_v2.json
```
