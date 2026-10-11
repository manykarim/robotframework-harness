# Hook lifecycle per agent

The harness uses one internal event model. Each agent has its own names, payload shapes and limits; the launcher and
dispatcher translate between them.

| harness event | what the harness does | Claude Code | Codex | Copilot CLI | VS Code | OpenCode |
|---|---|---|---|---|---|---|
| session start | context lines, lazy helper start, keyword docs for imported libraries | `SessionStart` | `SessionStart` | `sessionStart` / `SessionStart` | `SessionStart` | plugin init + `session.created` |
| prompt | short task context (RF project facts) | `UserPromptSubmit` | `UserPromptSubmit` | `userPromptSubmitted` | output fields only | edits `chat.message` text |
| pre-tool | refuse certainly-wrong edits, rewrite REPL calls, keyword docs on demand, read-streak nudge | `PreToolUse` (`updatedInput`) | `PreToolUse` (patch text) | `preToolUse` (`modifiedArgs`) | `PreToolUse` | `tool.execute.before` |
| post-tool | run new lines live / summarize `robot` runs / feedback | `PostToolUse` + `PostToolUseFailure` (failing Bash) | `PostToolUse` | `postToolUse` | `PostToolUse` | `tool.execute.after` |
| stop | require a green plain `robot` run | `Stop` (block) | `Stop` (reason becomes next prompt) | `agentStop` (≤ 8 blocks) | `Stop` | follow-up message (no blocking stop) |
| session end | signal helpers to stop | `SessionEnd` (1.5 s budget) | `SessionEnd` (≤ 3 s) | ignored (fires after every run) | no event | `dispose()` |

## Payloads and edits

- **Claude Code / VS Code:** `tool_input` with `file_path` and `content` or `old_string`/`new_string`; VS Code uses its
  own tool names (`create_file`, `replace_string_in_file`, `run_in_terminal`).
- **Codex:** edits arrive as `apply_patch` text with absolute paths. The harness applies the patch to a copy before it
  decides on a refusal.
- **Copilot CLI:** camelCase fields, `toolArgs` as a raw string.
- **OpenCode:** the JS plugin passes `tool`, `args` and `output` to the launcher.

The shared marketplace `hooks.json` is read by Claude Code, Copilot CLI, VS Code and Codex. It passes `--agent auto`,
and the launcher identifies the agent from its environment and the payload shape.

## Limits that shaped the design

- **Injected context caps:** Claude ≈ 10,000 characters, Codex ≈ 2,500 tokens, Copilot 10 KB. Feedback is far below
  them ([profiles](output-profiles.md)).
- **Hook timeouts:** Claude 600 s, Codex 600 s, Copilot 30 s by default. A hook blocks the agent while it runs, so
  long work happens in the helper, and hooks return what is ready.
- **Copilot CLI:** a crashing `preToolUse` hook denies the tool. The launcher never exits with an error.
- **Codex:** hooks run only after they are trusted ([quick start](../get-started/codex.md)).
- **Parallel tool calls:** several hooks can fire at once. The helper serializes execution
  ([helper lifecycle](helper-lifecycle.md)).

The full payload facts per agent are in the round-4 hook matrix:
[evidence/rounds/04-hooks-matrix-and-hooks-ab](../../evidence/rounds/04-hooks-matrix-and-hooks-ab/).
