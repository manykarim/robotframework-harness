# robotframework-harness

**An agent harness for Robot Framework.** It gives coding agents — Claude Code, OpenAI Codex, GitHub Copilot (CLI and
VS Code) and OpenCode — what they need to write, debug and repair Robot Framework tests reliably:

- **Live execution while the agent edits.** Every write or edit of a `.robot` file runs the new lines in a local Robot
  Framework session (built on [robotcode](https://github.com/robotcodedev/robotcode)). The agent gets a short answer:
  passed, or the failing line with a verdict and the next step.
- **Failures the agent can act on.** Covered elements, missing elements, iframes, timing and wrong values are told
  apart from evidence. The agent also gets concrete selectors and the page state as files it can grep.
- **Guard rails, not handcuffs.** Only certainly-wrong edits are refused (broken syntax, deleted tests, hidden
  failures). Everything else becomes a one-line warning, and a green plain `robot` run is required before the agent
  finishes.

Everything runs on your machine; no MCP server is needed.

## Quick start

```bash
cd your-robot-project
uvx robotframework-harness install     # pick your agents; installs the skill, hooks and the runtime
uvx robotframework-harness doctor      # proves the hooks fire and the live session works
```

Then ask your agent for a test. Per-agent guides are in [docs/](docs/).

Plugin marketplace (Claude Code, Copilot CLI, VS Code, Codex):

```bash
claude plugin marketplace add manykarim/robotframework-harness
claude plugin install rf-harness@robotframework-harness
```

## Why: evidence

In same-window A/B runs on live end-to-end journeys (insurance quote, shop checkout, car configurator), the harness
**passed 83% of sessions versus 69% for rf-mcp** across six agent/model combinations (206 sessions). It also cut wall
time and cost for most agents. Weaker, cheaper models gained the most (Qwen 3.8 Flash: 0.38 → 0.88). All data,
graders and reports are in [evidence/](evidence/).

## Repository

| path | what |
|---|---|
| `plugins/rf-harness/` | the plugin: Agent Skill, hook definitions, launcher, per-agent variants |
| `.claude-plugin/marketplace.json` | plugin marketplace for Claude Code, Copilot CLI, VS Code and Codex |
| `src/rf_harness/installer/` | the `rf-harness` installer (no dependencies) |
| `src/rf_harness/runtime/` | hook dispatcher and live session (installed into your project environment) |
| `docs/` | documentation |
| `evidence/` | all experiment data behind the claims |
| `eval/` | the A/B evaluation harness used as release gate |

## License

Apache-2.0
