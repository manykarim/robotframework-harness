# Round 4 — hook capability matrix for a skills+hooks RF harness (2026-10-08)

Source: hooks-matrix subagent report (saved by the coordinating session). Evidence: `runs/<agent>/<cell>/{hooks.jsonl, agent_stdout.log, result.json, helper.log}`; probes `bin/hooklog.py`, `plugins/opencode_probe.js`, `run_probe.py`, `run_claude_skill.py`; `results_summary.json`; config snippets `configs/` (incl. `configs/codex_pretrust_hooks.py`).

Versions: Claude Code 2.1.289, Codex 0.161.0, Copilot CLI 1.0.91, OpenCode 1.15.12. Copilot 1.0.91: `--model gpt-4.1` (also gpt-5-mini, claude-haiku-4.5) "not available"; only `--model auto` (picked gpt-6-luna; bills AI credits).

## Verdict
The skills+hooks harness design works in all four CLIs. Claude Code and Codex support every part natively; Copilot CLI everything except a usable SessionEnd; OpenCode has no blocking Stop hook (plugin workaround passed headless). VS Code from docs only.

## Matrix (✓ = model repeated the hook's unique marker; V = verified live)
| | SessionStart ctx | Prompt ctx | Pre deny / rewrite | Post ctx | Stop block → continue | SessionEnd headless | Timeout (default / expiry) | Crashed hook |
|---|---|---|---|---|---|---|---|---|
| Claude (V) | ✓ | ✓ | ✓ / ✓ `updatedInput` | ✓; failing Bash fires **PostToolUseFailure** instead | ✓ (`stop_hook_active`) | ✓ `reason=other`, 1.5 s budget | 600 s / killed, run continues | run continues, JSON applied |
| Codex (V) | ✓ | ✓ | ✓ / ✓ `updatedInput.command` (patch text) | ✓, also non-zero Bash | ✓ (reason becomes next user prompt) | ✓ `other`; 1 s default, 3 s max | 600 s / silent | run continues |
| Copilot CLI (V) | ✓ (fires after userPromptSubmitted) | ✓ | ✓ / ✓ `modifiedArgs` (raw patch string) | ✓, appended to tool result | ✓ (≤ 8 blocks) | fires after **every** run incl. Stop continuations | 30 s / warning | **preToolUse crash denies the tool** |
| OpenCode plugin (V) | plugin init + `session.created` | ✓ by editing `chat.message` text | ✓ throw / ✓ mutate `output.args` | ✓ mutate `output.output` | no native; workaround ✓ | `dispose()` ✓ | none (awaited) | throw = deny |
| VS Code Local (docs) | ✓ | output fields only | ✓ (+ask) / ✓ `updatedInput` | ✓ | ✓ | **no event** | 30 s | exit 2 blocks |

Also verified: a synchronous 20 s hook blocks the agent in all four CLIs. Parallel tool calls → hooks run concurrently in Codex, OpenCode, Claude (Bash only; Claude serializes Write); Copilot runs postToolUse sequentially. A helper started with `setsid -f` from SessionStart/plugin init survived between hooks and after agent exit in all four. Claude only: hooks in SKILL.md frontmatter activate once the skill is invoked (PostToolUse + Stop block worked); `asyncRewake` exit-2 stderr reached the model in `-p` (2/2).

## Payload fields
- Claude: `tool_input{file_path, content | old_string, new_string}`, `tool_response`, `tool_use_id`; PostToolUseFailure `error:"Exit code 3\n<output>"`.
- Codex: `tool_input.command` = patch text (absolute paths); `turn_id`, `model`; Bash `tool_response` = output only, no exit code.
- Copilot (camelCase): `toolName`, `toolArgs` (raw string for apply_patch), `toolResult.textResultForLlm` (contains "exit code N"); no tool-call id.
- OpenCode: `before(input{tool, sessionID, callID}, output{args})`, `after(…, output{title, output, metadata.exit})`.

