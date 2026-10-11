# Upstream evidence: robotcode CLI experiments (summary only)

**Source:** the author's `robotcode-experiments` repository ("robotcode CLI experiments"). At import time
(2026-10-11) it had no remote and no commit, so there is no URL or commit to pin. Once it is published, this file
should link to its published location and name the commit.
Owner decision of 2026-10-11 (design D9): only this findings summary is imported. The raw logs, suites and
results stay in that repository.

**Files summarized:** `README.md`, `reports/robotcode-cli-report.md` (646 lines), `reports/robotcode-defects.md`
(319 lines), `reports/github-issues-posted.txt`.

**Date and versions:** 2026-09-26, re-checked 2026-10-09. robotcode 2.7.0, Robot Framework 7.5, Python 3.13.11,
robotframework-browser 20.5.0, robotframework-requests 0.9.7, Linux x86_64.

## What was tested

121 scripted experiments against four public demo systems: Flowline demoshop UI and API
(`https://demoshop.makrocode.de/`), Restful Booker API and Sauce Demo. They covered test discovery, keyword
documentation, stepwise execution (`robotcode repl`), the CLI debugger (`robotcode robot-debug`), result
analysis (`robotcode results`), the `--wrapper` option and AI-agent mode. Every experiment saved its command,
piped input, full output and exit code as an evidence log. Six suites with 29 tests were used, with a known mix
of 24 passed, 4 failed (intentional, tagged `expected-fail`) and 1 skipped.

## Findings

| Feature | Command | Result |
|---|---|---|
| Test discovery | `robotcode discover …` | works |
| Keyword docs | `robotcode libdoc …`, REPL `.kw` / `.doc` | works |
| Stepwise execution | `robotcode repl` | partly works |
| CLI debugger | `robotcode robot-debug` | works; the best feature is the `(rdb)` prompt at a failure with the browser still open |
| Result analysis | `robotcode results …` | works |
| Wrapper | `--wrapper`, profile `wrapper` | works |
| AI-agent mode | automatic / `ROBOTCODE_*_AI_AGENT` | works; piped input gets the plain line-by-line backend |

The report lists 14 limitations. The three most important for agents:
1. The REPL does not create its output directory, so Browser keywords fail with `FileNotFoundError`.
2. `.save` keeps lines that failed, so the saved suite fails too.
3. A runtime `.break "Keyword Name"` with quotes never matches, with no warning.

Also relevant to the harness: the REPL exit code is always 0 and its `output.xml` test is PASS even when a step
failed (fixed on robotcode `main`). RequestsLibrary logs credentials in plain text at INFO, and its
`*args, **kwargs` signatures hide the real parameters.

## Defects filed upstream (2026-10-09)

The defects file counts 11 robotcode defects (D1–D11). It re-verified them against v2.7.0 and against robotcode
`main` at `20c1767`: D7 and D10 are fixed on `main`, and the other nine were filed:

| ID | Defect | Issue |
|---|---|---|
| D1 | REPL does not create the output directory | [robotcode#662](https://github.com/robotcodedev/robotcode/issues/662) |
| D2 | REPL `.save` keeps failed lines | [robotcode#663](https://github.com/robotcodedev/robotcode/issues/663) |
| D5 | `--break-on-failed-test` keyword run raises `IndexError` | [robotcode#664](https://github.com/robotcodedev/robotcode/issues/664) |
| D6 | `--dry` still runs the wrapper | [robotcode#665](https://github.com/robotcodedev/robotcode/issues/665) |
| D8 | missing wrapper exits 1, the same code as a test failure | [robotcode#666](https://github.com/robotcodedev/robotcode/issues/666) |
| D9 | REPL silently ignores test settings such as `[Tags]` | [robotcode#667](https://github.com/robotcodedev/robotcode/issues/667) |
| D3 | quoted `.break "Name"` never matches | [robotcode#668](https://github.com/robotcodedev/robotcode/issues/668) |
| D4 | failed breakpoint condition stops without a hint | [robotcode#669](https://github.com/robotcodedev/robotcode/issues/669) |
| D11 | debugger `.set` cannot create a variable | [robotcode#670](https://github.com/robotcodedev/robotcode/issues/670) |

## How it fed into this project

This study came before the rf-mcp research rounds (`../rounds/`). It established that the robotcode CLI is usable
from agents with piped input, and that the debugger prompt at a failure is valuable. It also produced the list
of REPL traps that the harness's REPL format rules (round 5, `../rounds/05-v2/research/`) and the skill text
work around.
