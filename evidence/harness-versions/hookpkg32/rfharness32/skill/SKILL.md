---
name: robotframework
description: Robot Framework test automation - write, debug and repair .robot/.resource tests (Browser/Playwright web UI incl. iframes, shadow DOM, custom widgets; SeleniumLibrary; RequestsLibrary APIs), explore unknown web pages, fix failing suites, find keywords, analyze output.xml. Hooks execute your test lines live after every edit and attach the results. Use for any Robot Framework task.
---

# Robot Framework with live hooks

No helper command: you write files and run `robot`; hooks do the rest.
- **Every Write/Edit of a test file** runs its new/changed lines in a live RF session (page, sessions, variables kept)
  and answers briefly: `L10-L16 PASS (7 lines)` + the page, or the failing line, the error, a `verdict:`, the nearest
  controls and a `NEXT:` step (some sessions also get a controls list after each new page, the keyword's signature and
  a `hint:` with every failure). A failing line stays open: fix it (or insert lines before it) and only that
  part re-runs. Changing an executed line restarts the test (fresh browser context). `[Teardown]` runs only in the
  plain run. Only edits that break the file's syntax/structure, delete tests or hide failures are refused; other
  static findings come as a one-line warning and the live run decides.
- **Verdicts** (live element timeout 2.5 s; navigation/`Wait*` keep the normal one; never in your files):
  `COVERED` (another element, e.g. a styled `<span>` over a radio, intercepts the click -> click its label / the element
  on top; waits and force do not help), `NOT_VISIBLE`, `DISABLED`, `ANIMATING`, `AMBIGUOUS` (several matches),
  `PRESENT` (element exists, not a timing issue), `MISSING` (no match: wrong selector or iframe), `IN_IFRAME`
  (use the given `frame >>> sel`), `SLOW` (was absent, appeared late: the page keeps the normal timeout; a wait is only
  suggested when close to the limit). Value checks show `actual ... vs expected ...`: fix data/steps, not timing.

## Files the hooks write (Read / Grep them; never Read whole huge files)
- `.rf/state/latest/` after the last executed step of an edit and on failures: `page.txt` (url, title + the page's
  VISIBLE TEXT), `controls.txt` (every control with label/id/name/data-test, hidden?, `=>` suggested selector, iframe
  controls with `frame >>> `), `aria.yaml`, `source.html`, `screenshot.jpg`; history `.rf/state/step-NNN-<keyword>/`.
- `.rf/docs/<Library>.md`: one line per keyword (`grep -i "select option" .rf/docs/*.md`), `<Library>.full.md`: full
  docs; reading `.rf/docs/kw/<Library>.<Keyword>.md` (path given with a failure) writes that keyword's full doc.

## New test (web or API)
1. Write the file with `*** Settings ***` (`Library    Browser`, `Suite Setup    New Browser    chromium    headless=True`)
   and the first lines (`New Page    ${URL}`); pick selectors from `.rf/state/latest/controls.txt`. In a user journey
   reach pages by clicking like a user (no `Go To` deep links).
2. Add a few lines per edit and read each result. Read values from the page instead of guessing.
3. Final proof: `robot -d results tests/x.robot`. Failures are summarized and the first one reproduced live (if it
   passes live it is a timing race: wait for the needed state before the failing step); a gate at the end of your turn
   asks for this run if a test file changed since its last green plain run.

## Repair an existing failing suite (references/debug.md)
1. `robot -d results path/suite.robot` -> one line per failure + live reproduction stopped at the first failing line.
2. Fix that line with your edit tool (state files show the page at the failure) -> it re-runs from there.
3. Never delete/rename/skip tests or silence failures (refused) or weaken assertions; no `Sleep`. Finish with a green
   plain run.
Results only: `robotcode results summary|show --failed -o results/output.xml` (references/results.md).

## REPL / debugger (optional; a test file runs live too and keeps its page)
```
robotcode repl --plain --no-history -d .rf/out 2>&1 <<'RF'
Library    Browser
New Browser    chromium    headless=True
New Page    file:///abs/path/page.html
${t}=    Get Title
.exit
RF
```
Quoted heredoc, one statement per line, 4 spaces between cells, no `...` lines, `[ FAIL ]` on stderr, exit code
always 0, new session per call; `[rfh32] COVERED/SLOW/MISSING` lines judge failures. `robotcode robot-debug --plain -d .rf/out
--break tests/x.robot:12 tests/x.robot 2>&1 <<'RF'` then `.where` / `.pp ${v}` / `.c` (bare `.break` args).

## Rules
- PORTABLE: plain `robot <file>` must pass. Import project code by path (`Library    ${CURDIR}/../lib/MyLib.py`,
  `Resource    ${CURDIR}/common.resource`); never -P/PYTHONPATH (warned); pip/playwright installs are refused.
- Separate keyword and arguments with 4 spaces. A cell starting with `#` is a comment: write `\#id`, `id=x`, `css=#x`.

## Browser facts (verified, Browser 19.12 / 20.5)
- iframe: `id=frame >>> id=field` (no select-frame keyword). Open shadow DOM: css/id/text pierce it, xpath does not.
- Stable selectors first: `data-test=x`, `id=x`, `role=button[name="Save"]` (exact name), `text="Save"` (exact;
  `text=Save` = substring). ARIA lines are not selectors. Strict mode: >1 match fails -> unique or `>> nth=0`.
- Values do not wait: `${t}=    Get Text    id=x` returns the current value; with an operator it retries only ~1 s.
  Async UI: `Wait For Condition    Text    id=x    contains    Done    timeout=15s` or
  `Wait For Elements State    id=spinner    hidden    timeout=15s`.
- Hidden styled radio/checkbox: click its label (`Click    label[for="opt"]`), assert `Get Checkbox State    id=opt    ==    checked`.
  Native `<select>`: `Select Options By    id=x    label    Oslo`; custom dropdown: click it, then `role=option[name="Oslo"]`.
  Cookie banner/overlay: close it first (force=True would click the overlay). Styled radio/checkbox covered by a
  `<span>`: click the `label[for="id"]`, or `label:has(#id)` when the input sits inside its label (no `for=`);
  never a positional `>> nth=` pick.

More: references/{browser,explore,waits,debug,requests,results,selenium}.md.
