# hookpkg32 (v3.2): targeted fixes from the v3.1 interim failures (build report, 2026-10-10)

Built by the coordinating session. `ab/hookpkg32/` (`rfharness32`, `RFH32_`, `.rf/{hook32,exec32,lint32}`, plugin
`rfharness32.js`, `[rfh32]` markers) is a side-by-side copy of v3.1. hookpkg31 stays untouched because the v3.1 runs use
it.

## Evidence that drove v3.2 (v3.1 interim, about 30% of the cells)

1. **Covered radio with no usable target.**
   - Where it shows: tricentis_quote, "form fields driven: missing 'platinum'" (Codex v3.1, Qwen v3.1).
   - The live COVERED feedback said `covered by <span class="ideal-radio">` plus "click the visible label". The nearest
     controls were only the sibling radios.
   - Cause: the Tricentis price radio sits inside a `<label class="choosePrice">` with **no `for=` and no text**. The
     covering `span.ideal-radio` is not unique. So both the label path and the cover path of `_COVER_JS`/`_PROXY_JS`
     returned nothing.
   - What agents did instead: improvised `Click  css=label.choosePrice >> nth=2`. It works, but it is positional and
     brittle, and the journey grader does not credit it.
   - The controls list also suggested `=> id=selectplatinum`, which leads straight into COVERED.
2. **Read loop, Gemini 3.8 Flash only.**
   - Gemini made about 71 Reads per session, with up to 35 in a row (`source.html` paged with offset/limit, the test
     file re-read). It made 5 edits and hit the 80-turn cap in 9 of 10 cells (both arms 0/5).
   - Every other model averaged 0.4–6 Reads per session.

## Changes vs v3.1

- **`pagestate._CONTROLS_JS`.** A visible radio/checkbox whose centre lies inside a later sibling's rect (geometric:
  works off-screen, never scrolls) is marked `covered`. Its click target is chosen in this order:
  1. `label[for=…]`;
  2. else `label:has(#id)`, when unique;
  3. else `css=#id + tag.cls`, when unique.

  The controls row now reads, for example:
  `=> label:has(#selectplatinum)   (styled input covered by <span class="ideal-radio">: click its label …; assert on the input: Get Checkbox State    id=selectplatinum    ==    checked)`.
  The rich formatter maps this note to "styled: click this label".
- **`rthooks._COVER_JS` (guard path) and `execd._PROXY_JS` (Playwright-log path).** Both fall back to
  `label:has(#id)` when the wrapping label has neither `for=` nor text, and to a `#id + tag.cls` / `#id ~ tag.cls`
  cover selector when it resolves to exactly the covering element.
- **`hook.py` read-streak nudge.** `READ_STREAK_AT=8` (`RFH32_READ_STREAK_AT`, 0 disables it).
  - The counter lives in the session store, only in harness projects.
  - Any edit or shell call resets it.
  - At exactly 8 and 16 consecutive Reads, the agent gets one non-blocking note: "grep controls.txt (not source.html),
    write the next 2-4 lines; the test file is unchanged since your last edit". It never overrides a deny.
  - Logged as `guard=readstreak`.
- **SKILL.md** (78 lines): covered styled input → `label[for="id"]`, or `label:has(#id)` when the input sits inside its
  label; never a positional `>> nth=` pick. This is generic CSS guidance with no fixture text.
- **Harness.**
  - New arm `hookpkg32`, with `hookpkg32_usage` = v3.1 metrics + `read_streak_nudges`.
  - The v3 marker is tightened to `rfharness3(?![12])`. This is identical on existing transcripts.
  - `.rf/hook32` is added to the contamination checks.
- **Analyzer.** v3/v3.1 tables and the profile table are enabled for `hookpkg32`. The v3main report is regenerated
  **byte-identical**.

## Verification

- New simulation scenario L, with a Tricentis-like `site/price.html`: **8/8**.
  - L1: the controls row suggests `label:has(#selectplatinum)`.
  - L2: COVERED names it.
  - L3: clicking it plus `Get Checkbox State == checked` PASS live.
  - L4: exactly one nudge at the 8th Read.
  - L5: an edit resets the streak.
  - Plus cleanup, SessionEnd and orphan checks.
- Full simulation: **221/224**.
  - The 3 failures are all in D[codex|copilot|opencode]: the pre-tool "not blocking" typo warning was not delivered,
    while the post-tool verdict `STATIC KeywordNotFound` still was.
  - **The same check also fails on hookpkg31 under the same load** (load average 5–6.7 from the parallel v3.1 runs):
    v3.1 scored 18/20 in scenario D, v3.2 19/20. The pre-edit lint has a budget of about 1.6 s, so this is
    timing-sensitive under load and not a v3.2 regression.
- Real smoke: Qwen 3.8 Flash on live tricentis_quote (`results_live_v32smoke.jsonl`). See findings_v31.md.

## Harness issue found: shared OpenRouter budget baseline

`openrouter.Budget` compares **account-wide** key usage against `baseline + budget`. Parallel OpenRouter runs therefore
consume each other's budgets: Gemini's about $24.5 counts against v31or's $50. The baseline is read only at process
start.

- Workaround: Gemini v3.2 runs wait until v31or finishes.
- Proper fix (spec `harness-evaluation`): budget by the per-run sum of cell usage deltas or provider-reported per-request
  cost, with a global key-limit guard on top.
