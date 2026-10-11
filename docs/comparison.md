# Comparison with rf-mcp and rf-agentskills

| | rf-harness (this project) | [rf-mcp](https://github.com/manykarim/rf-mcp) | [rf-agentskills](https://github.com/manykarim/robotframework-agentskills) |
|---|---|---|---|
| what it is | skill + hooks + local live session | MCP server with ~60 tools | knowledge skills, subagents, validation hooks |
| how the agent uses it | writes `.robot` files; hooks run and judge every edit | calls tools (`execute_step`, `build_test_suite`, …) | reads skills; hooks validate edits |
| execution | local, in your project environment | in the MCP server process (local) | none (the agent runs `robot` itself) |
| feedback after an edit | live result, verdict, controls, `NEXT:` | when the agent calls a tool | static validation |
| agents | Claude Code, Codex, Copilot CLI, VS Code, OpenCode | any MCP client | Claude Code, Copilot, VS Code, Codex, Cursor, OpenCode, Goose, Claude Desktop |
| desktop (PlatynUI) | guards vendored, opt-in in this release | full support | skill only |
| evidence vs rf-mcp | 0.83 vs 0.69 (round 7, same window) | baseline | skill on top of rf-mcp ≤ 0 (bundle eval) |

## When to use which

- **Local coding agents writing and repairing RF tests:** rf-harness. It needs no server, and the feedback arrives
  without the agent asking.
- **MCP-only clients**, or agents that should drive RF step by step through tools (chat apps, remote setups): rf-mcp.
- **Broad RF knowledge across many agents and libraries**, including mobile and desktop references: rf-agentskills.
  It coexists with rf-harness. The installer lets rf-agentskills report static errors and the harness report live
  results.

## Combining them

- **rf-harness + rf-agentskills:** supported. Use `--coexist keep`, the default.
- **rf-harness + rf-mcp:** both work, but agents may mix the routes. The research found that skills and rf-mcp
  substitute for each other rather than add up. Choose one per project.
