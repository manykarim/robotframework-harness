# Round 3 — robotcode LSP as validator + file-based step execution (2026-10-01)

Source: lsp_quality subagent report (saved by the coordinating session). Evidence: scripts, `results/*.json` (key numbers `results/summary.json`), `logs/`, test projects `proj/`, `proj2/`. Round-2 files and `src/` unchanged. Note: four orphaned robotcode multiprocessing workers from the sibling agent_lsp runs were left running (not this agent's).

## 1. Detection (33 planted errors, 15 valid controls)
| | LSP | analyze (R1) | in-process analyzer | dryrun (R1) |
|---|---|---|---|---|
| caught | 28 | 28 | 28 | 30 |
| FPs on valid | 3 | 3 | 3 | 0 |
| codes identical to analyze | **48/48** | – | **48/48** | – |

Same engine; all static routes miss: POST without url, library init args, enum, int, duplicate test. Noise comes only from robocop (default: 158 diagnostics over 45 files — DOC02/DOC03/SPC03/LEN09…, warnings/info); robotcode itself reports no hints/unused by default. Mute: project `robocop.toml` `[tool.robocop.lint] select=["ERR*"]`, or LS `robotcode.robocop.enabled=false` via `initializationOptions`. LS honours `robot.toml [tool.robotcode-analyze.modifiers]` (e.g. `warning=["VariableNotFound"]`).

## 2. LSP latency / memory (Browser + Requests + resource)
| | stock LS | 50 ms-poll launcher (`ls_fastpoll.py`) |
|---|---|---|
| spawn→initialized | 0.93 s | 1.04 s |
| open→first diagnostics, no library cache | **5.05 s** | – |
| open→first diagnostics, warm cache | 0.08 s | 0.09 s |
| one-line change→diagnostics (n=30) | **median 1.31 s, p90 1.68 s** | **median 74 ms, p90 100 ms** |
| RSS | 74–92 MB | 74 MB |

Stock delay = robotcode's 1 s idle poll in the diagnostics loop; monkeypatched cap → ~17× faster, 30/30 correct. Client gotchas: full-text `didChange` without `range` rejected (server uses INCREMENTAL sync — why R1 saw nothing in change mode); pull diagnostics (`textDocument/diagnostic`) is a stub returning `[]` — only push carries results. `analyze code` silently skips files under `.rf/` (`files: 0`, exit 0); LS and in-process analyzer check them.

## 3. False positives in a growing `.rf/live.robot`
| Probe | Static | Fix |
|---|---|---|
| `${x}=` earlier, VAR scope=TEST/SUITE, BDD prefixes, embedded-arg resource kws, `${resp.json()}[0][id]`, keywords defined in live file | clean | – |
| `Set Test/Suite Variable ${x}` (flagged on both lines) or `\${x}` | FP | write `VAR` (robocop DEPR05 agrees) or helper live filter |
| var set by a resource keyword / VAR inside a called keyword | FP | live filter |
| var only via `-v` | FP | LS `robot.variables`, robot.toml, or helper variables |
| in-body `Set Library Search Order` Browser+Selenium (`Get Text`) | FP (MultipleKeywords) | `global-library-search-order`, qualified name, live filter |
| `Get Variable Value ${maybe}` / `Variable Should Exist` | FP | inline `# robotcode: ignore[VariableNotFound]` |

Gotchas: an `ignore[...]` comment on its own line hides every following line until `reset` (hid a real typo); global VariableNotFound ignore hides real undefined vars; a running LS never reloads a helper-written variable file (even with `didChangeWatchedFiles` + watcher registration) — restart only.

## 4. Other LSP features
| Feature | Result |
|---|---|
| hover | full libdoc in 3–6 ms (Fill Text 1.3 KB, POST On Session 1.0 KB); undocumented resource kw → name only |
| signatureHelp | typed params + active param, 1–8.5 KB; RequestsLibrary only `*args, **kwargs` |
| completion at `Cli\|` | 341 unfiltered items, 180 KB (R1: 600 KB without lazy docs); only 2 match |
| workspace/symbol | project keywords only, no library keywords |
| definition | resource line or library `.py` |

Claude Code's LSP tool has no diagnostics/completion/signatureHelp operations.

## 5. File-based step execution (`filestep_daemon.py`, `filestep.py`)
Design: agent writes RF lines with its own Write/Edit; runs `python3 -S .rf/filestep.py run .rf/live.robot --new|--lines A-B|--all` or `check`. Only `{op, path, mode, lines}` crosses the socket (`raw_requests.log`: no RF syntax through the shell). Helper:
- parses with RF's parser into test-body items with line ranges; executed items tracked by content hash (survive line shifts — adding Variables section + import moved every line, no false "changed");
- copies the file's imports/Variables/Keywords into a hidden generated resource with **identical line numbers**, re-imports on change;
- checks with an in-process copy of the `analyze code` engine, then filters each item's diagnostics against the **live** session right before running it (variable exists now, keyword resolves now);
- runs items one by one, stops at first failure, reports file line numbers.

Scenarios: saucedemo login/cart and restful-booker flows passed; all 5 dynamic-variable FPs dropped by the live filter (with reasons); static blocks before execution with line numbers (`Clik` L35, `${usrname}` L36, missing arg L37); after an Edit, `--new` re-ran only the fixed line; runtime failure (missing element) reported at L39.
Edge cases: FOR/WHILE/IF split over two edits is blocked until `END`, then runs as one item (`L32-34 FOR`); editing an already-run line → "already-executed lines changed, first_changed_line 32" (`--lines` re-runs explicitly, `rebase` accepts); keywords added to the live file work, edited bodies re-imported; typos inside live-file keywords reported as `file_diags` without blocking the step.

Latency (100-line file, n=20): `fast.py step 'Get Title'` 47 ms; `filestep run --new` **85 ms** (in helper: parse 7 + resource 6 + check 16 = 38 ms); `--no-check` 66 ms; `check` only 50 ms. In-process check ~0.1 ms/line (5 ms @47 lines, 46 ms @467, 165 ms @1,517); first check ~170 ms warm library cache, 2.6–5 s cold; analyzer adds ~7.5 MB.

## Risks / open questions
1. A finished live file is not automatically a consistent suite: replay with `robotcode robot` failed (earlier assertion stale after editing `Live Helper`) → final full replay mandatory; mark earlier lines stale when a keyword body changes.
2. Stop slows to ~2 s after an uncached library load (robotcode multiprocessing `resource_tracker` ignores SIGTERM) → SIGKILL at stop, or pre-warm the analyzer in a background thread at start.
3. Undocumented internals (`CodeAnalyzer`/`DocumentsCacheHelper`, INCREMENTAL sync, stub pull, 1 s poll monkeypatch) → pin `robotcode>=2.7,<2.8`.
4. Scripts importing the analyzer need `if __name__ == "__main__"` (robotcode loads libraries in spawned processes).
5. Not yet handled: test setup/teardown, `[Template]`, re-running side-effecting lines via `--lines`, partial side effects of a failed step; whether agent harnesses can pass LSP settings (robocop on/off, variables) untested.
6. Hint text: failure owner shows `.kwtypo.live` (generated resource name); hint should point at the faulty keyword line (`failed_in`/`file_diags`), not the calling line.
