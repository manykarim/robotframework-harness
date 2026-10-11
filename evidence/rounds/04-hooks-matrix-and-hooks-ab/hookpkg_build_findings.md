# hookpkg — Agent Skill + hooks RF harness, no agent-facing CLI (build report, 2026-10-08)

Source: hookpkg builder subagent report (saved by the coordinating session). Package `ab/hookpkg/` (`rfharness`, editable-installed in the worktree venv, no console scripts). Blind protocol: no fixtures / target sites used. Capability basis: `round4/hooks_matrix/findings.md`.

## Layout (lines)
- `install.py` (276) — same interface as skillpkg's installer.
- `rfharness/hook.py` (663) — single entry point for every agent/event (`python -S …/hook.py <Event> --agent X`), stdlib only, ~40 ms start.
- `rfharness/hookcore.py` (754) — payload normalization for 4 agents, proposed-content computation (incl. apply_patch parse/apply/rebuild), daemon management, output.xml parsing, formatting.
- `rfharness/execd.py` (598) — live RF session daemon (file-step engine, page snapshots).
- `rfharness/lintd.py` (402) — static-gate daemon (robotcode analyzer + robocop agent profile + portability).
- `rfharness/docs.py` (190) — keyword docs.
- Copied from skillpkg without CLI wording: `engine`, `rthooks`, `pagestate`, `kwdocs`, `portable`, `analyzer`, `proto`, `procs` (2,592).
- `skill/SKILL.md` (4,991 B) + 7 references (browser, explore, waits, debug, requests, results, selenium).
- `verify/` — `verify_hooks.py`, `simlib.py`, `agents_run.py`, `harness_smoke.py`, local site (cookie banner, hidden styled radio/checkbox, select, payment iframe, async confirmation), JSON API server, `repair/checkout.robot` (3 planted bugs), `results_hooks.json`, `results_agents.json`.

## Hooks (simulated latencies, warm)
- **SessionStart (~80 ms)**: start exec + lint daemons detached (idempotent, race-safe); snapshot RF files; write `.rf/docs/<Lib>.md` (one line per keyword, repaired `*args`, cached per library version, + `project.md`; 0.3–0.9 s); inject a short note.
- **PreToolUse (median 120–160 ms; deny ~120 ms; rewrite 280–390 ms)**: proposed content from Write/Edit/MultiEdit/apply_patch; deny with line numbers only for NEW hard errors (unknown keyword, arg count, syntax/model, missing resource/library, non-portable imports); deprecated syntax → robocop safe fixes + rewritten tool input; cold/busy gate (≤ 1.6 s first call) → allow; after 3 denials of the same file → allow (no deadlock).
- **PostToolUse on a test file (~0.3–1 s per few lines; 3–5 s with browser start)**: only new/changed test lines run; fixing a failing line resumes there in the same open page; changing an already-run line restarts the test (Suite Setup re-run only if the test opens no page itself); editing a user keyword re-runs the first test calling it; leftover tests from a whole-file write continue afterwards. Output ≤ 2 KB: per-line PASS/FAIL, guard results (NOT_FOUND with `frame >>> selector` fix, NOT_VISIBLE, COVERED), keyword file:line for failures inside keywords, assignment return values, page summary; full controls/aria/source/screenshot to `.rf/state/`. Over budget (`RFH_BUDGET`, default 90 s) → "still running", delivered with the next hook (verified).
- **PostToolUse(Failure) on Bash `robot` (~8 s)**: output.xml failure summary; reproduces the first failing test live (stopped at the failing line, page saved); green run marks the file verified.
- **Stop (~70 ms)**: blocks once per state if a changed test file has no green plain run since; respects `stop_hook_active`, ≤ 2 blocks.
- **SessionEnd (~300–380 ms)**: signals both daemons, removes generated files; fallbacks: daemons exit when the agent process dies or after 20 min idle.

## Agent support
| Agent | Hooks wired | Verified in real sessions |
|---|---|---|
| Claude | all events + PostToolUseFailure | everything |
| Codex | config.toml hooks + `--dangerously-bypass-hook-trust` | everything except rewrite (simulated; patch rebuild) |
| OpenCode | plugin before/after, Stop via assistant-message-finish + `noReply` prompt, dispose | everything |
| Copilot (`--model auto`) | plugin `hooks.json` (v1, camelCase) | start/pre/post/agentStop; deny/rewrite simulated; sessionEnd deliberately ignored |

## Verification
- Simulation 62/62: incremental + whole-file writes, fail → fix → resume, iframe, earlier-line restart, keyword edits, planted-error deny, rewrite, Stop block then allow, robot-run reproduction, API GET/POST, 4 payload shapes, still-running, 0 orphans / stray daemons.
- Real sessions 13: Browser journey + 3-bug suite repair — Claude haiku-4-5 121 s, Codex luna@low 88 s, OpenCode M2.7 125 s, Copilot 98/120 s; all suites pass plain `robot`; 32–37 lines auto-executed per session; 0 `rfmcp` calls. Copilot run 1 left 4 processes (Node agent process named "MainThread" not recognized) → fixed, run 2 left 0. API task: Codex and OpenCode each blocked once by the Stop gate, then ran robot and passed; Claude ran robot unprompted. Gate probe: Claude denied twice (also wrote `If` in wrong case), Codex once. Rewrite probe: file modernized to IF/END for Claude and OpenCode.

## A/B harness changes
New arm `hookpkg` (ARMS, ARM_SPEC, HOOK_ARMS) via `hookpkg/install.py`; hook log `<cell>/rfh_hooks.jsonl`; `row["hookpkg"]` metrics (firings per event, auto-executed lines, denials, rewrites, Stop blocks, reproductions, `.rf/state` + `.rf/docs` reads); contamination: `rfmcp` calls in this arm, `rfharness`/`.rf/hook` in others. `check-scenarios` still IDENTICAL. Note: plain `run`/`pilot` without `--arms` now also schedules hookpkg. `analyze.py` still reports only the original 3 arms.

## Known gaps
Guard probes only top-level lines (failure inside a keyword waits the full 10 s); teardowns never run live; tests depending on earlier tests may fail on restart; keyword re-runs follow only direct callers; VariableNotFound/ambiguous keyword not denied, named args not validated; multi-file apply_patch allowed + warned, never rewritten; OpenCode Stop workaround timing-dependent (3/3 here); Copilot fires every hook for every tool (~40 ms each); agent-process detection is a process-name heuristic. Left: keyword-docs cache `~/.cache/rfharness` (108 KB).
