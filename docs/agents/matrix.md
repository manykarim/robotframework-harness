# Agent support matrix

| | Claude Code | Codex | Copilot CLI | VS Code (Copilot) | OpenCode |
|---|---|---|---|---|---|
| install via marketplace | ✓ | ✓ (+ hook trust once) | ✓ | ✓ (preview settings) | – (files) |
| install via files | ✓ | ✓ | ✓ | – | ✓ |
| project scope committed file | `.claude/settings.json` | – (each user runs the plugin commands; hooks in `.codex/` for trusted projects) | `.claude/settings.json` or `.github/copilot/settings.json` | `.claude/settings.json` (recommends the plugin) | `.opencode/` |
| skill | ✓ | ✓ | ✓ | ✓ | ✓ |
| live feedback after edits | ✓ | ✓ | files mode ✓; plugin mode: decision/reason only | ✓ | ✓ |
| refusals of certainly-wrong edits | ✓ | ✓ | ✓ | ✓ | ✓ (throw) |
| REPL rewrite | ✓ (`updatedInput`) | ✓ (patch/command) | ✓ (`modifiedArgs`) | ✓ | ✓ (args) |
| stop gate | ✓ blocking | ✓ (next prompt) | ✓ blocking (≤ 8) | ✓ | best effort (follow-up message) |
| session-end cleanup | ✓ | ✓ | idle exit (sessionEnd fires every run) | idle exit (no event) | ✓ `dispose()` |
| default output profile | lean | lean | lean | lean | rich (open-weight models) |

## Verified versions

| agent | version | how |
|---|---|---|
| Claude Code | 2.1.289 (research), current at release | live sessions (rounds 4–7) |
| Codex | 0.161.0 (research), 0.162.1 (installer trust test) | live sessions, real trust provisioning |
| Copilot CLI | 1.0.91 (research) | live probes (round 4); A/B excluded because only `--model auto` was available |
| OpenCode | 1.15.12 (research) | live sessions (rounds 4–7) |
| VS Code | per docs | not yet verified live; verification is a release task |

The release check (`eval/quickstart_check.py`) records the versions used for each release in this table.

## Not supported in v1

Cursor, Goose, Gemini CLI and Claude Desktop stay out of v1 until tested live. Cursor may load the marketplace plugin,
but this is unverified.
