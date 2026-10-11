# Helper lifecycle

Hooks are short-lived processes; a browser session is not. The harness keeps the state in long-lived helpers and
keeps the hooks thin.

| helper | module | job |
|---|---|---|
| live session | `execd` | the robotcode REPL engine with your libraries: executes lines, captures pages, classifies failures |
| static checks | `lintd` | robotcode analyzer + Robocop, warm caches |
| keyword docs | `docs` / `docsgen` | libdoc to `.rf/docs/` |

## Rules

- **Lazy, single instance per project.** The first hook that needs a helper starts it, detached with `setsid`, so the
  agent's own process cleanup does not kill it. That matters for Codex, which kills plain background jobs. Later hooks
  find it through a local socket under `.rf/`. A second start is a no-op.
- **Serialized.** Agents can fire hooks in parallel (Claude for Bash, Codex, OpenCode). The helper runs steps one
  after another, and each answer contains only its own steps.
- **Idle exit.** Helpers exit after an idle period, and when the process they watch exits (`RFH_WATCH_PID`, set for
  `doctor` probes).
- **Session end.** On `SessionEnd`, helpers are signalled to stop; the hook does not wait. Agents give hooks only
  1–3 s at session end. The helper closes the browser and kills its process group, so no Playwright, node or chromium
  processes remain.
- **Copilot CLI and VS Code** have no usable session-end event. Their helpers end through the idle timeout.

## Why

The research measured the alternatives:
- `robotcode repl-server` (JSON-RPC): undocumented, unauthenticated, slow orphan-prone shutdown.
- A REPL on a FIFO: 66 ms per step, workable but fragile.
- One process per call: loses state.

The embedded engine took 36–45 ms per step, stopped in 0.3–0.5 s and left 0 orphans. See
[round 2](../../evidence/rounds/02-local-runtime/) and the stepwise spikes in
[round 1](../../evidence/rounds/01-capability-spikes/).
