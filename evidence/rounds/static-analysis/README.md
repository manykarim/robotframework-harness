# Static-analysis study: Robocop + robotcode analyze as quality gates (2026-10-02)

**Question.** Does running Robocop and robotcode's static analyzer next to rf-mcp raise the quality of the
suites that rf-mcp and its agents produce? Which defects do they catch that rf-mcp misses, and at what cost?
Which `build_test_suite` defects did they expose?

**Tools.** Robot Framework 7.5 (cross-checked on 7.3.2), robotcode 2.7.0, Robocop 9.1.0, Browser 20.5.0
(cross-checked on 19.12.7), RequestsLibrary 0.9.7. Base: rf-mcp 0.36.0 (`main` at c1a18eb).

**Key results** (from `static-analysis-quality-gates.md`):

| gate | errors caught (of 33 planted) | false positives (15 valid files) |
|---|---|---|
| Robocop, default rules | 8 | 0 errors (3–6 style warnings per file) |
| Robocop, agent profile | 26 | 1 |
| robotcode analyze | 28 | 3 |
| `robot --dryrun` (what rf-mcp uses) | 30 | 0 |
| Robocop agent profile + robotcode analyze | 30 | – |
| + `robot --dryrun` | 32 | – |

rf-mcp ships no static analysis. On a generated BDD suite with 6 planted errors, its dry run surfaced 2 unique
errors without line numbers, while robotcode analyze found 6 of 6 with `line:col`.

**Files.**
- `static-analysis-quality-gates.md`: the report (from rf-mcp `docs/research/`).
- `build_suite_bugs/`: reproductions of the `build_test_suite` defects (`repro_f1.py`, `repro_ws.py`) and the
  Robocop agent profile (`robocop-agent.toml`).

The detection corpus and its raw outputs are in `../01-capability-spikes/static/`, and the Robocop study is in
`../03-lsp-robocop/robocop/`. The report also cites suites from other rf-mcp experiment folders
(`experiments/cc-web`, `experiments/file-proc`, `experiments/web-carconfig`) that are outside this import.

**Config.** `config.json`. **Checksums.** `checksums.sha256`.
