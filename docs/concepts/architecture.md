# Architecture

```text
┌───────────── coding agent (Claude Code / Codex / Copilot / VS Code / OpenCode) ─────────────┐
│  skill rf-harness (SKILL.md + references)          hooks: SessionStart · Prompt · PreToolUse │
│                                                           PostToolUse · Stop · SessionEnd   │
└──────────────────────────────────────────────┬──────────────────────────────────────────────┘
                                               │ JSON payload on stdin
                         bin/rfh-launch  (stdlib, ~2 ms; finds the project interpreter)
                                               │ exec
                      <project python> -m rf_harness.runtime.hook <Event> --agent <agent>
                                               │  thin: ≤150 ms median
              ┌────────────────────────────────┼─────────────────────────────────┐
              ▼                                ▼                                 ▼
   execd: live session helper         lintd: static checks              docs: keyword docs
   (robotcode REPL engine embedded,   (robotcode analyzer +             (robotcode libdoc ->
    Browser/Requests/… in-process,     Robocop agent profile)            .rf/docs/*.md)
    one per project, serialized)
              │
              ▼
   .rf/state/latest/{page.txt, controls.txt, aria.yaml, source.html, screenshot.jpg}
```

## Components

| component | where | job |
|---|---|---|
| Skill `rf-harness` | `plugins/rf-harness/skills/rf-harness/` | how to write RF and Browser code, and how to use the harness feedback |
| Hook definitions | `plugins/rf-harness/hooks/hooks.json`, `variants/` | which agent events call the launcher |
| Launcher | `plugins/rf-harness/bin/rfh-launch` | finds the project's Python, checks the runtime version, execs the runtime, never crashes |
| Hook dispatcher | `rf_harness.runtime.hook` | turns each agent's payload into one event model, decides, renders the agent's output format |
| Live session | `rf_harness.runtime.execd` | runs test lines in a persistent Robot Framework session ([details](live-session.md)) |
| Static checks | `rf_harness.runtime.lintd` | robotcode analyzer + Robocop agent profile ([details](static-quality.md)) |
| Keyword docs | `rf_harness.runtime.docs`, `kwdoc` | libdoc to files ([details](keyword-knowledge.md)) |
| Feedback | `leanfmt`, `richfmt`, `profiles`, `pwlog` | verdicts and bounded output per model ([verdicts](verdicts.md), [profiles](output-profiles.md)) |
| Desktop guards | `rf_harness.runtime.desktop` | PlatynUI safety, isolation and focus ([details](desktop-safety.md)) |
| Installer | `rf_harness.installer` | sets everything up per agent ([CLI](../reference/cli.md)) |

## Design choices and why

- **Hooks, not a CLI or MCP server.** A helper CLI only helps when the agent decides to call it, and agents often don't.
  Hooks deliver feedback after every edit unasked. Claude scored 0.53 with hooks vs 0.20 with a helper CLI in
  [round 4](../../evidence/rounds/04-hooks-matrix-and-hooks-ab/); the hook harness beat rf-mcp in
  [round 6](../../evidence/rounds/06-v3-main/) and [round 7](../../evidence/rounds/07-v31-v32/).
- **The edited file is the test.** The agent writes the real `.robot` file, and the hooks run its new lines. There is no
  journal-to-suite step that could change arguments, and no shell quoting of `${variables}`.
- **The runtime lives in your project environment.** Library imports, keyword docs and execution must see exactly the
  libraries your suites use. The hook process itself stays thin; the heavy work runs in long-lived helpers.
- **Everything is local.** No test data, page content or results leave your machine.
