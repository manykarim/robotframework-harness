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

### "Python was not found": the Microsoft Store placeholder

Windows ships `python.exe` and `python3.exe` in `%LOCALAPPDATA%\Microsoft\WindowsApps`. They are App Execution
Aliases: placeholders for the Microsoft Store, not Python. Run with arguments, they print "Python was not found" and
exit with code 9009. Up to 1.0.0 the installer then stopped with `error: …\WindowsApps\python3.EXE did not start`.

The installer now runs every candidate interpreter once before using it. It skips the placeholder, Pythons older than
3.10 and interpreters that do not start. It also never uses its own `uvx` environment, which uv may delete at any time.
When nothing usable is left, it offers to create the project environment with uv:

```text
Python environment: none usable in C:\work\demo
  skipped  python3 on PATH  C:\Users\me\AppData\Local\Microsoft\WindowsApps\python3.exe
           -> the Microsoft Store placeholder (App Execution Alias), not a Python installation
  skipped  python on PATH   C:\Users\me\AppData\Local\uv\cache\archive-v0\…\Scripts\python.exe
           -> the installer's own (uvx) environment
Create a project environment with uv?  uv venv --python 3.12 C:\work\demo\.venv [Y/n]
```

- **Accept**, or pass `--yes`: uv creates `.venv` in the project, and the runtime is installed there. Pick another
  version with `--venv-python 3.13`. With `--no-input` and without `--yes`, the installer prints the command and exits
  with status 1.
- **No uv:** install [uv](https://docs.astral.sh/uv/getting-started/installation/) and rerun, or pass
  `--python <path>` with an interpreter or virtual environment you created.
- **Turn the placeholder off:** Settings → Apps → Advanced app settings → App execution aliases, then switch off the
  `python.exe` and `python3.exe` entries. `python3` is then simply not found.
- **uv cannot create the environment**, for example "untrusted mount point (os error 448)" when AppData is redirected:
  the installer shows uv's message and installs nothing. Create the environment with a Python from python.org and pass
  `--python`.
- **An existing `.venv` that does not work** is never replaced. Repair or remove it, then rerun.

`doctor` reports the same reasons in its "python environment" check. The behaviour was measured on GitHub's
`windows-2025` and `windows-2022` runners; the
[spike results](https://github.com/manykarim/robotframework-harness/tree/7441981dfe0cdbba0c294fa2528bf85a210b4a6c/openspec/changes/fix-windows-python-detection/spike)
are in the repository, and the CI job `windows-install` repeats the check on every change.

### Hooks: files mode is the default

The marketplace hooks call `python3`, which on Windows is missing or the Store placeholder. On Windows, `install`
therefore uses files mode by default. It writes the absolute interpreter path or `py -3` into the hooks. With an
explicit `--mode plugin` on Windows, the installer warns that the agents will not run the harness hooks. A plugin-mode
bootstrap for Windows is planned. Windows has not been through the live release gate yet.

## Wrong selectors from a model that keeps re-reading files

If an agent reads `source.html` chunk by chunk, the [read-streak nudge](concepts/page-state.md#the-read-streak-nudge)
points it to `controls.txt`. Some models (Gemini 3.8 Flash in round 7) still loop; the rich profile and the stop gate
limit the damage.
