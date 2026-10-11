# Round 3 — Robocop 9.1 as static analysis for agent-written RF (2026-10-01)

Source: robocop subagent report (saved by the coordinating session). Evidence: `scripts/`, `configs/` (incl. `robocop-agent.toml`, `claude_settings_hooks.json`, `opencode_robocop_plugin.ts`), `corpus1/` (round-1 copy), `corpus2/` (28 new cases), `noise_corpus/` (36 agent-written suites), `out/*.json`, `logs/`.

## 1. Detection on the round-1 corpus (33 planted errors, 15 valid controls)
| Error class | robocop default | robocop + project rules / agent profile | robotcode analyze | dryrun |
|---|---|---|---|---|
| keyword typo, single space, wrong `Lib.` prefix, missing import, wrong library (KW05) | no | yes | yes | yes |
| arg count: BuiltIn, Browser, Requests `Create Session`, user kw, kw-only (ARG08) | no | yes | yes | yes |
| unknown named argument | no | **no** | yes | yes |
| undefined variable, unclosed `${` | no | **no** | yes | no |
| ambiguous keyword (KW06) | no | yes | yes | yes |
| bad embedded-arg call | no | yes | yes | yes |
| FOR/IF/RETURN/setting/section/empty test | yes (ERR*, NAME16, LEN05) | yes | yes | yes |
| resource path (IMP07); lib not installed / bad init args (IMP09) | no | yes incl. init args | init args flaky (G2) | yes |
| enum/int conversion | no | no | no | yes |
| duplicate test | yes (DUP01) | yes | no | warn |
| `* On Session` missing url | no | no | no | no |
| **caught /33** | **8** | **26** | 28 | 30 |
| FPs on 15 controls | 0 errors (3–6 DOC/SPC warnings/file) | 1 (v07 search order) | 3 | 0 |

Combined: agent profile + analyze 30/33; + dryrun 32/33. Robocop really imports libraries (libdoc in-process → executes their code); resource kws, embedded args, BDD prefixes, `AS` aliases, Run Keyword variants, setup/teardown names checked. Robocop beats robotcode on library priority: RF prefers a custom library over a standard one — robotcode reported "Take Screenshot" (Browser + Screenshot) ambiguous 3× in real suites; RF runs it fine; robocop silent (correct). Gaps: named-arg names never validated; keyword names containing a variable skipped (`Should Be Equal ${a}` with single spaces missed; robotcode catches); no undefined-variable rule; failed library import → KW05/ARG08 silent for every importing file ("fails open"), only IMP09.

## 2. Outdated/incorrect syntax corpus (28 cases)
- Deprecated-but-runs (7: Run Keyword If/Unless, `[Return]`, Exit/Continue For Loop (If), `WITH NAME`, Force/Default Tags, singular headers, Return From Keyword): agent profile 7/7, analyze 4/7; `check --fix` (safe) repaired 7/7, all fixed files ran clean; correct on hard cases (`${r}=  Run Keyword If … ELSE`, ELSE IF chains, `Run Keywords … AND`, assigned `Run Keyword Unless` → adds ELSE setting `${None}`).
- Real errors (13): agent profile 12, analyze 13, dryrun fails 12. Safe fixes repaired 4 (`...arg` no separator, `[Documentation]text`, `VAR ${y}=2`, lowercase `else`). Lowercase `else` trap: real run **passes silently** (else branch becomes dead code). `:FOR` only generic KW05 (robotcode explains old syntax). Not fixable: missing END, TRY without EXCEPT, invalid header, Selenium kw in Browser suite, wrong arg counts.
- Unsafe "safe" fix: SPC22 turns `Test Setupp    Log` into `Test Setup    p    Log` → profile marks SPC22 `unfixable`.
- `robocop format`: semantically safe, but rewrote all 37 noise files (715 lines) → don't run after each agent edit.

