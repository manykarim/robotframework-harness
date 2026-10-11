# Troubleshooting

Start with `uvx robotframework-harness doctor`. Every failed check prints its fix.

## No live feedback after edits

1. **Is the harness installed for this agent?** Run `rf-harness list`, and check `doctor`'s "installed" line for the
   agent.
2. **Do the hooks reach the harness?** `doctor` sends a probe event in the agent's format through the launcher. If that
   fails, the hook configuration is not loaded:
   - **Claude Code:** check `/plugin` (plugin mode) or `.claude/settings.json` hooks (files mode).
   - **Codex:** the hooks must be **trusted**. Run `/hooks` in a Codex session, or re-run `install --yes`. In files mode
     the project must be trusted too.
   - **Copilot CLI:** repository `.github/hooks` run only in trusted folders. The installer uses the plugin or
     `$COPILOT_HOME` hooks instead. In plugin mode Copilot forwards only decisions and reasons, so use `--mode files`
     for live feedback.
   - **VS Code:** set `chat.plugins.enabled` and `chat.useHooks` in user settings, and approve hook commands.
   - **OpenCode:** `.opencode/plugins/rf-harness.js` must exist, and Node.js must be on PATH.
3. **Is the runtime in the right environment?** `doctor` shows the chosen Python. If it is wrong, run
   `install --runtime-only --python /path/to/python`. A missing runtime shows up as one setup line at session start.
4. **Is the file a test file?** Live execution runs `.robot` files with a `*** Test Cases ***` or `*** Tasks ***`
   section. `.resource` files get static checks only.

## "Browser" errors

- **"Executable doesn't exist" / no browsers:** run `rfbrowser init chromium` in the project environment
  (`uv run rfbrowser init chromium`).
- **Browsers already downloaded elsewhere:** the runtime reuses `~/.cache/ms-playwright`. Set
  `PLAYWRIGHT_BROWSERS_PATH` if they are somewhere else.

## Every click fails with COVERED

This is a styled control: a `<span>` drawn over a radio or checkbox, or an overlay such as a cookie banner. Click the
suggested label or the element on top. For overlays, close the banner first. `force=True` would click the overlay.
See [verdicts](concepts/verdicts.md).

## A test passes live but fails with plain `robot`

A timing race. The [reproduction](concepts/plain-run-reproduction.md) says `NOT reproduced`. Add a wait for the state
the failing step needs, for example `Wait For Elements State    id=total    visible`, not a `Sleep`.

## Leftover processes

The helpers kill their process group at session end or after the idle timeout. To clean up by hand, stop the processes
listed in `.rf/exec/*.pid`. Agents without a session-end event (Copilot CLI, VS Code) rely on the idle exit.

## Sandboxed agents

Agent sandboxes (Codex `--sandbox`, bwrap) can block detached helper processes or local sockets. Run the agent without
the sandbox for RF work, or allow the project directory. Sandbox detection with a slower synchronous fallback is
planned.

## Windows

The marketplace hooks call `python3`, which many Windows machines don't have. Use files mode, which writes the
absolute interpreter path or `py -3`: `uvx robotframework-harness install --mode files`. Windows has not been through
the live release gate yet.

## Wrong selectors from a model that keeps re-reading files

If an agent reads `source.html` chunk by chunk, the [read-streak nudge](concepts/page-state.md#the-read-streak-nudge)
points it to `controls.txt`. Some models (Gemini 3.8 Flash in round 7) still loop; the rich profile and the stop gate
limit the damage.
