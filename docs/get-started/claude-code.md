# Quick start: Claude Code

**Time:** under 5 minutes. **Needs:** Claude Code 2.1 or later, Python 3.10+, uv.

## 1. Create a project with a Python environment

```bash
mkdir rf-demo && cd rf-demo
uv venv && uv pip install robotframework robotframework-browser
uv run rfbrowser init chromium          # downloads the browser once (skip if already initialized)
```

## 2. Install the harness

```bash
uvx robotframework-harness install --agent claude-code
```

Expected output, shortened:

```text
Python environment: ./.venv/bin/python (robotframework 7.x)  -> install the runtime there? [Y/n] y
claude-code  plugin mode, project scope
  + .claude/settings.json   (marketplace robotframework-harness, plugin rf-harness enabled)
  + .rf/harness.json        (runtime: robotframework-harness[runtime]==<version>)
done: 1 agent, runtime installed, .rf/ added to .gitignore
```

Plugin mode writes a committed `.claude/settings.json` that enables the plugin from the marketplace, so teammates get
the harness automatically. `--mode files` copies the skill and hooks into `.claude/` instead.

## 3. Check it

```bash
uvx robotframework-harness doctor
```

All lines should show ✓, including `live smoke: page title read in N s`.

## 4. Ask Claude for a test

```bash
claude "Write tests/demo.robot: open the bundled demo page with the Browser library (headless chromium), \
fill in the form and assert the confirmation text. Then run robot until it passes."
```

What you should see:
- after each edit of `tests/demo.robot`, a short hook message such as `Live tests/demo.robot: L6-L9 PASS (4 lines)` with
  the page title;
- for a failure, the failing line, a verdict (for example `MISSING`) and a `NEXT:` step;
- at the end, Claude runs `robot -d results tests/demo.robot`. If a test file changed since its last green plain run,
  the stop gate asks for that run before Claude may finish.

!!! note "Marketplace commands instead of the installer"
    ```bash
    claude plugin marketplace add manykarim/robotframework-harness
    claude plugin install rf-harness@robotframework-harness
    uvx robotframework-harness install --runtime-only   # the hooks still need the runtime in your project
    ```

Next: [use it in your own project](your-project.md) · [how the hooks work](../concepts/hook-lifecycle.md)
