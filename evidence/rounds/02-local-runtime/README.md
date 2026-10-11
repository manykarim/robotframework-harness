# Round 2: local runtime (2026-10-01)

**Question.** Round 1 needed a long-lived `repl-server`. Can the same be done locally and more simply? Does a
helper that agents call from their shell work in every coding agent?

| study | folder | key result |
|---|---|---|
| embedded robotcode helper (Python API) | `python_api/findings.md` | Embedding robotcode's REPL engine in a per-project daemon is faster than `repl-server`, shuts down cleanly and runs rf-mcp logic around each keyword in the live RF context (spike 1,526 lines, core about 860). |
| stock `robotcode repl` instead of repl-server | `repl_only/findings.md` | `repl-server` is not needed: stock `repl --plain` fed from a named pipe plus a listener gives per-step JSON. Shutdown 0.4 s vs 5.5–22 s. |
| keyword docs via robotcode, locally | `keyword_docs/findings.md` | robotcode returns full keyword docs locally. Only *search* is name-only; BM25 search runs locally in under 2 ms per query. |
| local helper channel across agents | `agents/findings.md` | Works in all four CLI agents if the helper self-detaches with `setsid` (34 headless sessions) |

**Agents (agents study).** Claude Code 2.1.286 + claude-haiku-4-5, Codex 0.153.4 + gpt-5.6-luna@low (no sandbox:
bwrap cannot start on this host), OpenCode 1.15.12 + MiniMax-M2.7, Copilot CLI 1.0.54 + gpt-4.1. VS Code Copilot
was assessed from its docs only.

**Files.** Each study folder holds its `findings.md`, the code (`python_api/rfmcp_local/`, `repl_only/rfrepl.py`,
`keyword_docs/helper/KwDocs.py`, `agents/common/`), and the committed results (`agents/results_summary.json`,
`keyword_docs/outputs/`, `repl_only/run/`). The agent run directories (`agents/runs/`), logs and benchmark work
dirs were not committed upstream and are not archived.

**Config.** `config.json`. **Checksums.** `checksums.sha256`.

**Limits.** One session per agent × scenario. The sandboxes were not tested (Codex ran without sandbox, and Claude's
sandbox cannot run on this host).
