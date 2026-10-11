# Quick start: OpenAI Codex

**Time:** under 5 minutes. **Needs:** Codex CLI with hook support (verified on 0.161–0.162), Python 3.10+, uv.

## 1. Project and environment

```bash
mkdir rf-demo && cd rf-demo
uv venv && uv pip install robotframework robotframework-browser
uv run rfbrowser init chromium
```

## 2. Install

```bash
uvx robotframework-harness install --agent codex --yes
```

With `--yes` the installer:
- runs `codex plugin marketplace add manykarim/robotframework-ai-engineering` and
  `codex plugin add rf-harness@robotframework-ai-engineering`;
- trusts exactly the installed hooks, by writing their hashes to Codex's `config.toml`;
- installs the runtime into `.venv`.

Without `--yes` it prints those commands for you to run.

!!! warning "Hook trust"
    Codex runs no plugin hook until it is trusted. If the installer could not pre-trust them, open a Codex session once
    and run `/hooks` to trust the `rf-harness` hooks. `doctor` reports untrusted hooks as a failure, with this fix.

!!! note "Project trust"
    Codex loads a project's `.codex/` files only in projects you trust. In files mode, trust the project when Codex asks.

## 3. Check

```bash
uvx robotframework-harness doctor
```

## 4. Ask Codex

```bash
codex exec "Write tests/demo.robot for the bundled demo page with the Browser library (headless), assert the \
confirmation text, then run robot until it passes."
```

Codex edits with `apply_patch`; the hooks read the patch and run the changed lines. Codex shows hook output in its
event stream rather than the transcript, but the model receives it.

Next: [use it in your own project](your-project.md)
