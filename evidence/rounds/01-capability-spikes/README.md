# Round 1: capability spikes (2026-10-01)

**Question.** Can robotcode replace the parts of rf-mcp that an agent harness needs: stepwise execution, hints on
failures, static validation, keyword discovery, result analysis and locator guidance? Can a remote MCP server
drive local execution at all?

**How.** Six scripted studies, run by research subagents of the coordinating session against robotcode 2.7.0,
Robot Framework 7.5 (cross-checked on 7.3.2) and rf-mcp 0.36.0. Public demo sites: Sauce Demo, the Flowline
demoshop, Restful Booker, the-internet. No coding agents were involved and there are no A/B sessions.

| study | folder | key result |
|---|---|---|
| deep research: remote MCP + robotcode | `research/findings.md` | A remote MCP server cannot make the client execute anything. robotcode `repl-server` is the only released way to keep RF state across separate shell calls. |
| rf-mcp host-dependency map | `map/host-dependency-map.md` | Which rf-mcp components need the host (browser, files, RF context), with `file:line` references |
| hints on robotcode output | `hints/findings.md` | rf-mcp's hint logic is portable: 32/33 identical hints from parsed `robotcode repl -k` output |
| persistent stepwise sessions | `stepwise/findings.md` | `repl-server` + one-shot client: 24 ms (bash) / 81 ms (Python) median per step |
| static validation, keyword search, results | `static/findings.md` | `robotcode analyze` + `robot --dryrun` catch 32 of 33 planted errors. Neither alone is enough. |
| locator intelligence as RF steps | `locators/findings.md` | A guarded step reports 13 failure classes with live re-counted candidate locators, more informative than rf-mcp for Browser |

**Files.** Each study folder holds its `findings.md`, the scripts and the committed outputs (tables, raw JSON,
corpora). The outputs that were *not* committed upstream (run directories, caches, large logs, about 46 MB) are
not in this archive; see `../../PROVENANCE.md`.

**Config.** `config.json`. **Checksums.** `checksums.sha256` (run `sha256sum -c checksums.sha256` in this folder).

**Limits.** Single machine, single runs. The latency numbers come from a machine that was running other Browser jobs.
These are capability findings, not effect sizes.
