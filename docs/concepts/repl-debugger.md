# REPL and debugger

A test file runs live and keeps its page, so most agents never need a REPL. For quick experiments, robotcode's REPL and
debugger are available. The harness enforces the format that works for agents.

## Required format

```bash
robotcode repl --plain --no-history -d .rf/out 2>&1 <<'RF'
Library    Browser
New Browser    chromium    headless=True
New Page    file:///abs/path/page.html
${t}=    Get Title
.exit
RF
```

- quoted heredoc (`<<'RF'`), so the shell does not expand `${t}`;
- one statement per line, four spaces between cells, no `...` continuation lines;
- `-d .rf/out`, so outputs stay out of your project;
- every call is a fresh session: `[ FAIL ]` goes to stderr and the exit code is always 0. The harness's
  `[rfh] COVERED/SLOW/MISSING` lines judge failures, as in live runs.

Debugger:

```bash
robotcode robot-debug --plain -d .rf/out --break tests/x.robot:12 tests/x.robot 2>&1 <<'RF'
.where
.pp ${v}
.c
RF
```

## What the hooks do

- **Format card.** The first time the agent starts a REPL or debugger, the harness shows the format above once.
- **Rewrite.** Correctable mistakes are fixed before the command runs, and the agent is told once:
  - an unquoted heredoc;
  - single-space cells;
  - `...` lines;
  - a missing `-d`.
- **Refuse.** Anything that can't be corrected is refused, with the required format in the reason.
- **Short timeouts.** REPL sessions use the same live element timeouts as the live session, so a wrong selector costs
  seconds.
- **Docs on import.** A `Library` line in a REPL call triggers the keyword docs, as a test file does.

The rules come from the round-5 REPL research (`repl_format_rules.json`), see [round 5](../../evidence/rounds/05-v2/).
