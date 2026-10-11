# Evaluation method

Harness changes ship only with same-window A/B evidence. The evaluation harness lives in `eval/`.

## Scenarios

Five live journeys on public demo sites, each started from the home page:

| id | kind | task |
|---|---|---|
| `tricentis_quote` | explore | request an automobile insurance quote end to end (all fields, start date computed at run time, Platinum price, send the quote) |
| `carconfig_order` | explore | configure a car with given options, assert the total, buy it with customer data |
| `demoshop_order` | explore | sign in, search, add to cart, check out, assert summary and confirmation |
| `demoshop_debug` | debug | repair an existing failing shop suite |
| `tricentis_debug` | debug | repair an existing failing insurance suite |

## Grading

The agent's final suite is **rerun cleanly** at TRACE log level, and the run's `output.xml` is graded:

- **Confirmation read from the page.** The confirmation text was asserted from the page, not hard-coded.
- **Values read from the page.** Prices and totals came from the page.
- **Form fields driven.** The given data was typed or selected.
- **No shortcut.** No deep links, no JavaScript navigation, no hard-coded assertions.

These come on top of file checks, a green `robot` run and no deprecated syntax. A session passes only if every check
passes.

## Isolation and validity

- **Isolation.** Each cell gets its own workspace and agent home, with only its arm's tools installed. Cells that touch
  another arm's tools are marked contaminated.
- **Invalid sessions.** Sessions that did no real work are detected from transcripts and rerun: expired logins,
  exhausted provider credits recorded as success, backend outages. Round 7 lost 76 sessions to exhausted credits before
  this rule existed.
- **Resilient runner.** The runner is self-healing: it resumes after kills and has distinct exit codes for auth,
  budget and balance problems.
- **Budgets.** OpenRouter budgets are per run, plus an account-balance guard.

## The release gate

The candidate is compared with the current release in the **same time window**: same scenarios, at least 3 reps, main
agents plus one cheap OpenRouter model. The gate fails when:
- the main agent's pass rate drops by more than 0.05 (non-inferiority margin);
- or any agent shows a significant regression (two-sided Fisher p < 0.05, candidate worse).

The report gives:
- pass rates with 95% confidence intervals;
- Fisher and per-cell sign tests;
- cost, wall time and turns.

Live sites drift, so only same-window comparisons are valid. See [Evidence](../evidence.md) for all past rounds, the
harness code as used in the research ([eval snapshot](../../evidence/eval-snapshots/ab-7994ae3/)), and `eval/` for the
commands. The method as used in the last two rounds: [round 6](../../evidence/rounds/06-v3-main/),
[round 7](../../evidence/rounds/07-v31-v32/).
