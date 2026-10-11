# Round 3 — robotcode LSP diagnostics inside coding agents (2026-10-01)

Source: agent_lsp subagent report (saved by the coordinating session). Evidence (R3 = this folder): `orchestrate.py`, `analyze.py`, `lsp_timeline.py`, `probe/lsp_probe.py`, fixes `shim/rc_lsp_shim.py` + `hooks/rf_analyze_hook.py`, `results_summary.json`, `harness_notes.json`, per run `runs/<agent>/<cell>/{agent_stdout.log, lsp.jsonl, hook.jsonl, claude_debug.log, result.json}`. 32 headless sessions; every run's final file independently checked with `robotcode analyze code`.

## Short answer
The hypothesis holds only after fixes. As-is, robotcode's LS gives no usable feedback after the first edit in Claude Code and none in OpenCode, due to three client/server mismatches:
1. Claude Code sends whole-file `didChange` without range; robotcode accepts only incremental → update silently dropped → publishes for the old version → Claude discards as stale.
2. OpenCode labels `.robot` as `plaintext` → robotcode ignores it.
3. OpenCode pulls diagnostics on demand; robotcode's pull returns `[]` and pushes real results ~1–2 s later; OpenCode treats the empty pull as final.
`shim/rc_lsp_shim.py` (between agent and server) fixes all three and logs traffic.

## Matrix
| Agent | Custom LSP? | Diagnostics after edit? | Hover / symbols | Fixed without running? |
|---|---|---|---|---|
| Claude Code 2.1.286 | yes: plugin `.lsp.json` via `--plugin-dir` | **async**, attached to the *next* model request; raw: first edit per file only. Quote: `✘ [Line 12:5] No keyword with name 'Clik' found. [KeywordNotFound] (robotcode)` | hover = full kw docs (project, BuiltIn, Browser); definition works; workspace symbols project-only | raw (errors in 2nd edit): **0/2** (`pass_forced3_r1/r2`, 3 errors left, NO_DIAGNOSTICS_SEEN); shim: **2/2** |
| OpenCode 1.15.12 | yes: `lsp` in `opencode.json` | raw: **never**; shim: **synchronous** inside the edit result, errors only, waits ≤ 5 s: `LSP errors detected in this file, please fix: <diagnostics …> ERROR [12:5] No keyword with name 'Clik' found.` | LSP tool needs `OPENCODE_EXPERIMENTAL_LSP_TOOL=true`; raw JSON | `fix_forced3`: 3→2→1→0 (MiniMax kept 2 "intentional" errors in the ambiguous `forced` prompt) |
| Copilot CLI 1.0.54 | yes: `.github/lsp.json` (`lspServers`, `fileExtensions`), `~/.copilot/lsp-config.json`, or plugin `.lsp.json` | **no** — server not started on edits; a "wait for diagnostics" function in the bundle is never called | `lsp` tool: hover, definition, workspace symbols work (`fix_tools_r1`) | only via hook |
| Codex 0.153.4 | **no LSP support** | no | n/a | only via hook; control left 3 errors |
| VS Code Copilot (docs) | robotcode VS Code extension → Problems panel | agent mode checks edited files; `#read/problems` | `#search/usages` | expected, untested |

Latency: server start lazy (first edit Claude / first read OpenCode / first LSP call Copilot); initialize 0.9–1.4 s; first diagnostics 0.2 s warm, 5–7 s cold (Browser + Requests load); after edit 0.35–1.8 s incl. robotcode's 0.75 s debounce. Claude doesn't wait: if the next step is the final answer, diagnostics are lost (`claude/fix_forced_r2`, cold `fix/pass_forced_r1`).
Memory: robotcode + shim ~92 MB warm, 160–180 MB cold; shim ~14 MB.
Noise: robocop installed in the venv → Claude also gets warnings ("Missing documentation…", sorted by severity, ≤10/file, ≤30 total); `settings: {"robotcode":{"robocop":{"enabled":false}}}` → errors only (`fix_norc_forced2_r1`). OpenCode + hook: errors only.
Tokens: ~200/attachment (robocop on), ~90 (off); fix loop ≈ $0.01–0.02 per Claude session; Codex 50k input tokens without hook, 65–76k with (mostly cached).

