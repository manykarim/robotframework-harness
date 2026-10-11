# Hints on robotcode output — findings (2026-10-01)

Source: hints subagent report (saved by the coordinating session; the harness blocks subagent report files). Generated tables: `results/coverage.md`, `results/parser_eval.md`, `results/stress_eval.md`; raw data `results/*.json`, `runs/`.

## Verdict
rf-mcp's hint logic is portable. `generate_hints`, plugin failure hints and link/image guidance are pure functions of (keyword, raw args, error text, library list), and robotcode output supplies all four. Caveats: ~¼ of native Browser diagnoses come from the *live* pre-validation gate, and hint examples reference rf-mcp tools and must be re-rendered for robotcode.

## Key numbers (44-mistake corpus: Browser on saucedemo/demoshop, RequestsLibrary on restful-booker, BuiltIn/Collections/Process; each run in `robotcode repl` plain and `-k`, in repl-server, and in native rf-mcp in-process)
- **32/33 identical hints** (byte-identical incl. top-1 "minimal" hint) where native failed in keyword execution: parsed `robotcode repl -k` output → real `generate_hints`. 21 have ≥1 hint, 11 have none in both. The 1 diff (M40) is RF 7.3.2 vs 7.5 message wording; native's hint there is a false positive.
- Error text alone fires only **5/21** hint-bearing cases; 16 need keyword/args/library context.
- Plain REPL output + the agent's own input script: **20/21**.
- Live pre-validation (class c): **7/44**; text rules still give a useful hint for 6/7 (better for 3 invalid-selector cases).
- Native *prevents* 4/44 via managed search order / auto-import / installed lib (class env); robotcode surfaces them.
- Neither system hints: **11/44** (rule gaps, not portability): wrong arg count, bad named arg converted into positional enum, Browser assertion mismatch, wrong expected_status, bad JSON key, int-vs-string compare, variable-name typo, bare named query params, old `:FOR`.
- Classes: a=16, a0=5, c=7, env=4, gap=11, diff=1.

## Parser reliability
| Source | Keyword+args extraction |
|---|---|
| repl-server JSON-RPC `executeCell` / `results log` JSON | exact, 43/43 |
| `repl -k` text | 43/43 corpus; 18/18 multi-failure stress (after fix: nested resource failure prints FAIL once at the innermost keyword → propagate to top-level step) |
| plain REPL text | no keyword/args; correlation to input lines heuristic: 15/18 with positional anchors, 3/18 without |

## Output facts for the design
- FAIL lines go to **stderr** → agents must use `2>&1`.
- REPL exit code always 0; REPL output.xml test is PASS even with failed steps.
- Structured outputs (output.xml, repl-server) truncate long messages ("Message content over the limit has been removed"); console text keeps them full.
- RequestsLibrary logs credentials/tokens at INFO.
- repl-server exits with a cosmetic traceback. robot-debug prints `* exception Owner.Kw (file:line) — Keyword failed: msg` (parses cleanly).

## Rule portability
- (a) unchanged from text — 18 rules: Evaluate, RequestsLibrary shape, dict/method access, invalid selector, Evaluate JavaScript shape, Process `-x=y`, link guidance, ranker, deprecation; keyword ambiguity / not-found are text-only.
- (b) small adaptation — ~17: library-aware Browser/Selenium/Appium element rules need the library list (from `-k` owners or `Import Library` lines); Requests/PlatynUI plugins need the owner; examples re-rendered. Of 85 hint examples: 68 already RF lines, 7 map to `robotcode libdoc`/`.kw`, 10 are `get_session_state` calls.
- (c) needs live state — 4: pre-validation → `Get Element States <sel>`; inspect-page → `Get Aria Snapshot body` / `Get Element Count` (verified Browser 20.5); recovery/evidence → emitted RF lines.
- (d) not portable — 3: control-structure hints (REPL has real FOR/IF/TRY), ADR-014 memory recall (server state), `pre_validate_timeout` hint.

## Proposed remote hint-service API
- Input: `failures[]` = `{keyword, owner, args (raw, unresolved), error, location?}` + optional `input_script`, `libraries`, `versions`, `live_state`, `detail_level`; raw console text only as fallback.
- Output: `hints[]` with runnable `rf_lines` and robotcode `commands`; `follow_up[]` (RF lines that gather live state, returned as `live_state`); `lint[]` (pre-execution checks on the input script).
- Existing hint code reusable as-is (emulated pipeline matched native 32/33).

## Bugs found in existing rf-mcp hints (native too)
1. "Element not found" hint fires as noise on nearly every Browser error (every Playwright call log contains `waiting for locator(`).
2. Invalid-selector check misses Playwright's "is not a valid selector".
3. `link=` role-prefix hint suggests invalid `css=link:text-is(...)`.
4. "headers must be a dictionary" rule too broad (M40 false positive).
5. M07: RF captures `button=Login` as Click's `button` named arg; native pre-validation masks it.

## Open questions
1. Keeping the browser alive for follow-up steps (piped REPL loses state at exit): repl-server, robot-debug, or pre-appending "on failure run these lines".
2. Client-side failure extraction vs server parsing raw output (secrets, blobs).
3. Ship libdoc indexes to close gaps (arg count, missing import)?
4. Run text rules as a pre-execution lint?
5. RF/Browser version matrix for message patterns.

## Environment side effects
- `rfbrowser init --skip-browsers` in the worktree venv; native runs used `PLAYWRIGHT_BROWSERS_PATH=~/.cache/ms-playwright`.
- Native runs wrote `.robotmcp_artifacts/` into the worktree root → moved to `runs/native_artifacts/`.