## 3. Speed / output (24-line file, 3 errors)
- Cold CLI: default 0.52 s; agent profile 0.95 s no cache, 0.54–0.60 s with persistent `.robocop_cache`; robotcode analyze 1.03 s.
- Project rules lint the whole project root even for one file: 37 files 2.0 s cold / 0.65 s cached; 181 files 2.3 / 0.82 s; output covers the project (7 KB / 31 KB) → filter to the edited file.
- Warm Python API `robocop.run.check_files(return_result=True)`: import 0.3 s once; agent profile 0.25 s/call no cache, **0.04 s/call** cached; default 0.03 s.
- Hook script 0.58 s wall (1.3 s first).
- Output for 3 issues: default extended 1,208 B (~300 tok); simple 323 B; compact `--issue-format "{source}:{line}:{col} {rule_id} {desc}"` 238 B (~60 tok); JSON 938 B; SARIF 117 KB. Default rules on same file 2.2 KB (mostly doc noise).

## 4. Noise on 36 agent-written suites
| Rule set | Issues | Notes |
|---|---|---|
| default | 609 | 465 W; line length, blank lines, unused var, DEPR05/06, docs |
| `robocop:minimal` | 95 | mostly VAR02/VAR03 |
| **agent profile** | **63** | 5 files, all true positives |

True positives: corrupted rf-mcp `build_test_suite` multi-line suite (file-proc); `RF-MCP Lab =    Get Title` (variable name replaced by its value); dropped `Replace String` arg; `Execute JavaScript` in a Browser suite; unescaped `#result` (RF reads a comment). Missed: `${greeting}` never assigned (robotcode caught).

Agent profile `configs/robocop-agent.toml`: select ERR*, ARG05, DUP01/02/03/09, LEN05, LEN15–17, LEN21, MISC08, NAME09/10/11/16, SPC14/16/17/19–22, KW05, KW06, ARG08, IMP07, IMP09, DEPR03/04/07/08/09/10/11, VAR11, VAR13, MISC10, ARG01 (info; often a typo'd variable). Severity: KW06/IMP07/IMP09 → E, SPC17 → W, SPC22 unfixable. Excluded on purpose: DOC, naming, lengths, tags, DEPR05/06 (Set Variable/Create List → VAR is valid RF 7; flagging makes agents rewrite working code).

## 5. Integration
- robotcode LSP already emits robocop findings as LSP diagnostics (source `robocop`, code e.g. `DEPR08-deprecated-run-keyword-if`) when robocop is installed in the LS venv; `robotcode.robocop.enabled` (default true) + `configFile`; reads `[tool.robocop]` from robot.toml; verified agent profile removes doc noise. Per-file rules only, never project rules (robotcode's own analysis covers those). `robotcode analyze` CLI doesn't run robocop.
- Claude Code: `scripts/robocop_hook.py` + `configs/claude_settings_hooks.json` — PostToolUse on `Write|Edit|MultiEdit`, returns `hookSpecificOutput.additionalContext` (~100 tokens; limit 10k chars); tested with simulated payloads for Claude, Codex `apply_patch`, Copilot `toolArgs`; optional `ROBOCOP_HOOK_AUTOFIX=1` applies safe fixes first.
- Codex: PostToolUse covers `apply_patch` (matcher `apply_patch|Edit|Write`); parse file path from patch text.
- Copilot CLI: `.github/hooks/*.json` `postToolUse` + `additionalContext` (docs; not tested live).
- OpenCode: `tool.execute.after` plugin; `configs/opencode_robocop_plugin.ts` untested sketch (field names partly documented).
- pre-commit: local `language: system` hook in the project venv (upstream hook installs robocop in an isolated env → libraries missing → IMP09 noise, KW05/ARG08 silently skipped).

Which tool where: Write/Edit hook + local helper before a file-based step → robocop agent profile in-process (0.04 s cached; only layer that auto-fixes outdated syntax). Interactive/build-suite gate → robotcode analyze or LS (variables, named args, better messages). Before execution/CI → dryrun (type conversion, init args, duplicates).

## Risks / open questions
- Silent config traps (verified): `--select A,B` selects nothing → "No issues found", exit 0 (repeat the flag); a `--config` file not named `robocop.toml` needs `[tool.robocop]` tables or is ignored; git-ignored resource files dropped from project analysis (KW05/ARG08 silent) unless `--skip-gitignore` (same G1 trap as robotcode).
- Project analysis executes library code; cost grows with project size (`--library-workers`, `--ignored-library`).
- Robocop ships its own MCP server (`robocop/mcp`) — doesn't fit the no-MCP direction.
- To do: live tests of Copilot/OpenCode hooks; hook auto-fix vs report-only.
