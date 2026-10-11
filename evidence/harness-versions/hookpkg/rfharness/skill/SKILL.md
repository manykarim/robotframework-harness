---
name: robotframework
description: Robot Framework test automation - write, debug and repair .robot/.resource tests (Browser/Playwright web UI incl. iframes, shadow DOM, custom widgets; SeleniumLibrary; RequestsLibrary APIs), explore unknown web pages, fix failing suites, find keywords, analyze output.xml. Hooks execute your test lines live after every edit and attach the results. Use for any Robot Framework task.
---

# Robot Framework with live hooks

There is no helper command to run. You only write files and run `robot`; hooks do the rest:
- **After every Write/Edit of a test file** (`*** Test Cases ***`) its new or changed test lines run in a live RF
  session (open browser, API sessions, variables are kept) and the result is attached to your edit:
  `L12 PASS ...`, `L14 FAIL ...` + message + hints, `NOT RUN (refused before execution: NOT_FOUND | NOT_VISIBLE |
  COVERED)` + `fix:`, and after navigation/failure a page summary (title, url, controls with `=>` suggested selectors,
  iframes). `-> value` shows what an assignment returned.
- **A failing line stays open**: fix that line (or insert lines before it) and only that part re-runs, in the same
  page. Changing a line that already ran restarts the test from the top. `[Teardown]` runs only in the plain run.
- **Broken edits are refused before writing** (unknown keyword, wrong argument count, syntax), with line numbers.
  Outdated syntax (`Run Keyword If`, `[Return]`, `WITH NAME`, `Force Tags`) is modernized automatically.
- A long line may come back as "still running"; its result is attached to your next edit or robot run.

Files the hooks keep up to date (Read / Grep them):
- `.rf/state/controls.txt` every field/button/link: label, id, name, data-test, hidden?, native/custom, `=>` selector
  (iframe content listed with its `frame >>> ` prefix); `.rf/state/aria.yaml` texts/roles (one section per iframe);
  `source.html`, `screenshot.png`, `page.txt`.
- `.rf/docs/<Library>.md` one line per keyword `Name(args) -- short doc` (Browser, BuiltIn, RequestsLibrary, ...);
  `.rf/docs/project.md` project resources/libraries. Search: `grep -i "select option" .rf/docs/*.md`.

## New test (web or API)
1. Write the file with `*** Settings ***` (`Library    Browser`, `Suite Setup    New Browser    chromium    headless=True`)
   and the first lines (`New Page    ${URL}`); read the page summary / `.rf/state/controls.txt` before choosing selectors.
2. Add a few lines per edit (or the whole test at once) and read each result; fix what fails. Read values from the
   page instead of guessing them.
3. Final proof: `robot -d results tests/x.robot` (plain run, fresh browser). Its failures are summarized for you and
   the first failing test is reproduced live with its page saved. At the end of your turn a gate asks for this run if
   a test file changed since its last green plain run.

## Repair an existing failing suite (references/debug.md)
1. `robot -d results path/suite.robot` -> one line per failure + live reproduction stopped at the first failing line.
2. Fix that line with your edit tool (state files show the page at the failure) -> it re-runs from there. Editing a
   line of another failing test runs that test.
3. Never delete/skip tests or weaken assertions. Finish with a green plain `robot` run.
Results only (no browser needed): `robotcode results summary|show --failed|log "*Name*" -o results/output.xml` (references/results.md).

## Rules
- PORTABLE: the suite must pass with plain `robot <file>` from the project root. Import project libraries/resources by
  path: `Library    ${CURDIR}/../lib/MyLib.py`, `Resource    ${CURDIR}/common.resource`; never -P/PYTHONPATH.
- Separate keyword and arguments with 4 spaces. A cell starting with `#` is a comment: write `\#id`, `id=x`, `css=#x`.

## Browser facts (verified)
- iframe: `id=frame >>> id=field` (no select-frame keyword). Open shadow DOM: css/id/text pierce it, xpath does not.
- Stable selectors first: `data-test=x`, `id=x`, `role=button[name="Save"]` (exact name), `text="Save"` (exact;
  `text=Save` = substring). ARIA lines are not selectors. Strict mode: >1 match fails -> unique or `>> nth=0`.
- Values do not wait: `${t}=    Get Text    id=x` returns the current value; with an operator (`Get Text    id=x    ==    Done`)
  it retries only ~1 s. Async UI: `Wait For Condition    Text    id=x    contains    Done    timeout=15s` or
  `Wait For Elements State    id=spinner    hidden    timeout=15s`. Never Sleep.
- Hidden styled radio/checkbox: click its label (`Click    label[for="opt"]`), assert `Get Checkbox State    id=opt    ==    checked`.
  Native `<select>`: `Select Options By    id=x    label    Oslo`; custom dropdown: click it, then `role=option[name="Oslo"]`.
  Cookie banner/overlay: close it first (force=True would click the overlay).

More: references/browser.md (locators, iframes, shadow DOM), explore.md (widgets, dates, dialogs, new tabs),
waits.md, debug.md, requests.md, results.md, selenium.md.
