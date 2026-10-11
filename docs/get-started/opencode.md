# Quick start: OpenCode

**Time:** under 5 minutes. **Needs:** OpenCode 1.15 or later, Python 3.10+, uv, Node.js (OpenCode plugins are
JavaScript).

## 1. Project and environment

```bash
mkdir rf-demo && cd rf-demo
uv venv && uv pip install robotframework robotframework-browser
uv run rfbrowser init chromium
```

## 2. Install

```bash
uvx robotframework-harness install --agent opencode
```

OpenCode has no plugin marketplace, so the installer always uses files mode and says so. It writes:
- the skill to `.opencode/skills/rf-harness/`;
- the plugin `.opencode/plugins/rf-harness.js`, which forwards every tool event to the launcher;
- the runtime into `.venv`.

## 3. Check

```bash
uvx robotframework-harness doctor
```

## 4. Ask OpenCode

```bash
opencode run "Write tests/demo.robot for the bundled demo page with the Browser library (headless), assert the \
confirmation text, then run robot until it passes."
```

!!! info "Richer output for open-weight models"
    OpenCode is often used with open-weight models (MiniMax, DeepSeek, Qwen, GLM). For them the harness switches to the
    [rich output profile](../concepts/output-profiles.md): more controls, the keyword signature and a hint on every
    failure. The A/B data shows this helps them.

!!! note "Stop gate"
    OpenCode has no blocking stop hook. The plugin sends a follow-up message instead, asking for a green plain `robot`
    run. This works headless but depends on timing.

Next: [use it in your own project](your-project.md)
