# Live session

After each write or edit of a `.robot` test file, the harness runs the **new or changed lines** of that test in a Robot
Framework session that stays alive between tool calls. The open page, browser context, variables and API sessions carry
over, so the agent explores a site by writing the test itself.

## Rules

- **Incremental.** Only lines that have not run yet in this test are executed. If the first edit opens a page and the
  second appends a `Click`, only the `Click` runs, on the page the first edit opened.
- **A failing line stays open.** If line 15 fails, the next edit that fixes line 15, or inserts lines before it,
  resumes at that point. Lines that already passed are not repeated.
- **Changing an executed line restarts the test**, from its first line, in a fresh browser context. A fresh context
  keeps state from leaking into the rerun.
- **`[Teardown]` runs only in the plain `robot` run.** Live, the test stays open so the next edit can continue.
- **Several tests in one file** each keep their own position.

The answer the agent sees is short. Feedback size depends on the [output profile](output-profiles.md):

```text
Live tests/shop.robot: L8-L12 PASS (5 lines)
Page "Cart" demoshop/cart (14 controls) | files: .rf/state/latest/
```

```text
Live tests/shop.robot: L13 FAIL  Click    text=Checkout
  verdict: MISSING - nothing matched; the page has role=button[name="Proceed to checkout"]
  NEXT: fix line 13 (or insert a line before it); only that part re-runs.
```

## Why it works this way

- The agent writes the artefact you keep. There is no separate journal to turn into a suite, so nothing can be lost or
  changed in between. The research found real defects in such a step (rf-mcp `build_test_suite`), see
  [evidence/rounds/static-analysis](../../evidence/rounds/static-analysis/).
- Incremental execution keeps every edit fast. The hooks answer within seconds, not after a full suite run.

## What runs where

The session is a robotcode REPL engine embedded in the long-lived `execd` helper. It runs in your project's Python
environment, with your libraries: Browser, SeleniumLibrary, RequestsLibrary and your own keywords. Library and
resource imports come from the file's `*** Settings ***`. Import project files by path relative to the suite (for
example `Resource    ${CURDIR}/common.resource`), so that plain `robot` works the same way.

## Related

- [Live timeouts](live-timeouts.md): why live failures come fast but never leak into your files.
- [Plain-run reproduction](plain-run-reproduction.md): what happens when the agent runs `robot`.
- [Helper lifecycle](helper-lifecycle.md): start, serialization and cleanup.