## Working configs (exact files in run dirs)
- Claude `.lsp.json`: `{"robotcode":{"command":"/usr/bin/python3","args":["<shim>","--","<venv>/bin/robotcode","language-server","--stdio"],"extensionToLanguage":{".robot":"robotframework",".resource":"robotframework"},"startupTimeout":120000,"settings":{"robotcode":{"robocop":{"enabled":false}}}}}`
- OpenCode: `"lsp":{"robotcode":{"command":["/usr/bin/python3","<shim>","--","<venv>/bin/robotcode","language-server","--stdio"],"extensions":[".robot",".resource"]}}`
- Copilot `.github/lsp.json`: `{"lspServers":{"robotcode":{"command":…,"args":[…],"fileExtensions":{".robot":"robotframework",".resource":"robotframework"}}}}`
- Hooks (`rf_analyze_hook.py` → `robotcode analyze code --severity error` on changed files): Claude `--settings` PostToolUse matcher `Edit|Write|MultiEdit`; Codex config.toml `[[hooks.PostToolUse]] matcher="apply_patch|Edit|Write"` (only trusted hooks run: approve via `/hooks`, headless `--dangerously-bypass-hook-trust`); Copilot plugin dir `hooks/hooks.json` PostToolUse via `--plugin-dir`, hook must print top-level `{"additionalContext":…}`.

## Failures with evidence
- Raw Claude: full-text update dropped → "Dropping stale publishDiagnostics … (server v1 < current v2)" (`claude/pass_forced3_r1/claude_debug.log`).
- OpenCode `plaintext` + empty pull (`opencode/pass_forced_r1/lsp.jsonl`, `opencode/fix_forced_r1`).
- Claude LSP tool: parallel calls during startup fail ("server is starting"); workspace-symbol results dropped when the project folder was git-excluded though the server returned them (`claude/fix_tools_r1` vs `r2`).
- Wrong root: starting from the parent folder ignores robot.toml `python-path` → false "No keyword with name 'Normalize Term' found" (`probe/multiroot`).
- Copilot hooks: repo `.github/hooks/*.json` didn't run in `-p` mode (`copilot/hook_forced2_r1`); Claude-format `hookSpecificOutput` not forwarded (`plughook_forced2_r1`); top-level `additionalContext` works (`plughook2_forced2_r1`).
- Cache: `.robotcode_cache/` per project (~1 MB, gitignored); `robotcode analyze code` 5.6 s cold / 0.85 s warm.
- Diagnostics only for open files (default) → untouched files add no noise.
- (Coordinator observation) Four robotcode multiprocessing workers (resource_tracker + spawn_main) from `runs/claude/{fix,pass}_forced_r1/proj` survived as orphans (PPID systemd --user) after the headless Claude sessions ended → LS library-loader workers outlive the agent; killed by the coordinator.

## Recommendation
1. Primary mechanism for all agents: `robotcode analyze code` PostToolUse hook — synchronous (~0.9 s warm), errors only, works in Claude, Codex, Copilot; succeeded in all 4 valid hook runs (Claude 1, Codex 2, Copilot 1), incl. the quick-exit case where async LSP diagnostics are lost.
2. LSP = optional extra for Claude/OpenCode (and hover/definition in Copilot), only via the shim; file the three mismatches upstream (accept full-document changes, assign language by extension, real results on pull).
3. Pre-warm the analysis cache at session start; launch agents from the folder containing robot.toml; disable robocop in LSP settings.
4. Codex needs the hook; MCP-to-LSP bridges untested.

## Cleanup
Shim/robotcode/agent processes gone; copied credentials deleted. Left: Codex home folders (~57 MB each, 4 folders) under `runs/codex/` (no credentials).
