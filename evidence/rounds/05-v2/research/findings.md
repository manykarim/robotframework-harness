# Round 5 — REPL/debugger hook research for hookpkg v2 (2026-10-08)

Source: round-5 research subagent report (saved by the coordinating session). Evidence in this folder: `repl_format_rules.json` (40 rules), `repl_format/{repl_lint.py, format_card.txt}`, `timeouts/results.json`, `capture/`, `docs/` (incl. `failure_rules.json`, 15 regexes), `hooks_survey/hook_ideas.json`, `diag/`. ~95 REPL cases verified live (RF 7.5, robotcode 2.7); linter 34/34; 15 rewritten commands ran clean (14/15 originals wrong, 3 silently).

## 1. REPL / robot-debug input format
- Exit codes: REPL always 0; robot-debug = number of failed tests (253 after `.abort`).
- Shell: `[ FAIL ]` on stderr (pipe without `2>&1` drops it); unquoted heredoc turns `${x}` into empty; no `--plain` on a real TTY without agent env → hang (killed at 25 s).
- Output dir: missing `-d` ≈ 16 s per Browser keyword; relative `-d` resolves from the project root (nearest robot.toml / pyproject.toml / .git).
- Statements: single spaces → whole line one keyword name; `...` lines run as separate statements; blank line inside a block breaks it; block without END silently runs nothing; markdown fences / section headers → extra FAIL lines; `*** Keywords ***` cannot define keywords; `[Setup]` etc. silently ignored; bare `${x}` → "Keyword name cannot be empty"; return values print only when assigned (cut ~200 chars). Harmless: CRLF, tabs, indentation, `Run Keyword If`.
- File argument: all or nothing (one syntax error → nothing runs). Each invocation is a fresh session.
- Dot-commands: `.kw` exact name (case-insensitive, `Lib.Kw` ok) or substring search; quoted name finds nothing; `.doc` only imported library/resource; `exit`/`.quit` end, `quit`/`.q` don't.
- robot-debug: `.break "Name"` with quotes never matches; conditions evaluated at the call site; `FOR` and `Library X` don't work at `(rdb)` (use `Import Library`); `.vars` Local empty inside keywords (use `.pp`); EOF continues the run; `--break-on-failed-test` → IndexError.

Format card (1,010 B, `repl_format/format_card.txt`; inject via Claude PreToolUse additionalContext, else deny reason / first PostToolUse output):
```
RF REPL format:
mkdir -p out && robotcode repl --plain --no-history -d out <<'RF' 2>&1
Library    Browser
${t}=    Get Title
RF
- Quote the heredoc ('RF') or the shell eats ${vars}. 2>&1: [ FAIL ] goes to stderr. Exit code is always 0.
- One statement per line, 4 spaces between cells. No `...` lines: keep all args on one line.
- FOR/IF/WHILE/TRY end with END, no blank line inside; unclosed blocks run nothing.
- No *** sections ***, test names, [Tags]/[Setup], keyword definitions (use Import Resource).
- Only assigned values print. A failure doesn't stop later lines: fix the first FAIL.
- Each call is a new session: start with Library/New Browser/New Page.
- .kw <name or text> docs/search, .doc <imported lib>, .vars --user, .exit
robotcode robot-debug --plain -d out x.robot <<'RF' 2>&1 pauses at the first failure:
.where .pp ${v} .s .n .c; keywords run live (=> value), one line each, no FOR; Import Library.
.break Kw Name (no quotes) stops at the call: conditions see caller vars. EOF = continue.
```

## 2. Timeouts (`timeouts/results.json`)
- Missing locator time-to-fail: Browser 10.1 / 2.1 / 1.1 s at 10 / 2 / 1 s timeout; Selenium `Wait Until*` same.
- At 2 s: element appearing after 1.5 s passes; at 4 s and 8 s falsely fails at 2.07 s.
- Browser timeout (`Set Browser Timeout` / import `timeout=`) covers element waits AND navigation; assertion retry = min(retry setting, timeout); `Get Element Count` never waits (safe probe); failed `Go To` ≈ 2× timeout (failure screenshot); `Set Selenium Timeout` only `Wait Until*`, implicit wait every lookup.
- Policy: REPL-only listener via `ROBOT_OPTIONS` → 2 s element waits, normal navigation timeout; after a locator failure one re-check: page stable ≥ 5 s → "wrong locator" (2.1 s vs 10.1 s); else poll element count until 5 s after the page change ("appeared after 4.2 s; add `Wait For Elements State … timeout=10s`"); probe iframes; 10 s window for known-slow apps. Listener inert under `robot`/`robot-debug`; `.save` copies agent-typed timeouts → hook flags agent-typed timeout changes.

