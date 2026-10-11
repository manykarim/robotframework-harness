# Use it in your own project

## Which Python environment gets the runtime

The runtime executes Robot Framework in-process. It must therefore live in the environment that has your libraries
(Browser, SeleniumLibrary, RequestsLibrary, your own keywords). The installer and the hook launcher look for it in this
order:

1. `--python PATH` (installer) or `RFH_PYTHON` (launcher);
2. `.rf/harness.json`, written by the installer;
3. the active virtual environment (`VIRTUAL_ENV`);
4. `<project>/.venv`;
5. a uv- or poetry-managed environment of the project;
6. `python3` on `PATH`.

The installer shows which environment it chose and asks before installing into it. `doctor` repeats the choice. If
`doctor` names the wrong environment, re-run `install --runtime-only --python <path-to-python>`.

## Team setup

Plugin mode at project scope writes files you commit:
- `.claude/settings.json`, used by Claude Code, Copilot CLI and VS Code;
- `.github/copilot/settings.json`, used by Copilot CLI.

Teammates then only need the runtime in their environment: `uvx robotframework-harness install --runtime-only`. Pin a
release with `--ref v1.0.0`.

The harness writes its working files to `.rf/` (live state, page captures, keyword docs, logs). The installer adds
`.rf/` to `.gitignore`. See [Files and directories](../reference/files.md).

## Existing tools

- **rf-agentskills:** both validate `.robot` edits. With the default `--coexist keep`, rf-agentskills reports static
  errors and the harness reports live results only (`RFH_STATIC=runtime-only`).
- **rf-mcp:** both routes work, but agents may mix them. The installer reports a configured rf-mcp server and leaves it
  alone. See the [comparison](../comparison.md).
- **Research prototypes** (`rfharness*` hooks from the experiments): `--coexist replace` removes them.

## Upgrade and remove

```bash
uvx robotframework-harness install          # again, after a new release: idempotent, removes files no longer shipped
uvx robotframework-harness uninstall        # removes what install recorded; files you edited are kept and listed
uvx robotframework-harness list             # what is installed where
```
