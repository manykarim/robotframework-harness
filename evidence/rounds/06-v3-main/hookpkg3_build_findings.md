# hookpkg3 — tuned skills+hooks RF harness (build report, 2026-10-09)

Source: v3 builder subagent report (saved by the coordinating session). Package `ab/hookpkg3/` (`rfharness3`; `RFH3_` env vars; `.rf/{hook3,exec3,lint3}`; side by side with v1/v2, both untouched). Round-6 diagnosis (`round6/diag/findings.md`) integrated and took precedence over the brief (2.5 s live timeout, page stable after 2 s, ≤ 3 controls, budgets 250/700, no per-step settle). Simulation 188/188; 6 real sessions passed, 0 orphans, credentials deleted.

## Changes vs v2
1. **Failure classification from the Playwright log before any re-check** (`pwlog.py`): COVERED, NOT_VISIBLE, DISABLED, ANIMATING, AMBIGUOUS, NO_OPTION, WRONG_ELEMENT, PRESENT, MISSING, IN_IFRAME; COVERED keeps "… intercepts pointer events" verbatim and names the input's label (or the covering element); pre-check catches small styled `<span>`s over radios/checkboxes (fail fast); SLOW only for absent→present; no re-check when the element exists.
2. **Adaptive timeouts** (`livetmo.py`): element steps 2.5 s; navigation/`Wait*` normal; page stable = DOM quiet 2 s + no pending fetch/XHR/long timer + page ≥ 6 s old → immediate MISSING; after a real SLOW the page is never shortened again and the site timeout = min(normal, 1.5 × observed); learned values in `.rf/exec3/timeouts.json` (REPL listener reads them); nothing leaks into suites.
3. **No hidden waits between steps**: capture only on failure and after the last step of an edit; only settle (≤ 1.5 s) at end of run; failing plain run that passes in live reproduction → "NOT reproduced … timing race", reproductions stop for the session.
4. **Lean output** (`leanfmt.py`): 250 chars success / 700 failure (OpenCode 600, NEXT first), mandatory parts kept; success = one line per passed block + one page line; failure = failing line, error, verdict, actual vs expected for value checks, ≤ 3 nearby controls, NEXT; once per session: keyword signature (per keyword), hints, page-file list, import notes.
5. **Page/docs files**: `page.txt` = visible page text (≤ 4 KB); keyword docs generated on demand when the agent reads `.rf/docs/kw/X.md`.
6. **Loop hint**: one line ≤ 200 chars, once per failure signature, failure-type specific.
7. **Denials only for certain errors** (ModelError-type parse errors, removed tests, new failure-hiding, installs); unknown keyword, arg count, `-P`/PYTHONPATH, Sleep, big reads, fewer assertions → allow + one-line warning.
8. Kept: guards, REPL format enforcement, OpenCode fixes; SKILL.md updated (76 lines).

## Files (v2 → v3 lines)
hook 1377→1796, execd 961→1118, livetmo 199→383, leanfmt (new) 435, pwlog (new) 89, rthooks 519→547, kwdoc 243→291, pagestate 440→460, listener 201→236. `verify/`: verify_hooks.py (946), compare_ctx.py (new), agents_run.py (`--pkg=v2|v3`, `web3` task), site3/, repair3/, `runs/web3_v{2,3}.json`. `harness.py` +83 (arm `hookpkg3`, metrics: context chars per edit ok/fail, captures + skipped, re-checks by verdict incl. instant MISSING, adaptive timeout changes, failure classes, denials vs warnings, race reproductions; v1/v2/v3 contamination markers, v1 marker `rfharness(?![23])`). `analyze_hooks.py` +47 (v3 table; rounds 4/5 reports unchanged; `--arms mcp,hookpkg2,hookpkg3` works). `check-scenarios` IDENTICAL ×4.

## Latencies / context
PreToolUse median 110–150 ms; SessionStart ~120 ms; SessionEnd 0.3–0.4 s; page capture median 117–168 ms; per-step DOM probe 6.5 ms (v2 source hash 14.6 ms, repeated during settles).
Same scripted Claude session v2 vs v3: chars per edit mean/max 887/1214 → **277/581 (−69%)**; failing plain run 1541 chars / 14.7 s hook → 654 / 6.8 s; total edit hook time 19.4 → 16.9 s.

## Real sessions (local `web3`: covered radio/checkbox, payment iframe, confirmation after 4 s, + failing-suite repair; 1 run per cell)
| agent | v2 | v3 |
|---|---|---|
| claude-haiku-4-5 | PASS, 124 s, 13 calls / 15 turns, 1,382 B/edit, 1 false SLOW (covered radio → "add a wait") | PASS, 126 s, 19 calls / 21 turns, 422 B/edit, 2 genuine MISSING; classes covered 2, absent 2, value 2 |
| codex luna@low | PASS, 60 s, 4 calls, 2,147 B/edit | PASS, 52 s, 4 calls, 315 B/edit |
| opencode M2.5 | PASS, 208 s, 17 calls, 465 B/edit, 2 false SLOW + 1 MISSING | PASS, 201 s, 26 calls, 312 B/edit, 1 MISSING; classes covered 1, value 2 |
Harness smoke (Claude, hookpkg3): pass, uncontaminated, 308 chars/edit, one kw doc on demand.

## Self-healing runner
`ab/harness/run_ab_resilient.sh TAG ARMS REPS [AGENTS] [SCENARIOS] [extra]`: every start backs up results, drops aborted + Claude auth-failure rows, checks Claude auth (exit 2 on failure), runs the harness (`--max-turns 80 --browser-concurrency 3`), cleans and re-runs up to 3 passes; exit 0 complete / 1 incomplete (restart); per-tag lock; forwards SIGTERM. Tested under systemd with a fake batch (SIGTERM → restart → resume → exit 0; auth failure → exit 2, no restart). Launch: `systemd-run --user --unit=<name> -p Restart=always -p RestartSec=60 -p "RestartPreventExitStatus=0 2" -p StartLimitIntervalSec=0 --working-directory="$PWD" --setenv=PATH="$PATH" --setenv=HOME="$HOME" ./run_ab_resilient.sh <tag> <arms> <reps>`.

## Known gaps
Browser 19 has no init scripts → load-time timers invisible; missing element on a page < 6 s old waits until 6 s; element appearing > 6 s after load on a quiet page judged MISSING; per-site learning coarse (all file:// = one site); after a SLOW, MISSING on that page waits the full timeout; live session wraps fetch/XHR/setTimeout (plain runs don't); end-of-run settle ≤ 1.5 s/edit on pages with periodic timers; "expected text on page" is a substring check; Codex/Copilot transcripts don't show hook text; Selenium and Copilot not run live. Left: `~/.cache/rfharness3` (948 KB).
