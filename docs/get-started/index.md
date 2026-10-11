# Get started

You need:

- **Your coding agent:** Claude Code, Codex, Copilot CLI, VS Code with Copilot, or OpenCode.
- **Python 3.10+** and [uv](https://docs.astral.sh/uv/). `pipx` works too: replace `uvx` with `pipx run`.
- **A Robot Framework project**, or an empty folder. The quick starts use the bundled demo page, so they work offline.

Every quick start has the same three steps:

1. **Install** with `uvx robotframework-harness install`. It shows the agents found on your machine, preselected,
   then:
   - installs the skill and hooks for the ones you choose;
   - installs the runtime into the project's Python environment, after asking;
   - prints anything still missing, such as `rfbrowser init chromium`.
2. **Check** with `uvx robotframework-harness doctor`. It sends a test event through each agent's hook format and runs
   one live step against the demo page. Every check prints ✓ or ✗ with its fix.
3. **Ask your agent** for a test. Watch for the hook feedback after each edit: `L5-L9 PASS`, or a failing line with a
   verdict and `NEXT:`.

| agent | quick start | install method |
|---|---|---|
| Claude Code | [Claude Code](claude-code.md) | plugin marketplace or files |
| OpenAI Codex | [Codex](codex.md) | plugin marketplace + one-time hook trust, or files |
| GitHub Copilot CLI | [Copilot CLI](copilot-cli.md) | plugin marketplace or files |
| VS Code (Copilot) | [VS Code](vscode.md) | plugin marketplace (preview settings) |
| OpenCode | [OpenCode](opencode.md) | files (OpenCode has no marketplace) |

!!! tip "Several agents in one project"
    Select several agents in the same `install` run. They share one runtime and one `.rf/` folder.

Next: [use it in your own project](your-project.md).
