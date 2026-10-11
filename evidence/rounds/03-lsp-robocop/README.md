# Round 3: robotcode LSP in agents, LSP as validator, Robocop (2026-10-01)

**Question.** Can static feedback reach the agent *while it edits*, without running anything? Which static
analyzer catches which agent mistakes, and how noisy is it?

| study | folder | key result |
|---|---|---|
| robotcode LSP diagnostics inside coding agents | `agent_lsp/findings.md` | Holds only after fixes. As-is, the LSP gives no usable feedback after the first edit in Claude Code and none in OpenCode, because of three client/server mismatches. `shim/rc_lsp_shim.py` fixes all three. Codex has no LSP support, and Copilot CLI never starts the server on edits. |
| LSP as validator + file-based step execution | `lsp_quality/findings.md` | Same engine as `robotcode analyze`: 28 of 33 planted errors caught, 48/48 diagnostic codes identical. All noise comes from Robocop defaults. |
| Robocop 9.1 for agent-written RF | `robocop/findings.md` | Default rules catch 8 of 33; the project-rule "agent profile" catches 26. Robocop is the only layer that auto-fixes outdated syntax. |

**Agents (agent_lsp, 32 headless sessions).** Claude Code 2.1.286, OpenCode 1.15.12, Copilot CLI 1.0.54,
Codex 0.153.4. Every run's final file was checked independently with `robotcode analyze code`.

**Tools.** robotcode 2.7.0, Robocop 9.1.0, Robot Framework 7.5.

**Files.** `agent_lsp/` (orchestrator, analyzer, LSP probe, shim, hook, `results_summary.json`,
`harness_notes.json`), `lsp_quality/` (experiment scripts, test projects; the `results/` and `logs/` folders were
not committed upstream), `robocop/` (configs incl. `robocop-agent.toml`, corpora, scripts). Agent run directories
(`agent_lsp/runs/`, about 260 MB) are not archived.

**Config.** `config.json`. **Checksums.** `checksums.sha256`.

**Limits.** One run per agent × cell. The error corpus is planted (33 errors, 15 valid controls), not sampled from
real agent output; `robocop/noise_corpus` (36 agent-written suites) covers the noise side.