## 3. Page capture (`capture/`)
URL+title 3–7 ms; page source 5–41 ms; ARIA snapshot 12–292 ms (`Get Aria Snapshot mode=ai` covers iframes + shadow DOM); one-call controls inventory 13–37 ms; PNG 56–92 ms (JPEG larger on text-heavy pages → don't). Dedup: URL + SHA-1(source) (13–16 ms). Layout `.rf/state/step-NNN-<kw>/{url, source.html, aria.yaml, controls.tsv, meta.json}` + `latest/` + `history.tsv`, keep last 30. Inline 0.36–0.53 KB controls grouped by role/name with selector; on locator failure grep the selector against `controls.tsv`. Hazard: ARIA snapshot floods REPL stdout (~4,200 lines on a large page).

## 4. Keyword docs (`docs/`)
`robotcode libdoc … show` 1.1–1.45 s/keyword; wrong name → exit 0, empty output. In-process cache: Browser 0.43–0.51 s first build, 0.1–3 ms/lookup; key by package version + import args (resources: path + mtime). On failure inline `Lib.Kw(args=defaults)` + first sentence + file pointer; fuzzy near-miss names. `failure_rules.json`: 15 verified failure-message regexes.

## 5. Top 10 hook ideas (`hooks_survey/hook_ideas.json`; prototype detectors 26/26)
| # | Idea | Event | Trigger | Action |
|---|---|---|---|---|
| 1 | Loop breaker | Post / PostFailure | same failure 3× without a green run | inject "inspect live state, change one thing" once |
| 2 | Wait-strategy guard | PreToolUse | edit raises a timeout / adds `Sleep` / force click | context; deny a new `Sleep` once |
| 3 | Failure-class hints | Post | iframe, strict-mode, covered, "No keyword" | hint ≤ 600 chars |
| 4 | Debugger offer | Post on `robot` | same test fails twice | ready-made `robot-debug` command |
| 5 | Environment card | SessionStart / compact | start or compaction | libraries, profiles, resources, tests |
| 6 | REPL format enforcer | PreToolUse Bash | `robotcode repl` / `robot-debug` | `repl_lint.py` fixes + card |
| 7 | Big-file steering | Pre / Post | reading output.xml, logs, page source | point to `robotcode results` / grep |
| 8 | Test-tampering guard | PreToolUse (debug tasks) | deleted tests/assertions, Ignore Error, Skip | deny once |
| 9 | Install / PYTHONPATH guard | PreToolUse Bash | pip, playwright install, `-P` | deny |
| 10 | Stop gate v2 | Stop | changed tests without green run | block; give up on a failure seen twice |
Loop detector fired in 36/60 OpenCode sessions (pass 0.25 vs 0.62 without; correlation). No agent used the REPL or debugger unprompted in 180 sessions.

## 6. Diagnosis: OpenCode regression + Claude "errors" (`diag/`)
OpenCode failed journey checks, not robot runs: 6/9 explore sessions deep-linked via `href=` values from the controls list the hook injected (after failed clicks); restarts reused the same browser context → cart/cookie state piled up (19–36 restarts/session); 35.6 edits/session vs 11.1 in the CLI arm, ~37k chars hook output; misleading denials (e.g. "No keyword" when `*** Keywords ***` header missing); plugin bugs: SessionStart note never delivered, `spawnSync` blocks OpenCode ~5 s per edit. Ruled out: ignored hook output, throw-denial derailing, Stop misfires.
Fixes (ordered): hide same-origin hrefs inline + warn on deep links; fresh browser context per restart; no restart for probe-only changes; root-cause denial messages; ~600-char cap with a `NEXT:` line; retry-loop guard; plugin: deliver SessionStart note, async spawn, skip screenshot reads for text-only models.
Claude "agent-side errors": all 10 are `error_max_turns` (81 vs cap 80); 9 skillpkg, 1 hookpkg → harness should label "turn cap".
