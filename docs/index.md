# Robot Framework agent harness

The harness makes coding agents good at Robot Framework. It is three things that work together on your machine:

1. **An Agent Skill** (`rf-harness`): a short guide to Robot Framework, the Browser library and the harness itself.
   The agent loads it when a task involves `.robot` files.
2. **Agent hooks**: small programs your agent runs before and after its tool calls. They execute the test lines the
   agent just wrote, judge failures, refuse only certainly-wrong edits, and keep the agent going until the suite passes
   with a plain `robot` run.
3. **A local runtime** built on [robotcode](https://github.com/robotcodedev/robotcode). It keeps a Robot Framework
   session alive between tool calls, with the open browser, variables and API sessions, so each edit runs only the new
   lines.

```text
 agent edits tests/checkout.robot ──▶ PostToolUse hook ──▶ live session runs the new lines
                                                              │
 agent reads: "L12-L14 PASS · Page 'Cart' (9 controls)"  ◀────┘   or
              "L15 FAIL Click id=accept  verdict: COVERED - <span class="ideal-radio"> intercepts
               pointer events -> click its label `Click    label:has(#accept)`  NEXT: fix line 15"
```

Nothing runs in the cloud and no MCP server is needed. The harness supports **Claude Code, OpenAI Codex, GitHub Copilot
CLI, VS Code (Copilot) and OpenCode**.

## Start

```bash
cd your-robot-project
uvx robotframework-harness install     # choose your agents
uvx robotframework-harness doctor      # proves the hooks fire and a live step works
```

Then pick your agent's [quick start](get-started/index.md).

## Why

In same-window A/B tests on live end-to-end journeys (an insurance quote, a shop checkout, a car configurator, and
repairing broken suites), agents with the harness passed **0.83** of sessions versus **0.69** with rf-mcp: 206
sessions, six agent/model combinations. The gain was largest for weaker, cheaper models, and wall time and cost dropped
for most agents. See [Evidence](evidence.md) for every number, its data and its limits.

## Where to go next

- **New here:** [Get started](get-started/index.md).
- **How it works:** start with [Architecture](concepts/architecture.md), then the
  [hook lifecycle](concepts/hook-lifecycle.md).
- **Something does not work:** [Troubleshooting](troubleshooting.md).
- **Choosing between tools:** [Comparison with rf-mcp and rf-agentskills](comparison.md).
