# rfmcp command reference

| Command | Does | Notes |
|---|---|---|
| `rfmcp start [-v name:value] [-P path] [--idle 1800]` | starts the live RF session in the background | idempotent; exits itself after 30 min idle |
| `rfmcp stop` / `rfmcp status` | stop (closes browsers, kills leftovers) / show state | `orphans:0` expected; no-op when nothing runs |
| `rfmcp step [--no-guard] '<line>' ['<line2>' ...]` | runs RF line(s) in the live session | stop at first failure |
| `rfmcp step - <<'RF' ... RF` | lines from a quoted heredoc | for IF/FOR blocks or `'` in a line |
| `rfmcp run FILE [--new\|--lines A-B\|--all\|--rebase] [--test NAME] [--force] [--no-check] [--no-guard]` | runs lines of a .robot file you edited (or an existing failing one) | default `--new`; static check first; stops AT the first failing line, page stays open |
| `rfmcp check FILE` | static errors without running | robotcode analyzer + robocop agent rules + portability; does NOT start the helper |
| `rfmcp search "<what>" [--lib L] [-n 5]` | keyword search over imported libraries | `--lib` indexes a library not imported yet |
| `rfmcp doc "<Keyword>" [--full] [--lib L]` | signature + short (or full) doc | typo -> `did_you_mean` |
| `rfmcp state controls\|aria\|source\|url\|screenshot [--selector S]` | page inspection, files under `.rf/state/` | controls: fields/buttons with stable attributes + `=>` selector; aria: one section per iframe |
| `rfmcp vars [NAME ...]` | variables created in the session | secrets redacted |
| `rfmcp wait JOB` | result of a step that ran > 25 s | |
| `rfmcp guide [topic]` | debug, explore, browser, selenium, requests, results, waits, visual, quoting | |

## Result fields
- `step`: `{"ok", "steps":[{"kw","status":"PASS|FAIL|NOT RUN","ret","msg","hints":[{"title","msg","try":[...]}],"guard"}], "ms"}`
  - `ret` = return value (assign it with `${x}=    Keyword ...`), `console` = Log To Console output.
  - `NOT RUN` + `guard` = the Browser probe refused the step before execution; `guard.fix` says what to do:
    `NOT_FOUND` (no match after 1.5 s; 5 s for `run` lines and later lines of one `step`; `inside_iframe` = working
    `frame >>> selector`), `NOT_VISIBLE` (hidden element; `click_instead` = its visible label), `COVERED` (an
    overlay covers it; `overlay_buttons` = buttons to close it), `INVALID_SELECTOR`. `--no-guard` skips the probe.
- `run`: `{"ok","file","ran":[{"line","kw","status",...}],"blocked":{"line","errors":[...]},"hint","file_errors"}`
  - `blocked` lines were NOT executed. `file_errors` = errors in Settings/Variables/Keywords sections.
  - `dropped_static` = static warnings the live session proved wrong (e.g. variable set at run time).
  - `portable` = imports that work in the session but fail in a plain `robot` run, each with the fix.
- `check`: `{"ok","errors":[{"line","code","msg"}],"robocop":["L3 W DEPR07 ..."],"portable":[{"line","msg","fix"}],"fix"}`
- `state controls`: one line per control: `tag "accessible name" id=.. name=.. data-test=..  => selector  (notes)`;
  notes flag HIDDEN inputs (click the label shown), `native select [options]`, `custom dropdown`, date formats,
  links that open a new tab.
- Exit codes: 0 ok, 1 failed, 3 no helper, 4 still running (`rfmcp wait JOB`).

## Post-edit hook
After you edit a `.robot`/`.resource` file, the hook may auto-fix outdated syntax (Run Keyword If -> IF,
[Return] -> RETURN, Force Tags -> Test Tags ...) and report static errors and NOT PORTABLE imports. If it says the file was rewritten,
re-read the file before editing it again.

## Files
`.rf/` (helper state, journal, page state files). A hidden `.<name>.live.resource` appears next to a test file
while `rfmcp run` uses it; it is removed on `rfmcp stop`. Do not commit `.rf/`.
