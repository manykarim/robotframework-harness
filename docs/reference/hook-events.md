# Hook events

Every hook runs `bin/rfh-launch <Event> --agent <agent>` with the agent's JSON payload on stdin. The launcher execs
`python -m rf_harness.runtime.hook <Event> --agent <claude|codex|copilot|vscode|opencode>` in the project interpreter.

## Event names per agent

| harness event | Claude Code / VS Code / Codex (marketplace hooks.json) | Copilot CLI (files mode) | OpenCode plugin |
|---|---|---|---|
| session-start | `SessionStart` | `sessionStart` | init + `session.created` |
| prompt | `UserPromptSubmit` | `userPromptSubmitted` | `chat.message` |
| pre-tool | `PreToolUse` | `preToolUse` | `tool.execute.before` |
| post-tool | `PostToolUse`, `PostToolUseFailure` (Claude, failing Bash) | `postToolUse` | `tool.execute.after` |
| stop | `Stop` | `agentStop` | assistant message finished (follow-up workaround) |
| session-end | `SessionEnd` (dropped for Copilot) | – (dropped) | `dispose()` |

## Matchers

| agent | pre-tool | post-tool |
|---|---|---|
| Claude Code | `Write\|Edit\|MultiEdit\|Bash\|Read` | `Write\|Edit\|MultiEdit\|Bash` (+ `PostToolUseFailure`: `Bash`) |
| Codex | `apply_patch\|Edit\|Write\|Bash` | `apply_patch\|Edit\|Write\|Bash` |
| VS Code | VS Code tool names (`create_file`, `replace_string_in_file`, `run_in_terminal`, `read_file`) | same |

## Outputs

| harness result | Claude Code / Codex / VS Code | Copilot CLI | OpenCode |
|---|---|---|---|
| context | `hookSpecificOutput.additionalContext` | `additionalContext` (files mode) | appended to tool output |
| refuse | `permissionDecision: deny` + reason | `permissionDecision: deny` + reason | `throw new Error(reason)` |
| rewrite | `permissionDecision: allow` + `updatedInput` | `modifiedArgs` | mutate `args` |
| stop gate | `decision: block` + reason | `decision: block` + reason | follow-up message |

## Agent detection (`--agent auto`)

The launcher decides which agent sent an `auto` event, using these signals in order:
- `COPILOT_CLI` → copilot;
- `CLAUDECODE` → claude;
- Codex payload keys (`turn_id`, `model`) → codex;
- VS Code tool names or `tool_input.filePath` → vscode;
- camelCase event names → copilot;
- otherwise claude.

Duplicate deliveries of the same event and payload within 5 s run only once (overlapping hook files).
