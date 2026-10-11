# Stop gate

An agent may report success while its test has never passed a plain run. The stop gate prevents that. When the agent
tries to finish and a test file changed since its last **green plain `robot` run**, the harness asks it to run that
file first:

```text
tests/shop.robot changed since its last green plain run. Run: robot -d results tests/shop.robot
```

| agent | mechanism |
|---|---|
| Claude Code | `Stop` hook blocks (at most `RFH_MAX_STOP_BLOCKS`, default 2, then it lets go) |
| Codex | `Stop` hook; the reason becomes the next prompt |
| Copilot CLI | `agentStop` block (Copilot allows up to 8) |
| VS Code | `Stop` hook |
| OpenCode | no blocking stop: the plugin sends a follow-up message when the assistant finishes. Best effort; works headless but depends on timing |

## Why

In the research, plain runs that failed after live runs passed were a real failure mode, often a timing race. The
journey graders re-run the final suite cleanly. A test that only passed live does not count. The gate makes the
agent check this itself, and [plain-run reproduction](plain-run-reproduction.md) helps it fix the race. The
live-pass/plain-fail divergence is analyzed in the [round 6 diagnosis](../../evidence/rounds/06-v3-main/diag/).
