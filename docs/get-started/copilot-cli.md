# Quick start: GitHub Copilot CLI

**Time:** under 5 minutes. **Needs:** Copilot CLI 1.0.9x or later, Python 3.10+, uv.

## 1. Project and environment

```bash
mkdir rf-demo && cd rf-demo
uv venv && uv pip install robotframework robotframework-browser
uv run rfbrowser init chromium
```

## 2. Install

```bash
uvx robotframework-harness install --agent copilot-cli
```

- **Plugin mode (default; files mode on Windows):** writes `.claude/settings.json`, and for project scope also `.github/copilot/settings.json`.
  Copilot CLI loads the plugin from the marketplace in this repository without a separate install step.
- **Files mode** (`--mode files`): installs the Copilot-format hooks.

!!! note "Windows"
    On Windows, `install` uses files mode by default: plugin-mode hooks are not supported on Windows yet. Without a
    project environment, the installer offers to create `.venv` with uv. See
    [Troubleshooting: Windows](../troubleshooting.md#windows).

!!! info "What Copilot passes to the model"
    In plugin mode, Copilot CLI forwards only a hook's decision and reason to the model. You get refusals and gate
    messages, but not the short live-feedback text. Files mode uses Copilot's own hook format, which also delivers the
    feedback. See the [agent matrix](../agents/matrix.md).

## 3. Check

```bash
uvx robotframework-harness doctor
```

## 4. Ask Copilot

```bash
copilot -p "Write tests/demo.robot for the bundled demo page with the Browser library (headless), assert the \
confirmation text, then run robot until it passes." --allow-all-tools
```

Copilot CLI fires `sessionEnd` after every run, not only at the real end of a session. The launcher therefore ignores
it, and the live session stops on its own after an idle period.

Next: [use it in your own project](your-project.md)
