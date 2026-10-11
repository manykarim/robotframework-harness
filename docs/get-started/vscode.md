# Quick start: VS Code (GitHub Copilot)

**Time:** about 5 minutes. **Needs:** VS Code with GitHub Copilot (agent mode), Python 3.10+, uv.

Plugins and hooks are preview features in VS Code. Enable them once in your **user** settings:

```json
{
  "chat.plugins.enabled": true,
  "chat.useHooks": true,
  "chat.plugins.marketplaces": ["manykarim/robotframework-ai-engineering"]
}
```

## 1. Project and environment

```bash
mkdir rf-demo && cd rf-demo
uv venv && uv pip install robotframework robotframework-browser
uv run rfbrowser init chromium
```

## 2. Install

```bash
uvx robotframework-harness install --agent vscode
```

The installer:
- installs the runtime;
- writes the committed `.claude/settings.json`, which recommends the plugin to everyone who opens the workspace;
- prints the user settings above if they are missing.

Then install `rf-harness` from the marketplace in the Extensions view.

## 3. Check

```bash
uvx robotframework-harness doctor
```

## 4. Ask Copilot in agent mode

Open the folder in VS Code and ask Copilot Chat in **Agent** mode:

> Write tests/demo.robot for the bundled demo page with the Browser library (headless), assert the confirmation text,
> then run robot until it passes.

VS Code asks before running hook commands unless your chat approval mode allows them. VS Code has no session-end
event; the live session stops on its own after an idle period.

Next: [use it in your own project](your-project.md)