## Working config shapes (full files in `configs/`)
- Claude plugin `hooks/hooks.json` (project `.claude/settings.json` also runs in `-p`): `{"hooks":{"PostToolUse":[{"matcher":"Write|Edit|MultiEdit|Bash","hooks":[{"type":"command","command":"python3 ${CLAUDE_PLUGIN_ROOT}/h.py","timeout":60}]}]}}`; outputs `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":…}}`, `…{"permissionDecision":"allow","updatedInput":{…}}`, Stop `{"decision":"block","reason":…}`.
- Codex `config.toml`: `[[hooks.PostToolUse]] matcher="apply_patch|Edit|Write|Bash"` + `[[hooks.PostToolUse.hooks]] type="command" command="…" timeout=60`; same JSON outputs as Claude.
- Copilot plugin `hooks.json`: `{"version":1,"hooks":{"postToolUse":[{"type":"command","bash":"…","timeoutSec":60}]}}`; outputs `{"additionalContext":…}`, `{"permissionDecision":"deny","permissionDecisionReason":…}`, `{"permissionDecision":"allow","modifiedArgs":…}`, `{"decision":"block","reason":…}`.
- OpenCode `.opencode/plugins/rf.js` exporting `"tool.execute.before"` (mutate `o.args` / `throw new Error(reason)`), `"tool.execute.after"` (`o.output += ctx`), `event`, `dispose`.

## Gotchas
1. Claude: `robot` exits non-zero when tests fail → hook **PostToolUseFailure** too.
2. Codex hooks silently skipped unless trusted: `--dangerously-bypass-hook-trust`, or pre-trust (app-server `hooks/list` → key+hash → `[hooks.state."<key>"] trusted_hash="sha256:…"` in config.toml; `trustprobe/`, `configs/codex_pretrust_hooks.py`).
3. Copilot repo `.github/hooks` run only if the folder is in `trusted_folders` (explains round 3); plugin and `$COPILOT_HOME/hooks` always run; isolated `COPILOT_HOME` still authenticates.
4. Copilot sessionEnd fires after every run → stopping the helper there kills it mid-session.
5. OpenCode `run` exits on first idle, before `session.idle` handlers → working Stop workaround: insert a user message via `client.session.prompt({…, body:{noReply:true, parts:[…]}})` when an assistant message finishes (1/1 each for two variants; timing-dependent).
6. OpenCode `experimental.chat.system.transform` never reached the model (3 runs); no hook timeout → a hung plugin hangs the agent.
7. GPT models in Codex/Copilot edit via apply_patch → rewrite must rebuild patch text; Edit-style tools give old/new strings → validation must apply them to the file first.
8. Injected-context caps: Claude 10k chars, Codex ~2,500 tokens (`additionalContextLimit`), Copilot 10 KB.
9. SessionEnd budgets (Claude 1.5 s, Codex 1–3 s) → only signal the helper, don't wait.

## Feasibility per agent
- Claude: all natively; skill-frontmatter hooks can scope the harness; asyncRewake suits long runs.
- Codex: all, once hook trust is provisioned; read results from robot output (no Bash exit code).
- Copilot CLI: all except SessionEnd; ship as plugin or trust the folder; raise `timeoutSec` above RF step time (timeouts invisible to the model).
- OpenCode: Pre/Post + helper start/stop work; Stop gate needs the noReply workaround or a wrapper.
- VS Code Local (docs): SessionStart, Pre/Post, Stop; no SessionEnd; Claude-format hook files there ignore matchers; Copilot/Claude/Codex sessions in VS Code use their own CLI hook implementations.
- All: Pre/Post lazily start the helper (idempotent ping), idle auto-exit, serialize inside the helper (hooks can run concurrently).

## Docs
https://code.claude.com/docs/en/hooks · https://developers.openai.com/codex/hooks · https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-hooks-reference · https://opencode.ai/docs/plugins/ · https://code.visualstudio.com/docs/agent-customization/hooks · https://code.visualstudio.com/docs/agents/reference/hooks-reference

## Housekeeping
All own processes gone; two ~5.6 h old `codex app-server` daemons (not started by this agent) left running; copied credentials deleted; Codex plugin caches + OpenCode node_modules pruned (`runs/` 47 MB).
