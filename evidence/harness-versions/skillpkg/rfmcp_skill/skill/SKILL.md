---
name: robotframework
description: Robot Framework test automation with the local `rfmcp` helper - write, debug and repair .robot/.resource tests (Browser/Playwright web UI incl. iframes, shadow DOM, custom widgets; SeleniumLibrary; RequestsLibrary APIs) step by step in a live session, explore unknown web pages, fix failing suites, find keywords and their arguments, validate files, and analyze output.xml results. Use for any Robot Framework task.
---

# Robot Framework with `rfmcp`

`rfmcp` keeps ONE live Robot Framework session (imports, variables, open browser, API sessions) between shell
calls, so you can try keywords against the real app before you commit them to a .robot file. Every command prints
one JSON object; `ok:false` = something to fix: read `msg`, `hints[].try`, `guard.fix`.

## Pick the workflow
| Task | Do | Helper |
|---|---|---|
| New test for a web app / API | Workflow below: look at the live page, write the file, `rfmcp run` it | yes |
| Fix an existing failing suite | `rfmcp guide debug`: plain `robot` run -> read failures -> `rfmcp run FILE --test "Name"` stops AT the failing line with the page open -> inspect, try, edit, re-run -> plain `robot` | yes |
| Questions about results / output.xml | `robotcode results summary\|show --failed\|log "*Name*" -o path/output.xml`, or a short python script with `from robot.api import ExecutionResult` (`rfmcp guide results`) | NO |
| Static edits (rename, refactor, syntax) | edit, then `rfmcp check FILE` (runs without the helper) | NO |

Do not start the helper when you will not execute keywords. `rfmcp stop` is a harmless no-op when nothing runs.

## Rules
- Run `rfmcp` from the project root, one call per shell command, never in parallel or in the background.
- RF line = keyword and arguments separated by 4 spaces, in SINGLE quotes: `rfmcp step 'Fill Text    id=user    ${USER}'`.
  Several lines, IF/FOR blocks or a `'` inside: quoted heredoc `rfmcp step - <<'RF'` ... `RF`.
- `{"status":"running","job":N}` -> `rfmcp wait N`.
- PORTABLE: the final suite must pass with plain `robot <file>` from the project root. Import project libraries
  and resources by path: `Library    ${CURDIR}/../lib/MyLib.py`, `Resource    ${CURDIR}/common.resource`. Never
  rely on `-P`, PYTHONPATH, robot.toml or on anything you only did in the session. The helper and robotcode find
  modules in ./lib and ./resources by name, plain robot does not: `rfmcp check`/`run` report it as `portable`
  with the exact fix.
- Repairing tests: never delete or skip tests and never weaken assertions; fix locators, waits, imports, data.

## Workflow (new test)
1. Open the page and LOOK: `rfmcp step 'Import Library    Browser' 'New Browser    chromium    headless=True' 'New Page    https://app.example'`,
   then `rfmcp state controls` (every field/button/link: label, id, data-test, hidden?, native/custom, `=>` suggested
   selector) and `rfmcp state aria` (texts, roles, one section per iframe). Look again after each page change.
   API: `rfmcp step 'Import Library    RequestsLibrary' 'Create Session    api    http://host'`, then
   `rfmcp step '${resp}=    GET On Session    api    /items'`.
2. Try actions with `rfmcp step`, write the test file with your edit tool, run only the new lines:
   `rfmcp run tests/x.robot` (Suite Setup/[Setup] + body; stops at the first problem; reports file lines).
   - `blocked` = static error, NOT executed -> fix that line. `ran[-1].status` FAIL / NOT RUN -> fix, run again.
   - Only new/changed lines run; `--lines A-B` re-runs lines, `--all` everything, `--rebase` accepts edited earlier
     lines, `--test "Name"` one test. Teardowns run only in the final robot run.
3. Keywords: `rfmcp search "select option in dropdown"`; arguments: `rfmcp doc "Select Options By"` (`--full`, `--lib X`).
4. `rfmcp check tests/x.robot`, final proof `robot -d results tests/x.robot`, then `rfmcp stop`.

## Key facts (Browser library)
- `NOT RUN` + `guard` = refused before execution: NOT_FOUND (no match; inside an iframe it names the
  `frame >>> selector`), NOT_VISIBLE (hidden styled radio/checkbox -> click the label it names), COVERED (cookie
  banner/overlay -> close it first; force=True would click the overlay). Page still loading? repeat or `--no-guard`.
- iframe: `id=frame >>> id=field` (no "select frame" keyword). Open shadow DOM: css/id/text pierce it, xpath not.
- Stable selectors first: `data-test=x`, `id=x`, `role=button[name="Save"]` (exact name), `text="Save"` (exact;
  `text=Save` = substring). ARIA lines are not selectors. Strict mode: >1 match fails -> unique or `>> nth=0`.
- Values do not wait: `${t}=    Get Text    id=x` returns the current value; with an operator
  (`Get Text    id=x    ==    Done`) it retries only 1 s. Async UI: `Wait For Condition    Text    id=x    contains    Done    timeout=15s`
  or `Wait For Elements State    id=spinner    hidden    timeout=15s`. Never Sleep.
- Native `<select>`: `Select Options By    id=x    label    Oslo`; custom dropdowns, styled radios/checkboxes, dates
  relative to today, JS dialogs, new tabs, cookie banners: `rfmcp guide explore`.

## More
`rfmcp guide debug | explore | browser | waits | requests | results | selenium | visual | quoting`;
references/cli.md (all commands and JSON fields), references/examples.md (examples incl. a repair session).
