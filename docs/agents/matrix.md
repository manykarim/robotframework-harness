# Agent support matrix

| | Claude Code | Codex | Copilot CLI | VS Code (Copilot) | OpenCode |
|---|---|---|---|---|---|
| install via marketplace | ✓ | ✓ (+ hook trust once) | ✓ | ✓ (preview settings) | – (files) |
| install via files | ✓ | ✓ | ✓ | – | ✓ |
| on Windows | install in files mode (default); live runtime not yet | install in files mode (default); live runtime not yet | install in files mode (default); live runtime not yet | install in files mode (default, `.claude/` hooks); live runtime not yet | install ✓ (files); live runtime not yet |
| project scope committed file | `.claude/settings.json` | – (each user runs the plugin commands; hooks in `.codex/` for trusted projects) | `.claude/settings.json` or `.github/copilot/settings.json` | `.claude/settings.json` (recommends the plugin) | `.opencode/` |
| skill | ✓ | ✓ | ✓ | ✓ | ✓ |
| live feedback after edits | ✓ | ✓ | files mode ✓; plugin mode: decision/reason only | ✓ | ✓ |
| refusals of certainly-wrong edits | ✓ | ✓ | ✓ | ✓ | ✓ (throw) |
| REPL rewrite | ✓ (`updatedInput`) | ✓ (patch/command) | ✓ (`modifiedArgs`) | ✓ | ✓ (args) |
| stop gate | ✓ blocking | ✓ (next prompt) | ✓ blocking (≤ 8) | ✓ | best effort (follow-up message) |
| session-end cleanup | ✓ | ✓ | idle exit (sessionEnd fires every run) | idle exit (no event) | ✓ `dispose()` |
| default output profile | lean | lean | lean | lean | rich (open-weight models) |

## Verified versions

| agent | version | how (2026-10-11, release candidate 0.9.0) |
|---|---|---|
| Claude Code | 2.1.296 | quick-start check (install, doctor incl. live smoke, plain robot) + a real session on the live Tricentis journey: 12/12 checks, 258 s |
| Codex | 0.162.1 | quick-start check + a real session on the live Tricentis journey: 12/12, 110 s; hook trust provisioned by the installer |
| OpenCode | 1.15.12 | quick-start check + a real session on the live Tricentis journey (rich profile): 12/12, 119 s |
| Copilot CLI | 1.0.91 | quick-start check + a real session on the live Tricentis journey (files mode, `--model auto`, trusted folder): 12/12, all hooks firing (83 events) |
| VS Code | 1.138.0 | quick-start check (install, doctor incl. live smoke); no headless session possible, verify in the IDE |

The research rounds used Claude Code 2.1.289, Codex 0.161.0, Copilot CLI 1.0.91 and OpenCode 1.15.12. Copilot CLI was
not part of the A/B rounds: only `--model auto` was available.

!!! note "Copilot CLI files mode needs a trusted folder"
    Copilot CLI runs repository hooks (`.github/hooks`, files mode at project scope) only in folders listed in
    `trusted_folders` of `~/.copilot/config.json`. Accept the folder-trust prompt once, or add the folder there.
    `doctor` checks this. In an untrusted folder the first real session passed the task without any hook firing; after
    trusting the folder the hooks fired on every event.

!!! note "Windows: files mode"
    The marketplace hooks call `python3`, which on Windows is missing or the Microsoft Store placeholder. `install`
    therefore defaults to files mode on Windows and warns on an explicit `--mode plugin`. The hook runtime itself is
    POSIX-only so far (`fcntl`, Unix sockets), so live feedback does not work on Windows yet. See
    [Troubleshooting: Windows](../troubleshooting.md#windows).

## Not supported in v1

Cursor, Goose, Gemini CLI and Claude Desktop stay out of v1 until tested live. Cursor may load the marketplace plugin,
but this is unverified.
